"""Recipient-scoped message projections and durable personal read-state commands."""

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import and_, exists, func, or_, select, text

from app.api.directory import bounded
from app.api.message_schemas import (
    DismissalEvidence,
    MessageReadState,
    MessageRequest,
    MessageRequestSlot,
    PersonalMessage,
    RequestResolutionActor,
)
from app.api.renewal_policy import usable_purchase
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import MessageReadReceipt, RenewalDismissal
from app.models.communications import (
    ChangeRequest,
    Message,
    MessageReceipt,
    RequestEvent,
    RequestSlot,
)
from app.models.evidence import RemunerationApproval
from app.models.package_actions import (
    PackageActionReceipt,
    PackageActionRequest,
    PackageDeletionUndo,
)
from app.models.people import StaffUser
from app.models.session_mutations import (
    MutationRequest,
    MutationSession,
    SessionMutation,
    SessionMutationUndo,
)
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
        or_(
            own,
            and_(
                owner, Message.kind.not_in(["admin_operation_request", "admin_operation_decision"])
            ),
        ),
        Message.remuneration_id.is_(None),
        ~Message.kind.startswith("remuneration"),
        Message.kind != "trainer_rates",
    )


def mutation_projections(session, principal, message_ids):
    """Only operations or the original Trainer receive a permitted-change Undo entry."""
    rows = session.scalars(
        select(SessionMutation).where(SessionMutation.message_id.in_(message_ids))
    ).all()
    mutations = {
        row.id: row
        for row in rows
        if principal.manages_operations
        or (row.actor_id == principal.user_id and row.actor_role == "trainer")
    }
    undone = dict(
        session.execute(
            select(SessionMutationUndo.mutation_id, SessionMutationUndo.created_at).where(
                SessionMutationUndo.mutation_id.in_(mutations)
            )
        ).all()
    )
    counts = dict(
        session.execute(
            select(MutationSession.mutation_id, func.count())
            .where(MutationSession.mutation_id.in_(mutations), MutationSession.side == "after")
            .group_by(MutationSession.mutation_id)
        ).all()
    )
    now = session.scalar(select(func.clock_timestamp()))
    result = {}
    for row in mutations.values():
        result[row.message_id] = {
            "id": row.id,
            "kind": "session_change",
            "count": counts.get(row.id, 0),
            "expiresAt": row.expires_at,
            "status": "undone"
            if row.id in undone
            else "expired"
            if row.expires_at <= now
            else "available",
            "notice": "Undo corrects this record; it cannot recall a shared message."
            if row.operation == "session.handoff"
            else None,
        }
    return result


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
    resolutions = {
        row.request_id: RequestResolutionActor(id=row.actor_id, name=row.actor_name)
        for row in session.scalars(
            select(RequestEvent).where(
                RequestEvent.request_id.in_(request_ids), RequestEvent.sequence == 2
            )
        )
    }
    reversals = dict(
        session.execute(
            select(PackageActionRequest.request_id, PackageDeletionUndo.created_at)
            .join(
                PackageDeletionUndo, PackageDeletionUndo.action_id == PackageActionRequest.action_id
            )
            .where(PackageActionRequest.request_id.in_(request_ids))
        ).all()
    )
    requests = {}
    for row in session.scalars(select(ChangeRequest).where(ChangeRequest.id.in_(request_ids))):
        fields = {
            name: getattr(row, name)
            for name in MessageRequest.model_fields
            if name not in {"slots", "resolved_by"}
        }
        requests[row.id] = MessageRequest(
            **fields, slots=slots[row.id], resolved_by=resolutions.get(row.id)
        )
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
            usable_purchase(),
        ),
    )
    dismissals = {
        row.message_id: dismissal_evidence(row)
        for row in session.scalars(
            select(RenewalDismissal).where(RenewalDismissal.message_id.in_(ids))
        )
    }
    actions = (
        {
            row.message_id: row
            for row in session.scalars(
                select(PackageActionReceipt).where(
                    PackageActionReceipt.message_id.in_(ids),
                    PackageActionReceipt.undo_expires_at.is_not(None),
                )
            )
        }
        if principal.manages_operations
        else {}
    )
    undone = set(
        session.scalars(
            select(PackageDeletionUndo.action_id).where(
                PackageDeletionUndo.action_id.in_([row.id for row in actions.values()])
            )
        )
    )
    mutations = mutation_projections(session, principal, ids)
    reversals.update(
        dict(
            session.execute(
                select(MutationRequest.entity_id, SessionMutationUndo.created_at)
                .join(
                    SessionMutationUndo,
                    SessionMutationUndo.mutation_id == MutationRequest.mutation_id,
                )
                .where(MutationRequest.entity_id.in_(request_ids), MutationRequest.side == "after")
            ).all()
        )
    )
    result = []
    for row in messages:
        purchase = purchases.get(row.purchase_id)
        renewal = None
        if row.kind == "renewal":
            renewal = (
                "renewed"
                if purchase
                and any(p.client_id == purchase.client_id and p.id != purchase.id for p in later)
                else "active"
            )
        result.append(
            PersonalMessage(
                **read_state(row.id, receipts.get(row.id)).model_dump(),
                undo=(
                    {
                        "id": actions[row.id].id,
                        "count": len(actions[row.id].result["deletedSessionIds"]),
                        "expiresAt": actions[row.id].undo_expires_at,
                        "status": "undone"
                        if actions[row.id].id in undone
                        else "expired"
                        if actions[row.id].undo_expires_at <= datetime.now(UTC)
                        else "available",
                    }
                    if row.id in actions
                    else mutations.get(row.id)
                ),
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
                reversedAt=reversals.get(row.request_id),
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
