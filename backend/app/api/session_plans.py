"""Reviewed plan replacement retains item identities, history and original retry receipts."""

import hashlib
import json
from datetime import date, datetime, time
from uuid import UUID

from pydantic import Field, StrictStr, model_validator
from sqlalchemy import exists, func, select, text

from app.api import session_reads
from app.api.request_cancellation import DECISION_LOCK as PLAN_LOCK
from app.api.schemas import Contract
from app.api.session_read_schemas import SessionPlanRead
from app.auth.errors import AuthError
from app.authorization import conflict, session_record, session_scope, unavailable
from app.models.api import SessionPlanReceipt
from app.models.communications import SessionEvent
from app.models.people import Client
from app.models.training import (
    Acknowledgement,
    CreditDebit,
    ExercisePlanDetail,
    ExercisePlanItem,
    PackagePurchase,
    TrainingSession,
)


class PlanDetail(Contract):
    id: StrictStr = Field(min_length=1, max_length=200)
    value: StrictStr = Field(min_length=1, max_length=10000)


class PlanItem(Contract):
    id: StrictStr = Field(min_length=1, max_length=200)
    name: StrictStr = Field(min_length=1, max_length=200)
    weight: StrictStr = Field(max_length=100)
    reps: StrictStr = Field(max_length=100)
    rounds: StrictStr = Field(max_length=100)
    rest: StrictStr = Field(max_length=100)
    customDetails: list[PlanDetail] = Field(max_length=100)

    @model_validator(mode="after")
    def valid_details(self):
        if not self.name.strip() or len({d.id for d in self.customDetails}) != len(
            self.customDetails
        ):
            raise ValueError("Every exercise needs a name and distinct detail identities")
        if any(not d.id.strip() or not d.value.strip() for d in self.customDetails):
            raise ValueError("Details need an identity and text")
        return self


class SavePlan(Contract):
    expected: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    items: list[PlanItem] = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def distinct_items(self):
        if len({p.id for p in self.items}) != len(self.items):
            raise ValueError("Exercise identities must be distinct")
        return self


class PlanReview(Contract):
    sessionId: UUID
    version: int
    expected: str
    items: list[SessionPlanRead]


class PlanSaved(Contract):
    sessionId: UUID
    version: int
    items: list[SessionPlanRead]
    savedAt: datetime


def inspect(session, principal, identity, *, write=True):
    """Bind aggregate/item versions; write reviews require current authority and finality checks."""
    booking = session_record(session, principal, identity, write=write)
    for model in (Acknowledgement, CreditDebit) if write else ():
        if session.scalar(select(model.id).where(model.session_id == identity).limit(1)):
            raise AuthError("plan_final", "Acknowledged session plans cannot change.", 409)
    rows = list(
        session.scalars(
            select(ExercisePlanItem)
            .where(ExercisePlanItem.session_id == identity, ExercisePlanItem.retired_at.is_(None))
            .order_by(ExercisePlanItem.id)
            .with_for_update()
        )
    )
    details = list(
        session.scalars(
            select(ExercisePlanDetail)
            .join(ExercisePlanItem, ExercisePlanDetail.plan_item_id == ExercisePlanItem.id)
            .where(ExercisePlanItem.session_id == identity, ExercisePlanItem.retired_at.is_(None))
            .order_by(ExercisePlanDetail.id)
        )
    )
    view = session_reads.detail(session, principal, identity)
    client = session.get(Client, booking.client_id)
    purchase = session.get(PackagePurchase, booking.purchase_id)
    evidence = [
        [str(booking.id), booking.version, str(booking.trainer_id)],
        [str(client.id), client.version],
        [str(purchase.id), purchase.version],
        [[str(p.id), p.version] for p in rows],
        [[str(d.id), d.version] for d in details],
    ]
    expected = hashlib.sha256(json.dumps(evidence).encode()).hexdigest()
    return (
        PlanReview(
            sessionId=identity, version=booking.version, expected=expected, items=view.exercisePlan
        ),
        booking,
        rows,
        details,
    )


def review(session, principal, identity):
    return inspect(session, principal, identity)[0]


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": PLAN_LOCK})
    return session.scalar(
        select(SessionPlanReceipt).where(
            SessionPlanReceipt.actor_id == principal.user_id, SessionPlanReceipt.request_key == key
        )
    )


def reconcile(session, principal, key):
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return decode_saved(saved.result)


def save(session, principal, identity, key, body):
    """Retire removals; never move results or media to newly inserted plan identities."""
    saved = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps(
            {"session": str(identity), **body.model_dump(mode="json")}, sort_keys=True
        ).encode()
    ).hexdigest()
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "This key belongs to another plan.", 409)
        return PlanSaved.model_validate(saved.result)
    viewed, booking, rows, details = inspect(session, principal, identity)
    if viewed.expected != body.expected:
        raise conflict()
    return apply_plan(
        session, principal, identity, key, digest, body, viewed, booking, rows, details
    )


def apply_plan(
    session, principal, identity, key, digest, body, viewed, booking, rows, details, *, source=None
):
    """Shared atomic replacement preserves old item ownership for ordinary saves and copies."""
    active = {str(p.id): p for p in rows if p.retired_at is None}
    for item in body.items:
        if item.id not in active and not item.id.startswith("draft-"):
            raise unavailable()
    now = session.scalar(select(func.clock_timestamp()))
    retained = {p.id for p in body.items}
    for row in active.values():
        if str(row.id) not in retained:
            row.retired_at, row.position = now, None
    for position, item in enumerate(body.items, 1):
        row = active.get(item.id)
        if row is None:
            row = ExercisePlanItem(session_id=identity, position=position, name=item.name.strip())
            session.add(row)
            session.flush()
        row.position = position
        for field in ("name", "weight", "reps", "rounds", "rest"):
            setattr(row, field, getattr(item, field).strip())
        # Legacy notes are projected as an editable detail until the first reviewed save;
        # the prior notes remain in the immutable receipt, including deliberate removal.
        row.notes = ""
        current = {d.detail_key: d for d in details if d.plan_item_id == row.id}
        wanted = {d.id for d in item.customDetails}
        for detail in current.values():
            if detail.detail_key not in wanted:
                session.delete(detail)
        for index, detail in enumerate(item.customDetails, 1):
            target = current.get(detail.id)
            if target is None:
                target = ExercisePlanDetail(
                    plan_item_id=row.id,
                    detail_key=detail.id,
                    position=index,
                    value=detail.value.strip(),
                )
                session.add(target)
            target.position, target.value = index, detail.value.strip()
    if source is not None:
        booking.copied_from_session_id = source.sessionId
    booking.status = "planned"
    booking.version += 1
    session.add(
        SessionEvent(
            session_id=identity,
            session_version=viewed.version,
            kind="exercise_plan",
            note=f"{len(body.items)} exercises saved.",
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    session.flush()
    result = PlanSaved(
        sessionId=identity,
        version=booking.version,
        savedAt=now,
        items=session_reads.detail(session, principal, identity).exercisePlan,
    )
    if source is not None:
        result = PlanCopied(**result.model_dump(), copiedFromSessionId=source.sessionId)
    session.add(
        SessionPlanReceipt(
            request_key=key,
            request_sha256=digest,
            session_id=identity,
            previous=(
                viewed.model_dump(mode="json")
                if source is None
                else {
                    "target": viewed.model_dump(mode="json"),
                    "source": source.model_dump(mode="json"),
                }
            ),
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    return result


class PreviousSource(PlanReview):
    date: date
    startsAt: time


class PreviousPlan(Contract):
    target: PlanReview
    source: PreviousSource | None


class CopyPlan(Contract):
    expected: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    sourceId: UUID
    sourceExpected: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class PlanCopied(PlanSaved):
    copiedFromSessionId: UUID


def decode_saved(result):
    model = PlanCopied if "copiedFromSessionId" in result else PlanSaved
    return model.model_validate(result)


def previous(session, principal, identity, *, write=False):
    """Select only readable nonempty plans on earlier days; same-day sessions never qualify."""
    target, booking, _, _ = inspect(session, principal, identity, write=write)
    if not principal.manages_operations and booking.trainer_id != principal.trainer_id:
        raise unavailable()
    source = None
    if booking.schedule_state != "open":
        source = session.scalar(
            select(TrainingSession)
            .where(
                TrainingSession.client_id == booking.client_id,
                TrainingSession.training_date < booking.training_date,
                TrainingSession.schedule_state != "open",
                session_scope(principal),
                exists().where(
                    ExercisePlanItem.session_id == TrainingSession.id,
                    ExercisePlanItem.retired_at.is_(None),
                ),
            )
            .order_by(
                TrainingSession.training_date.desc(),
                TrainingSession.starts_at.desc(),
                TrainingSession.id.desc(),
            )
            .limit(1)
        )
    projected = None
    if source is not None:
        viewed = inspect(session, principal, source.id, write=False)[0]
        projected = PreviousSource(
            **viewed.model_dump(), date=source.training_date, startsAt=source.starts_at
        )
    return PreviousPlan(target=target, source=projected)


def copy_previous(session, principal, identity, key, body):
    """Confirm both reviewed plans and latest-source selection before replacing the target."""
    saved = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps(
            {"session": str(identity), "copy": True, **body.model_dump(mode="json")}, sort_keys=True
        ).encode()
    ).hexdigest()
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "This key belongs to another plan.", 409)
        return PlanCopied.model_validate(saved.result)
    preview = previous(session, principal, identity, write=True)
    source = preview.source
    if (
        preview.target.expected != body.expected
        or source is None
        or source.sessionId != body.sourceId
        or source.expected != body.sourceExpected
    ):
        raise conflict()
    viewed, booking, rows, details = inspect(session, principal, identity)
    # New target identities intentionally exclude source media ownership and results.
    items = [
        PlanItem(
            id=f"draft-copy-{index}",
            name=p.name,
            weight=p.weight,
            reps=p.reps,
            rounds=p.rounds,
            rest=p.rest,
            customDetails=[d.model_dump() for d in p.customDetails],
        )
        for index, p in enumerate(source.items)
    ]
    return apply_plan(
        session,
        principal,
        identity,
        key,
        digest,
        SavePlan(expected=body.expected, items=items),
        viewed,
        booking,
        rows,
        details,
        source=source,
    )
