"""Typed change proposals, immutable notices and independent per-user read state."""

from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import ActorEvidence, Record, Versioned, choices


class ChangeRequest(ActorEvidence, Versioned, Base):
    __tablename__ = "change_requests"
    __table_args__ = (
        choices(
            "kind",
            "session_time",
            "session_trainer",
            "fixed_weekly_schedule",
            "trainer_availability",
        ),
        choices("status", "pending", "approved", "rejected", "cancelled", "superseded"),
        ForeignKeyConstraint(
            ["session_id", "purchase_id", "client_id"],
            [
                "training_sessions.id",
                "training_sessions.purchase_id",
                "training_sessions.client_id",
            ],
        ),
        ForeignKeyConstraint(
            ["purchase_id", "client_id"], ["package_purchases.id", "package_purchases.client_id"]
        ),
        CheckConstraint("expected_version > 0", name="review_version"),
        CheckConstraint(
            "(kind IN ('session_time', 'session_trainer') AND session_id IS NOT NULL AND "
            "purchase_id IS NOT NULL AND client_id IS NOT NULL) OR (kind = "
            "'fixed_weekly_schedule' AND session_id IS NULL AND purchase_id IS NOT NULL AND "
            "client_id IS NOT NULL) OR (kind = 'trainer_availability' AND session_id IS NULL "
            "AND purchase_id IS NULL AND client_id IS NULL)",
            name="typed_target",
        ),
        CheckConstraint(
            "(kind = 'session_time' AND old_date IS NOT NULL AND new_date IS NOT NULL AND "
            "old_start IS NOT NULL AND old_end IS NOT NULL AND new_start IS NOT NULL AND "
            "new_end IS NOT NULL AND old_start < old_end AND new_start < new_end) OR (kind <> "
            "'session_time' AND num_nonnulls(old_date, new_date, old_start, old_end, "
            "new_start, new_end) = 0)",
            name="typed_times",
        ),
        CheckConstraint(
            "(kind = 'session_trainer' AND replacement_trainer_id IS NOT NULL AND "
            "replacement_trainer_id <> trainer_id) OR (kind <> 'session_trainer' AND "
            "replacement_trainer_id IS NULL)",
            name="typed_replacement",
        ),
        CheckConstraint(
            "(status = 'pending' AND resolved_at IS NULL AND resolved_by IS NULL) OR (status "
            "<> 'pending' AND resolved_at IS NOT NULL AND resolved_by IS NOT NULL)",
            name="decision_evidence",
        ),
        Index(
            "ix_request_pending",
            "trainer_id",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"), index=True)
    client_id: Mapped[UUID | None] = mapped_column(ForeignKey("clients.id"), index=True)
    purchase_id: Mapped[UUID | None] = mapped_column(index=True)
    session_id: Mapped[UUID | None] = mapped_column(index=True)
    expected_version: Mapped[int] = mapped_column(Integer)
    replacement_trainer_id: Mapped[UUID | None] = mapped_column(ForeignKey("trainers.id"))
    old_date: Mapped[date | None] = mapped_column(Date)
    old_start: Mapped[time | None] = mapped_column(Time)
    old_end: Mapped[time | None] = mapped_column(Time)
    new_date: Mapped[date | None] = mapped_column(Date)
    new_start: Mapped[time | None] = mapped_column(Time)
    new_end: Mapped[time | None] = mapped_column(Time)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[UUID | None] = mapped_column(ForeignKey("staff_users.id"))
    resolution_note: Mapped[str] = mapped_column(Text, server_default="")
    created_xid: Mapped[str] = mapped_column(
        Text, server_default=text("pg_current_xact_id()::text")
    )


class RequestSlot(Record, Base):
    __tablename__ = "request_slots"
    __table_args__ = (
        choices("side", "old", "new"),
        CheckConstraint("weekday BETWEEN 0 AND 6 AND starts_at < ends_at", name="valid_slot"),
        UniqueConstraint("request_id", "side", "slot_identity"),
    )
    request_id: Mapped[UUID] = mapped_column(ForeignKey("change_requests.id"), index=True)
    side: Mapped[str] = mapped_column(String(3))
    slot_identity: Mapped[UUID] = mapped_column()
    weekday: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)


class RequestEvent(ActorEvidence, Record, Base):
    __tablename__ = "request_events"
    __table_args__ = (
        choices("status", "pending", "approved", "rejected", "cancelled", "superseded"),
        UniqueConstraint("request_id", "sequence"),
        CheckConstraint("sequence IN (1, 2)", name="bounded_history"),
    )
    request_id: Mapped[UUID] = mapped_column(ForeignKey("change_requests.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Text, server_default="")


class Message(ActorEvidence, Record, Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(title)) > 0 AND length(btrim(kind)) > 0", name="details_required"
        ),
        ForeignKeyConstraint(
            ["purchase_id", "client_id"], ["package_purchases.id", "package_purchases.client_id"]
        ),
        CheckConstraint("purchase_id IS NULL OR client_id IS NOT NULL", name="purchase_scope"),
    )
    kind: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    client_id: Mapped[UUID | None] = mapped_column(ForeignKey("clients.id"), index=True)
    purchase_id: Mapped[UUID | None] = mapped_column(index=True)
    session_id: Mapped[UUID | None] = mapped_column(ForeignKey("training_sessions.id"), index=True)
    trainer_id: Mapped[UUID | None] = mapped_column(ForeignKey("trainers.id"), index=True)
    request_id: Mapped[UUID | None] = mapped_column(ForeignKey("change_requests.id"), index=True)
    remuneration_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("remuneration_approvals.id"), index=True
    )
    exercise_id: Mapped[UUID | None] = mapped_column(ForeignKey("exercises.id"))
    content_id: Mapped[UUID | None] = mapped_column(ForeignKey("content_entries.id"))


class MessageReceipt(Versioned, Base):
    __tablename__ = "message_receipts"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id"),
        Index(
            "ix_receipt_unread", "user_id", "created_at", postgresql_where=text("read_at IS NULL")
        ),
    )
    message_id: Mapped[UUID] = mapped_column(ForeignKey("messages.id"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("staff_users.id"), index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionEvent(ActorEvidence, Record, Base):
    __tablename__ = "session_events"
    __table_args__ = (CheckConstraint("session_version > 0", name="valid_version"),)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("training_sessions.id"), index=True)
    session_version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(64))
    note: Mapped[str] = mapped_column(Text, server_default="")
    old_date: Mapped[date | None] = mapped_column(Date)
    new_date: Mapped[date | None] = mapped_column(Date)
    old_start: Mapped[time | None] = mapped_column(Time)
    old_end: Mapped[time | None] = mapped_column(Time)
    new_start: Mapped[time | None] = mapped_column(Time)
    new_end: Mapped[time | None] = mapped_column(Time)
    old_trainer_id: Mapped[UUID | None] = mapped_column(ForeignKey("trainers.id"))
    new_trainer_id: Mapped[UUID | None] = mapped_column(ForeignKey("trainers.id"))
