"""Atomic replacement batch, access revocation and immutable command recovery."""

import hashlib
import json
from typing import Literal
from uuid import UUID

from sqlalchemy import select, text

from app.api.schemas import Contract
from app.api.session_mutation_journal import journal
from app.api.trainer_deactivation import inspect
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import TrainerDeactivationReceipt
from app.models.communications import Message, MessageReceipt, SessionEvent
from app.models.people import LifecycleEvent, StaffUser


class TrainerDeactivationState(Contract):
    id: UUID
    version: int
    status: Literal["inactive"] = "inactive"


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(714602050)"))
    return session.scalar(
        select(TrainerDeactivationReceipt).where(
            TrainerDeactivationReceipt.actor_id == principal.user_id,
            TrainerDeactivationReceipt.request_key == key,
        )
    )


def reconcile(session, principal, key):
    principal.operations()
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return TrainerDeactivationState.model_validate(saved.result)


@journal("trainer.deactivate")
def save(session, principal, identity, key, body):
    principal.operations()
    saved = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps({"id": str(identity), **body.model_dump(mode="json")}, sort_keys=True).encode()
    ).hexdigest()
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Review the original deactivation.", 409)
        return TrainerDeactivationState.model_validate(saved.result)
    viewed, trainer, user, bookings, trainers = inspect(
        session, principal, identity, body.replacements, write=True
    )
    if body.expected != viewed.expected or set(body.replacements) != {b.id for b in bookings}:
        raise conflict()
    for row in viewed.sessions:
        selected = next((t for t in row.choices if t.id == body.replacements[row.id]), None)
        if selected is None or selected.error:
            raise conflict()
    for booking in bookings:
        replacement_id = body.replacements[booking.id]
        session.add(
            SessionEvent(
                session_id=booking.id,
                session_version=booking.version,
                kind="trainer_deactivation",
                note="Reassigned before Trainer deactivation.",
                old_trainer_id=trainer.id,
                new_trainer_id=replacement_id,
                actor_id=principal.user_id,
                actor_name=principal.name,
            )
        )
        booking.trainer_id = replacement_id
        booking.version += 1
        replacement_user = trainers[replacement_id].user_id
        if replacement_user and session.scalar(
            select(StaffUser.id).where(
                StaffUser.id == replacement_user, StaffUser.status == "active"
            )
        ):
            row = next(r for r in viewed.sessions if r.id == booking.id)
            when = (
                "Open session"
                if row.scheduleState == "open"
                else (f"{row.date} · {row.startsAt}–{row.endsAt}")
            )
            notify(
                session,
                principal,
                {replacement_user},
                kind="assignment",
                title="Session reassigned to you",
                body=f"{row.clientName} · {when}",
                trainer_id=replacement_id,
                client_id=booking.client_id,
                session_id=booking.id,
            )
    trainer.status, trainer.version = "inactive", trainer.version + 1
    if user:
        user.status, user.version = "inactive", user.version + 1
    # Existing epoch triggers close active application sessions in this same transaction.
    session.add(
        LifecycleEvent(
            trainer_id=trainer.id,
            status="inactive",
            reason="owner",
            actor_id=principal.user_id,
            actor_name=principal.name,
            note="Remaining sessions reassigned; application access closed.",
        )
    )
    session.flush()
    result = TrainerDeactivationState(id=trainer.id, version=trainer.version)
    session.add(
        TrainerDeactivationReceipt(
            request_key=key,
            request_sha256=digest,
            trainer_id=trainer.id,
            previous=viewed.model_dump(mode="json"),
            replacements=body.model_dump(mode="json")["replacements"],
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    owners = set(
        session.scalars(
            select(StaffUser.id).where(StaffUser.role == "owner", StaffUser.status == "active")
        )
    )
    notify(
        session,
        principal,
        owners,
        kind="trainer_status",
        title=f"{trainer.name} deactivated",
        body=f"{len(bookings)} remaining sessions reassigned before account deactivation.",
        trainer_id=trainer.id,
    )
    return result


def notify(session, principal, recipients, **values):
    notice = Message(**values, actor_id=principal.user_id, actor_name=principal.name)
    session.add(notice)
    session.flush()
    for recipient in recipients:
        session.add(MessageReceipt(message_id=notice.id, user_id=recipient))
