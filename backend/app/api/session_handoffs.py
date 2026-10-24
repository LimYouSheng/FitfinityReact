"""Legacy opening evidence only; the current PDF UI never calls this compatibility action."""

import hashlib
import json
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import Field, StrictStr
from sqlalchemy import func, select, text

from app.api.request_cancellation import DECISION_LOCK
from app.api.schemas import Contract
from app.api.session_mutation_journal import journal
from app.api.session_summaries import inspect as summary_scope
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import SessionHandoffReceipt
from app.models.communications import Message, MessageReceipt, SessionEvent
from app.models.people import StaffUser


class MarkHandoff(Contract):
    expected: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class HandoffReview(Contract):
    sessionId: UUID
    version: int
    expected: str
    whatsappOpenedAt: datetime | None
    whatsappOpenCount: int


class HandoffSaved(Contract):
    sessionId: UUID
    version: int
    whatsappOpenedAt: datetime
    whatsappOpenCount: int


def inspect(session, principal, identity):
    """Retain current write scope and reject Open/future dates using the database clock."""
    base, booking = summary_scope(session, principal, identity)
    today = session.scalar(text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date"))
    if booking.training_date is None or booking.training_date > today:
        raise conflict()
    expected = hashlib.sha256(json.dumps([base.expected, str(today)]).encode()).hexdigest()
    return HandoffReview(
        sessionId=identity,
        version=booking.version,
        expected=expected,
        whatsappOpenedAt=booking.whatsapp_opened_at,
        whatsappOpenCount=booking.whatsapp_open_count,
    ), booking


def review(session, principal, identity):
    return inspect(session, principal, identity)[0]


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": DECISION_LOCK})
    return session.scalar(
        select(SessionHandoffReceipt).where(
            SessionHandoffReceipt.actor_id == principal.user_id,
            SessionHandoffReceipt.request_key == key,
        )
    )


def reconcile(session, principal, key):
    found = receipt(session, principal, key)
    if found is None:
        raise unavailable()
    return HandoffSaved.model_validate(found.result)


@journal("session.handoff")
def save(session, principal, identity, key, body):
    """Commit one opening and its receipt, without delivery, completion or credit effects."""
    found = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps(
            {"session": str(identity), **body.model_dump(mode="json")}, sort_keys=True
        ).encode()
    ).hexdigest()
    if found:
        if found.request_sha256 != digest:
            raise AuthError(
                "idempotency_conflict", "This key belongs to another opening action.", 409
            )
        return HandoffSaved.model_validate(found.result)
    viewed, booking = inspect(session, principal, identity)
    if body.expected != viewed.expected:
        raise conflict()
    booking.whatsapp_opened_at = session.scalar(select(func.clock_timestamp()))
    booking.whatsapp_open_count += 1
    booking.version += 1
    session.add(
        SessionEvent(
            session_id=identity,
            session_version=viewed.version,
            kind="whatsapp_opened",
            note="Legacy WhatsApp opening recorded; delivery is not verified.",
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    saved = HandoffSaved(
        sessionId=identity,
        version=booking.version,
        whatsappOpenedAt=booking.whatsapp_opened_at,
        whatsappOpenCount=booking.whatsapp_open_count,
    )
    notice = Message(
        id=uuid4(),
        kind="session_update",
        title="Session opening recorded",
        body="Legacy WhatsApp opening recorded; delivery is not verified.",
        session_id=identity,
        client_id=booking.client_id,
        trainer_id=booking.trainer_id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    for user_id in session.scalars(
        select(StaffUser.id).where(
            StaffUser.status == "active",
            (StaffUser.role == "owner") | (StaffUser.id == principal.user_id),
        )
    ):
        session.add(MessageReceipt(message_id=notice.id, user_id=user_id))
    session.add(
        SessionHandoffReceipt(
            message_id=notice.id,
            request_key=key,
            request_sha256=digest,
            session_id=identity,
            previous=viewed.model_dump(mode="json"),
            result=saved.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    return saved
