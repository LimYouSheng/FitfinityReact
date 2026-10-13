"""Authoritative permanent-assignment review; historical bookings retain their trainer."""

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import Field
from sqlalchemy import func, select

from app.api.client_deactivation import target
from app.api.directory import MAX_RECORDS, bounded
from app.api.schemas import Contract
from app.authorization import conflict
from app.models.people import Client, Trainer, TrainerAvailability
from app.models.training import (
    Acknowledgement,
    AssignmentEvent,
    CreditDebit,
    PackagePurchase,
    PurchaseScheduleSlot,
    TrainingSession,
)
from app.persistence import occupied_booking_clause
from app.purchase_schedule import WeeklySlot, covered


class AssignmentTrainer(Contract):
    id: UUID
    name: str


class AssignmentChoice(AssignmentTrainer):
    version: int
    error: str | None


class AssignmentPurchase(Contract):
    id: UUID
    version: int
    trainerId: UUID
    name: str


class AssignmentSession(Contract):
    id: UUID
    version: int
    trainerId: UUID
    purchaseId: UUID
    scheduleState: Literal["booked", "open"]
    date: date | None
    startsAt: str | None
    endsAt: str | None


class AssignmentHistory(Contract):
    id: UUID
    at: datetime
    actor: AssignmentTrainer
    previous: AssignmentTrainer
    replacement: AssignmentTrainer


class AssignmentReview(Contract):
    id: UUID
    version: int
    name: str
    expected: str = Field(pattern=r"^[0-9a-f]{64}$")
    current: AssignmentTrainer
    purchases: list[AssignmentPurchase]
    sessions: list[AssignmentSession]
    choices: list[AssignmentChoice]
    history: list[AssignmentHistory]


def inspect(session, principal, identity, *, write=False):
    principal.operations()
    client, all_purchases = target(session, identity, write=write)
    if client.status != "active":
        raise conflict()
    purchases = [p for p in all_purchases if p.status == "active" and p.stage != "archived"]
    purchase_ids = {p.id for p in purchases}
    # The client's standing schedule is retained even when its current package
    # is inactive. It constrains the replacement without moving that purchase.
    standing_ids = purchase_ids | {p.id for p in all_purchases if p.stage == "current"}
    bookings = bounded(
        session,
        select(TrainingSession)
        .where(TrainingSession.client_id == identity)
        .order_by(TrainingSession.id)
        .with_for_update(read=not write),
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
    now = session.scalar(select(func.clock_timestamp())).astimezone(ZoneInfo("Asia/Singapore"))
    eligible = [
        b
        for b in bookings
        if b.purchase_id in purchase_ids
        and b.status not in {"completed", "cancelled"}
        and b.id not in locked
        and (
            b.schedule_state == "open"
            or datetime.combine(b.training_date, b.starts_at) > now.replace(tzinfo=None)
        )
    ]
    slots = bounded(
        session,
        select(PurchaseScheduleSlot)
        .where(PurchaseScheduleSlot.purchase_id.in_(standing_ids))
        .order_by(PurchaseScheduleSlot.id)
        .with_for_update(read=True),
        MAX_RECORDS * 7,
    )
    trainers = bounded(
        session, select(Trainer).order_by(Trainer.id).with_for_update(read=not write)
    )
    by_id = {t.id: t for t in trainers}
    hours = defaultdict(list)
    for slot in bounded(
        session,
        select(TrainerAvailability).where(TrainerAvailability.trainer_id.in_(by_id)),
        MAX_RECORDS * 100,
    ):
        hours[slot.trainer_id].append(WeeklySlot(slot.weekday, slot.starts_at, slot.ends_at))
    competing = bounded(
        session,
        select(TrainingSession)
        .join(PackagePurchase, TrainingSession.purchase_id == PackagePurchase.id)
        .join(Client, TrainingSession.client_id == Client.id)
        .where(
            occupied_booking_clause(),
            TrainingSession.id.not_in({b.id for b in eligible}),
            TrainingSession.training_date.in_({b.training_date for b in eligible}),
        ),
        MAX_RECORDS * 365,
    )
    choices = []
    for trainer in trainers:
        if trainer.status != "active" or trainer.id == client.trainer_id:
            continue
        error = availability_error(client, purchases, slots, eligible, trainer, hours[trainer.id])
        if not error and any(
            other.trainer_id == trainer.id
            and b.schedule_state == "booked"
            and b.training_date == other.training_date
            and b.starts_at < other.ends_at
            and other.starts_at < b.ends_at
            for b in eligible
            for other in competing
        ):
            error = "The selected trainer has another booking during an eligible session."
        choices.append(
            AssignmentChoice(id=trainer.id, name=trainer.name, version=trainer.version, error=error)
        )
    evidence = {
        "client": [
            str(client.id),
            client.version,
            str(client.trainer_id),
            client.gender_preference,
        ],
        "purchases": [
            [str(p.id), p.version, str(p.trainer_id), p.gender_preference] for p in purchases
        ],
        "sessions": [
            [
                str(b.id),
                b.version,
                str(b.trainer_id),
                str(b.purchase_id),
                b.schedule_state,
                str(b.training_date),
                str(b.starts_at),
                str(b.ends_at),
            ]
            for b in eligible
        ],
        "slots": [
            [str(s.id), s.version, s.weekday, str(s.starts_at), str(s.ends_at)] for s in slots
        ],
        "trainers": [[str(t.id), t.version, t.status] for t in trainers],
    }
    history = bounded(
        session,
        select(AssignmentEvent)
        .where(AssignmentEvent.client_id == identity)
        .order_by(AssignmentEvent.created_at, AssignmentEvent.id),
    )
    current = by_id[client.trainer_id]
    result = AssignmentReview(
        id=client.id,
        version=client.version,
        name=client.name,
        expected=hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest(),
        current=AssignmentTrainer(id=current.id, name=current.name),
        purchases=[
            AssignmentPurchase(id=p.id, version=p.version, trainerId=p.trainer_id, name=p.name)
            for p in purchases
        ],
        sessions=[
            AssignmentSession(
                id=b.id,
                version=b.version,
                trainerId=b.trainer_id,
                purchaseId=b.purchase_id,
                scheduleState=b.schedule_state,
                date=b.training_date,
                startsAt=b.starts_at.strftime("%H:%M") if b.starts_at else None,
                endsAt=b.ends_at.strftime("%H:%M") if b.ends_at else None,
            )
            for b in eligible
        ],
        choices=choices,
        history=[
            AssignmentHistory(
                id=e.id,
                at=e.created_at,
                actor=AssignmentTrainer(id=e.actor_id, name=e.actor_name),
                previous=AssignmentTrainer(id=e.old_trainer_id, name=e.old_trainer_name),
                replacement=AssignmentTrainer(id=e.new_trainer_id, name=e.new_trainer_name),
            )
            for e in history
        ],
    )
    return result, client, purchases, eligible, by_id


def availability_error(client, purchases, slots, bookings, trainer, hours):
    for preference in [client.gender_preference, *[p.gender_preference for p in purchases]]:
        gender = {"female": "Female", "male": "Male"}.get(preference)
        if gender and trainer.gender != gender:
            return "The selected trainer does not match the saved trainer preference."
    if any(not covered(WeeklySlot(s.weekday, s.starts_at, s.ends_at), hours) for s in slots):
        return "The selected trainer is unavailable for a saved weekly schedule."
    if any(
        b.schedule_state == "booked"
        and not covered(WeeklySlot(b.training_date.weekday(), b.starts_at, b.ends_at), hours)
        for b in bookings
    ):
        return "The selected trainer is unavailable for an eligible session."
    return None


def review(session, principal, identity):
    return inspect(session, principal, identity)[0]
