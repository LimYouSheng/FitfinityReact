"""Explicit session-media cleanup; expiry and deletion holds survive process interruption."""

from datetime import timedelta

from sqlalchemy import select, text

from app.api.exercise_library import evidence
from app.api.request_cancellation import DECISION_LOCK
from app.library_cleanup import clock
from app.models.media import MediaAsset, MediaDeletion


def claim(database, bucket):
    """Serialize with package Undo, then release DB locks before immutable-object deletion."""
    with database.transaction() as session:
        session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": DECISION_LOCK})
        now = clock(session)
        expired = session.scalars(
            select(MediaAsset)
            .where(
                MediaAsset.bucket == bucket,
                MediaAsset.purpose == "session_video",
                MediaAsset.status == "ready",
                MediaAsset.expires_at <= now,
            )
            .order_by(MediaAsset.id)
            .limit(100)
            .with_for_update()
        ).all()
        for asset in expired:
            asset.status = "delete_pending"
            work = session.scalar(select(MediaDeletion).where(MediaDeletion.media_id == asset.id))
            if work is None:
                session.add(MediaDeletion(media_id=asset.id, reason="expired", next_attempt_at=now))
        session.flush()
        work = session.scalar(
            select(MediaDeletion)
            .join(MediaAsset)
            .where(
                MediaAsset.bucket == bucket,
                MediaAsset.purpose == "session_video",
                MediaAsset.status.in_(["ready", "delete_pending"]),
                MediaDeletion.status != "done",
                MediaDeletion.next_attempt_at <= now,
                (MediaDeletion.lease_until.is_(None)) | (MediaDeletion.lease_until <= now),
                (MediaAsset.session_id.is_(None)) | (MediaAsset.expires_at <= now),
            )
            .order_by(MediaDeletion.next_attempt_at, MediaDeletion.id)
            .limit(1)
            .with_for_update()
        )
        if work is None:
            return None
        asset = session.get(MediaAsset, work.media_id)
        asset.status = "delete_pending"
        work.status, work.lease_until = "processing", now + timedelta(minutes=2)
        work.attempts += 1
        session.flush()
        return work.id, work.version, evidence(asset)


def finish(database, identity, version, succeeded):
    """Only the current lease can finalize; failed IO retains durable retry evidence."""
    with database.transaction() as session:
        session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": DECISION_LOCK})
        work = session.get(MediaDeletion, identity, with_for_update=True)
        if work is None or work.status != "processing" or work.version != version:
            return False
        now = clock(session)
        work.lease_until = None
        if succeeded:
            work.status, work.completed_at, work.error_code = "done", now, None
            session.get(MediaAsset, work.media_id, with_for_update=True).status = "deleted"
        else:
            work.status, work.error_code = "pending", "storage_unavailable"
            work.next_attempt_at = now + timedelta(minutes=1)
        return True


def run_once(database, store, bucket):
    claimed = claim(database, bucket)
    if claimed is None:
        return False
    identity, version, original = claimed
    try:
        store.delete(original)
    except Exception:
        finish(database, identity, version, False)
        raise
    return finish(database, identity, version, True)


def main():
    """Bounded manual worker only; this command neither provisions storage nor schedules itself."""
    from app.config import load_settings
    from app.database import Database
    from app.media_storage import configured_storage

    settings = load_settings()
    if not settings.media_enabled:
        raise RuntimeError("Protected media must be explicitly configured before cleanup")
    database, store = Database(settings), configured_storage(settings)
    try:
        for _ in range(100):
            if not run_once(database, store, settings.media_bucket):
                break
    finally:
        store.close()
        database.close()


if __name__ == "__main__":
    main()
