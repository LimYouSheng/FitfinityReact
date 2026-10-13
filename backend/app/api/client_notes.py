"""General coaching notes are separate from restricted assessment forms/answers."""

import hashlib
import json
from uuid import UUID

from pydantic import Field, StrictInt, StrictStr, model_validator
from sqlalchemy import select, text

from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import ClientNoteAccess, ClientNoteReceipt
from app.models.people import Client, ClientPerson


class NotePatch(Contract):
    remarks: StrictStr | None = Field(default=None, max_length=10000)
    healthNotes: StrictStr | None = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def explicit_values(self):
        if not self.model_fields_set or any(
            getattr(self, field) is None for field in self.model_fields_set
        ):
            raise ValueError("Supply the note fields being changed")
        return self


class SaveNotes(Contract):
    expectedVersion: StrictInt = Field(ge=1)
    patch: NotePatch


class NoteState(Contract):
    id: UUID
    version: int


class PersonNote(NoteState):
    healthNotes: str


class NoteView(NoteState):
    remarks: str
    healthNotes: str
    people: list[PersonNote]


def record(session, principal, client_id, *, write=False):
    query = select(Client).where(Client.id == client_id)
    if not principal.manages_operations:
        query = query.where(Client.trainer_id == principal.trainer_id)
    client = session.scalar(query.with_for_update(read=not write))
    if client is None:
        raise unavailable()
    if write and client.status != "active":
        raise conflict()
    return client


def audit(session, principal, client_id, action):
    session.add(
        ClientNoteAccess(
            client_id=client_id,
            action=action,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )


def view(session, principal, client_id):
    client = record(session, principal, client_id)
    people = session.scalars(
        select(ClientPerson)
        .where(ClientPerson.client_id == client.id)
        .order_by(ClientPerson.position)
        .with_for_update(read=True)
    ).all()
    notes = client.health_notes
    if notes is None:
        notes = "\n".join(
            f"{p.name}: {p.health_notes}" if client.kind == "couple" else p.health_notes
            for p in people
            if p.health_notes
        )
    audit(session, principal, client.id, "view")
    return NoteView(
        id=client.id,
        version=client.version,
        remarks=client.remarks,
        healthNotes=notes,
        people=[PersonNote(id=p.id, version=p.version, healthNotes=p.health_notes) for p in people],
    )


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(714602034)"))
    return session.scalar(
        select(ClientNoteReceipt).where(
            ClientNoteReceipt.actor_id == principal.user_id,
            ClientNoteReceipt.request_key == key,
        )
    )


def reconcile(session, principal, key):
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    record(session, principal, saved.client_id, write=True)
    audit(session, principal, saved.client_id, "replay")
    return NoteState.model_validate(saved.result)


def save(session, principal, client_id, key, body):
    previous = receipt(session, principal, key)
    client = record(session, principal, client_id, write=True)
    digest = hashlib.sha256(
        json.dumps(
            {"id": str(client_id), **body.model_dump(mode="json", exclude_unset=True)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    if previous:
        if previous.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Review this request before retrying.", 409)
        audit(session, principal, client.id, "replay")
        return NoteState.model_validate(previous.result)
    if client.version != body.expectedVersion:
        raise conflict()
    person = None
    if "healthNotes" in body.patch.model_fields_set and client.kind == "individual":
        person = session.scalar(
            select(ClientPerson).where(ClientPerson.client_id == client.id).with_for_update()
        )
        if person is None:
            raise conflict()
    if "remarks" in body.patch.model_fields_set:
        client.remarks = body.patch.remarks
    if "healthNotes" in body.patch.model_fields_set:
        client.health_notes = body.patch.healthNotes.strip()
        if person is not None:
            person.health_notes = client.health_notes
            person.version += 1
    client.version += 1
    result = NoteState(id=client.id, version=client.version)
    session.add(
        ClientNoteReceipt(
            request_key=key,
            request_sha256=digest,
            client_id=client.id,
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    audit(session, principal, client.id, "save")
    from app.api.client_details import notify_saved

    notify_saved(session, principal, client, "Updated general coaching notes.")
    return result
