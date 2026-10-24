"""Reviewed application reactivation; provider identities and closed sessions stay untouched."""

import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictInt
from sqlalchemy import select, text

from app.api.schemas import Contract
from app.api.session_mutation_journal import journal
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import TrainerReactivationReceipt
from app.models.communications import Message, MessageReceipt
from app.models.people import LifecycleEvent, StaffUser, Trainer


class ReactivationReview(Contract):
    id: UUID
    version: StrictInt = Field(ge=1)
    accountId: UUID | None
    accountVersion: StrictInt | None = Field(ge=1)


class ReactivateTrainer(Contract):
    expectedVersion: StrictInt = Field(ge=1)
    expectedAccountId: UUID | None
    expectedAccountVersion: StrictInt | None = Field(ge=1)


class ReactivationState(Contract):
    id: UUID
    version: StrictInt = Field(ge=1)
    status: Literal["active"] = "active"


def allowed(principal):
    if not principal.manages_operations:
        raise AuthError("forbidden", "Trainer reactivation is unavailable.", 403)


def target(session, trainer_id, *, write=False):
    # Authentication and profile writers acquire the linked user before the trainer.
    user_id = session.scalar(select(Trainer.user_id).where(Trainer.id == trainer_id))
    user = session.scalar(
        select(StaffUser).where(StaffUser.id == user_id).with_for_update(read=not write)
    )
    trainer = session.scalar(
        select(Trainer).where(Trainer.id == trainer_id).with_for_update(read=not write)
    )
    if trainer is None:
        raise unavailable()
    if trainer.user_id != user_id or (user_id is not None and user is None):
        raise conflict()
    return trainer, user


def review(session, principal, trainer_id):
    allowed(principal)
    trainer, user = target(session, trainer_id)
    if trainer.status != "inactive":
        raise conflict()
    return ReactivationReview(
        id=trainer.id,
        version=trainer.version,
        accountId=user.id if user else None,
        accountVersion=user.version if user else None,
    )


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(714602039)"))
    return session.scalar(
        select(TrainerReactivationReceipt).where(
            TrainerReactivationReceipt.actor_id == principal.user_id,
            TrainerReactivationReceipt.request_key == key,
        )
    )


def reconcile(session, principal, key):
    allowed(principal)
    previous = receipt(session, principal, key)
    if previous is None:
        raise unavailable()
    return ReactivationState.model_validate(previous.result)


@journal("trainer.reactivate")
def save(session, principal, trainer_id, key, body):
    allowed(principal)
    trainer, user = target(session, trainer_id, write=True)
    previous = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps(
            {"id": str(trainer_id), **body.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    if previous:
        if previous.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Review this request before retrying.", 409)
        return ReactivationState.model_validate(previous.result)
    if (
        trainer.status != "inactive"
        or trainer.version != body.expectedVersion
        or trainer.user_id != body.expectedAccountId
        or (user.version if user else None) != body.expectedAccountVersion
    ):
        raise conflict()
    trainer.status, trainer.version = "active", trainer.version + 1
    if user:
        user.status, user.version = "active", user.version + 1
    # Existing authentication triggers advance the epoch and revoke sessions; never reopen them.
    session.add(
        LifecycleEvent(
            trainer_id=trainer.id,
            status="active",
            reason="owner",
            actor_id=principal.user_id,
            actor_name=principal.name,
            note="Trainer reactivated; a fresh sign-in is required.",
        )
    )
    session.flush()
    result = ReactivationState(id=trainer.id, version=trainer.version)
    session.add(
        TrainerReactivationReceipt(
            request_key=key,
            request_sha256=digest,
            trainer_id=trainer.id,
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    notice = Message(
        kind="trainer_status",
        title=f"{trainer.name} reactivated",
        body="The trainer is eligible for active scheduling and availability matching again.",
        trainer_id=trainer.id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    for recipient in session.scalars(
        select(StaffUser.id).where(
            StaffUser.status == "active",
            StaffUser.role == "owner",
        )
    ):
        session.add(MessageReceipt(message_id=notice.id, user_id=recipient))
    return result
