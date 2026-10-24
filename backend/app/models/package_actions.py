"""Typed retained booking identities and reversible package-session deletion evidence."""

from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import ActorEvidence, Record, choices


class SessionIdentity(Record, Base):
    __tablename__ = "session_identities"
    __table_args__ = (
        UniqueConstraint("id", "purchase_id", "client_id"),
        ForeignKeyConstraint(
            ["purchase_id", "client_id"], ["package_purchases.id", "package_purchases.client_id"]
        ),
    )
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    purchase_id: Mapped[UUID] = mapped_column(index=True)
    created_xid: Mapped[str] = mapped_column(
        Text, server_default=text("pg_current_xact_id()::text")
    )


class PackageActionReceipt(ActorEvidence, Record, Base):
    __tablename__ = "package_action_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        ForeignKeyConstraint(
            ["purchase_id", "client_id"], ["package_purchases.id", "package_purchases.client_id"]
        ),
        choices("operation", "deactivate", "delete_sessions"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
        CheckConstraint("client_version > 0 AND purchase_version > 0", name="reviewed_versions"),
        CheckConstraint(
            "undo_expires_at IS NULL OR (operation = 'delete_sessions' "
            "AND undo_expires_at > created_at)",
            name="undo_scope",
        ),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    operation: Mapped[str] = mapped_column(String(24))
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    purchase_id: Mapped[UUID] = mapped_column(index=True)
    client_version: Mapped[int] = mapped_column(Integer)
    purchase_version: Mapped[int] = mapped_column(Integer)
    message_id: Mapped[UUID | None] = mapped_column(ForeignKey("messages.id"), unique=True)
    undo_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict] = mapped_column(JSONB)
    created_xid: Mapped[str] = mapped_column(
        Text, server_default=text("pg_current_xact_id()::text")
    )


class SessionArchive(Record, Base):
    __tablename__ = "session_archives"
    __table_args__ = (
        UniqueConstraint("action_id", "session_id"),
        UniqueConstraint("session_id", "original_version"),
        ForeignKeyConstraint(
            ["session_id", "purchase_id", "client_id"],
            [
                "session_identities.id",
                "session_identities.purchase_id",
                "session_identities.client_id",
            ],
        ),
        ForeignKeyConstraint(
            ["schedule_slot_id", "purchase_id"],
            ["purchase_schedule_slots.id", "purchase_schedule_slots.purchase_id"],
        ),
        choices("status", "scheduled", "planned"),
        choices("schedule_state", "booked", "open"),
        CheckConstraint("contents_sha256 ~ '^[0-9a-f]{64}$'", name="contents_digest"),
        CheckConstraint(
            "original_version > 0 AND whatsapp_open_count >= 0", name="snapshot_versions"
        ),
        CheckConstraint(
            "(schedule_state = 'open' AND num_nonnulls(session_number, training_date, "
            "starts_at, ends_at, schedule_slot_id) = 0) OR (schedule_state = 'booked' "
            "AND session_number BETWEEN 1 AND 365 AND training_date IS NOT NULL "
            "AND starts_at IS NOT NULL AND ends_at IS NOT NULL AND starts_at < ends_at)",
            name="snapshot_booking",
        ),
    )
    action_id: Mapped[UUID] = mapped_column(ForeignKey("package_action_receipts.id"), index=True)
    session_id: Mapped[UUID] = mapped_column(index=True)
    client_id: Mapped[UUID]
    purchase_id: Mapped[UUID]
    trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"))
    contents_sha256: Mapped[str] = mapped_column(String(64), server_default=text("''"))
    original_version: Mapped[int] = mapped_column(Integer)
    original_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    original_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    schedule_slot_id: Mapped[UUID | None]
    schedule_state: Mapped[str] = mapped_column(String(16))
    session_number: Mapped[int | None] = mapped_column(Integer)
    training_date: Mapped[date | None] = mapped_column(Date)
    starts_at: Mapped[time | None] = mapped_column(Time)
    ends_at: Mapped[time | None] = mapped_column(Time)
    status: Mapped[str] = mapped_column(String(16))
    trainer_comments: Mapped[str] = mapped_column(Text)
    client_summary: Mapped[str] = mapped_column(Text)
    copied_from_session_id: Mapped[UUID | None] = mapped_column(ForeignKey("session_identities.id"))
    whatsapp_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    whatsapp_open_count: Mapped[int] = mapped_column(Integer)


class PackageDeletionUndo(ActorEvidence, Record, Base):
    __tablename__ = "package_deletion_undos"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    action_id: Mapped[UUID] = mapped_column(ForeignKey("package_action_receipts.id"), unique=True)
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    message_id: Mapped[UUID] = mapped_column(ForeignKey("messages.id"))
    result: Mapped[dict] = mapped_column(JSONB)
    created_xid: Mapped[str] = mapped_column(
        Text, server_default=text("pg_current_xact_id()::text")
    )


class PackageArchivedMedia(Record, Base):
    __tablename__ = "package_archived_media"
    __table_args__ = (
        UniqueConstraint("archive_id", "media_id"),
        CheckConstraint("original_version > 0", name="original_version"),
    )
    archive_id: Mapped[UUID] = mapped_column(ForeignKey("session_archives.id"))
    media_id: Mapped[UUID] = mapped_column(ForeignKey("media_assets.id"))
    original_version: Mapped[int] = mapped_column(Integer)


class PackageActionRequest(Record, Base):
    __tablename__ = "package_action_requests"
    __table_args__ = (
        UniqueConstraint("action_id", "request_id"),
        CheckConstraint("resolved_version > 0", name="resolved_version"),
    )
    action_id: Mapped[UUID] = mapped_column(ForeignKey("package_action_receipts.id"))
    request_id: Mapped[UUID] = mapped_column(ForeignKey("change_requests.id"))
    resolved_version: Mapped[int] = mapped_column(Integer)
