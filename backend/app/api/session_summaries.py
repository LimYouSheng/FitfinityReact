"""Reviewed client-facing text, independent of completion, credits and delivery claims."""

import hashlib
import json
from datetime import datetime
from uuid import UUID

from pydantic import Field, StrictStr, field_validator
from sqlalchemy import func, select, text

from app.api.admin_supervision import supervised, supervised_recovery
from app.api.request_cancellation import DECISION_LOCK
from app.api.schemas import Contract
from app.api.session_mutation_journal import journal
from app.auth.errors import AuthError
from app.authorization import conflict, session_record, unavailable
from app.models.api import SessionSummaryReceipt
from app.models.communications import SessionEvent
from app.models.people import Client
from app.models.training import PackagePurchase


class SaveSummary(Contract):
    expected: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    summary: StrictStr = Field(min_length=1, max_length=20000)

    @field_validator("summary")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Enter a client-facing summary")
        return value.strip()


class SummaryReview(Contract):
    sessionId: UUID
    version: int
    expected: str
    summary: str


class SummarySaved(Contract):
    sessionId: UUID
    version: int
    summary: str
    savedAt: datetime


def inspect(session, principal, identity):
    """Bind text to current session, assignment and purchase lifecycle versions."""
    booking = session_record(session, principal, identity, write=True, allow_final_notes=True)
    client = session.get(Client, booking.client_id)
    purchase = session.get(PackagePurchase, booking.purchase_id)
    expected = hashlib.sha256(
        json.dumps(
            [
                str(booking.id),
                booking.version,
                str(booking.trainer_id),
                str(client.id),
                client.version,
                str(purchase.id),
                purchase.version,
            ]
        ).encode()
    ).hexdigest()
    return SummaryReview(
        sessionId=identity,
        version=booking.version,
        expected=expected,
        summary=booking.client_summary,
    ), booking


def review(session, principal, identity):
    return inspect(session, principal, identity)[0]


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": DECISION_LOCK})
    return session.scalar(
        select(SessionSummaryReceipt).where(
            SessionSummaryReceipt.actor_id == principal.user_id,
            SessionSummaryReceipt.request_key == key,
        )
    )


@supervised_recovery("session.summary")
def reconcile(session, principal, key):
    found = receipt(session, principal, key)
    if found is None:
        raise unavailable()
    return SummarySaved.model_validate(found.result)


@supervised("sessionContent", "session.summary", SaveSummary, receipt=receipt, target="identity")
@journal("session.summary")
def save(session, principal, identity, key, body):
    """Commit text, prior-value audit and private retry receipt together, with no handoff effect."""
    found = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps(
            {"session": str(identity), **body.model_dump(mode="json")}, sort_keys=True
        ).encode()
    ).hexdigest()
    if found:
        if found.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "This key belongs to another summary.", 409)
        return SummarySaved.model_validate(found.result)
    viewed, booking = inspect(session, principal, identity)
    if body.expected != viewed.expected:
        raise conflict()
    now = session.scalar(select(func.clock_timestamp()))
    booking.client_summary = body.summary
    booking.version += 1
    session.add(
        SessionEvent(
            session_id=identity,
            session_version=viewed.version,
            kind="session_summary",
            note="Client-facing summary saved.",
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    result = SummarySaved(
        sessionId=identity, version=booking.version, summary=booking.client_summary, savedAt=now
    )
    session.add(
        SessionSummaryReceipt(
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
