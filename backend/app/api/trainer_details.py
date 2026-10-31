"""Versioned trainer profiles; email, rates, status and approvals retain dedicated commands."""

import hashlib
import json
import re
from datetime import date
from typing import Literal

from pydantic import Field, StrictInt, StrictStr, field_validator, model_validator
from sqlalchemy import or_, select, text

from app.api.admin_supervision import supervised, supervised_recovery
from app.api.client_details import Phone
from app.api.schemas import Contract
from app.api.trainer_rates import RateState
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import TrainerDetailReceipt
from app.models.communications import Message, MessageReceipt
from app.models.people import StaffUser, Trainer


class TrainerProfilePatch(Contract):
    name: StrictStr | None = Field(default=None, min_length=1, max_length=200)
    phone: Phone | None = None
    birthday: date | None = None
    gender: Literal["Female", "Male", "Other", "Prefer not to say"] | None = None
    trainerType: StrictStr | None = Field(default=None, min_length=1, max_length=120)
    qualifications: StrictStr | None = Field(default=None, max_length=10000)
    publicProfile: Literal["Visible", "Hidden"] | None = None

    @field_validator("name", "trainerType")
    @classmethod
    def nonblank(cls, value):
        if value is None or not value.strip():
            raise ValueError("A nonblank value is required")
        return value.strip()

    @field_validator("birthday", mode="before")
    @classmethod
    def exact_date(cls, value):
        if value is None or value == "":
            return None
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("A calendar date is required")
        return value

    @model_validator(mode="after")
    def supplied_fields(self):
        if not self.model_fields_set or any(
            field != "birthday" and getattr(self, field) is None for field in self.model_fields_set
        ):
            raise ValueError("Supply valid profile fields")
        return self


class SaveTrainerDetails(Contract):
    expectedVersion: StrictInt = Field(ge=1)
    patch: TrainerProfilePatch


def allowed(principal, trainer_id, *, name=False):
    if not principal.manages_operations and (
        principal.role != "trainer" or principal.trainer_id != trainer_id or name
    ):
        raise AuthError("forbidden", "This trainer profile change is unavailable.", 403)


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(714602037)"))
    return receipt_probe(session, principal, key)


def receipt_probe(session, principal, key):
    """Read under the Admin barrier without reversing the target-row lock order."""
    return session.scalar(
        select(TrainerDetailReceipt).where(
            TrainerDetailReceipt.actor_id == principal.user_id,
            TrainerDetailReceipt.request_key == key,
        )
    )


@supervised_recovery("trainer.details")
def reconcile(session, principal, key):
    previous = receipt(session, principal, key)
    if previous is None:
        raise unavailable()
    allowed(principal, previous.trainer_id)
    return RateState.model_validate(previous.result)


@supervised(
    "trainerDetails",
    "trainer.details",
    SaveTrainerDetails,
    receipt=receipt_probe,
    target="trainer_id",
)
def save(session, principal, trainer_id, key, body):
    allowed(principal, trainer_id, name="name" in body.patch.model_fields_set)
    # Match authentication/email writers' user -> trainer -> command-lock order.
    user_id = session.scalar(select(Trainer.user_id).where(Trainer.id == trainer_id))
    user = session.scalar(select(StaffUser).where(StaffUser.id == user_id).with_for_update())
    trainer = session.scalar(select(Trainer).where(Trainer.id == trainer_id).with_for_update())
    if trainer is None:
        raise unavailable()
    if not principal.manages_operations and trainer.status != "active":
        raise conflict()
    previous = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps(
            {"id": str(trainer_id), **body.model_dump(mode="json", exclude_unset=True)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    if previous:
        if previous.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Review this request before retrying.", 409)
        return RateState.model_validate(previous.result)
    if trainer.version != body.expectedVersion:
        raise conflict()
    patch = body.patch
    for field in patch.model_fields_set:
        value = getattr(patch, field)
        if field == "phone":
            trainer.phone_country_code, trainer.phone_number = value.countryCode, value.number
        elif field == "publicProfile":
            trainer.public_profile = value == "Visible"
        elif field == "trainerType":
            trainer.trainer_type = value
        else:
            setattr(trainer, field, value.strip() if field == "qualifications" else value)
    if "name" in patch.model_fields_set and user:
        user.name = patch.name
    trainer.version += 1
    session.flush()
    result = RateState(id=trainer.id, version=trainer.version)
    session.add(
        TrainerDetailReceipt(
            request_key=key,
            request_sha256=digest,
            trainer_id=trainer.id,
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    notice = Message(
        kind="saved_edit",
        title=f"Trainer details saved: {trainer.name}",
        body="Updated trainer profile information.",
        trainer_id=trainer.id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    for recipient in session.scalars(
        select(StaffUser.id).where(
            StaffUser.status == "active",
            or_(StaffUser.role == "owner", StaffUser.id == trainer.user_id),
        )
    ):
        session.add(MessageReceipt(message_id=notice.id, user_id=recipient))
    return result
