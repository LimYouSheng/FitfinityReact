"""Package deletion/Undo checks actual private bytes and durable cleanup deadlines."""

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app import session_media_cleanup
from app.api.exercise_library import evidence
from app.models.media import MediaAsset, MediaDeletion
from app.models.training import ExercisePlanItem, TrainingSession
from tests.test_package_actions import future as future
from tests.test_package_actions import review, save
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database
VIDEO = b"\x1a\x45\xdf\xa3isolated-video-evidence"


@pytest.fixture
def recording(api, domain_db, graph, future, media_store, request):
    store, bucket = media_store
    api.app.state.media = store
    identity, bookings = future
    with domain_db.transaction() as session:
        plan = session.scalar(
            select(ExercisePlanItem).where(ExercisePlanItem.session_id == bookings[0])
        )
        asset = MediaAsset(
            purpose="session_video",
            status="ready",
            bucket=bucket,
            object_key=str(uuid4()),
            original_filename="training.webm",
            content_type="video/webm",
            size_bytes=len(VIDEO),
            content_sha256=hashlib.sha256(VIDEO).hexdigest(),
            uploaded_by=graph["owner_id"],
            client_id=graph["client_id"],
            purchase_id=identity,
            session_id=bookings[0],
            original_session_id=bookings[0],
            original_plan_item_id=plan.id,
            expires_at=datetime.now(UTC) + getattr(request, "param", timedelta(days=7)),
        )
        session.add(asset)
        session.flush()
        item, media_id, expiry = evidence(asset), asset.id, asset.expires_at
    store.client.put_object(Bucket=bucket, Key=item.key, Body=VIDEO, ContentType=item.content_type)
    assert save(api, graph, review(api, graph, identity)).status_code == 200
    deleted = save(api, graph, review(api, graph, identity, "delete_sessions"))
    assert deleted.status_code == 200, deleted.text
    return store, item, media_id, expiry, deleted.json()


def test_undo_checks_real_bytes_and_retains_original_expiry(api, domain_db, recording):
    store, item, media_id, expiry, deleted = recording
    assert session_media_cleanup.run_once(domain_db, store, item.bucket) is False
    assert store.verified_bytes(item) == VIDEO
    path = f"/api/package-actions/{deleted['id']}"
    viewed = api.get(path + "/undo-review")
    assert viewed.status_code == 200, viewed.text
    saved = api.post(
        path + "/undo",
        json={"expected": viewed.json()["expected"]},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert saved.status_code == 200, saved.text
    with domain_db.transaction() as session:
        asset = session.get(MediaAsset, media_id)
        assert asset.session_id == asset.original_session_id
        assert asset.expires_at == expiry
        work = session.scalar(select(MediaDeletion).where(MediaDeletion.media_id == media_id))
        assert work.next_attempt_at == expiry
        assert work.reason == "session_deleted"
    assert session_media_cleanup.run_once(domain_db, store, item.bucket) is False


def test_missing_original_bytes_block_undo_without_restoring_any_booking(api, domain_db, recording):
    store, item, _, _, deleted = recording
    store.delete(item)
    path = f"/api/package-actions/{deleted['id']}"
    viewed = api.get(path + "/undo-review").json()
    saved = api.post(
        path + "/undo",
        json={"expected": viewed["expected"]},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert saved.status_code == 409, saved.text
    assert saved.json()["error"]["code"] == "MEDIA_MISSING"
    with domain_db.transaction() as session:
        assert all(
            session.get(TrainingSession, UUID(value)) is None
            for value in deleted["deletedSessionIds"]
        )


def test_worker_deletes_only_after_hold_and_retains_retry_after_lost_response(
    api, domain_db, recording, monkeypatch
):
    from app.auth.errors import AuthError

    store, item, media_id, _, deleted = recording
    due = datetime.fromisoformat(deleted["undoUntil"].replace("Z", "+00:00"))
    monkeypatch.setattr(session_media_cleanup, "clock", lambda _: due - timedelta(seconds=1))
    assert session_media_cleanup.run_once(domain_db, store, item.bucket) is False
    assert store.head(item)
    monkeypatch.setattr(session_media_cleanup, "clock", lambda _: due + timedelta(seconds=1))
    actual = store.delete

    def lost(original):
        actual(original)
        raise AuthError("MEDIA_UNAVAILABLE", "Synthetic lost deletion response", 503)

    monkeypatch.setattr(store, "delete", lost)
    with pytest.raises(AuthError):
        session_media_cleanup.run_once(domain_db, store, item.bucket)
    assert store.head(item) is None
    with domain_db.transaction() as session:
        work = session.scalar(select(MediaDeletion).where(MediaDeletion.media_id == media_id))
        assert work.status == "pending" and work.attempts == 1
    monkeypatch.setattr(store, "delete", actual)
    monkeypatch.setattr(session_media_cleanup, "clock", lambda _: due + timedelta(minutes=2))
    assert session_media_cleanup.run_once(domain_db, store, item.bucket) is True
    with domain_db.transaction() as session:
        assert session.get(MediaAsset, media_id).status == "deleted"


@pytest.mark.parametrize("recording", [timedelta(minutes=1)], indirect=True)
def test_original_media_expiry_blocks_undo_before_its_24_hour_deadline(
    api, domain_db, recording, monkeypatch
):
    from app.api import package_action_review

    store, item, _, expiry, deleted = recording
    monkeypatch.setattr(package_action_review, "clock", lambda: expiry + timedelta(seconds=1))
    assert api.get(f"/api/package-actions/{deleted['id']}/undo-review").status_code == 409
    assert store.head(item)
    monkeypatch.setattr(session_media_cleanup, "clock", lambda _: expiry + timedelta(seconds=1))
    assert session_media_cleanup.run_once(domain_db, store, item.bucket) is True
    assert store.head(item) is None
    assert api.get(f"/api/package-actions/{deleted['id']}/undo-review").status_code == 409
