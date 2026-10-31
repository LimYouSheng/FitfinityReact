"""Read-only retained-calendar review shared by client and individual purchase restoration."""

import hashlib
import json
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator
from sqlalchemy import or_, select

from app.api.client_deactivation import target
from app.api.client_matching import MatchRequest
from app.api.directory import bounded
from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.people import Client, LifecycleEvent, Trainer
from app.models.training import Acknowledgement, CreditDebit, PackagePurchase, TrainingSession
from app.persistence import occupied_booking_clause


class ReactivationDates(Contract):
    expected: str = Field(pattern=r"^[0-9a-f]{64}$")
    dates: dict[UUID, date] = Field(max_length=2000)

    @field_validator("dates", mode="before")
    @classmethod
    def calendar_dates(cls, value):
        if not isinstance(value, dict):
            raise ValueError("Review each replacement date")
        for day in value.values():
            MatchRequest.calendar_date(day)
        return value


class RetainedSession(Contract):
    id: UUID
    version: int
    purchaseId: UUID
    trainerId: UUID
    trainerName: str
    scheduleState: Literal["booked", "open"]
    originalDate: date | None
    date: date | None
    startsAt: str | None
    endsAt: str | None
    locked: bool
    error: str | None


class ClientReactivationReview(Contract):
    id: UUID
    version: int
    name: str
    expected: str
    purchaseIds: list[UUID]
    rows: list[RetainedSession]
    packageError: str | None


class PackageReactivationReview(ClientReactivationReview):
    packageId: UUID


def review(session, principal, identity, body=None, *, write=False, package_id=None):
    principal.operations()
    client, purchases = target(session, identity, write=write)
    if client.status != ("active" if package_id is not None else "inactive"):
        raise conflict()
    selected = next((p for p in purchases if p.id == package_id), None)
    if package_id is not None:
        if selected is None:
            raise unavailable()
        if selected.status != "inactive":
            raise conflict()
    bookings = bounded(
        session,
        select(TrainingSession)
        .where(TrainingSession.client_id == identity)
        .order_by(TrainingSession.id)
        .with_for_update(read=not write),
    )
    trainers = {
        t.id: t
        for t in bounded(
            session,
            select(Trainer)
            .where(Trainer.id.in_({b.trainer_id for b in bookings}))
            .order_by(Trainer.id)
            .with_for_update(read=not write),
        )
    }
    events = {
        e.id: e
        for e in bounded(
            session,
            select(LifecycleEvent).where(
                LifecycleEvent.id.in_({p.lifecycle_event_id for p in purchases})
            ),
        )
    }
    restoring = [
        p
        for p in purchases
        if p.status == "inactive"
        and (event := events.get(p.lifecycle_event_id))
        and event.reason == "client"
    ]
    if package_id is not None:
        restoring = [selected]
    active_ids = {p.id for p in purchases if p.status == "active"} | {p.id for p in restoring}
    ids = {b.id for b in bookings}
    acknowledged = set(
        session.scalars(
            select(Acknowledgement.session_id).where(Acknowledgement.session_id.in_(ids))
        )
    )
    debited = set(
        session.scalars(select(CreditDebit.session_id).where(CreditDebit.session_id.in_(ids)))
    )
    evidence = {
        "client": [str(client.id), client.version, str(client.trainer_id), client.status],
        "purchases": [
            [
                str(p.id),
                p.version,
                p.status,
                str(p.lifecycle_event_id),
                str(p.start_date),
                str(p.end_date),
            ]
            for p in purchases
        ],
        "sessions": [
            [
                str(b.id),
                b.version,
                str(b.purchase_id),
                str(b.trainer_id),
                b.status,
                b.schedule_state,
                str(b.training_date),
                str(b.starts_at),
                str(b.ends_at),
                b.id in acknowledged,
                b.id in debited,
            ]
            for b in bookings
        ],
        "trainers": [[str(t.id), t.version, t.status] for t in trainers.values()],
    }
    if package_id is not None:
        evidence["packageId"] = str(package_id)
    expected = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
    if body is not None and body.expected != expected:
        raise conflict()
    dates = body.dates if body else {}
    retained = [
        b
        for b in bookings
        if b.purchase_id in active_ids
        and (package_id is None or b.purchase_id == package_id)
        and b.status in {"scheduled", "planned"}
    ]
    if set(dates) - {b.id for b in retained}:
        raise AuthError("invalid_request", "Review only retained unfinished sessions.", 422)
    package_error = None  # Independent purchases may have overlapping validity.
    competing = bounded(
        session,
        select(TrainingSession)
        .join(PackagePurchase, TrainingSession.purchase_id == PackagePurchase.id)
        .join(Client, TrainingSession.client_id == Client.id)
        .where(
            occupied_booking_clause(),
            TrainingSession.training_date.in_({dates.get(b.id, b.training_date) for b in retained}),
            or_(TrainingSession.trainer_id.in_(trainers), TrainingSession.client_id == identity),
            TrainingSession.id.not_in({b.id for b in retained}),
        )
        .order_by(TrainingSession.id),
    )
    rows = []
    for booking in retained:
        day = (
            None
            if booking.schedule_state == "open"
            else dates.get(booking.id, booking.training_date)
        )
        trainer = trainers[booking.trainer_id]
        locked = booking.id in acknowledged or booking.id in debited
        error = None
        if booking.schedule_state == "open" and booking.id in dates:
            error = "Schedule an open session through Change ad-hoc date/time after reactivation."
        elif trainer.status != "active":
            error = "Reactivate the assigned trainer before restoring this session."
        elif locked and day != booking.training_date:
            error = "Acknowledged sessions cannot be rescheduled."
        elif booking.schedule_state == "booked" and any(
            other.schedule_state == "booked"
            and other.id != booking.id
            and (other.trainer_id == booking.trainer_id or other.client_id == identity)
            and dates.get(other.id, other.training_date) == day
            and other.starts_at < booking.ends_at
            and booking.starts_at < other.ends_at
            for other in [*retained, *competing]
        ):
            error = "Conflicts with another booking for this trainer or client. Choose a free date."
        rows.append(
            RetainedSession(
                id=booking.id,
                version=booking.version,
                purchaseId=booking.purchase_id,
                trainerId=booking.trainer_id,
                trainerName=trainer.name,
                scheduleState=booking.schedule_state,
                originalDate=booking.training_date,
                date=day,
                startsAt=booking.starts_at.strftime("%H:%M") if booking.starts_at else None,
                endsAt=booking.ends_at.strftime("%H:%M") if booking.ends_at else None,
                locked=locked,
                error=error,
            )
        )
    response = PackageReactivationReview if package_id is not None else ClientReactivationReview
    return response(
        id=client.id,
        version=client.version,
        name=client.name,
        expected=expected,
        purchaseIds=[p.id for p in restoring],
        rows=rows,
        packageError=package_error,
        **({"packageId": package_id} if package_id is not None else {}),
    )
