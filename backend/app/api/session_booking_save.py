"""Atomic booking changes, chronology and notices with actor-scoped retry receipts."""

import hashlib
import json
from datetime import date, time
from uuid import UUID

from sqlalchemy import select, text

from app.api.schemas import Contract
from app.api.session_booking_review import BookingPosition, inspect, position, validate_change
from app.api.session_mutation_journal import journal
from app.auth.errors import AuthError
from app.authorization import unavailable
from app.models.api import SessionBookingReceipt
from app.models.communications import Message, MessageReceipt, SessionEvent
from app.models.people import StaffUser
from app.session_numbering import renumber_purchase


class BookingSavedVersion(Contract):
    id: UUID
    version: int


class SessionBookingState(Contract):
    session: BookingPosition
    client: BookingSavedVersion
    purchase: BookingSavedVersion
    positions: list[BookingPosition]
    messageId: UUID | None


def receipt(session, principal, key):
    # Serialize retry identity before taking aggregate locks, matching other domain writers.
    session.execute(text("SELECT pg_advisory_xact_lock(714602052)"))
    return session.scalar(
        select(SessionBookingReceipt).where(
            SessionBookingReceipt.actor_id == principal.user_id,
            SessionBookingReceipt.request_key == key,
        )
    )


def reconcile(session, principal, key):
    principal.operations()
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return SessionBookingState.model_validate(saved.result)


def notify(session, principal, booking, client, trainer):
    """Store a notice and private recipient states in the same booking transaction."""
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
        kind="session_update",
        title=f"Session details saved: {client.name}",
        body=f"{booking.training_date} · {booking.starts_at:%H:%M}–{booking.ends_at:%H:%M}",
        client_id=client.id,
        purchase_id=booking.purchase_id,
        session_id=booking.id,
        trainer_id=trainer.id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    for user_id in recipients:
        session.add(MessageReceipt(message_id=notice.id, user_id=user_id))
    return notice.id


@journal("session.details")
def save(session, principal, identity, key, body):
    """Retain the original result on replay; any failure rolls back the complete write."""
    principal.operations()
    saved = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps({"id": str(identity), **body.model_dump(mode="json")}, sort_keys=True).encode()
    ).hexdigest()
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Review the original booking change.", 409)
        return SessionBookingState.model_validate(saved.result)
    view, booking, client, purchase, bookings, trainers, pending, previous = inspect(
        session, principal, identity, write=True
    )
    changed = validate_change(session, view, booking, trainers, pending, body)
    message_id = None
    if changed:
        message_id = apply_booking(
            session, principal, booking, client, purchase, bookings, trainers, body
        )
    session.flush()
    result = SessionBookingState(
        session=position(booking),
        client=BookingSavedVersion(id=client.id, version=client.version),
        purchase=BookingSavedVersion(id=purchase.id, version=purchase.version),
        positions=[position(row) for row in bookings],
        messageId=message_id,
    )
    session.add(
        SessionBookingReceipt(
            request_key=key,
            request_sha256=digest,
            session_id=booking.id,
            client_id=client.id,
            purchase_id=purchase.id,
            message_id=message_id,
            previous={"review": view.model_dump(mode="json"), "positions": previous},
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    return result


def apply_booking(
    session, principal, booking, client, purchase, bookings, trainers, body, *, request_id=None
):
    """Apply an already validated change inside the caller-owned transaction."""
    session.add(
        SessionEvent(
            session_id=booking.id,
            session_version=booking.version,
            kind="session_details",
            request_id=request_id,
            note="Session date, time or assigned Trainer changed.",
            old_date=booking.training_date,
            new_date=date.fromisoformat(body.date),
            old_start=booking.starts_at,
            old_end=booking.ends_at,
            new_start=time.fromisoformat(body.startsAt),
            new_end=time.fromisoformat(body.endsAt),
            old_trainer_id=booking.trainer_id,
            new_trainer_id=body.trainerId,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    if booking.schedule_state == "open":
        booking.session_number = 1 + sum(row.schedule_state == "booked" for row in bookings)
    booking.schedule_state = "booked"
    booking.training_date = date.fromisoformat(body.date)
    booking.starts_at, booking.ends_at = (
        time.fromisoformat(body.startsAt),
        time.fromisoformat(body.endsAt),
    )
    booking.trainer_id = body.trainerId
    booking.version += 1
    client.version += 1
    purchase.version += 1
    renumber_purchase(session, purchase.id)
    trainer = next(t for t in trainers if t.id == body.trainerId)
    message_id = notify(session, principal, booking, client, trainer)
    return message_id


def apply_open_reassignment(
    session, principal, booking, client, purchase, trainer_id, *, request_id=None
):
    """Retain undated identity and credit history when changing an Open session Trainer."""
    session.add(
        SessionEvent(
            session_id=booking.id,
            session_version=booking.version,
            kind="session_trainer",
            request_id=request_id,
            note="Reassignment of an undated Open session.",
            old_trainer_id=booking.trainer_id,
            new_trainer_id=trainer_id,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    booking.trainer_id = trainer_id
    booking.version += 1
    client.version += 1
    purchase.version += 1
