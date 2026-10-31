"""Shared reviewed purchase schedule and atomic persistence for onboarding and renewal."""

from dataclasses import dataclass
from datetime import time, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.api.client_matching import DAYS, package_terms, require_future_start
from app.auth.errors import AuthError
from app.authorization import conflict
from app.models.people import Trainer, TrainerAvailability
from app.models.training import (
    PackagePurchase,
    PackageTemplateRevision,
    PurchasePreference,
    PurchaseScheduleSlot,
    TrainingSession,
)
from app.persistence import add_purchase
from app.purchase_schedule import DatedSlot, WeeklySlot, covered, generated_dates


@dataclass
class PreparedPurchase:
    terms: PackageTemplateRevision
    trainer: Trainer
    preferences: list[WeeklySlot]
    slots: list[WeeklySlot]
    dates: list[DatedSlot]
    gender_preference: str


def prepare_purchase(session, body, *, allow_subwindows=False):
    require_future_start(session, body.startDate)
    terms = package_terms(session, body)
    trainer = session.scalar(select(Trainer).where(Trainer.id == body.trainerId).with_for_update())
    expected_gender = {"Female trainer preferred": "Female", "Male trainer preferred": "Male"}.get(
        body.genderPreference
    )
    if (
        trainer is None
        or trainer.status != "active"
        or trainer.version != body.trainerVersion
        or (expected_gender and trainer.gender != expected_gender)
    ):
        raise conflict()
    hours = [
        WeeklySlot(s.weekday, s.starts_at, s.ends_at)
        for s in session.scalars(
            select(TrainerAvailability).where(TrainerAvailability.trainer_id == trainer.id)
        )
    ]
    preferences = list(
        dict.fromkeys(slot for block in body.clientPreferences for slot in block.slots())
    )
    slots = [
        WeeklySlot(DAYS.index(s.day), time.fromisoformat(s.from_), time.fromisoformat(s.to))
        for s in body.fixedWeeklySchedule
    ]
    if any(
        not (covered(slot, preferences) if allow_subwindows else slot in preferences)
        or not covered(slot, hours)
        for slot in slots
    ):
        raise conflict()
    try:
        dates = generated_dates(body.startDate, terms.total_sessions, terms.validity_days, slots)
    except ValueError:
        raise AuthError("invalid_request", "Review the complete package schedule.", 422) from None
    gender_preference = {
        "No gender preference": "any",
        "Female trainer preferred": "female",
        "Male trainer preferred": "male",
    }[body.genderPreference]
    return PreparedPurchase(terms, trainer, preferences, slots, dates, gender_preference)


def persist_purchase(session, client, body, prepared, *, stage):
    terms, trainer = prepared.terms, prepared.trainer
    preferences, slots, dates = prepared.preferences, prepared.slots, prepared.dates
    gender_preference = prepared.gender_preference
    purchase = PackagePurchase(
        client_id=client.id,
        template_id=terms.template_id,
        template_revision=terms.revision,
        name=terms.name,
        total_sessions=terms.total_sessions,
        validity_days=terms.validity_days,
        sessions_per_week=body.sessionsPerWeek,
        free_gym=body.sessionsPerWeek >= 2,
        start_date=body.startDate,
        end_date=body.startDate + timedelta(days=terms.validity_days - 1),
        purchased_trainer_id=trainer.id,
        trainer_id=trainer.id,
        gender_preference=gender_preference,
        stage=stage,
    )
    saved_slots = {
        slot: PurchaseScheduleSlot(
            id=uuid4(),
            weekday=slot.weekday,
            starts_at=slot.starts_at,
            ends_at=slot.ends_at,
            purchased_weekday=slot.weekday,
            purchased_starts_at=slot.starts_at,
            purchased_ends_at=slot.ends_at,
        )
        for slot in slots
    }
    bookings = [
        TrainingSession(
            client_id=client.id,
            trainer_id=trainer.id,
            schedule_slot_id=saved_slots[d.slot].id,
            session_number=index,
            training_date=d.training_date,
            starts_at=d.slot.starts_at,
            ends_at=d.slot.ends_at,
        )
        for index, d in enumerate(dates, 1)
    ]
    add_purchase(
        session,
        purchase,
        list(saved_slots.values()),
        [
            PurchasePreference(weekday=p.weekday, starts_at=p.starts_at, ends_at=p.ends_at)
            for p in preferences
        ],
        bookings,
        expected_client_version=client.version,
    )
    return purchase
