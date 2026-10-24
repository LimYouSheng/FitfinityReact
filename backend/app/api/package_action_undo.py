"""Restore only an unchanged, unexpired deletion; preserve increasing booking versions."""

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select

from app.api import package_action_review as reviews
from app.api.exercise_library import evidence
from app.api.package_action_save import ARCHIVED_FIELDS
from app.api.package_action_schemas import PackageUndoReview, PackageUndoState
from app.api.session_booking_review import position
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.communications import ChangeRequest, Message, MessageReceipt, SessionEvent
from app.models.media import MediaAsset, MediaDeletion
from app.models.package_actions import (
    PackageActionReceipt,
    PackageActionRequest,
    PackageArchivedMedia,
    PackageDeletionUndo,
    SessionArchive,
)
from app.models.training import TrainingSession
from app.session_numbering import renumber_purchase


def inspect(session, principal, identity):
    """A review covers every restored row and media lease before external verification."""
    principal.operations()
    action = session.get(PackageActionReceipt, identity)
    if action is None or action.operation != "delete_sessions" or action.undo_expires_at is None:
        raise unavailable()
    client, purchase, live = reviews.target(session, action.client_id, action.purchase_id)
    now = reviews.clock()
    if (
        action.undo_expires_at <= now
        or purchase.status != "inactive"
        or purchase.version != action.result["purchaseVersion"]
        or client.version != action.client_version
        or session.scalar(
            select(PackageDeletionUndo.id).where(PackageDeletionUndo.action_id == identity)
        )
    ):
        raise conflict()
    archives = session.scalars(
        select(SessionArchive)
        .where(SessionArchive.action_id == identity)
        .order_by(SessionArchive.session_id)
    ).all()
    local = now.astimezone(ZoneInfo("Asia/Singapore")).replace(tzinfo=None)
    if not archives or len(live) + len(archives) > purchase.total_sessions:
        raise conflict()
    for row in archives:
        if (
            session.get(TrainingSession, row.session_id) is not None
            or reviews.contents(session, row.session_id) != row.contents_sha256
            or (
                row.schedule_state == "booked"
                and datetime.combine(row.training_date, row.starts_at) <= local
            )
        ):
            raise conflict()
    links = session.scalars(
        select(PackageArchivedMedia).where(
            PackageArchivedMedia.archive_id.in_([row.id for row in archives])
        )
    ).all()
    originals = {row.media_id: row.original_version for row in links}
    media = session.scalars(
        select(MediaAsset)
        .where(MediaAsset.id.in_(originals))
        .order_by(MediaAsset.id)
        .with_for_update()
    ).all()
    if len(media) != len(originals) or any(
        row.status != "ready"
        or row.session_id is not None
        or row.expires_at <= now
        or row.version != originals[row.id] + 1
        for row in media
    ):
        raise conflict()
    requests = session.execute(
        select(ChangeRequest, PackageActionRequest.resolved_version)
        .join(PackageActionRequest, PackageActionRequest.request_id == ChangeRequest.id)
        .where(PackageActionRequest.action_id == identity)
    ).all()
    if any(row.status != "rejected" or row.version != version for row, version in requests):
        raise conflict()
    if session.scalar(
        select(ChangeRequest.id)
        .where(
            ChangeRequest.client_id == client.id,
            ChangeRequest.kind == "fixed_weekly_schedule",
            ChangeRequest.status == "pending",
        )
        .limit(1)
    ):
        raise conflict()
    for asset in media:
        work = session.scalar(
            select(MediaDeletion).where(MediaDeletion.media_id == asset.id).with_for_update()
        )
        if work and (work.status != "pending" or work.lease_until is not None):
            raise conflict()
    expected = reviews.digest(
        {
            "action": identity,
            "client": client.version,
            "purchase": purchase.version,
            "archives": [row.id for row in archives],
            "live": [[row.id, row.version] for row in live],
            "media": [[row.id, row.version, row.expires_at] for row in media],
        }
    )
    positions = [
        position(
            SimpleNamespace(
                id=row.session_id,
                version=row.original_version,
                **{field: getattr(row, field) for field in ARCHIVED_FIELDS},
            )
        )
        for row in archives
    ]
    view = PackageUndoReview(
        id=identity,
        messageId=action.message_id,
        clientId=client.id,
        purchaseId=purchase.id,
        expected=expected,
        expiresAt=action.undo_expires_at,
        sessions=positions,
    )
    return view, action, purchase, archives, media


def reconcile(session, principal, key):
    principal.operations()
    saved = session.scalar(
        select(PackageDeletionUndo).where(
            PackageDeletionUndo.actor_id == principal.user_id,
            PackageDeletionUndo.request_key == key,
        )
    )
    if saved is None:
        raise unavailable()
    return PackageUndoState.model_validate(saved.result)


def commit(session, principal, identity, key, body, checked):
    """Append compensation evidence and restore exact originals in one database transaction."""
    principal.operations()
    digest = reviews.digest({"id": identity, **body.model_dump()})
    saved = session.scalar(
        select(PackageDeletionUndo).where(
            PackageDeletionUndo.actor_id == principal.user_id,
            PackageDeletionUndo.request_key == key,
        )
    )
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Review the original Undo.", 409)
        return PackageUndoState.model_validate(saved.result)
    view, action, purchase, archives, media = inspect(session, principal, identity)
    if view.expected != body.expected or [evidence(row) for row in media] != checked:
        raise conflict()
    now = reviews.clock()
    notice = Message(
        kind="package_updated",
        title="Package session deletion undone",
        body="Upcoming sessions restored. Package remains inactive.",
        client_id=action.client_id,
        purchase_id=purchase.id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    recipients = set(
        session.scalars(
            select(MessageReceipt.user_id).where(MessageReceipt.message_id == action.message_id)
        )
    ) | {principal.user_id}
    for user in recipients:
        session.add(MessageReceipt(message_id=notice.id, user_id=user))
    result = PackageUndoState(id=uuid4(), undoneAt=now)
    session.add(
        PackageDeletionUndo(
            id=result.id,
            action_id=identity,
            request_key=key,
            request_sha256=digest,
            message_id=notice.id,
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    session.flush()
    for archive in archives:
        session.execute(
            insert(TrainingSession.__table__).values(
                id=archive.session_id,
                version=archive.original_version + 1,
                created_at=archive.original_created_at,
                **{field: getattr(archive, field) for field in ARCHIVED_FIELDS},
            )
        )
        session.add(
            SessionEvent(
                session_id=archive.session_id,
                session_version=archive.original_version + 1,
                kind="package_deletion_undone",
                note="Original future booking restored from retained archive.",
                actor_id=principal.user_id,
                actor_name=principal.name,
            )
        )
    for asset in media:
        asset.session_id = asset.original_session_id
        asset.version += 1
        work = session.scalar(select(MediaDeletion).where(MediaDeletion.media_id == asset.id))
        if work:
            work.next_attempt_at = asset.expires_at
            work.version += 1
    purchase.version += 1
    session.flush()
    renumber_purchase(session, purchase.id)
    return result
