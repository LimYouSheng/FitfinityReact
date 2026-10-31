"""Atomic permanent reassignment, immutable history and actor-scoped retry evidence."""

import hashlib
import json
from uuid import UUID

from pydantic import Field
from sqlalchemy import or_, select, text

from app.api.admin_supervision import supervised, supervised_recovery
from app.api.client_assignment import inspect
from app.api.directory import bounded
from app.api.schemas import Contract
from app.api.session_mutation_journal import journal
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import ClientAssignmentReceipt
from app.models.communications import (
    ChangeRequest,
    Message,
    MessageReceipt,
    RequestEvent,
    SessionEvent,
)
from app.models.people import StaffUser
from app.models.training import AssignmentChange, AssignmentEvent


class SaveAssignment(Contract):
    expected: str = Field(pattern=r"^[0-9a-f]{64}$")
    trainerId: UUID
    purchaseId: UUID | None = None


class AssignmentState(Contract):
    id: UUID
    version: int
    trainerId: UUID
    eventId: UUID


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(714602049)"))
    return session.scalar(
        select(ClientAssignmentReceipt).where(
            ClientAssignmentReceipt.actor_id == principal.user_id,
            ClientAssignmentReceipt.request_key == key,
        )
    )


@supervised_recovery("client.assignment")
def reconcile(session, principal, key):
    principal.operations()
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return AssignmentState.model_validate(saved.result)


@supervised(
    "trainerAssignment", "client.assignment", SaveAssignment, receipt=receipt, target="identity"
)
@journal("client.assignment")
def save(session, principal, identity, key, body):
    principal.operations()
    saved = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps(
            {"id": str(identity), **body.model_dump(mode="json", exclude_none=True)}, sort_keys=True
        ).encode()
    ).hexdigest()
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError(
                "idempotency_conflict", "Review the original reassignment request.", 409
            )
        return AssignmentState.model_validate(saved.result)
    viewed, client, purchases, bookings, trainers = inspect(
        session, principal, identity, write=True, purchase_id=body.purchaseId
    )
    choice = next((t for t in viewed.choices if t.id == body.trainerId), None)
    if body.expected != viewed.expected or choice is None or choice.error:
        raise conflict()
    old_id = viewed.current.id
    event = AssignmentEvent(
        client_id=client.id,
        old_trainer_id=old_id,
        new_trainer_id=choice.id,
        old_trainer_name=viewed.current.name,
        new_trainer_name=choice.name,
        client_version=client.version,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(event)
    session.flush()
    recipients = {old_id, choice.id}
    for purchase in purchases:
        recipients.add(purchase.trainer_id)
        session.add(
            AssignmentChange(
                event_id=event.id,
                purchase_id=purchase.id,
                old_trainer_id=purchase.trainer_id,
                new_trainer_id=choice.id,
                old_version=purchase.version,
            )
        )
        purchase.trainer_id = choice.id
        purchase.version += 1
    for booking in bookings:
        recipients.add(booking.trainer_id)
        session.add(
            AssignmentChange(
                event_id=event.id,
                session_id=booking.id,
                old_trainer_id=booking.trainer_id,
                new_trainer_id=choice.id,
                old_version=booking.version,
            )
        )
        session.add(
            SessionEvent(
                session_id=booking.id,
                session_version=booking.version,
                kind="client_trainer_assignment",
                note="Permanent client Trainer reassignment.",
                old_trainer_id=booking.trainer_id,
                new_trainer_id=choice.id,
                actor_id=principal.user_id,
                actor_name=principal.name,
            )
        )
        booking.trainer_id = choice.id
        booking.version += 1
    moves_default = purchases[0].stage == "current"
    if moves_default:
        client.trainer_id = choice.id
    client.version += 1
    reject_superseded(session, principal, identity, {b.id for b in bookings}, moves_default)
    session.flush()
    result = AssignmentState(
        id=client.id, version=client.version, trainerId=choice.id, eventId=event.id
    )
    session.add(
        ClientAssignmentReceipt(
            request_key=key,
            request_sha256=digest,
            client_id=client.id,
            event_id=event.id,
            previous=viewed.model_dump(mode="json"),
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    notify(session, principal, client, viewed, choice, recipients, trainers)
    return result


def reject_superseded(session, principal, identity, booking_ids, moves_default=True):
    requests = bounded(
        session,
        select(ChangeRequest)
        .where(
            ChangeRequest.status == "pending",
            or_(
                ChangeRequest.session_id.in_(booking_ids),
                (ChangeRequest.kind == "fixed_weekly_schedule")
                & (ChangeRequest.client_id == identity)
                & moves_default,
            ),
        )
        .order_by(ChangeRequest.id)
        .with_for_update(),
    )
    now = session.scalar(text("SELECT clock_timestamp()"))
    for request in requests:
        request.status = "rejected"
        request.resolved_by, request.resolved_at = principal.user_id, now
        request.resolution_note = "Superseded by permanent trainer reassignment."
        request.version += 1
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


def notify(session, principal, client, viewed, choice, trainer_ids, trainers):
    owner_ids = set(
        session.scalars(
            select(StaffUser.id).where(StaffUser.role == "owner", StaffUser.status == "active")
        )
    )
    target_users = {trainers[t].user_id for t in trainer_ids if trainers[t].user_id}
    trainer_users = set(
        session.scalars(
            select(StaffUser.id).where(StaffUser.id.in_(target_users), StaffUser.status == "active")
        )
    )
    notice = Message(
        kind="client_assignment",
        title=f"Trainer reassigned: {client.name}",
        body=f"{viewed.current.name} → {choice.name} · {len(viewed.sessions)} upcoming sessions · "
        f"{len(viewed.purchases)} current/additional packages · {principal.name}",
        client_id=client.id,
        trainer_id=choice.id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    for user_id in owner_ids | trainer_users:
        session.add(MessageReceipt(message_id=notice.id, user_id=user_id))
