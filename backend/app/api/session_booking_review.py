"""Owner/Admin booking reviews bind current session, purchase and Trainer versions."""

import hashlib
import json
from datetime import date, time
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import Field, StrictStr, model_validator
from sqlalchemy import func, select

from app.api.directory import bounded
from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import conflict, session_record, unavailable
from app.models.communications import ChangeRequest
from app.models.people import Client, Trainer
from app.models.training import Acknowledgement, CreditDebit, PackagePurchase, TrainingSession
from app.persistence import occupied_booking_clause

CLOCK = r"^(?:[01]\d|2[0-3]):[0-5]\d$"


class BookingPosition(Contract):
    id: UUID
    version: int
    sessionNumber: int | None
    scheduleState: Literal["booked", "open"]
    date: str | None
    startsAt: str | None
    endsAt: str | None
    trainerId: UUID
    slotId: UUID | None


class BookingTrainer(Contract):
    id: UUID
    version: int
    name: str


class SessionBookingReview(Contract):
    id: UUID
    version: int
    clientId: UUID
    clientVersion: int
    purchaseId: UUID
    purchaseVersion: int
    expected: str
    session: BookingPosition
    trainers: list[BookingTrainer]


class SaveSessionBooking(Contract):
    expected: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    date: StrictStr = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    startsAt: StrictStr = Field(pattern=CLOCK)
    endsAt: StrictStr = Field(pattern=CLOCK)
    trainerId: UUID

    @model_validator(mode="after")
    def valid_interval(self):
        date.fromisoformat(self.date)
        if self.startsAt >= self.endsAt:
            raise ValueError("Choose a valid interval")
        return self


def position(row):
    return BookingPosition(
        id=row.id,
        version=row.version,
        sessionNumber=row.session_number,
        scheduleState=row.schedule_state,
        date=row.training_date.isoformat() if row.training_date else None,
        startsAt=row.starts_at.strftime("%H:%M") if row.starts_at else None,
        endsAt=row.ends_at.strftime("%H:%M") if row.ends_at else None,
        trainerId=row.trainer_id,
        slotId=row.schedule_slot_id,
    )


def inspect(session, principal, identity, *, write=False, allow_assigned=False):
    """Lock the aggregate in lifecycle order; review exposes no clinical or pay data."""
    if not allow_assigned:
        principal.operations()
    booking = session_record(session, principal, identity, write=write)
    if (
        allow_assigned
        and not principal.manages_operations
        and booking.trainer_id != principal.trainer_id
    ):
        raise unavailable()
    client = session.get(Client, booking.client_id)
    purchase = session.get(PackagePurchase, booking.purchase_id)
    if (
        client.status != "active"
        or purchase.status != "active"
        or booking.status in {"completed", "cancelled"}
    ):
        raise conflict()
    for model in (Acknowledgement, CreditDebit):
        if session.scalar(select(model.id).where(model.session_id == identity).limit(1)):
            raise AuthError("booking_final", "Acknowledged or debited bookings cannot change.", 409)
    bookings = bounded(
        session,
        select(TrainingSession)
        .where(TrainingSession.purchase_id == purchase.id)
        .order_by(TrainingSession.id)
        .with_for_update(read=not write),
        365,
    )
    trainers = bounded(
        session, select(Trainer).order_by(Trainer.id).with_for_update(read=not write)
    )
    pending = bounded(
        session,
        select(ChangeRequest)
        .where(ChangeRequest.session_id == identity, ChangeRequest.status == "pending")
        .order_by(ChangeRequest.id)
        .with_for_update(read=not write),
    )
    previous = [position(row).model_dump(mode="json") for row in bookings]
    evidence = {
        "client": [str(client.id), client.version, client.status],
        "purchase": [str(purchase.id), purchase.version, purchase.status],
        "sessions": previous,
        "trainers": [[str(t.id), t.version, t.status] for t in trainers],
        "pending": [[str(r.id), r.version] for r in pending],
    }
    expected = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
    view = SessionBookingReview(
        id=booking.id,
        version=booking.version,
        clientId=client.id,
        clientVersion=client.version,
        purchaseId=purchase.id,
        purchaseVersion=purchase.version,
        expected=expected,
        session=position(booking),
        trainers=[
            BookingTrainer(id=t.id, version=t.version, name=t.name)
            for t in trainers
            if t.status == "active"
        ],
    )
    return view, booking, client, purchase, bookings, trainers, pending, previous


def validate_change(session, view, booking, trainers, pending, body):
    """Recheck current occupancy at commit, including completed inactive-client bookings."""
    if view.expected != body.expected:
        raise conflict()
    next_date = date.fromisoformat(body.date)
    start, end = time.fromisoformat(body.startsAt), time.fromisoformat(body.endsAt)
    if booking.schedule_state == "booked" and (
        booking.training_date,
        booking.starts_at,
        booking.ends_at,
        booking.trainer_id,
    ) == (next_date, start, end, body.trainerId):
        return False
    if pending:
        raise AuthError("pending_request", "Resolve the pending session request first.", 409)
    if not any(t.id == body.trainerId and t.status == "active" for t in trainers):
        raise AuthError("inactive_trainer", "Choose an active Trainer.", 409)
    if booking.schedule_state == "open":
        now = session.scalar(select(func.clock_timestamp())).astimezone(ZoneInfo("Asia/Singapore"))
        if (next_date, start) <= (now.date(), now.time().replace(tzinfo=None)):
            raise AuthError("past_booking", "Choose a date and start time in the future.", 409)
    occupied = session.scalar(
        select(TrainingSession.id)
        .join(PackagePurchase, TrainingSession.purchase_id == PackagePurchase.id)
        .join(Client, TrainingSession.client_id == Client.id)
        .where(
            occupied_booking_clause(),
            TrainingSession.id != booking.id,
            TrainingSession.training_date == next_date,
            TrainingSession.starts_at < end,
            TrainingSession.ends_at > start,
            (TrainingSession.trainer_id == body.trainerId)
            | (TrainingSession.client_id == booking.client_id),
        )
        .limit(1)
    )
    if occupied:
        raise AuthError("booking_conflict", "This time conflicts with another booking.", 409)
    return True


def review(session, principal, identity):
    return inspect(session, principal, identity)[0]
