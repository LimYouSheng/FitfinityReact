"""Atomic client, people, assessments and first purchased schedule creation."""

import hashlib
import json
import re
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictInt, StrictStr, field_validator, model_validator
from sqlalchemy import select, text

from app.api.admin_supervision import supervised, supervised_recovery
from app.api.assessments import audit, safe_answers
from app.api.client_details import Emergency, Phone
from app.api.client_matching import MatchedSlot, MatchRequest
from app.api.purchase_creation import persist_purchase, prepare_purchase
from app.api.schemas import Contract
from app.assessment_persistence import create_assessment, save_assessment
from app.auth.errors import AuthError
from app.authorization import unavailable
from app.models.api import ClientCreateReceipt
from app.models.communications import Message, MessageReceipt
from app.models.people import Client, ClientPerson, StaffUser
from app.persistence import add_client


class InitialAssessment(Contract):
    formId: StrictStr
    formVersion: StrictInt = Field(ge=1)
    assessmentDate: date
    answers: dict

    @field_validator("assessmentDate", mode="before")
    @classmethod
    def calendar_date(cls, value):
        return MatchRequest.calendar_date(value)


class NewPerson(Contract):
    name: StrictStr = Field(min_length=1, max_length=200)
    email: StrictStr = Field(min_length=1, max_length=320)
    phone: Phone
    birthday: date
    gender: Literal["Female", "Male", "Other", "Prefer not to say"]
    emergencyContact: Emergency
    healthNotes: StrictStr = Field(max_length=10000)
    assessments: list[InitialAssessment] = Field(max_length=11)

    @field_validator("birthday", mode="before")
    @classmethod
    def calendar_date(cls, value):
        return MatchRequest.calendar_date(value)

    @model_validator(mode="after")
    def complete_person(self):
        self.name, self.email = self.name.strip(), self.email.strip().lower()
        if not self.name or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", self.email):
            raise ValueError("Complete the client name and email")
        if (
            not self.phone.number
            or not self.emergencyContact.number
            or not self.emergencyContact.name.strip()
            or not self.emergencyContact.relationship
        ):
            raise ValueError("Complete the client phone and emergency contact")
        if len({a.formId for a in self.assessments}) != len(self.assessments):
            raise ValueError("Review each assessment once")
        return self


class CreateClient(MatchRequest):
    type: Literal["Individual", "Couple"]
    people: list[NewPerson] = Field(min_length=1, max_length=2)
    trainerId: UUID
    trainerVersion: StrictInt = Field(ge=1)
    fixedWeeklySchedule: list[MatchedSlot] = Field(min_length=1, max_length=7)
    remarks: StrictStr = Field(max_length=10000)

    @model_validator(mode="after")
    def people_and_cadence(self):
        if len(self.people) != (2 if self.type == "Couple" else 1):
            raise ValueError("Review every person's details")
        if len(self.fixedWeeklySchedule) != self.sessionsPerWeek:
            raise ValueError("Review the complete weekly cadence")
        return self


class CreatedClient(Contract):
    id: UUID
    version: int
    purchaseId: UUID


def receipt(session, principal, key):
    principal.operations()
    session.execute(text("SELECT pg_advisory_xact_lock(714602038)"))
    return session.scalar(
        select(ClientCreateReceipt).where(
            ClientCreateReceipt.actor_id == principal.user_id,
            ClientCreateReceipt.request_key == key,
        )
    )


@supervised_recovery("client.create")
def reconcile(session, principal, key):
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return CreatedClient.model_validate(saved.result)


@supervised("clientCreation", "client.create", CreateClient, receipt=receipt, target=False)
@safe_answers
def create(session, principal, key, body):
    previous = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps(
            body.model_dump(mode="json", by_alias=True), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    if previous:
        if previous.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Review this request before retrying.", 409)
        return CreatedClient.model_validate(previous.result)
    prepared = prepare_purchase(session, body)
    trainer, gender_preference = prepared.trainer, prepared.gender_preference
    people = [
        ClientPerson(
            name=p.name,
            email=p.email,
            birthday=p.birthday,
            gender=p.gender,
            phone_country_code=p.phone.countryCode,
            phone_number=p.phone.number,
            emergency_name=p.emergencyContact.name.strip(),
            emergency_relationship=p.emergencyContact.relationship,
            emergency_country_code=p.emergencyContact.countryCode,
            emergency_number=p.emergencyContact.number,
            health_notes=p.healthNotes.strip(),
        )
        for p in body.people
    ]
    client = add_client(
        session,
        Client(
            kind="couple" if body.type == "Couple" else "individual",
            name=" & ".join(p.name for p in people),
            trainer_id=trainer.id,
            gender_preference=gender_preference,
            remarks=body.remarks.strip(),
        ),
        people,
    )
    purchase = persist_purchase(session, client, body, prepared, stage="current")
    for person, draft in zip(people, body.people, strict=True):
        for assessment in draft.assessments:
            revision = create_assessment(
                session,
                person.id,
                assessment.formId,
                assessment.formVersion,
                principal.user_id,
                assessment.assessmentDate,
                assessment.answers,
            )
            save_assessment(
                session,
                revision.assessment_id,
                revision.revision,
                principal.user_id,
                assessment.assessmentDate,
                assessment.answers,
                event="completed",
            )
            audit(session, principal, person.id, "create", revision.assessment_id)
    notify_created(session, principal, client, trainer, purchase)
    result = CreatedClient(id=client.id, version=client.version, purchaseId=purchase.id)
    session.add(
        ClientCreateReceipt(
            request_key=key,
            request_sha256=digest,
            client_id=client.id,
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    return result


def notify_created(session, principal, client, trainer, purchase):
    owners = session.scalars(
        select(StaffUser.id).where(StaffUser.role == "owner", StaffUser.status == "active")
    ).all()
    for kind, title, body, recipients in (
        (
            "client_created",
            f"New client created: {client.name}",
            f"{trainer.name} is assigned to {client.name}. "
            f"{purchase.total_sessions} sessions were created with "
            f"{purchase.validity_days}-day validity.",
            owners,
        ),
        (
            "client_assignment",
            f"New client assigned: {client.name}",
            f"{client.name} has been added to your active client list.",
            [trainer.user_id] if trainer.user_id else [],
        ),
    ):
        notice = Message(
            kind=kind,
            title=title,
            body=body,
            client_id=client.id,
            trainer_id=trainer.id,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
        session.add(notice)
        session.flush()
        for user_id in recipients:
            session.add(MessageReceipt(message_id=notice.id, user_id=user_id))
    if purchase.total_sessions == 2:
        notice = Message(
            kind="renewal",
            title=f"Renewal follow-up: {client.name}",
            body=f"{client.name} is approaching package renewal. "
            "0/2 sessions used · 2 sessions remaining.",
            client_id=client.id,
            purchase_id=purchase.id,
            trainer_id=trainer.id,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
        session.add(notice)
        session.flush()
        for user_id in set(owners + ([trainer.user_id] if trainer.user_id else [])):
            session.add(MessageReceipt(message_id=notice.id, user_id=user_id))
