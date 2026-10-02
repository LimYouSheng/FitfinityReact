"""Durable staff sessions, challenge state and account-wide revocation barriers."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import Record, choices


class AuthAccount(Base):
    __tablename__ = "auth_accounts"
    __table_args__ = (
        CheckConstraint("epoch >= 0", name="nonnegative_epoch"),
        CheckConstraint("(pending_id IS NULL) = (pending_until IS NULL)", name="pending_pair"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("staff_users.id"), primary_key=True)
    epoch: Mapped[int] = mapped_column(BigInteger, server_default="0")
    pending_id: Mapped[UUID | None]
    pending_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthFlow(Record, Base):
    __tablename__ = "auth_flows"
    __table_args__ = (
        choices("kind", "sign_in", "recovery"),
        choices(
            "step",
            "starting",
            "NEW_PASSWORD_REQUIRED",
            "SOFTWARE_TOKEN_MFA",
            "MFA_SETUP",
            "recovery",
            "processing",
            "ended",
        ),
        CheckConstraint("attempts BETWEEN 0 AND 6", name="attempt_limit"),
        CheckConstraint("epoch >= 0", name="nonnegative_epoch"),
        CheckConstraint("created_at < expires_at", name="flow_window"),
        CheckConstraint("handle_hash ~ '^[0-9a-f]{64}$'", name="handle_digest"),
    )
    handle_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("staff_users.id"), index=True)
    epoch: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(16))
    step: Mapped[str] = mapped_column(String(32))
    username: Mapped[str] = mapped_column(String(128))
    provider_state: Mapped[bytes | None] = mapped_column(LargeBinary)
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuthSession(Record, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("handle_hash ~ '^[0-9a-f]{64}$'", name="handle_digest"),
        CheckConstraint("authenticated_at <= expires_at", name="session_window"),
        CheckConstraint("epoch >= 0", name="nonnegative_epoch"),
        CheckConstraint(
            "closed_at IS NOT NULL OR (access_cipher IS NOT NULL AND refresh_cipher IS NOT NULL)",
            name="open_credentials",
        ),
        CheckConstraint(
            "(refresh_lease_id IS NULL) = (refresh_lease_until IS NULL)", name="lease_pair"
        ),
        ForeignKeyConstraint(
            ["identity_id", "user_id"], ["staff_identities.id", "staff_identities.user_id"]
        ),
    )
    handle_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("staff_users.id"), index=True)
    identity_id: Mapped[UUID] = mapped_column(ForeignKey("staff_identities.id"), index=True)
    epoch: Mapped[int] = mapped_column(BigInteger)
    authenticated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    access_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    refresh_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refresh_lease_id: Mapped[UUID | None]
    refresh_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_pending: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), index=True)
