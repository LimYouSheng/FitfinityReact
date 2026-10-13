"""Recipient-scoped message projections and durable personal read-state commands."""

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import and_, exists, or_, select, text

from app.api.directory import bounded
from app.api.message_schemas import (
    DismissalEvidence,
    MessageReadState,
    MessageRequest,
    MessageRequestSlot,
    PersonalMessage,
)
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import MessageReadReceipt, RenewalDismissal
from app.models.communications import ChangeRequest, Message, MessageReceipt, RequestSlot
from app.models.evidence import RemunerationApproval
from app.models.people import StaffUser
from app.models.training import PackagePurchase


def scope(principal):
    own = exists().where(
        MessageReceipt.message_id == Message.id, MessageReceipt.user_id == principal.user_id
    )
    if principal.role != "admin":
        return own
    # Prototype Admins receive nonfinancial Owner notices, including retained notices
    # created before that Admin joined. Their read state is still entirely personal.
    owner = exists(
        select(MessageReceipt.id)
        .join(StaffUser, StaffUser.id == MessageReceipt.user_id)
        .where(MessageReceipt.message_id == Message.id, StaffUser.role == "owner")
    )
    return and_(
        or_(own, owner),
        Message.remuneration_id.is_(None),
        ~Message.kind.startswith("remuneration"),
        Message.kind != "trainer_rates",
    )


def read_state(message_id, receipt):
    return MessageReadState(
        id=message_id,
        version=receipt.version if receipt else 0,
        read=bool(receipt and receipt.read_at),
        readAt=receipt.read_at if receipt else None,
    )


def records(session, principal):
    messages = bounded(
        session,
        select(Message).where(scope(principal)).order_by(Message.created_at.desc(), Message.id),
    )
    ids = [row.id for row in messages]
    receipts = {
        row.message_id: row
        for row in session.scalars(
            select(MessageReceipt).where(
                MessageReceipt.message_id.in_(ids), MessageReceipt.user_id == principal.user_id
            )
        )
    }
    request_ids = [row.request_id for row in messages if row.request_id]
    slots = defaultdict(list)
    for row in bounded(
        session,
        select(RequestSlot)
        .where(RequestSlot.request_id.in_(request_ids))
        .order_by(RequestSlot.side, RequestSlot.weekday, RequestSlot.starts_at),
        28000,
    ):
        slots[row.request_id].append(MessageRequestSlot.model_validate(row))
    requests = {}
    for row in session.scalars(select(ChangeRequest).where(ChangeRequest.id.in_(request_ids))):
        fields = {
            name: getattr(row, name) for name in MessageRequest.model_fields if name != "slots"
        }
        requests[row.id] = MessageRequest(**fields, slots=slots[row.id])
    cycles = dict(
        session.execute(
            select(RemunerationApproval.id, RemunerationApproval.cycle_key).where(
                RemunerationApproval.id.in_(
                    [row.remuneration_id for row in messages if row.remuneration_id]
                )
            )
        ).all()
    )
    purchases = {
        row.id: row
        for row in session.scalars(
            select(PackagePurchase).where(
                PackagePurchase.id.in_(
                    [row.purchase_id for row in messages if row.kind == "renewal"]
                )
            )
        )
    }
    later = bounded(
        session,
        select(PackagePurchase).where(
            PackagePurchase.client_id.in_([row.client_id for row in purchases.values()]),
            PackagePurchase.status == "active",
        ),
    )
    dismissals = {
        row.message_id: dismissal_evidence(row)
        for row in session.scalars(
            select(RenewalDismissal).where(RenewalDismissal.message_id.in_(ids))
        )
    }
    result = []
    for row in messages:
        purchase = purchases.get(row.purchase_id)
        renewal = None
        if row.kind == "renewal":
            renewal = (
                "renewed"
                if purchase
                and any(
                    p.client_id == purchase.client_id
                    and p.id != purchase.id
                    and p.start_date > purchase.end_date
                    for p in later
                )
                else "active"
            )
        result.append(
            PersonalMessage(
                **read_state(row.id, receipts.get(row.id)).model_dump(),
                recipientUserId=principal.user_id,
                kind=row.kind,
                title=row.title,
                body=row.body,
                createdAt=row.created_at,
                actorId=row.actor_id,
                actorName=row.actor_name,
                clientId=row.client_id,
                purchaseId=row.purchase_id,
                sessionId=row.session_id,
                trainerId=row.trainer_id,
                requestId=row.request_id,
                exerciseId=row.exercise_id,
                packageId=row.package_template_id,
                contentId=row.content_id,
                remunerationCycle=cycles.get(row.remuneration_id),
                request=requests.get(row.request_id),
                renewalStatus="removed" if row.id in dismissals else renewal,
                renewalDismissal=dismissals.get(row.id),
            )
        )
    return result


def command_lock(session):
    session.execute(text("SELECT pg_advisory_xact_lock(714602041)"))


def visible_message(session, principal, identity):
    message = session.scalar(select(Message).where(Message.id == identity, scope(principal)))
    if message is None:
        raise unavailable()
    return message


def receipt(session, principal, key):
    command_lock(session)
    return session.scalar(
        select(MessageReadReceipt).where(
            MessageReadReceipt.actor_id == principal.user_id, MessageReadReceipt.request_key == key
        )
    )


def reconcile(session, principal, key):
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    visible_message(session, principal, saved.message_id)
    return MessageReadState.model_validate(saved.result)


def save(session, principal, message_id, key, body):
    saved = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps(
            {"id": str(message_id), **body.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    visible_message(session, principal, message_id)
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Review this request before retrying.", 409)
        return MessageReadState.model_validate(saved.result)
    current = session.scalar(
        select(MessageReceipt)
        .where(MessageReceipt.message_id == message_id, MessageReceipt.user_id == principal.user_id)
        .with_for_update()
    )
    if (current.version if current else 0) != body.expectedVersion:
        raise conflict()
    if current is None:
        current = MessageReceipt(message_id=message_id, user_id=principal.user_id)
        session.add(current)
    else:
        current.version += 1
    current.read_at = (current.read_at or datetime.now(UTC)) if body.read else None
    session.flush()
    result = read_state(message_id, current)
    session.add(
        MessageReadReceipt(
            request_key=key,
            request_sha256=digest,
            message_id=message_id,
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    return result


def dismissal_evidence(row):
    return DismissalEvidence(at=row.created_at, by={"id": row.actor_id, "name": row.actor_name})
