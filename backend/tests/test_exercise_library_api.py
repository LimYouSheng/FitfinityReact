"""Library HTTP transactions use real PostgreSQL and actual isolated object storage."""

import hashlib
from uuid import UUID, uuid4

import httpx2
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.api import exercise_library
from app.api.library_schemas import SaveLibrary
from app.authorization import Principal
from app.models.communications import Message
from app.models.media import LibrarySaveIntent, MediaAsset, MediaDeletion
from app.models.training import Exercise
from tests.test_media_storage import PNG
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


def test_completed_receipt_is_immutable(domain_db, graph):
    key = uuid4()
    actor = Principal(graph["owner_id"], "Owner", "owner", None)
    with domain_db.transaction() as session:
        exercise_library.reserve(
            session,
            actor,
            key,
            SaveLibrary(name="Immutable movement", category="Core", status="active"),
            "",
        )
    with domain_db.transaction() as session:
        saved = exercise_library.commit(session, actor, key, None)
        assert saved.name == "Immutable movement"
    with pytest.raises(DBAPIError, match="immutable"), domain_db.transaction() as session:
        original = exercise_library.original(session, actor, key)
        original.result = {"forged": True}


def test_pending_upload_intent_survives_refused_downgrade_and_command_rewrite(
    api, domain_db, migrate
):
    from sqlalchemy import text

    key, response = reserve(api)
    assert response.status_code == 200
    with pytest.raises(DBAPIError, match="immutable"), domain_db.transaction() as session:
        row = session.scalar(select(LibrarySaveIntent).where(LibrarySaveIntent.request_key == key))
        row.name = "Rewritten original command"
    with pytest.raises(DBAPIError, match="downgrade refused"):
        migrate("downgrade", "20261024_0040")
    with domain_db.transaction() as session:
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "20261024_0042"
        row = session.scalar(select(LibrarySaveIntent).where(LibrarySaveIntent.request_key == key))
        assert row.name == "New movement" and row.state == "pending"


def reserve(api, key=None, **patch):
    key = key or uuid4()
    body = dict(
        name="New movement", category="Core", description="Controlled movement", status="active"
    )
    body.update(patch)
    response = api.post(
        "/api/exercise-library/save-intents", json=body, headers={"Idempotency-Key": str(key)}
    )
    return key, response


def commit(api, key):
    return api.post(
        f"/api/exercise-library/save-intents/{key}/commit",
        json={},
        headers={"Idempotency-Key": str(key)},
    )


def attach_store(api, media_store):
    store, bucket = media_store
    api.app.state.media = store
    api.app.state.auth_settings.media_bucket = bucket
    return store


def upload(api, key):
    response = api.post(
        f"/api/exercise-library/save-intents/{key}/upload",
        json={},
        headers={"Idempotency-Key": str(key)},
    )
    assert response.status_code == 200, response.text
    lease = response.json()
    with httpx2.Client(trust_env=False) as client:
        result = client.put(lease["url"], headers=lease["headers"], content=PNG)
    assert result.status_code == 200, result.text


def media_input():
    return dict(
        name="movement.png", type="image/png", size=len(PNG), sha256=hashlib.sha256(PNG).hexdigest()
    )


def test_new_save_is_invisible_until_commit_and_recovers_original(api, domain_db):
    before = api.get("/api/exercise-library").json()["items"]
    key, response = reserve(api)
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "pending"
    assert api.get("/api/exercise-library").json()["items"] == before
    result = commit(api, key)
    assert result.status_code == 200, result.text
    assert commit(api, key).json() == result.json()
    assert api.get(f"/api/exercise-library/save-intents/{key}").json()["result"] == result.json()
    assert result.json() in api.get("/api/exercise-library").json()["items"]
    assert reserve(api, key=key, name="Different movement")[1].status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(LibrarySaveIntent)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.kind == "exercise_library_update")
            )
            == 1
        )


def test_duplicate_names_and_stale_commit_do_not_publish(api):
    key, response = reserve(api)
    assert response.status_code == 200
    saved = commit(api, key).json()
    assert reserve(api, name=" NEW   Movement ")[1].status_code == 409
    changes = dict(id=saved["id"], expectedVersion=saved["version"], name="Updated movement")
    first, response = reserve(api, **changes)
    assert response.status_code == 200
    second, response = reserve(api, **{**changes, "name": "Stale movement"})
    assert response.status_code == 200
    assert commit(api, first).status_code == 200
    assert commit(api, second).status_code == 409
    assert commit(api, key).json() == saved


def test_media_cannot_publish_before_bytes_and_reads_exact_original(api, media_store, domain_db):
    attach_store(api, media_store)
    key, response = reserve(api, upload=media_input())
    assert response.status_code == 200, response.text
    assert commit(api, key).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(Exercise).where(Exercise.name == "New movement")) is None
    upload(api, key)
    saved = commit(api, key)
    assert saved.status_code == 200, saved.text
    identity = saved.json()["media"]["id"]
    lease = api.get(f"/api/exercise-library/media/{identity}")
    assert lease.status_code == 200, lease.text
    with httpx2.Client(trust_env=False) as client:
        result = client.get(lease.json()["url"])
    assert result.content == PNG
    assert api.get(
        f"/api/exercise-library/media/{identity}/check", params={"version": saved.json()["version"]}
    ).json() == {"valid": True}
    assert api.get(f"/api/exercise-library/media/{uuid4()}").status_code == 404


def test_removal_denies_new_reads_and_waits_for_old_upload_lease(api, media_store, domain_db):
    attach_store(api, media_store)
    key, response = reserve(api, upload=media_input())
    assert response.status_code == 200
    upload(api, key)
    saved = commit(api, key).json()
    identity = saved["media"]["id"]
    removal, response = reserve(
        api, id=saved["id"], expectedVersion=saved["version"], removeMedia=True
    )
    assert response.status_code == 200
    changed = commit(api, removal)
    assert changed.status_code == 200, changed.text
    assert changed.json()["media"] is None
    assert api.get(f"/api/exercise-library/media/{identity}").status_code == 404
    assert (
        api.get(
            f"/api/exercise-library/media/{identity}/check", params={"version": saved["version"]}
        ).status_code
        == 404
    )
    with domain_db.transaction() as session:
        intent = session.scalar(
            select(LibrarySaveIntent).where(LibrarySaveIntent.request_key == key)
        )
        deletion = session.scalar(
            select(MediaDeletion).where(MediaDeletion.media_id == UUID(identity))
        )
        assert deletion.next_attempt_at >= intent.upload_until
        assert session.get(MediaAsset, UUID(identity)).status == "delete_pending"


def test_authority_is_rechecked_after_external_storage(
    api, media_store, domain_db, graph, monkeypatch
):
    from app.models.people import StaffUser

    store = attach_store(api, media_store)
    key, response = reserve(api, upload=media_input())
    assert response.status_code == 200
    upload(api, key)
    original = store.verified_bytes

    def deactivate(item):
        result = original(item)
        with domain_db.transaction() as session:
            session.get(StaffUser, graph["owner_id"]).status = "inactive"
        return result

    monkeypatch.setattr(store, "verified_bytes", deactivate)
    assert commit(api, key).status_code == 401
    with domain_db.transaction() as session:
        assert session.scalar(select(Exercise).where(Exercise.name == "New movement")) is None
        assert session.scalar(select(LibrarySaveIntent)).state == "pending"
        assert session.scalar(select(MediaAsset)).status == "pending"


def test_read_lease_is_not_returned_after_authority_changes_during_storage_lookup(
    api, media_store, domain_db, graph, monkeypatch
):
    from app.models.people import StaffUser

    store = attach_store(api, media_store)
    key, response = reserve(api, upload=media_input())
    assert response.status_code == 200
    upload(api, key)
    saved = commit(api, key).json()
    original = store.download

    def deactivate(item, lifetime):
        url = original(item, lifetime)
        with domain_db.transaction() as session:
            session.get(StaffUser, graph["owner_id"]).status = "inactive"
        return url

    monkeypatch.setattr(store, "download", deactivate)
    response = api.get(f"/api/exercise-library/media/{saved['media']['id']}")
    assert response.status_code == 401
    assert "url" not in response.json()


def test_late_failure_rolls_back_metadata_and_notice_but_keeps_original_upload(
    api, media_store, domain_db, monkeypatch
):
    store = attach_store(api, media_store)
    key, response = reserve(api, upload=media_input())
    assert response.status_code == 200
    upload(api, key)
    constructor = exercise_library.MessageReceipt

    def fail(**_values):
        raise RuntimeError("Injected after notice insertion")

    monkeypatch.setattr(exercise_library, "MessageReceipt", fail)
    assert commit(api, key).status_code == 500
    with domain_db.transaction() as session:
        assert session.scalar(select(Exercise).where(Exercise.name == "New movement")) is None
        assert (
            session.scalar(select(Message).where(Message.kind == "exercise_library_update")) is None
        )
        assert session.scalar(select(LibrarySaveIntent)).state == "pending"
        asset = session.scalar(select(MediaAsset))
        assert asset.status == "pending"
        item = exercise_library.evidence(asset)
    assert store.verified_bytes(item) == PNG
    monkeypatch.setattr(exercise_library, "MessageReceipt", constructor)
    assert commit(api, key).status_code == 200


@pytest.mark.parametrize("duplicate", [True, False])
def test_competing_connections_publish_one_reviewed_edit(
    api, domain_db, database_settings, graph, duplicate
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import text

    from app.auth.errors import AuthError
    from app.database import Database

    key, response = reserve(api)
    assert response.status_code == 200
    saved = commit(api, key).json()
    first, response = reserve(
        api, id=saved["id"], expectedVersion=saved["version"], name="First edit"
    )
    assert response.status_code == 200
    second = first
    if not duplicate:
        second, response = reserve(
            api, id=saved["id"], expectedVersion=saved["version"], name="Second edit"
        )
        assert response.status_code == 200
    actor = Principal(graph["owner_id"], "Owner", "owner", None)
    barrier = Barrier(2)

    def execute(key):
        db = Database(database_settings)
        try:
            barrier.wait()
            with db.transaction() as session:
                session.execute(
                    text("SELECT pg_advisory_xact_lock(:lock)"),
                    {"lock": exercise_library.LIBRARY_LOCK},
                )
                return exercise_library.commit(session, actor, key, None).version
        except AuthError as error:
            return error.status
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(execute, [first, second]))
    assert sorted(results) == ([2, 2] if duplicate else [2, 409])
    with domain_db.transaction() as session:
        assert session.get(Exercise, UUID(saved["id"])).version == 2
        assert (
            session.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.kind == "exercise_library_update")
            )
            == 2
        )


@pytest.mark.parametrize("action", ["upload", "commit"])
def test_original_actions_require_matching_header_key(api, action):
    key, response = reserve(api)
    assert response.status_code == 200
    path = f"/api/exercise-library/save-intents/{key}/{action}"
    assert api.post(path, json={}).status_code == 422
    assert api.post(path, json={}, headers={"Idempotency-Key": str(uuid4())}).status_code == 409
    assert api.get(f"/api/exercise-library/save-intents/{key}").json()["state"] == "pending"
    assert commit(api, key).status_code == 200
