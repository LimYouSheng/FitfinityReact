"""Object metadata and durable deletion work; no public URLs or media blobs in snapshots."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import Versioned, choices


class MediaAsset(Versioned, Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        UniqueConstraint("bucket", "object_key"),
        choices("purpose", "session_video", "exercise_media"),
        choices("status", "pending", "ready", "delete_pending", "deleted"),
        ForeignKeyConstraint(
            ["purchase_id", "client_id"], ["package_purchases.id", "package_purchases.client_id"]
        ),
        CheckConstraint(
            "size_bytes > 0 AND content_sha256 ~ '^[0-9a-f]{64}$'", name="content_evidence"
        ),
        CheckConstraint(
            "length(btrim(bucket)) > 0 AND length(btrim(object_key)) > 0", name="storage_required"
        ),
        CheckConstraint(
            "(purpose = 'session_video' AND original_session_id IS NOT NULL AND "
            "original_plan_item_id IS NOT NULL AND client_id IS NOT NULL AND purchase_id IS "
            "NOT NULL AND expires_at IS NOT NULL AND expires_at > created_at) OR (purpose = "
            "'exercise_media' AND num_nonnulls(original_session_id, original_plan_item_id, "
            "session_id, client_id, purchase_id, expires_at) = 0)",
            name="purpose_scope",
        ),
        Index(
            "ix_media_expiry",
            "expires_at",
            postgresql_where=text("status = 'ready' AND expires_at IS NOT NULL"),
        ),
    )
    purpose: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    bucket: Mapped[str] = mapped_column(String(63))
    object_key: Mapped[str] = mapped_column(String(1024))
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    content_sha256: Mapped[str] = mapped_column(String(64))
    uploaded_by: Mapped[UUID] = mapped_column(ForeignKey("staff_users.id"))
    client_id: Mapped[UUID | None] = mapped_column(ForeignKey("clients.id"), index=True)
    purchase_id: Mapped[UUID | None] = mapped_column(index=True)
    session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="SET NULL"), index=True
    )
    original_session_id: Mapped[UUID | None] = mapped_column()
    original_plan_item_id: Mapped[UUID | None] = mapped_column()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MediaDeletion(Versioned, Base):
    __tablename__ = "media_deletions"
    __table_args__ = (
        choices("status", "pending", "processing", "done"),
        choices("reason", "expired", "replaced", "removed", "session_deleted"),
        CheckConstraint("attempts >= 0", name="attempt_count"),
        CheckConstraint("(status = 'done') = (completed_at IS NOT NULL)", name="completion_state"),
        Index("ix_deletion_pending", "next_attempt_at", postgresql_where=text("status <> 'done'")),
    )
    media_id: Mapped[UUID] = mapped_column(ForeignKey("media_assets.id"), unique=True)
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    reason: Mapped[str] = mapped_column(String(24))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))


class ContentEntry(Versioned, Base):
    __tablename__ = "content_entries"
    __table_args__ = (
        choices("status", "draft", "ready", "archived"),
        CheckConstraint(
            "key ~ '^[a-z0-9]+([-/][a-z0-9]+)*$' AND length(btrim(title)) > 0 AND "
            "length(btrim(body)) BETWEEN 1 AND 20000",
            name="content_bounds",
        ),
    )
    key: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), server_default="draft")
