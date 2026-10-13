"""Staff-only content records; saving a ready record never publishes a public page."""

import hashlib
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictInt, StrictStr, field_validator, model_validator
from sqlalchemy import select, text

from app.api.directory import bounded
from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import ContentSaveReceipt
from app.models.communications import Message, MessageReceipt
from app.models.media import ContentEntry
from app.models.people import StaffUser


class ContentDraft(Contract):
    key: StrictStr = Field(max_length=120, pattern=r"^[a-z0-9]+(?:[-/][a-z0-9]+)*$")
    title: StrictStr = Field(min_length=1, max_length=180)
    body: StrictStr = Field(min_length=1, max_length=20000)
    status: Literal["draft", "ready", "archived"]

    @field_validator("title", "body")
    @classmethod
    def required_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Content title and body are required")
        return value


class ContentState(ContentDraft):
    id: UUID
    version: StrictInt = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class SaveContent(Contract):
    id: UUID | None = None
    expectedVersion: StrictInt | None = Field(default=None, ge=1)
    draft: ContentDraft

    @model_validator(mode="after")
    def reviewed_update(self):
        if (self.id is None) != (self.expectedVersion is None):
            raise ValueError("An update requires its reviewed version")
        return self


def content_lock(session, principal):
    principal.operations()
    # Serializes unique-key claims across actors and uncertain-save reconciliation.
    session.execute(text("SELECT pg_advisory_xact_lock(714602040)"))


def records(session, principal):
    principal.operations()
    return [
        ContentState.model_validate(row)
        for row in bounded(
            session, select(ContentEntry).order_by(ContentEntry.created_at.desc(), ContentEntry.id)
        )
    ]


def receipt(session, principal, key):
    content_lock(session, principal)
    return session.scalar(
        select(ContentSaveReceipt).where(
            ContentSaveReceipt.actor_id == principal.user_id,
            ContentSaveReceipt.request_key == key,
        )
    )


def reconcile(session, principal, key):
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return ContentState.model_validate(saved.result)


def save(session, principal, key, body):
    saved = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Review this request before retrying.", 409)
        return ContentState.model_validate(saved.result)
    current = (
        session.scalar(select(ContentEntry).where(ContentEntry.id == body.id).with_for_update())
        if body.id
        else None
    )
    if body.id and current is None:
        raise unavailable()
    if current and current.version != body.expectedVersion:
        raise conflict()
    duplicate = session.scalar(select(ContentEntry.id).where(ContentEntry.key == body.draft.key))
    if duplicate and duplicate != body.id:
        raise AuthError("duplicate_key", "This content key is already in use.", 409)
    previous = ContentState.model_validate(current).model_dump(mode="json") if current else None
    if current is None:
        current = ContentEntry(**body.draft.model_dump())
        session.add(current)
    else:
        for field, value in body.draft.model_dump().items():
            setattr(current, field, value)
        current.version += 1
    session.flush()
    result = ContentState.model_validate(current)
    session.add(
        ContentSaveReceipt(
            request_key=key,
            request_sha256=digest,
            content_id=current.id,
            previous=previous,
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    notice = Message(
        kind="content_update",
        title=f"Content saved: {current.title}",
        body=f"{current.key} · {current.status}.",
        content_id=current.id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    for user_id in session.scalars(
        select(StaffUser.id).where(StaffUser.role == "owner", StaffUser.status == "active")
    ):
        session.add(MessageReceipt(message_id=notice.id, user_id=user_id))
    return result
