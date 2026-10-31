"""Authoritative Add Package defaults and matching; a preview never reserves bookings."""

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator
from sqlalchemy import select

from app.api.client_deactivation import target
from app.api.client_matching import DAYS, MatchedSlot, MatchRequest, Preference, preview
from app.api.directory import bounded
from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import conflict
from app.models.training import PurchasePreference, PurchaseScheduleSlot
from app.purchase_schedule import WeeklySlot


class RenewalSlot(MatchedSlot):
    id: UUID


class RenewalPurchase(Contract):
    id: UUID
    version: int
    templateId: UUID
    total: int
    validityDays: int
    sessionsPerWeek: int
    startDate: date
    endDate: date


class RenewalReview(Contract):
    id: UUID
    version: int
    name: str
    trainerId: UUID
    genderPreference: str
    expected: str = Field(pattern=r"^[0-9a-f]{64}$")
    minimumStartDate: date
    package: RenewalPurchase
    fixedWeeklySchedule: list[RenewalSlot]
    clientPreferences: list[Preference]


class RenewalMatchRequest(MatchRequest):
    expected: str = Field(pattern=r"^[0-9a-f]{64}$")
    trainerId: UUID | None = None
    fixedWeeklySchedule: list[MatchedSlot] | None = Field(default=None, min_length=1, max_length=7)

    @model_validator(mode="after")
    def retained_schedule(self):
        if self.fixedWeeklySchedule is not None:
            if self.trainerId is None or len({s.day for s in self.fixedWeeklySchedule}) != len(
                self.fixedWeeklySchedule
            ):
                raise ValueError("Review the trainer and distinct weekly slots")
            for slot in self.fixedWeeklySchedule:
                WeeklySlot(
                    DAYS.index(slot.day),
                    time.fromisoformat(slot.from_),
                    time.fromisoformat(slot.to),
                )
        return self


def review(session, principal, identity, *, write=False):
    principal.operations()
    client, purchases = target(session, identity, write=write)
    if client.status != "active":
        raise conflict()
    current = next((p for p in purchases if p.stage == "current"), None)
    if current is None:
        raise AuthError("directory_incomplete", "Current package details are unavailable.", 503)
    slots = bounded(
        session,
        select(PurchaseScheduleSlot)
        .where(PurchaseScheduleSlot.purchase_id == current.id)
        .order_by(PurchaseScheduleSlot.weekday, PurchaseScheduleSlot.id)
        .with_for_update(read=not write),
    )
    preferences = bounded(
        session,
        select(PurchasePreference)
        .where(PurchasePreference.purchase_id == current.id)
        .order_by(PurchasePreference.weekday, PurchasePreference.starts_at, PurchasePreference.id),
    )
    evidence = {
        "client": [
            str(client.id),
            client.version,
            str(client.trainer_id),
            client.gender_preference,
        ],
        "purchases": [
            [str(p.id), p.version, p.status, p.stage, str(p.start_date), str(p.end_date)]
            for p in purchases
        ],
        "slots": [
            [str(s.id), s.version, s.weekday, str(s.starts_at), str(s.ends_at)] for s in slots
        ],
        "preferences": [
            [str(p.id), p.weekday, str(p.starts_at), str(p.ends_at)] for p in preferences
        ],
    }
    expected = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
    try:
        today = datetime.now(UTC).astimezone(ZoneInfo("Asia/Singapore")).date()
        minimum = today + timedelta(days=1)
    except OverflowError:
        raise AuthError(
            "invalid_request", "There is no later supported package date.", 422
        ) from None
    return RenewalReview(
        id=client.id,
        version=client.version,
        name=client.name,
        trainerId=client.trainer_id,
        genderPreference={
            "any": "No gender preference",
            "female": "Female trainer preferred",
            "male": "Male trainer preferred",
        }[client.gender_preference],
        expected=expected,
        minimumStartDate=minimum,
        package=RenewalPurchase(
            id=current.id,
            version=current.version,
            templateId=current.template_id,
            total=current.total_sessions,
            validityDays=current.validity_days,
            sessionsPerWeek=current.sessions_per_week,
            startDate=current.start_date,
            endDate=current.end_date,
        ),
        fixedWeeklySchedule=[
            RenewalSlot(
                id=s.id,
                day=DAYS[s.weekday],
                **{"from": s.starts_at.strftime("%H:%M"), "to": s.ends_at.strftime("%H:%M")},
            )
            for s in slots
        ],
        clientPreferences=[
            Preference(
                days=[DAYS[p.weekday]],
                **{"from": p.starts_at.strftime("%H:%M"), "to": p.ends_at.strftime("%H:%M")},
            )
            for p in preferences
        ],
    )


def matches(session, principal, identity, body):
    viewed = review(session, principal, identity)
    if viewed.expected != body.expected:
        raise conflict()
    if body.startDate < viewed.minimumStartDate:
        raise AuthError("invalid_request", "Choose a future start date.", 422)
    slots = (
        None
        if body.fixedWeeklySchedule is None
        else [
            WeeklySlot(DAYS.index(s.day), time.fromisoformat(s.from_), time.fromisoformat(s.to))
            for s in body.fixedWeeklySchedule
        ]
    )
    return preview(
        session,
        principal,
        body,
        client_id=identity,
        retained_trainer=body.trainerId,
        retained_slots=slots,
    )
