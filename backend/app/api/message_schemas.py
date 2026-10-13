"""Personal messages expose only this recipient's read state, never other readers."""

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt

from app.api.schemas import Contract


class MessageReadState(Contract):
    id: UUID
    version: StrictInt = Field(ge=0)
    read: StrictBool
    readAt: datetime | None


class SaveMessageRead(Contract):
    expectedVersion: StrictInt = Field(ge=0)
    read: StrictBool


class MessageRequestSlot(Contract):
    side: Literal["old", "new"]
    slot_identity: UUID
    weekday: int = Field(ge=0, le=6)
    starts_at: time
    ends_at: time


class MessageRequest(Contract):
    id: UUID
    version: int
    kind: Literal[
        "session_time", "session_trainer", "fixed_weekly_schedule", "trainer_availability"
    ]
    status: Literal["pending", "approved", "rejected", "cancelled", "superseded"]
    trainer_id: UUID
    client_id: UUID | None
    purchase_id: UUID | None
    session_id: UUID | None
    expected_version: int
    replacement_trainer_id: UUID | None
    old_date: date | None
    old_start: time | None
    old_end: time | None
    new_date: date | None
    new_start: time | None
    new_end: time | None
    resolved_at: datetime | None
    resolution_note: str
    slots: list[MessageRequestSlot]


class PersonalMessage(MessageReadState):
    recipientUserId: UUID
    kind: str
    title: str
    body: str
    createdAt: datetime
    actorId: UUID
    actorName: str
    clientId: UUID | None
    purchaseId: UUID | None
    sessionId: UUID | None
    trainerId: UUID | None
    requestId: UUID | None
    exerciseId: UUID | None
    packageId: UUID | None
    contentId: UUID | None
    remunerationCycle: str | None
    request: MessageRequest | None
    renewalStatus: Literal["active", "renewed"] | None
