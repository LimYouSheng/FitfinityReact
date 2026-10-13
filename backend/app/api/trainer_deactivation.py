"""Review complete session replacement before application-account deactivation."""

import hashlib
import json
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import Field
from sqlalchemy import select

from app.api.directory import MAX_RECORDS, bounded
from app.api.schemas import Contract
from app.api.trainer_reactivation import target
from app.authorization import conflict
from app.models.people import Client, Trainer
from app.models.training import Acknowledgement, CreditDebit, PackagePurchase, TrainingSession
from app.persistence import occupied_booking_clause


class TrainerDeactivationChoice(Contract):
    id: UUID
    name: str
    version: int
    error: str | None


class TrainerDeactivationSession(Contract):
    id: UUID
    version: int
    clientId: UUID
    clientName: str
    purchaseId: UUID
    trainerId: UUID
    scheduleState: Literal["booked", "open"]
    date: date | None
    startsAt: str | None
    endsAt: str | None
    choices: list[TrainerDeactivationChoice]


class TrainerDeactivationReview(Contract):
    id: UUID
    version: int
    name: str
    accountId: UUID | None
    accountVersion: int | None
    expected: str = Field(pattern=r"^[0-9a-f]{64}$")
    sessions: list[TrainerDeactivationSession]


class TrainerDeactivationSelection(Contract):
    expected: str = Field(pattern=r"^[0-9a-f]{64}$")
    replacements: dict[UUID, UUID] = Field(max_length=2000)


def overlapping(left, right):
    return (
        left.schedule_state == right.schedule_state == "booked"
        and left.training_date == right.training_date
        and left.starts_at < right.ends_at
        and right.starts_at < left.ends_at
    )


def inspect(session, principal, identity, replacements=None, *, write=False):
    principal.operations()
    replacements = replacements or {}
    # Follow lifecycle writers' client -> purchase -> booking order. Snapshot identities
    # first; after acquiring the Trainer barrier, reject any newly attached booking.
    candidates = set(
        session.scalars(select(TrainingSession.id).where(TrainingSession.trainer_id == identity))
    )
    client_ids = set(
        session.scalars(select(TrainingSession.client_id).where(TrainingSession.id.in_(candidates)))
    )
    clients = {
        c.id: c
        for c in bounded(
            session,
            select(Client)
            .where(Client.id.in_(client_ids))
            .order_by(Client.id)
            .with_for_update(read=not write),
        )
    }
    purchases = {
        p.id: p
        for p in bounded(
            session,
            select(PackagePurchase)
            .where(PackagePurchase.client_id.in_(client_ids))
            .order_by(PackagePurchase.id)
            .with_for_update(read=not write),
        )
    }
    bookings = bounded(
        session,
        select(TrainingSession)
        .where(TrainingSession.id.in_(candidates))
        .order_by(TrainingSession.id)
        .with_for_update(read=not write),
    )
    trainer, user = target(session, identity, write=write)
    if trainer.status != "active":
        raise conflict()
    trainers = bounded(
        session, select(Trainer).order_by(Trainer.id).with_for_update(read=not write)
    )
    if candidates != set(
        session.scalars(select(TrainingSession.id).where(TrainingSession.trainer_id == identity))
    ):
        raise conflict()
    eligible = [
        b
        for b in bookings
        if b.trainer_id == identity
        and clients[b.client_id].status == "active"
        and purchases[b.purchase_id].status == "active"
        and b.status not in {"completed", "cancelled"}
    ]
    ids = {b.id for b in eligible}
    # Completed evidence cannot be reassigned even if corrupt status disagrees.
    locked = set(
        session.scalars(
            select(Acknowledgement.session_id).where(Acknowledgement.session_id.in_(ids))
        )
    )
    locked.update(
        session.scalars(select(CreditDebit.session_id).where(CreditDebit.session_id.in_(ids)))
    )
    if locked or set(replacements) - ids:
        raise conflict()
    competing = bounded(
        session,
        select(TrainingSession)
        .join(PackagePurchase, TrainingSession.purchase_id == PackagePurchase.id)
        .join(Client, TrainingSession.client_id == Client.id)
        .where(
            occupied_booking_clause(),
            TrainingSession.id.not_in(ids),
            TrainingSession.training_date.in_({b.training_date for b in eligible}),
        ),
        MAX_RECORDS * 365,
    )
    rows = []
    for booking in eligible:
        choices = []
        for replacement in trainers:
            if replacement.status != "active" or replacement.id == identity:
                continue
            occupied = any(
                overlapping(booking, other)
                and (other.trainer_id == replacement.id or other.client_id == booking.client_id)
                for other in competing
            ) or any(
                other.id != booking.id
                and overlapping(booking, other)
                and (
                    other.client_id == booking.client_id
                    or replacements.get(other.id, other.trainer_id) == replacement.id
                )
                for other in eligible
            )
            choices.append(
                TrainerDeactivationChoice(
                    id=replacement.id,
                    name=replacement.name,
                    version=replacement.version,
                    error="This replacement conflicts with another session in the reviewed batch."
                    if occupied
                    else None,
                )
            )
        rows.append(
            TrainerDeactivationSession(
                id=booking.id,
                version=booking.version,
                clientId=booking.client_id,
                clientName=clients[booking.client_id].name,
                purchaseId=booking.purchase_id,
                trainerId=identity,
                scheduleState=booking.schedule_state,
                date=booking.training_date,
                startsAt=booking.starts_at.strftime("%H:%M") if booking.starts_at else None,
                endsAt=booking.ends_at.strftime("%H:%M") if booking.ends_at else None,
                choices=choices,
            )
        )
    evidence = {
        "trainer": [str(trainer.id), trainer.version, trainer.status],
        "user": [str(user.id), user.version, user.status] if user else None,
        "clients": [[str(c.id), c.version, c.status] for c in clients.values()],
        "purchases": [[str(p.id), p.version, p.status] for p in purchases.values()],
        "sessions": [r.model_dump(mode="json", exclude={"choices"}) for r in rows],
        "trainers": [[str(t.id), t.version, t.status] for t in trainers],
    }
    result = TrainerDeactivationReview(
        id=trainer.id,
        version=trainer.version,
        name=trainer.name,
        accountId=user.id if user else None,
        accountVersion=user.version if user else None,
        expected=hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest(),
        sessions=rows,
    )
    return result, trainer, user, eligible, {t.id: t for t in trainers}


def review(session, principal, identity):
    return inspect(session, principal, identity)[0]


def preview(session, principal, identity, body):
    result = inspect(session, principal, identity, body.replacements)[0]
    if result.expected != body.expected:
        raise conflict()
    return result
