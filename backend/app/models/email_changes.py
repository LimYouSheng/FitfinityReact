"""Pending account-holder email verification; never store verification codes."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import ActorEvidence, Record, choices


class StaffEmailChange(ActorEvidence, Record, Base):
    __tablename__ = "staff_email_changes"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        Index(
            "uq_staff_email_changes_pending_user",
            "user_id",
            unique=True,
            postgresql_where=text("state <> 'completed'"),
        ),
        Index(
            "uq_staff_email_changes_pending_email",
            "new_email",
            unique=True,
            postgresql_where=text("state <> 'completed'"),
        ),
        choices("state", "requested", "sending", "pending", "verifying", "completed"),
        CheckConstraint("attempts BETWEEN 0 AND 6", name="attempt_limit"),
        CheckConstraint("sends BETWEEN 0 AND 6", name="send_limit"),
        CheckConstraint("(lease_id IS NULL) = (lease_until IS NULL)", name="lease_pair"),
        CheckConstraint(
            "(state = 'completed') = (completed_at IS NOT NULL)", name="completion_pair"
        ),
        CheckConstraint(
            "old_email <> new_email AND new_email = lower(btrim(new_email)) "
            "AND position('@' in new_email) > 1",
            name="email_change",
        ),
    )
    request_key: Mapped[UUID]
    trainer_version: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("staff_users.id"), index=True)
    identity_id: Mapped[UUID] = mapped_column(ForeignKey("staff_identities.id"))
    old_email: Mapped[str] = mapped_column(String(320))
    new_email: Mapped[str] = mapped_column(String(320))
    state: Mapped[str] = mapped_column(String(16), server_default="requested")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    sends: Mapped[int] = mapped_column(Integer, server_default="0")
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_id: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
