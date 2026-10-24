"""Package status/deletion, retained archives, request decisions and receipts commit together."""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, text

from app.api import package_action_review as reviews
from app.api.package_action_schemas import PackageActionState
from app.api.request_cancellation import DECISION_LOCK
from app.api.request_resolution import notify as notify_decision
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.communications import Message, MessageReceipt, RequestEvent, SessionEvent
from app.models.media import MediaAsset, MediaDeletion
from app.models.package_actions import (
    PackageActionReceipt,
    PackageActionRequest,
    PackageArchivedMedia,
    SessionArchive,
)
from app.models.people import LifecycleEvent, StaffUser, Trainer
from app.session_numbering import renumber_purchase

ARCHIVED_FIELDS = (
    "client_id",
    "purchase_id",
    "trainer_id",
    "schedule_slot_id",
    "schedule_state",
    "session_number",
    "training_date",
    "starts_at",
    "ends_at",
    "status",
    "trainer_comments",
    "client_summary",
    "copied_from_session_id",
    "whatsapp_opened_at",
    "whatsapp_open_count",
)


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": DECISION_LOCK})
    return session.scalar(
        select(PackageActionReceipt).where(
            PackageActionReceipt.actor_id == principal.user_id,
            PackageActionReceipt.request_key == key,
        )
    )


def reconcile(session, principal, key):
    principal.operations()
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return PackageActionState.model_validate(saved.result)


def notify(session, principal, client, purchase, rows, operation, count, undo_until):
    """Only active recipients receive the durable internal notice; no provider delivery."""
    trainers = {client.trainer_id, purchase.trainer_id, *(row.trainer_id for row in rows)}
    users = set(session.scalars(select(Trainer.user_id).where(Trainer.id.in_(trainers))))
    users.add(principal.user_id)
    users.discard(None)
    recipients = set(
        session.scalars(
            select(StaffUser.id).where(
                StaffUser.status == "active", (StaffUser.role == "owner") | StaffUser.id.in_(users)
            )
        )
    )
    title = "Package deactivated" if operation == "deactivate" else "Package sessions deleted"
    notice = Message(
        kind="package_updated",
        title=f"{title}: {client.name}",
        body=f"{purchase.name}: {count} upcoming sessions deleted. "
        "Credits and purchased terms remain unchanged."
        + (" Undo is available in Messages for 24 hours." if undo_until else ""),
        client_id=client.id,
        purchase_id=purchase.id,
        trainer_id=purchase.trainer_id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    for identity in recipients:
        session.add(MessageReceipt(message_id=notice.id, user_id=identity))
    return notice.id


def reject_requests(session, principal, requests, removed, now, action_id):
    for request in requests:
        if request.session_id not in removed:
            continue
        request.status, request.resolved_by, request.resolved_at = (
            "rejected",
            principal.user_id,
            now,
        )
        request.version += 1
        request.resolution_note = "Session deleted from inactive package."
        session.add(
            RequestEvent(
                request_id=request.id,
                sequence=2,
                status="rejected",
                note=request.resolution_note,
                actor_id=principal.user_id,
                actor_name=principal.name,
            )
        )
        notify_decision(session, principal, request)
        session.flush()
        session.add(
            PackageActionRequest(
                action_id=action_id, request_id=request.id, resolved_version=request.version
            )
        )
    session.flush()


def detach_media(session, identities, now, undo_until, action_id):
    """Retain original ownership/expiry; delay physical cleanup through a permitted Undo window."""
    assets = session.scalars(
        select(MediaAsset)
        .where(MediaAsset.session_id.in_(identities))
        .order_by(MediaAsset.id)
        .with_for_update()
    ).all()
    for asset in assets:
        if asset.status == "ready":
            archive = session.scalar(
                select(SessionArchive).where(
                    SessionArchive.action_id == action_id,
                    SessionArchive.session_id == asset.session_id,
                )
            )
            session.add(
                PackageArchivedMedia(
                    archive_id=archive.id, media_id=asset.id, original_version=asset.version
                )
            )
            session.flush()
        asset.session_id = None
        if asset.status == "deleted":
            asset.version += 1
            continue
        if not undo_until:
            asset.status = "delete_pending"
        asset.version += 1
        work = session.scalar(
            select(MediaDeletion).where(MediaDeletion.media_id == asset.id).with_for_update()
        )
        due = min(undo_until, asset.expires_at) if undo_until else now
        if work is None:
            session.add(
                MediaDeletion(media_id=asset.id, reason="session_deleted", next_attempt_at=due)
            )
        elif work.status != "done":
            work.next_attempt_at = max(work.next_attempt_at, due)
            work.version += 1
    session.flush()


def save(session, principal, client_id, purchase_id, key, body):
    """The original key recovers one immutable result; changed intent never reuses it."""
    principal.operations()
    saved = receipt(session, principal, key)
    digest = reviews.digest(
        {"clientId": client_id, "purchaseId": purchase_id, **body.model_dump(mode="json")}
    )
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError(
                "idempotency_conflict", "Review the original package action before retrying.", 409
            )
        return PackageActionState.model_validate(saved.result)
    view, client, purchase, eligible, requests = reviews.review(
        session, principal, client_id, purchase_id, body.operation
    )
    if view.expected != body.expected:
        raise conflict()
    if body.operation == "delete_sessions" and body.deleteUpcomingSessions:
        raise AuthError("INVALID_REQUEST", "Review one package action.", 422)
    deactivating = body.operation == "deactivate" and purchase.status != "inactive"
    rows = (
        eligible
        if body.operation == "delete_sessions" or (deactivating and body.deleteUpcomingSessions)
        else []
    )
    now, action_id = reviews.clock(), uuid4()
    until = now + timedelta(hours=24) if rows and body.operation == "delete_sessions" else None
    if deactivating:
        event = LifecycleEvent(
            purchase_id=purchase.id,
            status="inactive",
            reason="owner",
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
        session.add(event)
        session.flush()
        purchase.status, purchase.lifecycle_event_id = "inactive", event.id
    if deactivating or rows:
        purchase.version += 1
        session.flush()
    message_id = (
        notify(session, principal, client, purchase, rows, body.operation, len(rows), until)
        if deactivating or rows
        else None
    )
    result = PackageActionState(
        id=action_id,
        clientId=client.id,
        purchaseId=purchase.id,
        purchaseVersion=purchase.version,
        status=purchase.status,
        deletedSessionIds=[row.id for row in rows],
        messageId=message_id,
        undoUntil=until,
    )
    action = PackageActionReceipt(
        id=action_id,
        request_key=key,
        request_sha256=digest,
        operation=body.operation,
        client_id=client.id,
        purchase_id=purchase.id,
        client_version=view.clientVersion,
        purchase_version=view.purchaseVersion,
        message_id=message_id,
        undo_expires_at=until,
        result=result.model_dump(mode="json"),
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(action)
    session.flush()
    for row in rows:
        session.add(
            SessionArchive(
                action_id=action.id,
                session_id=row.id,
                original_version=row.version,
                original_created_at=row.created_at,
                original_updated_at=row.updated_at,
                **{field: getattr(row, field) for field in ARCHIVED_FIELDS},
            )
        )
    session.flush()
    reject_requests(session, principal, requests, {row.id for row in rows}, now, action.id)
    detach_media(session, [row.id for row in rows], now, until, action.id)
    for row in rows:
        session.add(
            SessionEvent(
                session_id=row.id,
                session_version=row.version,
                kind="package_session_deleted",
                note="Retained package deletion archive.",
                actor_id=principal.user_id,
                actor_name=principal.name,
            )
        )
    session.flush()
    for row in rows:
        session.delete(row)
    session.flush()
    if rows:
        renumber_purchase(session, purchase.id)
    return result
