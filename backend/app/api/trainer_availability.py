"""Current Trainer availability: reviewed direct save or an immutable supervised proposal."""

import hashlib
import json
from datetime import time
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, StrictInt, StrictStr, model_validator
from sqlalchemy import delete, select, text

from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import TrainerAvailabilityReceipt
from app.models.communications import (
    ChangeRequest,
    Message,
    MessageReceipt,
    RequestEvent,
    RequestSlot,
)
from app.models.people import StaffUser, Trainer, TrainerAvailability

CLOCK = r"^(?:[01]\d|2[0-3]):[0-5]\d$"


class AvailabilityWindow(Contract):
    weekday: StrictInt = Field(ge=0, le=6)
    startsAt: StrictStr = Field(pattern=CLOCK)
    endsAt: StrictStr = Field(pattern=CLOCK)


class SaveAvailability(Contract):
    expectedVersion: StrictInt = Field(ge=1)
    slots: list[AvailabilityWindow] = Field(max_length=10080)

    @model_validator(mode="after")
    def nonoverlapping(self):
        previous = None
        for slot in sorted(self.slots, key=lambda row: (row.weekday, row.startsAt, row.endsAt)):
            if slot.startsAt >= slot.endsAt or (
                previous and previous.weekday == slot.weekday and previous.endsAt > slot.startsAt
            ):
                raise ValueError("Availability windows must be valid and nonoverlapping")
            previous = slot
        return self


class AvailabilityTrainer(Contract):
    id: UUID
    version: StrictInt = Field(ge=1)


class AvailabilityState(Contract):
    outcome: Literal["applied", "requested"]
    trainer: AvailabilityTrainer
    requestId: UUID | None


def allowed(principal):
    if principal.role != "trainer" or principal.trainer_id is None:
        raise AuthError(
            "forbidden", "Only the active Trainer can change their own availability.", 403
        )


def receipt(session, principal, key):
    allowed(principal)
    session.execute(text("SELECT pg_advisory_xact_lock(714602046)"))
    return session.scalar(
        select(TrainerAvailabilityReceipt).where(
            TrainerAvailabilityReceipt.actor_id == principal.user_id,
            TrainerAvailabilityReceipt.request_key == key,
        )
    )


def reconcile(session, principal, key):
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return AvailabilityState.model_validate(saved.result)


def snapshot(rows):
    return sorted(
        [
            {
                "weekday": row.weekday,
                "startsAt": row.starts_at.strftime("%H:%M"),
                "endsAt": row.ends_at.strftime("%H:%M"),
            }
            for row in rows
        ],
        key=lambda row: (row["weekday"], row["startsAt"], row["endsAt"]),
    )


def save(session, principal, trainer_id, key, body):
    saved = receipt(session, principal, key)
    after = sorted(
        [row.model_dump() for row in body.slots],
        key=lambda row: (row["weekday"], row["startsAt"], row["endsAt"]),
    )
    digest = hashlib.sha256(
        json.dumps(
            {"id": str(trainer_id), "expectedVersion": body.expectedVersion, "slots": after},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError(
                "idempotency_conflict",
                "Review the original availability save before retrying.",
                409,
            )
        return AvailabilityState.model_validate(saved.result)
    trainer = session.scalar(
        select(Trainer)
        .where(
            Trainer.id == trainer_id,
            Trainer.id == principal.trainer_id,
            Trainer.user_id == principal.user_id,
            Trainer.status == "active",
        )
        .with_for_update()
    )
    if trainer is None:
        raise unavailable()
    if trainer.version != body.expectedVersion:
        raise conflict()
    before = snapshot(
        session.scalars(
            select(TrainerAvailability)
            .where(TrainerAvailability.trainer_id == trainer.id)
            .with_for_update()
        ).all()
    )
    if before == after:
        raise AuthError("AVAILABILITY_UNCHANGED", "Change your availability before saving.", 422)
    request_id = None
    if trainer.approve_availability:
        pending = session.scalars(
            select(ChangeRequest).where(
                ChangeRequest.trainer_id == trainer.id,
                ChangeRequest.kind == "trainer_availability",
                ChangeRequest.status == "pending",
                ChangeRequest.expected_version == trainer.version,
            )
        ).all()
        for prior in pending:
            slots = session.scalars(
                select(RequestSlot).where(RequestSlot.request_id == prior.id)
            ).all()
            if (
                snapshot([row for row in slots if row.side == "old"]) == before
                and snapshot([row for row in slots if row.side == "new"]) == after
            ):
                request_id = prior.id
                break
        if request_id is None:
            proposal = ChangeRequest(
                kind="trainer_availability",
                trainer_id=trainer.id,
                expected_version=trainer.version,
                actor_id=principal.user_id,
                actor_name=principal.name,
            )
            session.add(proposal)
            session.flush()
            request_id = proposal.id
            session.add(
                RequestEvent(
                    request_id=request_id,
                    sequence=1,
                    status="pending",
                    actor_id=principal.user_id,
                    actor_name=principal.name,
                )
            )
            for side, values in [("old", before), ("new", after)]:
                for slot in values:
                    session.add(
                        RequestSlot(
                            request_id=request_id,
                            side=side,
                            slot_identity=uuid4(),
                            weekday=slot["weekday"],
                            starts_at=time.fromisoformat(slot["startsAt"]),
                            ends_at=time.fromisoformat(slot["endsAt"]),
                        )
                    )
            notify(session, principal, trainer, request_id)
    else:
        apply_availability(session, principal, trainer, after)
    result = AvailabilityState(
        outcome="requested" if request_id else "applied",
        trainer=AvailabilityTrainer(id=trainer.id, version=trainer.version),
        requestId=request_id,
    )
    session.add(
        TrainerAvailabilityReceipt(
            request_key=key,
            request_sha256=digest,
            trainer_id=trainer.id,
            previous={"slots": before},
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    return result


def notify(session, principal, trainer, request_id):
    owners = session.scalars(
        select(StaffUser.id).where(StaffUser.role == "owner", StaffUser.status == "active")
    ).all()
    recipients = [owners, [principal.user_id]] if request_id else [[*owners, principal.user_id]]
    for ids in recipients:
        notice = Message(
            kind="availability_request" if request_id else "availability_update",
            title=f"Availability change: {trainer.name}"
            if request_id
            else f"Availability updated: {trainer.name}",
            body=(
                "Review current and proposed availability. "
                "Approved availability remains unchanged until approval."
            )
            if request_id
            else (
                "Approved availability was updated. "
                "Existing booked sessions retain their scheduled times."
            ),
            request_id=request_id,
            trainer_id=trainer.id,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
        session.add(notice)
        session.flush()
        for identity in set(ids):
            session.add(MessageReceipt(message_id=notice.id, user_id=identity))


def apply_availability(session, principal, trainer, after):
    """Apply an already validated change inside the caller-owned transaction."""
    session.execute(delete(TrainerAvailability).where(TrainerAvailability.trainer_id == trainer.id))
    for slot in after:
        session.add(
            TrainerAvailability(
                trainer_id=trainer.id,
                weekday=slot["weekday"],
                starts_at=time.fromisoformat(slot["startsAt"]),
                ends_at=time.fromisoformat(slot["endsAt"]),
            )
        )
    trainer.version += 1
    notify(session, principal, trainer, None)
