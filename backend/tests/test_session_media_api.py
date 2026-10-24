"""Actual private recording bytes, authority rechecks and receipts in isolated PostgreSQL."""

import hashlib
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import httpx2
import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app import session_media_cleanup
from app.api import session_media
from app.api.exercise_library import evidence
from app.auth.errors import AuthError
from app.models.media import MediaAsset
from app.models.session_media import SessionMediaIntent
from app.models.training import ExercisePlanItem, TrainingSession
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database
VIDEO = b"\x1a\x45\xdf\xa3isolated-training-recording"


@pytest.fixture
def recording(api, graph, domain_db, media_store):
    store, bucket = media_store
    api.app.state.media = store
    api.app.state.auth_settings.media_bucket = bucket
    with domain_db.transaction() as session:
        item = ExercisePlanItem(session_id=graph["session_id"], position=1, name="Recorded squat")
        foreign = ExercisePlanItem(
            session_id=graph["second_session_id"], position=1, name="Other session"
        )
        session.add_all([item, foreign])
        session.flush()
        return store, item.id, foreign.id


def path(graph, item):
    return f"/api/sessions/{graph['session_id']}/exercises/{item}/video"


def reserve(api, graph, item, *, remove=False, key=None, **patch):
    viewed = api.get(path(graph, item) + "/review")
    assert viewed.status_code == 200, viewed.text
    body = {
        "sessionId": str(graph["session_id"]),
        "exerciseId": str(item),
        "expected": viewed.json()["expected"],
        "remove": remove,
        "upload": None
        if remove
        else {
            "name": "training.webm",
            "type": "video/webm",
            "size": len(VIDEO),
            "sha256": hashlib.sha256(VIDEO).hexdigest(),
        },
    }
    body.update(patch)
    key = key or uuid4()
    response = api.post(
        "/api/session-media/intents", json=body, headers={"Idempotency-Key": str(key)}
    )
    return key, body, response


def upload(api, key):
    lease = api.post(
        f"/api/session-media/intents/{key}/upload", json={}, headers={"Idempotency-Key": str(key)}
    )
    assert lease.status_code == 200, lease.text
    with httpx2.Client(trust_env=False) as client:
        response = client.put(lease.json()["url"], headers=lease.json()["headers"], content=VIDEO)
    assert response.status_code == 200, response.text


def commit(api, key):
    return api.post(
        f"/api/session-media/intents/{key}/commit", json={}, headers={"Idempotency-Key": str(key)}
    )


def publish(api, graph, item):
    key, _, reserved = reserve(api, graph, item)
    assert reserved.status_code == 200, reserved.text
    upload(api, key)
    saved = commit(api, key)
    assert saved.status_code == 200, saved.text
    return key, saved.json()


def test_real_upload_read_remove_and_private_original_receipt(api, graph, domain_db, recording):
    store, item, foreign = recording
    key, result = publish(api, graph, item)
    assert commit(api, key).json() == result
    assert api.get(f"/api/session-media/intents/{key}").json()["result"] == result
    media = result["media"]
    assert datetime.fromisoformat(media["expiresAt"]) - datetime.fromisoformat(
        media["attachedAt"]
    ) == timedelta(days=7)
    lease = api.get(path(graph, item)).json()
    with httpx2.Client(trust_env=False) as client:
        assert client.get(lease["url"]).content == VIDEO
        assert client.get(lease["url"].split("?", 1)[0]).status_code == 403
    assert (
        api.get(path(graph, item) + "/check", params={"version": lease["version"]}).status_code
        == 200
    )
    removed_key, _, response = reserve(api, graph, item, remove=True)
    assert response.status_code == 200, response.text
    removed = commit(api, removed_key)
    assert removed.status_code == 200 and removed.json()["media"] is None
    assert api.get(path(graph, item)).json() is None
    assert (
        api.get(path(graph, item) + "/check", params={"version": lease["version"]}).status_code
        == 409
    )
    with domain_db.transaction() as session:
        asset = session.get(MediaAsset, UUID(media["id"]))
        assert asset.session_id is None and store.verified_bytes(evidence(asset)) == VIDEO
        assert session.get(ExercisePlanItem, foreign).name == "Other session"
        assert session.get(TrainingSession, graph["second_session_id"]).version == 1


def test_missing_bytes_never_publish_and_conflicting_key_cannot_replace_original(
    api, graph, domain_db, recording
):
    _, item, _ = recording
    key, body, response = reserve(api, graph, item)
    assert response.status_code == 200
    assert commit(api, key).json()["error"]["code"] == "MEDIA_MISSING"
    changed = {**body, "caption": "Changed original"}
    assert (
        api.post(
            "/api/session-media/intents", json=changed, headers={"Idempotency-Key": str(key)}
        ).status_code
        == 409
    )
    assert api.get(path(graph, item)).json() is None
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, graph["session_id"]).version == 1
        assert session.scalar(select(SessionMediaIntent)).state == "pending"


def test_changed_plan_during_storage_verification_cannot_publish(
    api, graph, domain_db, recording, monkeypatch
):
    store, item, _ = recording
    key, _, response = reserve(api, graph, item)
    assert response.status_code == 200
    upload(api, key)
    real = store.verified_bytes

    def verify(checked):
        data = real(checked)
        with domain_db.transaction() as session:
            session.get(ExercisePlanItem, item).name = "New reviewed prescription"
        return data

    monkeypatch.setattr(store, "verified_bytes", verify)
    assert commit(api, key).status_code == 409
    assert api.get(path(graph, item)).json() is None
    with domain_db.transaction() as session:
        assert session.scalar(select(SessionMediaIntent)).state == "pending"
        assert session.scalar(select(MediaAsset)).status == "pending"


def test_interrupted_publication_rolls_back_asset_and_booking(
    api, graph, domain_db, recording, monkeypatch
):
    _, item, _ = recording
    key, _, response = reserve(api, graph, item)
    assert response.status_code == 200
    upload(api, key)

    def fail(**kwargs):
        raise AuthError("injected_failure", "Interrupted before receipt", 503)

    with monkeypatch.context() as patch:
        patch.setattr(session_media, "RecordingSaved", fail)
        assert commit(api, key).status_code == 503
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, graph["session_id"]).version == 1
        assert session.scalar(select(MediaAsset)).status == "pending"
        assert session.scalar(select(SessionMediaIntent)).state == "pending"
    assert commit(api, key).status_code == 200


def test_wrong_session_item_and_private_receipt_are_unavailable(api, graph, recording):
    _, item, foreign = recording
    assert api.get(path(graph, foreign)).status_code == 404
    assert api.get(path(graph, foreign) + "/review").status_code == 404
    assert api.get(f"/api/session-media/intents/{uuid4()}").status_code == 404
    key, body, response = reserve(api, graph, item)
    assert response.status_code == 200
    assert (
        api.post(
            "/api/session-media/intents",
            json={**body, "exerciseId": str(foreign)},
            headers={"Idempotency-Key": str(uuid4())},
        ).status_code
        == 404
    )


def test_original_expiry_is_immutable_and_read_denies_expired_bytes(
    api, graph, domain_db, recording, monkeypatch
):
    _, item, _ = recording
    _, result = publish(api, graph, item)
    identity = UUID(result["media"]["id"])
    with pytest.raises(DBAPIError, match="immutable"), domain_db.transaction() as session:
        session.get(MediaAsset, identity).expires_at += timedelta(days=1)
    with domain_db.transaction() as session:
        expiry = session.get(MediaAsset, identity).expires_at
    monkeypatch.setattr(session_media, "clock", lambda _session: expiry + timedelta(seconds=1))
    assert api.get(path(graph, item)).json() is None
    assert api.get(path(graph, item) + "/check", params={"version": 2}).status_code == 409


def test_abandoned_upload_is_durably_deleted_after_lease_expiry(
    api, graph, domain_db, recording, monkeypatch
):
    store, item, _ = recording
    key, _, response = reserve(api, graph, item)
    assert response.status_code == 200
    upload(api, key)
    with domain_db.transaction() as session:
        intent = session.scalar(select(SessionMediaIntent))
        deadline = intent.upload_until
        asset = session.get(MediaAsset, intent.upload_id)
        checked = evidence(asset)
    assert session_media_cleanup.run_once(domain_db, store, checked.bucket) is False
    monkeypatch.setattr(
        session_media_cleanup, "clock", lambda _session: deadline + timedelta(seconds=1)
    )
    assert session_media_cleanup.run_once(domain_db, store, checked.bucket) is True
    assert store.head(checked) is None
    with domain_db.transaction() as session:
        assert session.scalar(select(SessionMediaIntent)).state == "expired"
        assert session.scalar(select(MediaAsset)).status == "deleted"


def test_recording_evidence_refuses_populated_downgrade(api, graph, recording, migrate):
    _, item, _ = recording
    _, _, response = reserve(api, graph, item)
    assert response.status_code == 200
    with pytest.raises(DBAPIError, match="Recording downgrade refused"):
        migrate("downgrade", "20261024_0043")


@pytest.mark.parametrize("duplicate", [False, True])
def test_competing_commits_use_distinct_database_connections_and_publish_once(
    api, graph, domain_db, database_settings, recording, duplicate
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import text

    from app.api.request_cancellation import DECISION_LOCK
    from app.authorization import Principal
    from app.database import Database
    from app.models.communications import SessionEvent

    _, item, _ = recording
    first, _, response = reserve(api, graph, item)
    assert response.status_code == 200
    upload(api, first)
    second = first
    if not duplicate:
        second, _, response = reserve(api, graph, item)
        assert response.status_code == 200
        upload(api, second)
    actor = Principal(graph["owner_id"], "Owner Original", "owner", None)
    with domain_db.transaction() as session:
        checked = {
            key: evidence(
                session.get(MediaAsset, session_media.original(session, actor, key).upload_id)
            )
            for key in {first, second}
        }
    ready, pids = Barrier(2), []

    def apply(key):
        database = Database(database_settings)
        try:
            with database.transaction() as session:
                pids.append(session.scalar(text("SELECT pg_backend_pid()")))
                ready.wait(timeout=4)
                session.execute(
                    text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": DECISION_LOCK}
                )
                return 200, session_media.commit(session, actor, key, checked[key]).model_dump(
                    mode="json"
                )
        except AuthError as error:
            return error.status, None
        finally:
            database.close()

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(apply, [first, second]))
    assert len(set(pids)) == 2
    assert sorted(status for status, _ in results) == ([200, 200] if duplicate else [200, 409])
    if duplicate:
        assert results[0][1] == results[1][1]
    with domain_db.transaction() as session:
        assert (
            len(
                session.scalars(
                    select(SessionMediaIntent).where(SessionMediaIntent.state == "completed")
                ).all()
            )
            == 1
        )
        assert (
            len(
                session.scalars(
                    select(SessionEvent).where(SessionEvent.kind == "session_video_saved")
                ).all()
            )
            == 1
        )
        assert session.get(TrainingSession, graph["session_id"]).version == 2


def test_trainer_reads_and_saves_assigned_recording_but_foreign_scope_and_receipts_stay_private(
    api, graph, domain_db, recording, auth_settings, auth_service, fake_cognito
):
    from tests.test_directory_api import covered_session
    from tests.test_staff_api import trainer_login

    _, item, _ = recording
    owner_key, _ = publish(api, graph, item)
    client_id, covered, _ = covered_session(domain_db, graph)
    with domain_db.transaction() as session:
        foreign_session = session.scalar(
            select(TrainingSession).where(
                TrainingSession.client_id == client_id, TrainingSession.id != covered
            )
        )
        foreign_item = ExercisePlanItem(
            session_id=foreign_session.id, position=1, name="Foreign private exercise"
        )
        session.add(foreign_item)
        session.flush()
        foreign_graph, foreign_id = {**graph, "session_id": foreign_session.id}, foreign_item.id
    publish(api, foreign_graph, foreign_id)
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get(path(graph, item)).status_code == 200
    assert api.get(path(foreign_graph, foreign_id)).status_code == 404
    assert api.get(path(foreign_graph, foreign_id) + "/review").status_code == 404
    assert api.get(f"/api/session-media/intents/{owner_key}").status_code == 404
    _, _, reserved = reserve(api, graph, item, remove=True)
    assert reserved.status_code == 200


def test_authority_revocation_during_real_storage_read_prevents_publication(
    api, graph, domain_db, recording, monkeypatch
):
    from app.models.people import StaffUser

    store, item, _ = recording
    key, _, response = reserve(api, graph, item)
    assert response.status_code == 200
    upload(api, key)
    real = store.verified_bytes

    def revoke(checked):
        data = real(checked)
        with domain_db.transaction() as session:
            session.get(StaffUser, graph["owner_id"]).status = "inactive"
        return data

    monkeypatch.setattr(store, "verified_bytes", revoke)
    assert commit(api, key).status_code == 401
    with domain_db.transaction() as session:
        assert session.scalar(select(SessionMediaIntent)).state == "pending"
        assert session.scalar(select(MediaAsset)).status == "pending"
        assert session.get(TrainingSession, graph["session_id"]).version == 1


def test_completed_recording_remains_readable_but_cannot_be_replaced_or_removed(
    api, graph, domain_db, recording
):
    from app.persistence import acknowledge

    _, item, _ = recording
    publish(api, graph, item)
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        acknowledge(session, booking.id, booking.version, graph["owner_id"], method="late_no_show")
    assert api.get(path(graph, item)).status_code == 200
    for remove in [False, True]:
        _, _, response = reserve(api, graph, item, remove=remove)
        assert response.status_code == 409


def test_replaced_recording_is_retained_only_until_original_undo_hold(
    api, graph, domain_db, recording, monkeypatch
):
    store, item, _ = recording
    _, first = publish(api, graph, item)
    _, second = publish(api, graph, item)
    assert second["media"]["id"] != first["media"]["id"]
    with domain_db.transaction() as session:
        original = evidence(session.get(MediaAsset, UUID(first["media"]["id"])))
    assert session_media_cleanup.run_once(domain_db, store, original.bucket) is False
    assert store.verified_bytes(original) == VIDEO
    later = datetime.fromisoformat(second["savedAt"]) + timedelta(hours=24, seconds=1)
    monkeypatch.setattr(session_media_cleanup, "clock", lambda _session: later)
    assert session_media_cleanup.run_once(domain_db, store, original.bucket) is True
    assert store.head(original) is None
    assert api.get(path(graph, item)).status_code == 200
