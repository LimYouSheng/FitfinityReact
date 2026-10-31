"""Bounded durable library cleanup. Scheduling and production activation are separate."""

from datetime import timedelta

from sqlalchemy import exists, func, select, text

from app.api.exercise_library import LIBRARY_LOCK, evidence
from app.api.library_approval import held_for_review
from app.models.media import LibrarySaveIntent, MediaAsset, MediaDeletion
from app.models.training import Exercise


def clock(session):
    return session.scalar(select(func.clock_timestamp()))


def expire_uploads(database, bucket):
    """Atomically retire abandoned drafts only after every possible upload lease has expired."""
    with database.transaction() as session:
        session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": LIBRARY_LOCK})
        now = clock(session)
        intents = session.scalars(
            select(LibrarySaveIntent)
            .join(MediaAsset, MediaAsset.id == LibrarySaveIntent.upload_id)
            .where(
                LibrarySaveIntent.state == "pending",
                ~held_for_review(),
                LibrarySaveIntent.upload_until <= now,
                MediaAsset.bucket == bucket,
                MediaAsset.status == "pending",
            )
            .order_by(LibrarySaveIntent.id)
            .limit(100)
            .with_for_update()
        ).all()
        for intent in intents:
            asset = session.get(MediaAsset, intent.upload_id)
            intent.state, asset.status = "expired", "delete_pending"
            session.add(MediaDeletion(media_id=asset.id, reason="expired", next_attempt_at=now))
        return len(intents)


def claim(database, bucket):
    """Lease one unreferenced object; no network IO while holding database locks."""
    with database.transaction() as session:
        session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": LIBRARY_LOCK})
        now = clock(session)
        row = session.scalar(
            select(MediaDeletion)
            .join(MediaAsset)
            .where(
                MediaAsset.bucket == bucket,
                MediaAsset.purpose == "exercise_media",
                MediaAsset.status == "delete_pending",
                MediaDeletion.status != "done",
                MediaDeletion.next_attempt_at <= now,
                (MediaDeletion.lease_until.is_(None)) | (MediaDeletion.lease_until <= now),
                ~exists().where(Exercise.media_id == MediaAsset.id),
                ~exists().where(
                    LibrarySaveIntent.upload_id == MediaAsset.id,
                    LibrarySaveIntent.upload_until > now,
                ),
            )
            .order_by(MediaDeletion.next_attempt_at, MediaDeletion.id)
            .limit(1)
            .with_for_update()
        )
        if row is None:
            return None
        row.status, row.lease_until = "processing", now + timedelta(minutes=2)
        row.attempts += 1
        session.flush()
        return row.id, row.version, evidence(session.get(MediaAsset, row.media_id))


def finish(database, identity, version, succeeded):
    """An old worker cannot overwrite a newer lease; ambiguous deletion remains retryable."""
    with database.transaction() as session:
        session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": LIBRARY_LOCK})
        row = session.get(MediaDeletion, identity, with_for_update=True)
        if row is None or row.status != "processing" or row.version != version:
            return False
        now = clock(session)
        row.lease_until = None
        if succeeded:
            row.status, row.completed_at, row.error_code = "done", now, None
            session.get(MediaAsset, row.media_id, with_for_update=True).status = "deleted"
        else:
            row.status, row.error_code = "pending", "storage_unavailable"
            row.next_attempt_at = now + timedelta(minutes=1)
        return True


def run_once(database, store, bucket):
    """One bounded explicit sweep; retained leases recover process death without lost work."""
    expire_uploads(database, bucket)
    claimed = claim(database, bucket)
    if claimed is None:
        return False
    identity, version, item = claimed
    try:
        store.delete(item)
    except Exception:
        finish(database, identity, version, False)
        raise
    return finish(database, identity, version, True)


def main():
    """Explicit bounded worker command; this module never starts a scheduler or creates a bucket."""
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
