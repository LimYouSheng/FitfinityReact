"""Atomic reviewed completion, permanent signatures and exactly-once package credits."""

import hashlib
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictStr, model_validator
from sqlalchemy import func, select, text

from app.api import session_outcomes
from app.api.admin_supervision import supervised, supervised_recovery
from app.api.renewal_policy import usable_purchase
from app.api.request_cancellation import DECISION_LOCK
from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import SessionAcknowledgementReceipt
from app.models.communications import Message, MessageReceipt, SessionEvent
from app.models.people import Client, StaffUser, Trainer
from app.models.training import Acknowledgement, CreditDebit, ExerciseResult, PackagePurchase
from app.persistence import acknowledge, signature_evidence


class SaveAcknowledgement(Contract):
    expected: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    method: Literal["signature", "late_no_show"]
    signerName: StrictStr | None = Field(default=None, max_length=200)
    signature: list | None = None
    note: StrictStr = Field(default="", max_length=10000)

    @model_validator(mode="after")
    def evidence(self):
        self.note = self.note.strip()
        if self.method == "signature":
            if not self.signerName or not self.signerName.strip():
                raise ValueError("Enter the signer name")
            self.signerName = self.signerName.strip()
            signature_evidence(self.signature)
        elif self.signerName is not None or self.signature is not None:
            raise ValueError("No-show acknowledgement cannot contain a client signature")
        return self


class AcknowledgementReview(Contract):
    sessionId: UUID
    version: int
    expected: str
    previousMethod: Literal["late_no_show"] | None
    used: int
    total: int


class AcknowledgementSaved(Contract):
    sessionId: UUID
    version: int
    acknowledgementId: UUID
    method: Literal["signature", "late_no_show"]
    sequence: int
    used: int
    savedAt: datetime


def inspect(session, principal, identity):
    """Lock current scope and bind completion to the reviewed plan, results and credit balance."""
    outcome, booking, _, results = session_outcomes.inspect(session, principal, identity)
    today = session.scalar(text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date"))
    previous = session.scalar(
        select(Acknowledgement)
        .where(Acknowledgement.session_id == identity)
        .order_by(Acknowledgement.sequence.desc())
        .limit(1)
    )
    if (
        booking.schedule_state == "open"
        or booking.training_date > today
        or booking.status == "cancelled"
        or (previous and previous.method == "signature")
    ):
        raise conflict()
    purchase = session.get(PackagePurchase, booking.purchase_id)
    used = session.scalar(
        select(func.count()).select_from(CreditDebit).where(CreditDebit.purchase_id == purchase.id)
    )
    if not previous and used >= purchase.total_sessions:
        raise conflict()
    expected = hashlib.sha256(
        json.dumps(
            [
                outcome.expected,
                str(today),
                str(previous.id) if previous else None,
                used,
            ]
        ).encode()
    ).hexdigest()
    return (
        AcknowledgementReview(
            sessionId=identity,
            version=booking.version,
            expected=expected,
            previousMethod=previous.method if previous else None,
            used=used,
            total=purchase.total_sessions,
        ),
        booking,
        outcome,
        results,
    )


def review(session, principal, identity):
    return inspect(session, principal, identity)[0]


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": DECISION_LOCK})
    return session.scalar(
        select(SessionAcknowledgementReceipt).where(
            SessionAcknowledgementReceipt.actor_id == principal.user_id,
            SessionAcknowledgementReceipt.request_key == key,
        )
    )


@supervised_recovery("session.acknowledge")
def reconcile(session, principal, key):
    found = receipt(session, principal, key)
    if found is None:
        raise unavailable()
    return AcknowledgementSaved.model_validate(found.result)


def notify_renewal(session, principal, booking, used):
    """The retained two-credit policy creates one purchase notice, never external delivery."""
    purchase = session.get(PackagePurchase, booking.purchase_id)
    if purchase.total_sessions - used != 2:
        return
    if session.scalar(
        select(Message.id)
        .where(Message.kind == "renewal", Message.purchase_id == purchase.id)
        .limit(1)
    ):
        return
    if session.scalar(
        select(PackagePurchase.id)
        .where(
            PackagePurchase.client_id == purchase.client_id,
            PackagePurchase.id != purchase.id,
            usable_purchase(),
        )
        .limit(1)
    ):
        return
    client = session.get(Client, booking.client_id)
    trainer = session.get(Trainer, client.trainer_id)
    notice = Message(
        kind="renewal",
        title=f"Renewal follow-up: {client.name}",
        body=f"{client.name} is approaching package renewal. "
        f"{used}/{purchase.total_sessions} sessions used · 2 sessions remaining.",
        client_id=client.id,
        purchase_id=purchase.id,
        trainer_id=trainer.id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    owners = set(
        session.scalars(
            select(StaffUser.id).where(StaffUser.role == "owner", StaffUser.status == "active")
        )
    )
    if trainer.user_id:
        owners.add(trainer.user_id)
    for user_id in owners:
        session.add(MessageReceipt(message_id=notice.id, user_id=user_id))


@supervised(
    "sessionAcknowledgement",
    "session.acknowledge",
    SaveAcknowledgement,
    receipt=receipt,
    target="identity",
)
def save(session, principal, identity, key, body):
    """A receipt failure rolls back signature, measurements, credit, notice and completion."""
    found = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps(
            {"session": str(identity), **body.model_dump(mode="json")}, sort_keys=True
        ).encode()
    ).hexdigest()
    if found:
        if found.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "This key belongs to another completion.", 409)
        return AcknowledgementSaved.model_validate(found.result)
    viewed, booking, outcome, results = inspect(session, principal, identity)
    if viewed.expected != body.expected:
        raise conflict()
    if viewed.previousMethod and body.method != "signature":
        raise conflict()
    # Draft rows already suppress prescription fallback after any explicitly saved outcome.
    if body.method == "signature" and not results:
        for row in outcome.draftRows:
            if row.loadKg is not None and row.reps is not None and row.sets is not None:
                session.add(
                    ExerciseResult(
                        session_id=identity,
                        plan_item_id=row.planItemId,
                        name=row.name,
                        load_kg=row.loadKg,
                        reps=row.reps,
                        sets=row.sets,
                    )
                )
    evidence = acknowledge(
        session,
        identity,
        booking.version,
        principal.user_id,
        method=body.method,
        signer_name=body.signerName,
        strokes=body.signature,
        note=body.note,
    )
    used = viewed.used + (0 if viewed.previousMethod else 1)
    notify_renewal(session, principal, booking, used)
    session.add(
        SessionEvent(
            session_id=identity,
            session_version=viewed.version,
            kind="session_acknowledgement",
            note="Session acknowledgement saved.",
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    result = AcknowledgementSaved(
        sessionId=identity,
        version=booking.version,
        acknowledgementId=evidence.id,
        method=evidence.method,
        sequence=evidence.sequence,
        used=used,
        savedAt=evidence.created_at,
    )
    session.add(
        SessionAcknowledgementReceipt(
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
