"""Calendar labels and scoped detail evidence, without private profile/storage fields."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from app.api.schemas import Contract


class CalendarSession(Contract):
    readAccess: Literal["operations", "assigned", "historical"]
    id: UUID
    version: int
    clientId: UUID
    purchaseId: UUID
    trainerId: UUID
    scheduleState: Literal["booked", "open"]
    sessionNumber: int | None
    date: date | None
    startsAt: str | None
    endsAt: str | None
    status: Literal["scheduled", "planned", "completed", "cancelled"]


class SessionClientLabel(Contract):
    id: UUID
    name: str
    kind: Literal["individual", "couple"]
    status: Literal["active", "inactive"]


class SessionTrainerLabel(Contract):
    id: UUID
    name: str
    status: Literal["active", "inactive"]


class SessionPurchaseLabel(Contract):
    id: UUID
    clientId: UUID
    trainerId: UUID
    name: str
    status: Literal["active", "inactive"]
    stage: Literal["current", "queued", "archived"]
    total: int
    used: int
    validityDays: int
    startDate: date
    endDate: date


class SessionCalendar(Contract):
    viewerId: UUID
    sessions: list[CalendarSession]
    clients: list[SessionClientLabel]
    trainers: list[SessionTrainerLabel]
    purchases: list[SessionPurchaseLabel]


class SessionPlanDetailRead(Contract):
    id: str
    value: str


class SessionPlanRead(Contract):
    id: UUID
    version: int
    name: str
    weight: str
    reps: str
    rounds: str
    rest: str
    notes: str
    customDetails: list[SessionPlanDetailRead]
    videoAttached: bool


class SessionResultRead(Contract):
    id: UUID
    planItemId: UUID | None
    name: str
    loadKg: float
    reps: int
    sets: int


class SessionActorRead(Contract):
    id: UUID
    name: str


class SessionSignaturePoint(Contract):
    x: float
    y: float


class SessionAcknowledgementRead(Contract):
    id: UUID
    sequence: int
    method: Literal["signature", "late_no_show"]
    signerName: str | None
    signature: list[list[SessionSignaturePoint]] | None
    note: str
    recordedAt: datetime
    recordedBy: SessionActorRead


class SessionDetailRead(Contract):
    session: CalendarSession
    client: SessionClientLabel
    trainer: SessionTrainerLabel
    purchase: SessionPurchaseLabel
    exercisePlan: list[SessionPlanRead]
    retiredPlanItemIds: list[UUID]
    exerciseResults: list[SessionResultRead]
    acknowledgementHistory: list[SessionAcknowledgementRead]
    trainerComments: str
    clientSummary: str
    whatsappOpenedAt: datetime | None
    whatsappOpenCount: int
