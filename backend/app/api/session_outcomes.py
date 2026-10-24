"""Reviewed outcome corrections retain measurement revisions and permanent completion evidence."""

import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, StrictInt, StrictStr, model_validator
from sqlalchemy import func, select, text

from app.api.request_cancellation import DECISION_LOCK
from app.api.schemas import Contract
from app.api.session_mutation_journal import journal
from app.auth.errors import AuthError
from app.authorization import conflict, session_record, unavailable
from app.models.api import SessionOutcomeReceipt
from app.models.communications import SessionEvent
from app.models.people import Client
from app.models.training import (
    ExercisePlanItem,
    ExerciseResult,
    ExerciseResultRevision,
    PackagePurchase,
)


class Measurement(Contract):
    id: UUID
    loadKg: Decimal = Field(ge=0, le=2000, decimal_places=4)
    reps: StrictInt = Field(ge=1, le=1000)
    sets: StrictInt = Field(ge=1, le=100)


class SaveOutcome(Contract):
    expected: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    trainerComments: StrictStr = Field(max_length=20000)
    measurements: list[Measurement] = Field(max_length=2000)

    @model_validator(mode="after")
    def unique_measurements(self):
        if len({r.id for r in self.measurements}) != len(self.measurements):
            raise ValueError("Measurement identities must be distinct")
        return self


class OutcomeRow(Contract):
    id: UUID
    resultId: UUID | None
    planItemId: UUID | None
    name: str
    loadKg: float | None
    reps: int | None
    sets: int | None


class OutcomeReview(Contract):
    sessionId: UUID
    version: int
    expected: str
    durationMinutes: int
    trainerComments: str
    rows: list[OutcomeRow]
    draftRows: list[OutcomeRow]


class OutcomeSaved(Contract):
    sessionId: UUID
    version: int
    durationMinutes: int
    trainerComments: str
    rows: list[OutcomeRow]
    savedAt: datetime


def duration(booking):
    if booking.starts_at is None or booking.ends_at is None:
        return 0
    return (booking.ends_at.hour * 60 + booking.ends_at.minute) - (
        booking.starts_at.hour * 60 + booking.starts_at.minute
    )


def inspect(session, principal, identity):
    """Allow audited outcome corrections without changing signature, credit or schedule evidence."""
    booking = session_record(session, principal, identity, write=True, allow_final_notes=True)
    plan = list(
        session.scalars(
            select(ExercisePlanItem)
            .where(ExercisePlanItem.session_id == identity)
            .order_by(ExercisePlanItem.id)
            .with_for_update()
        )
    )
    results = list(
        session.scalars(
            select(ExerciseResult)
            .where(ExerciseResult.session_id == identity)
            .order_by(ExerciseResult.id)
            .with_for_update()
        )
    )
    client, purchase = (
        session.get(Client, booking.client_id),
        session.get(PackagePurchase, booking.purchase_id),
    )
    digest = hashlib.sha256(
        json.dumps(
            [
                [str(booking.id), booking.version, str(booking.trainer_id)],
                [str(client.id), client.version],
                [str(purchase.id), purchase.version],
                [[str(p.id), p.version] for p in plan],
                [[str(r.id), r.version] for r in results],
            ]
        ).encode()
    ).hexdigest()
    by_plan = {r.plan_item_id: r for r in results if r.plan_item_id}
    projected = []
    for item in sorted((p for p in plan if p.retired_at is None), key=lambda p: p.position):
        result = by_plan.get(item.id)
        measured = result is not None and result.retired_at is None
        projected.append(
            OutcomeRow(
                id=item.id,
                resultId=result.id if result else None,
                planItemId=item.id,
                name=result.name if measured else item.name,
                loadKg=float(result.load_kg) if measured else None,
                reps=result.reps if measured else None,
                sets=result.sets if measured else None,
            )
        )
    active_ids = {p.id for p in plan if p.retired_at is None}
    for result in results:
        if result.retired_at is None and result.plan_item_id not in active_ids:
            projected.append(
                OutcomeRow(
                    id=result.plan_item_id or result.id,
                    resultId=result.id,
                    planItemId=result.plan_item_id,
                    name=result.name,
                    loadKg=float(result.load_kg),
                    reps=result.reps,
                    sets=result.sets,
                )
            )
    if len(projected) > 2000 or len({r.id for r in projected}) != len(projected):
        raise AuthError("outcome_capacity", "The outcome could not be loaded completely.", 503)
    drafts = [r.model_copy() for r in projected]
    recorded = (
        bool(results)
        or session.scalar(
            select(SessionOutcomeReceipt.id)
            .where(SessionOutcomeReceipt.session_id == identity)
            .limit(1)
        )
        is not None
    )
    if not recorded:
        prescriptions = {p.id: p for p in plan}
        for row in drafts:
            item = prescriptions.get(row.planItemId)
            match = (
                re.fullmatch(r"(\d+(?:\.\d{1,4})?)\s*(?:kg)?", item.weight.strip(), re.I)
                if item
                else None
            )
            if match and item.reps.strip().isdigit() and item.rounds.strip().isdigit():
                weight, reps, sets = float(match[1]), int(item.reps), int(item.rounds)
                if 0 <= weight <= 2000 and 1 <= reps <= 1000 and 1 <= sets <= 100:
                    row.loadKg, row.reps, row.sets = weight, reps, sets
    return (
        OutcomeReview(
            sessionId=identity,
            version=booking.version,
            expected=digest,
            durationMinutes=duration(booking),
            trainerComments=booking.trainer_comments,
            rows=projected,
            draftRows=drafts,
        ),
        booking,
        plan,
        results,
    )


def review(session, principal, identity):
    return inspect(session, principal, identity)[0]


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": DECISION_LOCK})
    return session.scalar(
        select(SessionOutcomeReceipt).where(
            SessionOutcomeReceipt.actor_id == principal.user_id,
            SessionOutcomeReceipt.request_key == key,
        )
    )


def reconcile(session, principal, key):
    found = receipt(session, principal, key)
    if found is None:
        raise unavailable()
    return OutcomeSaved.model_validate(found.result)


def preserve(session, principal, row):
    """Record the exact previous measurement state before any correction or retirement."""
    session.add(
        ExerciseResultRevision(
            result_id=row.id,
            result_version=row.version,
            name=row.name,
            load_kg=row.load_kg,
            reps=row.reps,
            sets=row.sets,
            retired_at=row.retired_at,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )


@journal("session.outcome")
def save(session, principal, identity, key, body):
    """Save comments, measured rows, immutable history and original receipt in one transaction."""
    found = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps(
            {"session": str(identity), **body.model_dump(mode="json")}, sort_keys=True
        ).encode()
    ).hexdigest()
    if found:
        if found.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "This key belongs to another outcome.", 409)
        return OutcomeSaved.model_validate(found.result)
    viewed, booking, plan, results = inspect(session, principal, identity)
    if body.expected != viewed.expected:
        raise conflict()
    offered = {r.id: r for r in viewed.rows}
    if any(r.id not in offered for r in body.measurements):
        raise unavailable()
    current = {r.plan_item_id or r.id: r for r in results}
    requested = {r.id: r for r in body.measurements}
    now = session.scalar(select(func.clock_timestamp()))
    for identity_key, row in current.items():
        if row.retired_at is None and identity_key not in requested:
            preserve(session, principal, row)
            row.retired_at = now
    for value in body.measurements:
        projected = offered[value.id]
        row = current.get(value.id)
        if row is None:
            row = ExerciseResult(
                session_id=identity,
                plan_item_id=projected.planItemId,
                name=projected.name,
                load_kg=value.loadKg,
                reps=value.reps,
                sets=value.sets,
            )
            session.add(row)
        elif (row.load_kg, row.reps, row.sets, row.retired_at) != (
            value.loadKg,
            value.reps,
            value.sets,
            None,
        ):
            preserve(session, principal, row)
            row.load_kg, row.reps, row.sets, row.retired_at = (
                value.loadKg,
                value.reps,
                value.sets,
                None,
            )
    booking.trainer_comments = body.trainerComments.strip()
    booking.version += 1
    session.add(
        SessionEvent(
            session_id=identity,
            session_version=viewed.version,
            kind="session_outcome",
            note=f"{len(body.measurements)} measured exercises saved.",
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    session.flush()
    saved = review(session, principal, identity)
    result = OutcomeSaved(
        sessionId=identity,
        version=booking.version,
        durationMinutes=saved.durationMinutes,
        trainerComments=saved.trainerComments,
        rows=saved.rows,
        savedAt=now,
    )
    session.add(
        SessionOutcomeReceipt(
            request_key=key,
            request_sha256=digest,
            session_id=identity,
            previous=viewed.model_dump(mode="json"),
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    return result
