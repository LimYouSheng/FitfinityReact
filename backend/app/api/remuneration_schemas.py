"""Typed remuneration review and immutable approval contracts."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictStr

from app.api.schemas import Contract


class PayCycle(Contract):
    key: str
    start: date
    end: date
    payout: date


class PayRow(Contract):
    sessionId: UUID
    source: str
    clientId: UUID
    clientName: str
    clientType: Literal["Individual", "Couple"]
    date: date
    from_: str = Field(alias="from")
    to: str
    durationMinutes: int
    status: str
    billable: bool
    band: Literal["peak", "offPeak"]
    amountCents: int | None
    issues: list[str]


class PayRecord(Contract):
    cycle: PayCycle
    trainerId: UUID
    trainerName: str
    rows: list[PayRow]
    sessions: int
    totalSessions: int
    minutes: int
    amountCents: int
    reviewCount: int
    closed: bool
    status: Literal["In progress", "No sessions", "Pending review", "Pending approval", "Approved"]
    revision: str
    approvedAt: datetime | None = None
    approvedBy: UUID | None = None
    changed: bool = False
    current: "PayRecord | None" = None


class PayView(Contract):
    key: str
    cycle: PayCycle
    isCurrent: bool
    trainers: list[PayRecord]


class ApprovePay(Contract):
    revision: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class PaySaved(Contract):
    id: UUID
    trainerId: UUID
    cycle: str
    revision: str
    approvedAt: datetime
