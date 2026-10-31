"""Frozen Admin proposals and immutable Owner decision receipts."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import ActorEvidence, Record, Versioned, choices


class AdminOperationRequest(ActorEvidence, Versioned, Base):
    __tablename__ = "admin_operation_requests"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
        choices("status", "pending", "approved", "rejected", "cancelled"),
        CheckConstraint(
            "(status = 'pending' AND resolved_by IS NULL AND resolved_at IS NULL) OR "
            "(status <> 'pending' AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL)",
            name="decision_evidence",
        ),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    operation: Mapped[str] = mapped_column(String(100))
    area: Mapped[str] = mapped_column(String(32))
    body: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    resolved_by: Mapped[UUID | None] = mapped_column(ForeignKey("staff_users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminOperationDecision(ActorEvidence, Record, Base):
    __tablename__ = "admin_operation_decisions"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        UniqueConstraint("proposal_id"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    proposal_id: Mapped[UUID] = mapped_column(ForeignKey("admin_operation_requests.id"))
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSONB)
