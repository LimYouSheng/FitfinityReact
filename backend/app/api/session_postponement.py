"""Release a current booking or retain a supervised proposal without changing its dates."""

import hashlib
import json
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import Field, StrictStr
from sqlalchemy import func, select, text

from app.api.schemas import Contract
from app.api.session_booking_review import BookingPosition, inspect, position
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import SessionPostponementReceipt
from app.models.communications import (
    ChangeRequest,
    Message,
    MessageReceipt,
    RequestEvent,
    SessionEvent,
)
from app.models.people import StaffUser
from app.session_numbering import renumber_purchase


class PostponementReview(Contract):
    id: UUID
    version: int
    expected: str
    outcome: Literal["applied", "requested"]
    session: BookingPosition


class PostponeSession(Contract):
    expected: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class PostponementState(Contract):
    outcome: Literal["applied", "requested"]
    session: BookingPosition
    requestId: UUID | None
    messageId: UUID
    changedPositions: int


def review_context(session, principal, identity, *, write=False):
    """Only operations staff or the current assigned Trainer may release this booking."""
    view, booking, client, purchase, bookings, trainers, pending, previous = inspect(
        session, principal, identity, write=write, allow_assigned=True
    )
    trainer = next(t for t in trainers if t.id == booking.trainer_id)
    now = session.scalar(select(func.clock_timestamp())).astimezone(ZoneInfo("Asia/Singapore"))
    if (
        purchase.stage != "current"
        or booking.schedule_state != "booked"
        or trainer.status != "active"
        or (booking.training_date, booking.starts_at)
        <= (now.date(), now.time().replace(tzinfo=None))
    ):
        raise AuthError(
            "postponement_unavailable",
            "Only an upcoming current-package booking can be postponed.",
            409,
        )
    weekly = session.scalar(
        select(ChangeRequest.id)
        .where(
            ChangeRequest.client_id == client.id,
            ChangeRequest.kind == "fixed_weekly_schedule",
            ChangeRequest.status == "pending",
        )
        .limit(1)
        .with_for_update(read=not write)
    )
    if pending or weekly:
        raise AuthError(
            "pending_request", "Resolve the pending schedule or Trainer request first.", 409
        )
    outcome = (
        "requested"
        if not principal.manages_operations and trainer.approve_session_time
        else "applied"
    )
    reviewed = PostponementReview(
        id=booking.id,
        version=booking.version,
        expected=view.expected,
        outcome=outcome,
        session=position(booking),
    )
    return reviewed, booking, client, purchase, trainer, previous


def review(session, principal, identity):
    return review_context(session, principal, identity)[0]


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(714602053)"))
    return session.scalar(
        select(SessionPostponementReceipt).where(
            SessionPostponementReceipt.actor_id == principal.user_id,
            SessionPostponementReceipt.request_key == key,
        )
    )


def reconcile(session, principal, key):
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return PostponementState.model_validate(saved.result)


def notify(session, principal, booking, client, trainer, request_id):
    recipients = set(
        session.scalars(
            select(StaffUser.id).where(
                StaffUser.status == "active",
                (StaffUser.role == "owner")
                | (StaffUser.id == trainer.user_id)
                | (StaffUser.id == principal.user_id),
            )
        )
    )
    notice = Message(
        kind="session_postpone_request" if request_id else "session_update",
        title=f"{'Postponement requested' if request_id else 'Session postponed'}: {client.name}",
        body=(
            "When applied, this session becomes undated. "
            "Other bookings, credits and validity stay unchanged."
        ),
        client_id=client.id,
        purchase_id=booking.purchase_id,
        session_id=booking.id,
        trainer_id=trainer.id,
        request_id=request_id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    for identity in recipients:
        session.add(MessageReceipt(message_id=notice.id, user_id=identity))
    return notice.id


def save(session, principal, identity, key, body):
    """Receipt, proposal or applied booking, history and notices share one transaction."""
    saved = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps({"id": str(identity), **body.model_dump()}, sort_keys=True).encode()
    ).hexdigest()
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Check the original postponement request.", 409)
        return PostponementState.model_validate(saved.result)
    viewed, booking, client, purchase, trainer, previous = review_context(
        session, principal, identity, write=True
    )
    if viewed.expected != body.expected:
        raise conflict()
    request_id, changed = None, []
    if viewed.outcome == "requested":
        proposal = ChangeRequest(
            kind="session_postpone",
            session_id=booking.id,
            purchase_id=purchase.id,
            client_id=client.id,
            trainer_id=trainer.id,
            expected_version=booking.version,
            old_date=booking.training_date,
            old_start=booking.starts_at,
            old_end=booking.ends_at,
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
    else:
        session.add(
            SessionEvent(
                session_id=booking.id,
                session_version=booking.version,
                kind="session_postpone",
                note="Booking released; the same session remains open without a date or time.",
                old_date=booking.training_date,
                old_start=booking.starts_at,
                old_end=booking.ends_at,
                old_trainer_id=booking.trainer_id,
                new_trainer_id=booking.trainer_id,
                actor_id=principal.user_id,
                actor_name=principal.name,
            )
        )
        booking.schedule_state = "open"
        booking.training_date = booking.starts_at = booking.ends_at = None
        booking.session_number = booking.schedule_slot_id = None
        booking.version += 1
        client.version += 1
        purchase.version += 1
        changed = renumber_purchase(session, purchase.id)
    message_id = notify(session, principal, booking, client, trainer, request_id)
    session.flush()
    result = PostponementState(
        outcome=viewed.outcome,
        session=position(booking),
        requestId=request_id,
        messageId=message_id,
        changedPositions=len(changed),
    )
    session.add(
        SessionPostponementReceipt(
            request_key=key,
            request_sha256=digest,
            session_id=booking.id,
            client_id=client.id,
            purchase_id=purchase.id,
            message_id=message_id,
            request_id=request_id,
            previous={"review": viewed.model_dump(mode="json"), "positions": previous},
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    return result
