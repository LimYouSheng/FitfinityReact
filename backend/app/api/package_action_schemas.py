"""Reviewed purchase lifecycle commands never accept browser authority or timestamps."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt, StrictStr

from app.api.schemas import Contract
from app.api.session_booking_review import BookingPosition

Operation = Literal["deactivate", "delete_sessions"]


class PackageActionReview(Contract):
    clientId: UUID
    clientVersion: StrictInt
    purchaseId: UUID
    purchaseVersion: StrictInt
    name: str
    status: Literal["active", "inactive"]
    operation: Operation
    expected: str
    eligible: list[BookingPosition]


class SavePackageAction(Contract):
    expected: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    operation: Operation
    deleteUpcomingSessions: StrictBool = False


class PackageActionState(Contract):
    id: UUID
    clientId: UUID
    purchaseId: UUID
    purchaseVersion: StrictInt
    status: Literal["active", "inactive"]
    deletedSessionIds: list[UUID]
    messageId: UUID | None
    undoUntil: datetime | None


class UndoPackageDeletion(Contract):
    expected: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class PackageUndoReview(Contract):
    id: UUID
    messageId: UUID
    clientId: UUID
    purchaseId: UUID
    expected: str
    expiresAt: datetime
    sessions: list[BookingPosition]


class PackageUndoState(Contract):
    id: UUID
    status: Literal["undone"] = "undone"
    undoneAt: datetime
