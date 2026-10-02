"""Durable retry receipts and sensitive-access audit; never duplicate assessment answers."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import ActorEvidence, Record, choices


class ApiReceipt(ActorEvidence, Record, Base):
    __tablename__ = "api_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        choices("operation", "assessment_create", "assessment_save"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    operation: Mapped[str] = mapped_column(String(32))
    request_sha256: Mapped[str] = mapped_column(String(64))
    revision_id: Mapped[UUID] = mapped_column(ForeignKey("client_assessment_revisions.id"))


class AssessmentAccess(ActorEvidence, Record, Base):
    __tablename__ = "assessment_access"
    __table_args__ = (choices("action", "list", "view", "history", "create", "save", "replay"),)
    client_person_id: Mapped[UUID] = mapped_column(ForeignKey("client_people.id"), index=True)
    action: Mapped[str] = mapped_column(String(16))
    assessment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("client_assessments.id"), index=True
    )
