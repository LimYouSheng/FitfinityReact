"""Admin contact records and durable account-provisioning receipts, without credentials."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import ActorEvidence, Record, Versioned, choices


class AdminProfile(Versioned, Base):
    __tablename__ = "admin_profiles"
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "user_role"], ["staff_users.id", "staff_users.role"]),
        CheckConstraint("user_role = 'admin'", name="admin_role"),
        choices("gender", "Female", "Male", "Other", "Prefer not to say"),
    )
    user_id: Mapped[UUID] = mapped_column(unique=True)
    user_role: Mapped[str] = mapped_column(String(16), server_default="admin")
    phone_country_code: Mapped[str] = mapped_column(String(4))
    phone_number: Mapped[str] = mapped_column(String(32))
    birthday: Mapped[date] = mapped_column(Date)
    gender: Mapped[str] = mapped_column(String(24))


class StaffInvitation(ActorEvidence, Record, Base):
    __tablename__ = "staff_invitations"
    __table_args__ = (
        choices("status", "pending", "sending", "sent", "unknown"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
        CheckConstraint("(lease_id IS NULL) = (lease_until IS NULL)", name="lease_pair"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("staff_users.id"), unique=True)
    request_key: Mapped[UUID] = mapped_column(unique=True)
    request_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    lease_id: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
