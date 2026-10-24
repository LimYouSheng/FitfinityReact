"""Frozen original recording commands; storage bytes remain outside PostgreSQL."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import ActorEvidence, Versioned, choices


class SessionMediaIntent(ActorEvidence, Versioned, Base):
    __tablename__ = "session_media_intents"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        ForeignKeyConstraint(
            ["plan_item_id", "session_id"],
            ["exercise_plan_items.id", "exercise_plan_items.session_id"],
        ),
        choices("state", "pending", "completed", "expired"),
        choices("source", "recorded", "attached"),
        choices("processing_status", "complete", "deferred"),
        CheckConstraint(
            "request_sha256 ~ '^[0-9a-f]{64}$' AND expected_sha256 ~ '^[0-9a-f]{64}$'",
            name="request_digest",
        ),
        CheckConstraint(
            "(state = 'completed') = (result IS NOT NULL) AND "
            "(state = 'completed') = (completed_at IS NOT NULL)",
            name="receipt_state",
        ),
        CheckConstraint("remove_media = (upload_id IS NULL)", name="upload_action"),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds BETWEEN 1 AND 60", name="duration_bound"
        ),
        CheckConstraint("length(caption) <= 10000", name="caption_bound"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    expected_sha256: Mapped[str] = mapped_column(String(64))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("session_identities.id"), index=True)
    plan_item_id: Mapped[UUID]
    remove_media: Mapped[bool] = mapped_column(Boolean)
    upload_id: Mapped[UUID | None] = mapped_column(ForeignKey("media_assets.id"), unique=True)
    previous_media_id: Mapped[UUID | None] = mapped_column(ForeignKey("media_assets.id"))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16))
    caption: Mapped[str] = mapped_column(Text)
    processing_status: Mapped[str] = mapped_column(String(16))
    audio_included: Mapped[bool | None] = mapped_column(Boolean)
    upload_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(16), server_default="pending")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
