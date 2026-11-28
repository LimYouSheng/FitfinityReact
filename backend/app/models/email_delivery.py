"""Durable transactional mail intent and provider acceptance evidence."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import Record, choices


class EmailDelivery(Record, Base):
    __tablename__ = "email_deliveries"
    __table_args__ = (
        UniqueConstraint("event_key", "recipient"),
        choices("state", "pending", "sending", "accepted", "failed", "unknown"),
        CheckConstraint("attempts >= 0 AND attempts <= 5", name="bounded_attempts"),
        Index("ix_email_deliveries_state_available_at", "state", "available_at"),
    )
    event_key: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(40))
    recipient: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16), server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    lease_id: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_id: Mapped[str | None] = mapped_column(String(200))
    error_code: Mapped[str | None] = mapped_column(String(80))


class EmailReportReceipt(Record, Base):
    __tablename__ = "email_report_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        UniqueConstraint("actor_id", "request_sha256"),
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("staff_users.id"))
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSONB)
