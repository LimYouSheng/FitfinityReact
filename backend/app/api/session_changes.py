"""Assigned Trainer scheduling commands retain proposals or apply current autonomy policy."""

import hashlib
import json
from datetime import date, time
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import Field, StrictStr, model_validator
from sqlalchemy import func, select, text

from app.api import session_booking_review as booking_review
from app.api import session_booking_save as booking_save
from app.api.request_cancellation import DECISION_LOCK
from app.api.schemas import Contract
from app.api.session_mutation_journal import journal
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import SessionChangeReceipt
from app.models.communications import ChangeRequest, Message, MessageReceipt, RequestEvent
from app.models.people import StaffUser

ChangeKind = Literal["time", "trainer"]


class SessionChangeReview(booking_review.SessionBookingReview):
    kind: ChangeKind
    outcome: Literal["applied", "requested"]


class ChangeTime(Contract):
    expected: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    date: StrictStr = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    startsAt: StrictStr = Field(pattern=booking_review.CLOCK)
    endsAt: StrictStr = Field(pattern=booking_review.CLOCK)

    @model_validator(mode="after")
    def valid_interval(self):
        date.fromisoformat(self.date)
        if self.startsAt >= self.endsAt:
            raise ValueError("Choose a valid interval")
        return self


class ChangeTrainer(Contract):
    expected: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    trainerId: UUID


class SessionChangeState(Contract):
    kind: ChangeKind
    outcome: Literal["applied", "requested"]
    session: booking_review.BookingPosition
    requestId: UUID | None
    messageId: UUID | None


def require_trainer(principal):
    if principal.role != "trainer" or principal.trainer_id is None:
        raise AuthError("forbidden", "Only the assigned Trainer can request this change.", 403)


def context(session, principal, identity, kind, *, write=False):
    """Bind current assignment, aggregate versions and approval policy in one review."""
    require_trainer(principal)
    viewed = booking_review.inspect(session, principal, identity, write=write, allow_assigned=True)
    view, booking, _, _, _, trainers, pending, _ = viewed
    trainer = next(t for t in trainers if t.id == booking.trainer_id)
    if trainer.status != "active":
        raise conflict()
    if pending:
        raise AuthError("pending_request", "Resolve the pending session request first.", 409)
    if kind == "time" and booking.schedule_state == "booked":
        future_time(session, booking.training_date, booking.starts_at)
    outcome = (
        "requested"
        if (trainer.approve_session_time if kind == "time" else trainer.approve_session_trainer)
        else "applied"
    )
    expected = hashlib.sha256(f"{view.expected}/{kind}/{outcome}".encode()).hexdigest()
    reviewed = SessionChangeReview(
        **{**view.model_dump(), "expected": expected}, kind=kind, outcome=outcome
    )
    return reviewed, viewed, trainer


def future_time(session, day, start):
    now = session.scalar(select(func.clock_timestamp())).astimezone(ZoneInfo("Asia/Singapore"))
    if (day, start) <= (now.date(), now.time().replace(tzinfo=None)):
        raise AuthError(
            "past_booking", "Time changes require an upcoming session and future start.", 409
        )


def review(session, principal, identity, kind):
    return context(session, principal, identity, kind)[0]


def receipt(session, principal, key):
    require_trainer(principal)
    session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": DECISION_LOCK})
    return session.scalar(
        select(SessionChangeReceipt).where(
            SessionChangeReceipt.actor_id == principal.user_id,
            SessionChangeReceipt.request_key == key,
        )
    )


def reconcile(session, principal, key):
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return SessionChangeState.model_validate(saved.result)


def notify(session, principal, booking, client, original, replacement, request_id, kind):
    """Proposals stay with the requester and operations; replacements see applied changes only."""
    affected = {principal.user_id, original.user_id}
    if request_id is None:
        affected.add(replacement.user_id)
    affected.discard(None)
    recipients = set(
        session.scalars(
            select(StaffUser.id).where(
                StaffUser.status == "active",
                (StaffUser.role == "owner") | StaffUser.id.in_(affected),
            )
        )
    )
    subject = "time" if kind == "time" else "Trainer"
    action = "change requested" if request_id else "updated"
    notice = Message(
        kind=f"session_{kind}_request" if request_id else "session_update",
        title=f"Session {subject} {action}: {client.name}",
        body="The booking stays unchanged until approval."
        if request_id
        else "The reviewed booking change was applied.",
        client_id=client.id,
        purchase_id=booking.purchase_id,
        session_id=booking.id,
        trainer_id=original.id,
        request_id=request_id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    for identity in recipients:
        session.add(MessageReceipt(message_id=notice.id, user_id=identity))
    return notice.id


@journal("session.change")
def save(session, principal, identity, key, kind, body):
    """Commit proposal/application, history, notices and original retry receipt atomically."""
    saved = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps(
            {"id": str(identity), "kind": kind, **body.model_dump(mode="json")}, sort_keys=True
        ).encode()
    ).hexdigest()
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Check the original session change.", 409)
        return SessionChangeState.model_validate(saved.result)
    reviewed, viewed, original = context(session, principal, identity, kind, write=True)
    view, booking, client, purchase, bookings, trainers, pending, previous = viewed
    if reviewed.expected != body.expected:
        raise conflict()
    trainer_id = booking.trainer_id if kind == "time" else body.trainerId
    replacement = next((t for t in trainers if t.id == trainer_id and t.status == "active"), None)
    if replacement is None or (kind == "trainer" and trainer_id == original.id):
        raise AuthError("invalid_trainer", "Choose another active Trainer.", 409)
    day = date.fromisoformat(body.date) if kind == "time" else booking.training_date
    start = time.fromisoformat(body.startsAt) if kind == "time" else booking.starts_at
    end = time.fromisoformat(body.endsAt) if kind == "time" else booking.ends_at
    if kind == "time":
        future_time(session, day, start)
    booking_body = None
    changed = True
    if day is not None:
        booking_body = booking_review.SaveSessionBooking(
            expected=view.expected,
            date=day.isoformat(),
            startsAt=start.strftime("%H:%M"),
            endsAt=end.strftime("%H:%M"),
            trainerId=trainer_id,
        )
        changed = booking_review.validate_change(
            session, view, booking, trainers, pending, booking_body
        )
    request_id = message_id = None
    outcome = reviewed.outcome if changed else "applied"
    if changed and outcome == "requested":
        proposal = ChangeRequest(
            kind=f"session_{kind}",
            session_id=booking.id,
            purchase_id=purchase.id,
            client_id=client.id,
            trainer_id=original.id,
            expected_version=booking.version,
            replacement_trainer_id=trainer_id if kind == "trainer" else None,
            old_date=booking.training_date if kind == "time" else None,
            old_start=booking.starts_at if kind == "time" else None,
            old_end=booking.ends_at if kind == "time" else None,
            new_date=day if kind == "time" else None,
            new_start=start if kind == "time" else None,
            new_end=end if kind == "time" else None,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
        session.add(proposal)
        session.flush()
        request_id = proposal.id
        session.add(
            RequestEvent(
                request_id=request_id,
                sequence=1,
                status="pending",
                actor_id=principal.user_id,
                actor_name=principal.name,
            )
        )
    elif changed:
        if booking_body is None:
            booking_save.apply_open_reassignment(
                session, principal, booking, client, purchase, trainer_id
            )
        else:
            message_id = booking_save.apply_booking(
                session, principal, booking, client, purchase, bookings, trainers, booking_body
            )
    if changed and message_id is None:
        message_id = notify(
            session, principal, booking, client, original, replacement, request_id, kind
        )
    session.flush()
    result = SessionChangeState(
        kind=kind,
        outcome=outcome,
        session=booking_review.position(booking),
        requestId=request_id,
        messageId=message_id,
    )
    session.add(
        SessionChangeReceipt(
            request_key=key,
            request_sha256=digest,
            session_id=booking.id,
            client_id=client.id,
            purchase_id=purchase.id,
            message_id=message_id,
            request_id=request_id,
            previous={"review": reviewed.model_dump(mode="json"), "positions": previous},
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    return result
