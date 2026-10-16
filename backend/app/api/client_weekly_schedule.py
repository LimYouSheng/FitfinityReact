"""Authoritative current-purchase weekly-time review and complete calendar preview."""

import hashlib
import json
from datetime import date, datetime, time
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import Field, StrictInt, StrictStr, model_validator
from sqlalchemy import func, select

from app.api.client_deactivation import target
from app.api.client_notes import record
from app.api.directory import MAX_RECORDS, bounded
from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import conflict
from app.models.people import Client, Trainer
from app.models.training import (
    Acknowledgement,
    CreditDebit,
    PackagePurchase,
    PurchaseScheduleSlot,
    TrainingSession,
)
from app.persistence import occupied_booking_clause

CLOCK = r"^(?:[01]\d|2[0-3]):[0-5]\d$"


class ClientWeeklySlot(Contract):
    id: UUID
    weekday: StrictInt = Field(ge=0, le=6)
    startsAt: StrictStr = Field(pattern=CLOCK)
    endsAt: StrictStr = Field(pattern=CLOCK)


class ClientWeeklySession(Contract):
    id: UUID
    version: int
    trainerId: UUID
    date: date
    startsAt: str
    endsAt: str
    slotId: UUID | None


class ClientWeeklyReview(Contract):
    id: UUID
    version: int
    name: str
    purchaseId: UUID
    purchaseVersion: int
    trainerId: UUID
    trainerVersion: int
    outcome: Literal["applied", "requested"]
    expected: str = Field(pattern=r"^[0-9a-f]{64}$")
    slots: list[ClientWeeklySlot]
    sessions: list[ClientWeeklySession]


class SaveClientWeeklySchedule(Contract):
    expected: str = Field(pattern=r"^[0-9a-f]{64}$")
    slots: list[ClientWeeklySlot] = Field(min_length=1, max_length=7)

    @model_validator(mode="after")
    def valid_slots(self):
        if (
            len({s.id for s in self.slots}) != len(self.slots)
            or len({s.weekday for s in self.slots}) != len(self.slots)
            or any(s.startsAt >= s.endsAt for s in self.slots)
        ):
            raise ValueError("Keep distinct weekly days and valid time intervals")
        return self


class ClientWeeklyPreview(Contract):
    expected: str
    outcome: Literal["applied", "requested"]
    updatedSessions: int


def inspect(session, principal, identity, *, write=False):
    client = record(session, principal, identity, write=write)
    client, purchases = target(session, client.id, write=write)
    if client.status != "active":
        raise conflict()
    purchase = next((p for p in purchases if p.stage == "current"), None)
    if purchase is None:
        raise conflict()
    slots = bounded(
        session,
        select(PurchaseScheduleSlot)
        .where(PurchaseScheduleSlot.purchase_id == purchase.id)
        .order_by(PurchaseScheduleSlot.weekday, PurchaseScheduleSlot.id)
        .with_for_update(read=not write),
        7,
    )
    if not slots:
        raise conflict()
    bookings = bounded(
        session,
        select(TrainingSession)
        .where(TrainingSession.purchase_id == purchase.id)
        .order_by(TrainingSession.id)
        .with_for_update(read=not write),
    )
    trainers = bounded(
        session, select(Trainer).order_by(Trainer.id).with_for_update(read=not write)
    )
    trainer = next(t for t in trainers if t.id == client.trainer_id)
    if trainer.status != "active":
        raise conflict()
    now = (
        session.scalar(select(func.clock_timestamp()))
        .astimezone(ZoneInfo("Asia/Singapore"))
        .replace(tzinfo=None)
    )
    ids = {b.id for b in bookings}
    locked = set(
        session.scalars(
            select(Acknowledgement.session_id).where(Acknowledgement.session_id.in_(ids))
        )
    )
    locked.update(
        session.scalars(select(CreditDebit.session_id).where(CreditDebit.session_id.in_(ids)))
    )
    eligible = [
        b
        for b in bookings
        if purchase.status == "active"
        and b.status not in {"completed", "cancelled"}
        and b.id not in locked
        and b.schedule_state == "booked"
        and datetime.combine(b.training_date, b.starts_at) > now
    ]
    typed_slots = [
        ClientWeeklySlot(
            id=s.id,
            weekday=s.weekday,
            startsAt=s.starts_at.strftime("%H:%M"),
            endsAt=s.ends_at.strftime("%H:%M"),
        )
        for s in slots
    ]
    typed_sessions = [
        ClientWeeklySession(
            id=b.id,
            version=b.version,
            trainerId=b.trainer_id,
            date=b.training_date,
            startsAt=b.starts_at.strftime("%H:%M"),
            endsAt=b.ends_at.strftime("%H:%M"),
            slotId=b.schedule_slot_id,
        )
        for b in eligible
    ]
    outcome = (
        "requested"
        if not principal.manages_operations and trainer.approve_weekly_schedule
        else "applied"
    )
    evidence = {
        "client": [str(client.id), client.version, str(client.trainer_id)],
        "purchase": [str(purchase.id), purchase.version, purchase.status],
        "trainer": [
            str(trainer.id),
            trainer.version,
            trainer.status,
            trainer.approve_weekly_schedule,
        ],
        "slots": [
            [str(s.id), s.version, s.weekday, str(s.starts_at), str(s.ends_at)] for s in slots
        ],
        "sessions": [b.model_dump(mode="json") for b in typed_sessions],
        "outcome": outcome,
    }
    viewed = ClientWeeklyReview(
        id=client.id,
        version=client.version,
        name=client.name,
        purchaseId=purchase.id,
        purchaseVersion=purchase.version,
        trainerId=trainer.id,
        trainerVersion=trainer.version,
        outcome=outcome,
        slots=typed_slots,
        sessions=typed_sessions,
        expected=hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest(),
    )
    return viewed, client, purchase, trainer, slots, eligible, now


def changes(session, viewed, slots, bookings, now, body):
    if body.expected != viewed.expected or {(s.id, s.weekday) for s in body.slots} != {
        (s.id, s.weekday) for s in slots
    }:
        raise conflict()
    after = {s.id: s for s in body.slots}
    if all(
        after[s.id].startsAt == s.starts_at.strftime("%H:%M")
        and after[s.id].endsAt == s.ends_at.strftime("%H:%M")
        for s in slots
    ):
        raise AuthError("SCHEDULE_UNCHANGED", "Change a weekly time before saving.", 422)
    changed = []
    for booking in bookings:
        selected = after.get(booking.schedule_slot_id)
        if selected is None:
            selected = next(
                (s for s in body.slots if s.weekday == booking.training_date.weekday()), None
            )
        if selected is None and len(slots) == 1:
            selected = body.slots[0]
        if selected is None:
            matching = [
                s
                for s in slots
                if s.starts_at == booking.starts_at and s.ends_at == booking.ends_at
            ]
            if len(matching) == 1:
                selected = after[matching[0].id]
        if selected is None:
            raise AuthError(
                "SCHEDULE_UNMAPPED",
                "Review the unmatched booking date before changing weekly times.",
                409,
            )
        start, end = time.fromisoformat(selected.startsAt), time.fromisoformat(selected.endsAt)
        if start == booking.starts_at and end == booking.ends_at:
            continue
        if datetime.combine(booking.training_date, start) <= now:
            raise conflict()
        changed.append((booking, start, end))
    ids = {b.id for b, _, _ in changed}
    competing = bounded(
        session,
        select(TrainingSession)
        .join(PackagePurchase, TrainingSession.purchase_id == PackagePurchase.id)
        .join(Client, TrainingSession.client_id == Client.id)
        .where(
            occupied_booking_clause(),
            TrainingSession.id.not_in(ids),
            TrainingSession.training_date.in_({b.training_date for b, _, _ in changed}),
        ),
        MAX_RECORDS * 365,
    )
    intervals = [(b, b.starts_at, b.ends_at) for b in competing] + changed
    if any(
        b.id != other.id
        and b.training_date == other.training_date
        and (b.client_id == other.client_id or b.trainer_id == other.trainer_id)
        and start < other_end
        and other_start < end
        for b, start, end in changed
        for other, other_start, other_end in intervals
    ):
        raise AuthError(
            "SCHEDULE_CONFLICT",
            "The weekly change conflicts with another session. Choose another time.",
            409,
        )
    return changed


def review(session, principal, identity):
    return inspect(session, principal, identity)[0]


def preview(session, principal, identity, body):
    viewed, _, _, _, slots, bookings, now = inspect(session, principal, identity)
    planned = changes(session, viewed, slots, bookings, now, body)
    return ClientWeeklyPreview(
        expected=viewed.expected, outcome=viewed.outcome, updatedSessions=len(planned)
    )
