"""Purchases own stable sessions; mutable assignments do not rewrite purchased terms."""

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import ActorEvidence, Record, Versioned, choices


class PackageTemplate(Versioned, Base):
    __tablename__ = "package_templates"
    __table_args__ = (choices("status", "active", "inactive"),)
    status: Mapped[str] = mapped_column(String(16), server_default="active")


class PackageTemplateRevision(ActorEvidence, Record, Base):
    __tablename__ = "package_template_revisions"
    __table_args__ = (
        UniqueConstraint("template_id", "revision"),
        CheckConstraint(
            "revision > 0 AND total_sessions BETWEEN 1 AND 365 AND validity_days > 0",
            name="valid_terms",
        ),
        CheckConstraint("length(btrim(name)) > 0", name="name_required"),
    )
    template_id: Mapped[UUID] = mapped_column(ForeignKey("package_templates.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    total_sessions: Mapped[int] = mapped_column(Integer)
    validity_days: Mapped[int] = mapped_column(Integer)


class PackagePurchase(Versioned, Base):
    __tablename__ = "package_purchases"
    __table_args__ = (
        UniqueConstraint("id", "client_id"),
        ForeignKeyConstraint(
            ["template_id", "template_revision"],
            ["package_template_revisions.template_id", "package_template_revisions.revision"],
        ),
        choices("status", "active", "inactive"),
        choices("stage", "queued", "current", "archived"),
        choices("gender_preference", "any", "female", "male"),
        CheckConstraint(
            "total_sessions BETWEEN 1 AND 365 AND sessions_per_week BETWEEN 1 AND 7 AND "
            "validity_days > 0",
            name="valid_terms",
        ),
        CheckConstraint("end_date = start_date + validity_days - 1", name="inclusive_validity"),
        CheckConstraint(
            "template_revision > 0 AND length(btrim(name)) > 0", name="snapshot_required"
        ),
        ExcludeConstraint(
            ("client_id", "="),
            (text("daterange(start_date, end_date, '[]')"), "&&"),
            where=text("status = 'active'"),
            using="gist",
            name="ex_purchase_dates",
        ),
        Index(
            "uq_current_purchase",
            "client_id",
            unique=True,
            postgresql_where=text("stage = 'current'"),
        ),
        Index(
            "ix_purchase_activation",
            "start_date",
            postgresql_where=text("stage = 'queued' AND status = 'active'"),
        ),
    )
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    template_id: Mapped[UUID] = mapped_column(ForeignKey("package_templates.id"), index=True)
    template_revision: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    total_sessions: Mapped[int] = mapped_column(Integer)
    validity_days: Mapped[int] = mapped_column(Integer)
    sessions_per_week: Mapped[int] = mapped_column(Integer)
    free_gym: Mapped[bool] = mapped_column(Boolean)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    purchased_trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"))
    trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"), index=True)
    gender_preference: Mapped[str] = mapped_column(String(16), server_default="any")
    status: Mapped[str] = mapped_column(String(16), server_default="active")
    stage: Mapped[str] = mapped_column(String(16), server_default="queued")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifecycle_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("lifecycle_events.id", use_alter=True)
    )
    created_xid: Mapped[str] = mapped_column(
        Text, server_default=text("pg_current_xact_id()::text")
    )


class PurchaseScheduleSlot(Versioned, Base):
    __tablename__ = "purchase_schedule_slots"
    __table_args__ = (
        UniqueConstraint("id", "purchase_id"),
        UniqueConstraint("purchase_id", "weekday", deferrable=True, initially="DEFERRED"),
        CheckConstraint("weekday BETWEEN 0 AND 6 AND starts_at < ends_at", name="valid_slot"),
        CheckConstraint(
            "purchased_weekday BETWEEN 0 AND 6 AND purchased_starts_at < purchased_ends_at",
            name="valid_snapshot",
        ),
    )
    purchase_id: Mapped[UUID] = mapped_column(ForeignKey("package_purchases.id"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)
    purchased_weekday: Mapped[int] = mapped_column(Integer)
    purchased_starts_at: Mapped[time] = mapped_column(Time)
    purchased_ends_at: Mapped[time] = mapped_column(Time)


class PurchasePreference(Record, Base):
    __tablename__ = "purchase_preferences"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6 AND starts_at < ends_at", name="valid_slot"),
        UniqueConstraint("purchase_id", "weekday", "starts_at", "ends_at"),
    )
    purchase_id: Mapped[UUID] = mapped_column(ForeignKey("package_purchases.id"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)


class TrainingSession(Versioned, Base):
    __tablename__ = "training_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["purchase_id", "client_id"], ["package_purchases.id", "package_purchases.client_id"]
        ),
        ForeignKeyConstraint(
            ["schedule_slot_id", "purchase_id"],
            ["purchase_schedule_slots.id", "purchase_schedule_slots.purchase_id"],
        ),
        UniqueConstraint("purchase_id", "session_number"),
        UniqueConstraint("id", "purchase_id", "client_id"),
        choices("status", "scheduled", "planned", "completed", "cancelled"),
        CheckConstraint(
            "session_number BETWEEN 1 AND 365 AND starts_at < ends_at", name="valid_session"
        ),
        CheckConstraint("whatsapp_open_count >= 0", name="handoff_count"),
        Index("ix_session_trainer_calendar", "trainer_id", "training_date", "starts_at"),
        Index("ix_session_client_calendar", "client_id", "training_date", "starts_at"),
    )
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    purchase_id: Mapped[UUID] = mapped_column(index=True)
    trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"), index=True)
    schedule_slot_id: Mapped[UUID | None] = mapped_column()
    session_number: Mapped[int] = mapped_column(Integer)
    training_date: Mapped[date] = mapped_column(Date)
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)
    status: Mapped[str] = mapped_column(String(16), server_default="scheduled")
    trainer_comments: Mapped[str] = mapped_column(Text, server_default="")
    client_summary: Mapped[str] = mapped_column(Text, server_default="")
    copied_from_session_id: Mapped[UUID | None] = mapped_column(ForeignKey("training_sessions.id"))
    whatsapp_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    whatsapp_open_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class Exercise(Versioned, Base):
    __tablename__ = "exercises"
    __table_args__ = (
        choices("status", "active", "inactive"),
        CheckConstraint(
            "length(btrim(name)) > 0 AND length(btrim(category)) > 0", name="details_required"
        ),
        Index("uq_exercise_name", text("lower(btrim(name))"), unique=True),
    )
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text, server_default="")
    status: Mapped[str] = mapped_column(String(16), server_default="active")
    media_id: Mapped[UUID | None] = mapped_column(ForeignKey("media_assets.id", use_alter=True))


class ExercisePlanItem(Versioned, Base):
    __tablename__ = "exercise_plan_items"
    __table_args__ = (
        UniqueConstraint("session_id", "position", deferrable=True, initially="DEFERRED"),
        UniqueConstraint("id", "session_id"),
        CheckConstraint("position > 0 AND length(btrim(name)) > 0", name="valid_item"),
    )
    session_id: Mapped[UUID] = mapped_column(ForeignKey("training_sessions.id"), index=True)
    exercise_id: Mapped[UUID | None] = mapped_column(ForeignKey("exercises.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    weight: Mapped[str] = mapped_column(String(100), server_default="")
    reps: Mapped[str] = mapped_column(String(100), server_default="")
    rounds: Mapped[str] = mapped_column(String(100), server_default="")
    rest: Mapped[str] = mapped_column(String(100), server_default="")
    notes: Mapped[str] = mapped_column(Text, server_default="")


class ExerciseResult(Versioned, Base):
    __tablename__ = "exercise_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["plan_item_id", "session_id"],
            ["exercise_plan_items.id", "exercise_plan_items.session_id"],
        ),
        UniqueConstraint("session_id", "plan_item_id"),
        CheckConstraint(
            "load_kg BETWEEN 0 AND 2000 AND reps BETWEEN 1 AND 1000 AND sets BETWEEN 1 AND 100",
            name="measurement_bounds",
        ),
        CheckConstraint("length(btrim(name)) > 0", name="name_required"),
    )
    session_id: Mapped[UUID] = mapped_column(ForeignKey("training_sessions.id"), index=True)
    plan_item_id: Mapped[UUID | None] = mapped_column()
    name: Mapped[str] = mapped_column(String(200))
    load_kg: Mapped[Decimal] = mapped_column(Numeric(9, 4))
    reps: Mapped[int] = mapped_column(Integer)
    sets: Mapped[int] = mapped_column(Integer)


class ExerciseResultRevision(ActorEvidence, Record, Base):
    __tablename__ = "exercise_result_revisions"
    __table_args__ = (
        UniqueConstraint("result_id", "result_version"),
        CheckConstraint(
            "result_version > 0 AND load_kg BETWEEN 0 AND 2000 AND reps BETWEEN 1 AND 1000 AND "
            "sets BETWEEN 1 AND 100",
            name="measurement_bounds",
        ),
    )
    result_id: Mapped[UUID] = mapped_column(ForeignKey("exercise_results.id"), index=True)
    result_version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    load_kg: Mapped[Decimal] = mapped_column(Numeric(9, 4))
    reps: Mapped[int] = mapped_column(Integer)
    sets: Mapped[int] = mapped_column(Integer)


class Acknowledgement(ActorEvidence, Record, Base):
    __tablename__ = "acknowledgements"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence"),
        UniqueConstraint("id", "session_id"),
        choices("method", "signature", "late_no_show"),
        CheckConstraint("sequence IN (1, 2)", name="bounded_history"),
        CheckConstraint(
            "(method = 'signature' AND signer_name IS NOT NULL AND length(btrim(signer_name)) "
            "> 0 AND signature IS NOT NULL AND octet_length(signature) BETWEEN 1 AND 1000000 "
            "AND signature_sha256 IS NOT NULL AND signature_sha256 ~ '^[0-9a-f]{64}$') OR "
            "(method = 'late_no_show' AND signer_name IS NULL AND signature IS NULL AND "
            "signature_sha256 IS NULL)",
            name="signature_evidence",
        ),
    )
    session_id: Mapped[UUID] = mapped_column(ForeignKey("training_sessions.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(16))
    signer_name: Mapped[str | None] = mapped_column(String(200))
    signature: Mapped[bytes | None] = mapped_column(LargeBinary)
    signature_sha256: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str] = mapped_column(Text, server_default="")


class CreditDebit(ActorEvidence, Record, Base):
    __tablename__ = "credit_debits"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "purchase_id", "client_id"],
            [
                "training_sessions.id",
                "training_sessions.purchase_id",
                "training_sessions.client_id",
            ],
        ),
        CheckConstraint("amount = -1", name="single_credit"),
    )
    session_id: Mapped[UUID] = mapped_column(unique=True)
    purchase_id: Mapped[UUID] = mapped_column(ForeignKey("package_purchases.id"), index=True)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer, server_default=text("-1"))


class AssignmentEvent(ActorEvidence, Record, Base):
    __tablename__ = "assignment_events"
    __table_args__ = (CheckConstraint("old_trainer_id <> new_trainer_id", name="changed_trainer"),)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    old_trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"), index=True)
    new_trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"), index=True)
    old_trainer_name: Mapped[str] = mapped_column(String(200))
    new_trainer_name: Mapped[str] = mapped_column(String(200))
    client_version: Mapped[int] = mapped_column(Integer)


class AssignmentChange(Record, Base):
    __tablename__ = "assignment_changes"
    __table_args__ = (
        CheckConstraint("num_nonnulls(purchase_id, session_id) = 1", name="one_target"),
        CheckConstraint("old_version > 0", name="valid_version"),
        UniqueConstraint("event_id", "purchase_id"),
        UniqueConstraint("event_id", "session_id"),
    )
    event_id: Mapped[UUID] = mapped_column(ForeignKey("assignment_events.id"), index=True)
    purchase_id: Mapped[UUID | None] = mapped_column(ForeignKey("package_purchases.id"))
    session_id: Mapped[UUID | None] = mapped_column(ForeignKey("training_sessions.id"))
    old_trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"))
    new_trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"))
    old_version: Mapped[int] = mapped_column(Integer)
