"""Operational staff preview real purchased dates; no reservation or clinical data."""

import re
from collections import defaultdict
from datetime import date, time, timedelta
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictInt, StrictStr, field_validator, model_validator
from sqlalchemy import select

from app.api.directory import MAX_RECORDS, bounded
from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.people import Client, Trainer, TrainerAvailability
from app.models.training import (
    PackagePurchase,
    PackageTemplate,
    PackageTemplateRevision,
    TrainingSession,
)
from app.persistence import occupied_booking_clause
from app.purchase_schedule import DatedSlot, WeeklySlot, matching_schedule

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
Day = Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class Preference(Contract):
    days: list[Day] = Field(min_length=1, max_length=7)
    from_: StrictStr = Field(alias="from", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    to: StrictStr = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    @model_validator(mode="after")
    def interval(self):
        if self.from_ >= self.to or len(set(self.days)) != len(self.days):
            raise ValueError("Choose unique days and a From time earlier than To")
        return self

    def slots(self):
        return [
            WeeklySlot(DAYS.index(day), time.fromisoformat(self.from_), time.fromisoformat(self.to))
            for day in self.days
        ]


class MatchRequest(Contract):
    packageId: UUID
    packageVersion: StrictInt = Field(ge=1)
    startDate: date
    sessionsPerWeek: StrictInt = Field(ge=1, le=7)
    genderPreference: Literal[
        "No gender preference", "Female trainer preferred", "Male trainer preferred"
    ]
    clientPreferences: list[Preference] = Field(min_length=1, max_length=100)

    @field_validator("startDate", mode="before")
    @classmethod
    def calendar_date(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("A calendar date is required")
        return value


class MatchedSlot(Contract):
    day: Day
    from_: StrictStr = Field(alias="from", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    to: StrictStr = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class TrainerMatch(Contract):
    trainerId: UUID
    trainerVersion: int
    matches: int
    total: int
    schedule: list[MatchedSlot]


class MatchResult(Contract):
    matches: list[TrainerMatch]


def package_terms(session, body):
    template = session.scalar(
        select(PackageTemplate)
        .where(PackageTemplate.id == body.packageId)
        .with_for_update(read=True)
    )
    if template is None:
        raise unavailable()
    if template.status != "active" or template.version != body.packageVersion:
        raise conflict()
    terms = session.scalar(
        select(PackageTemplateRevision)
        .where(PackageTemplateRevision.template_id == template.id)
        .order_by(PackageTemplateRevision.revision.desc())
        .limit(1)
    )
    if terms is None:
        raise AuthError("directory_incomplete", "Package details are unavailable.", 503)
    return terms


def preview(session, principal, body):
    principal.operations()
    terms = package_terms(session, body)
    try:
        # Every possible cadence fills within this horizon, even with a partial first week.
        end = body.startDate + timedelta(
            days=min(
                terms.validity_days - 1,
                ((terms.total_sessions + body.sessionsPerWeek - 1) // body.sessionsPerWeek) * 7 + 6,
            )
        )
        body.startDate + timedelta(days=terms.validity_days - 1)
    except OverflowError:
        raise AuthError(
            "invalid_request", "The package exceeds the supported calendar.", 422
        ) from None
    query = select(Trainer).where(Trainer.status == "active").order_by(Trainer.name, Trainer.id)
    gender = {"Female trainer preferred": "Female", "Male trainer preferred": "Male"}.get(
        body.genderPreference
    )
    if gender:
        query = query.where(Trainer.gender == gender)
    trainers = bounded(session, query.with_for_update(read=True))
    ids = [t.id for t in trainers]
    availability, occupied = defaultdict(list), defaultdict(list)
    for slot in bounded(
        session,
        select(TrainerAvailability).where(TrainerAvailability.trainer_id.in_(ids)),
        MAX_RECORDS * 100,
    ):
        availability[slot.trainer_id].append(WeeklySlot(slot.weekday, slot.starts_at, slot.ends_at))
    for booking in bounded(
        session,
        select(TrainingSession)
        .join(PackagePurchase, TrainingSession.purchase_id == PackagePurchase.id)
        .join(Client, TrainingSession.client_id == Client.id)
        .where(
            TrainingSession.trainer_id.in_(ids),
            TrainingSession.training_date.between(body.startDate, end),
            occupied_booking_clause(),
        ),
        MAX_RECORDS * 365,
    ):
        occupied[booking.trainer_id].append(
            DatedSlot(
                booking.training_date,
                WeeklySlot(booking.training_date.weekday(), booking.starts_at, booking.ends_at),
            )
        )
    preferences = [slot for block in body.clientPreferences for slot in block.slots()]
    matches = []
    from app.purchase_schedule import covered

    for trainer in trainers:
        hours = availability[trainer.id]
        try:
            schedule = matching_schedule(
                body.startDate,
                terms.total_sessions,
                terms.validity_days,
                body.sessionsPerWeek,
                preferences,
                hours,
                occupied[trainer.id],
            )
        except ValueError:
            raise AuthError("invalid_request", "Review the package schedule.", 422) from None
        if schedule:
            matches.append(
                TrainerMatch(
                    trainerId=trainer.id,
                    trainerVersion=trainer.version,
                    matches=sum(
                        any(covered(slot, hours) for slot in block.slots())
                        for block in body.clientPreferences
                    ),
                    total=len(body.clientPreferences),
                    schedule=[
                        MatchedSlot(
                            day=DAYS[s.weekday],
                            **{
                                "from": s.starts_at.strftime("%H:%M"),
                                "to": s.ends_at.strftime("%H:%M"),
                            },
                        )
                        for s in schedule
                    ],
                )
            )
    # Stable sorting keeps database name/id order within the same coverage score.
    return MatchResult(matches=sorted(matches, key=lambda item: -item.matches))
