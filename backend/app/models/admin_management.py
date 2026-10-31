"""Owner-managed Admin supervision policy and immutable account change receipts."""

from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import ActorEvidence, Record, choices

APPROVAL_AREAS = (
    "clientCreation",
    "clientDetails",
    "clientLifecycle",
    "assessments",
    "trainerCreation",
    "trainerDetails",
    "trainerAssignment",
    "trainerLifecycle",
    "sessionScheduling",
    "sessionContent",
    "sessionAcknowledgement",
    "packageCatalogue",
    "clientPackages",
    "exerciseLibrary",
    "content",
    "progressReportSharing",
    "sessionPdfSharing",
)

DEFAULT_APPROVAL_AREAS = ("exerciseLibrary", "content")


class AdminApprovalRequirement(Base):
    __tablename__ = "admin_approval_requirements"
    __table_args__ = (choices("area", *APPROVAL_AREAS),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("admin_profiles.user_id"), primary_key=True)
    area: Mapped[str] = mapped_column(String(32), primary_key=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)


class AdminManagementReceipt(ActorEvidence, Record, Base):
    __tablename__ = "admin_management_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
        choices("operation", "details", "approvals", "deactivate", "reactivate"),
    )
    admin_id: Mapped[UUID] = mapped_column(ForeignKey("admin_profiles.user_id"), index=True)
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    operation: Mapped[str] = mapped_column(String(16))
    previous: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)
