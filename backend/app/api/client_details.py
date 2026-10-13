"""Owner/Admin personal edits and approved general notes; never accept assessment answers."""

import hashlib
import json
import re
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictInt, StrictStr, field_validator, model_validator
from sqlalchemy import or_, select, text

from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import client_write, conflict, unavailable
from app.models.api import ClientDetailReceipt
from app.models.communications import Message, MessageReceipt
from app.models.people import ClientPerson, StaffUser, Trainer

Country = Literal["+65", "+60", "+62", "+63", "+66", "+84", "+86", "+91", "+44", "+61"]


class Phone(Contract):
    countryCode: Country
    number: StrictStr = Field(max_length=32)

    @model_validator(mode="after")
    def valid_phone(self):
        self.number = self.number.strip()
        digits = re.sub(r"\D", "", self.number)
        if self.number and (
            not re.fullmatch(r"[\d\s()-]+", self.number)
            or len(digits) < 6
            or len(self.countryCode) - 1 + len(digits) > 15
        ):
            raise ValueError("Enter a valid phone number")
        return self


class Emergency(Phone):
    name: StrictStr = Field(max_length=200)
    relationship: Literal[
        "", "Spouse", "Parent", "Sibling", "Child", "Partner", "Friend", "Guardian", "Other"
    ]


class PersonDetails(Contract):
    id: UUID
    expectedVersion: StrictInt = Field(ge=1)
    name: StrictStr = Field(min_length=1, max_length=200)
    email: StrictStr = Field(max_length=320)
    healthNotes: StrictStr | None = Field(default=None, max_length=10000)
    birthday: date | None
    gender: Literal["", "Female", "Male", "Other", "Prefer not to say"]
    phone: Phone
    emergencyContact: Emergency

    @field_validator("name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("A name is required")
        return value.strip()

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        value = value.strip().lower()
        if value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("birthday", mode="before")
    @classmethod
    def exact_date(cls, value):
        if value is None or value == "":
            return None
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("A calendar date is required")
        return value


class SaveClientDetails(Contract):
    expectedVersion: StrictInt = Field(ge=1)
    people: list[PersonDetails] = Field(min_length=1, max_length=2)
    remarks: StrictStr = Field(max_length=10000)
    genderPreference: Literal[
        "No gender preference", "Female trainer preferred", "Male trainer preferred"
    ]


class PersonVersion(Contract):
    id: UUID
    version: int


class ClientDetailState(Contract):
    id: UUID
    version: int
    people: list[PersonVersion]


def receipt(session, principal, key):
    principal.operations()
    session.execute(text("SELECT pg_advisory_xact_lock(714602033)"))
    return session.scalar(
        select(ClientDetailReceipt).where(
            ClientDetailReceipt.actor_id == principal.user_id,
            ClientDetailReceipt.request_key == key,
        )
    )


def reconcile(session, principal, key):
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return ClientDetailState.model_validate(saved.result)


def save(session, principal, client_id, key, body):
    previous = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps(
            {"id": str(client_id), **body.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    if previous:
        if previous.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Review this request before retrying.", 409)
        return ClientDetailState.model_validate(previous.result)
    client = client_write(session, principal, client_id)
    people = session.scalars(
        select(ClientPerson)
        .where(ClientPerson.client_id == client_id)
        .order_by(ClientPerson.position)
        .with_for_update()
    ).all()
    if (
        client.version != body.expectedVersion
        or len(people) != (2 if client.kind == "couple" else 1)
        or len(body.people) != len(people)
        or any(
            p.id != draft.id or p.version != draft.expectedVersion
            for p, draft in zip(people, body.people, strict=True)
        )
    ):
        raise conflict()
    notes_changed = False
    for person, draft in zip(people, body.people, strict=True):
        if draft.healthNotes is not None and draft.healthNotes.strip() != person.health_notes:
            person.health_notes = draft.healthNotes.strip()
            notes_changed = True
        person.name, person.email = draft.name, draft.email
        person.birthday, person.gender = draft.birthday, draft.gender
        person.phone_country_code, person.phone_number = draft.phone.countryCode, draft.phone.number
        person.emergency_name = draft.emergencyContact.name.strip()
        person.emergency_relationship = draft.emergencyContact.relationship
        person.emergency_country_code = draft.emergencyContact.countryCode
        person.emergency_number = draft.emergencyContact.number
        person.version += 1
    if notes_changed:
        client.health_notes = "\n".join(
            f"{p.name}: {p.health_notes}" if client.kind == "couple" else p.health_notes
            for p in people
            if p.health_notes
        )
        from app.api.client_notes import audit

        audit(session, principal, client.id, "save")
    client.name = " & ".join(p.name for p in people)
    if len(client.name) > 400:
        raise AuthError("invalid_request", "The combined client name is too long.", 422)
    client.remarks = body.remarks
    client.gender_preference = {
        "No gender preference": "any",
        "Female trainer preferred": "female",
        "Male trainer preferred": "male",
    }[body.genderPreference]
    client.version += 1
    session.flush()
    result = ClientDetailState(
        id=client.id,
        version=client.version,
        people=[PersonVersion(id=p.id, version=p.version) for p in people],
    )
    session.add(
        ClientDetailReceipt(
            request_key=key,
            request_sha256=digest,
            client_id=client.id,
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    notify_saved(
        session, principal, client, "Updated personal information, remarks and gender preference."
    )
    return result


def notify_saved(session, principal, client, body):
    notice = Message(
        kind="saved_edit",
        title=f"Client details saved: {client.name}",
        body=body,
        client_id=client.id,
        trainer_id=client.trainer_id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    trainer_user_id = session.scalar(select(Trainer.user_id).where(Trainer.id == client.trainer_id))
    for user_id in session.scalars(
        select(StaffUser.id).where(
            StaffUser.status == "active",
            or_(StaffUser.role == "owner", StaffUser.id == trainer_user_id),
        )
    ):
        session.add(MessageReceipt(message_id=notice.id, user_id=user_id))
