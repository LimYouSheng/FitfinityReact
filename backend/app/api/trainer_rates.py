"""Owner-only reviewed pay rates with immutable before/after evidence."""

import hashlib
import json
from uuid import UUID

from pydantic import Field, StrictInt
from sqlalchemy import or_, select, text

from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import TrainerRateReceipt
from app.models.communications import Message, MessageReceipt
from app.models.people import StaffUser, Trainer

FIELDS = {"peak": "peak_rate_cents", "offPeak": "off_peak_rate_cents"}


class RateValues(Contract):
    peak: StrictInt = Field(ge=0, le=9007199254740991)
    offPeak: StrictInt = Field(ge=0, le=9007199254740991)


class SaveRates(Contract):
    expectedVersion: StrictInt = Field(ge=1)
    rates: RateValues


class RateState(Contract):
    id: UUID
    version: StrictInt = Field(ge=1)


def receipt(session, principal, key):
    principal.owner()
    # Receipt lookup must serialize with commit even before a new receipt exists.
    session.execute(text("SELECT pg_advisory_xact_lock(714602035)"))
    return session.scalar(
        select(TrainerRateReceipt).where(
            TrainerRateReceipt.actor_id == principal.user_id,
            TrainerRateReceipt.request_key == key,
        )
    )


def reconcile(session, principal, key):
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return RateState.model_validate(saved.result)


def save(session, principal, trainer_id, key, body):
    previous = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps(
            {"id": str(trainer_id), **body.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    if previous:
        if previous.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Review this request before retrying.", 409)
        return RateState.model_validate(previous.result)
    trainer = session.scalar(select(Trainer).where(Trainer.id == trainer_id).with_for_update())
    if trainer is None:
        raise unavailable()
    if trainer.version != body.expectedVersion:
        raise conflict()
    before = {field: getattr(trainer, column) for field, column in FIELDS.items()}
    for field, column in FIELDS.items():
        setattr(trainer, column, getattr(body.rates, field))
    trainer.version += 1
    session.flush()
    result = RateState(id=trainer.id, version=trainer.version)
    session.add(
        TrainerRateReceipt(
            request_key=key,
            request_sha256=digest,
            trainer_id=trainer.id,
            previous=before,
            rates=body.rates.model_dump(),
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    notice = Message(
        kind="trainer_rates",
        title=f"Trainer rates saved: {trainer.name}",
        body="The trainer session rates were updated.",
        trainer_id=trainer.id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    for user_id in session.scalars(
        select(StaffUser.id).where(
            StaffUser.status == "active",
            or_(StaffUser.role == "owner", StaffUser.id == trainer.user_id),
        )
    ):
        session.add(MessageReceipt(message_id=notice.id, user_id=user_id))
    return result
