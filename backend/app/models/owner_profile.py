"""Owner contact details and immutable self-service save receipts."""

from datetime import date
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import ActorEvidence, Record, choices


class OwnerProfile(Base):
    __tablename__ = "owner_profiles"
    __table_args__ = (
        choices("gender", "Female", "Male", "Other", "Prefer not to say"),
        ForeignKeyConstraint(["user_id", "user_role"], ["staff_users.id", "staff_users.role"]),
        CheckConstraint("user_role = 'owner'", name="owner_role"),
    )
    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_role: Mapped[str] = mapped_column(String(16), server_default="owner")
    phone_country_code: Mapped[str] = mapped_column(String(4))
    phone_number: Mapped[str] = mapped_column(String(32))
    birthday: Mapped[date] = mapped_column(Date)
    gender: Mapped[str] = mapped_column(String(24))


class OwnerProfileReceipt(ActorEvidence, Record, Base):
    __tablename__ = "owner_profile_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSONB)
