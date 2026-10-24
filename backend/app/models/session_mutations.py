"""Typed immutable before/after evidence for explicitly permitted domain compensation."""

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
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


class SessionMutation(ActorEvidence, Record, Base):
    __tablename__ = "session_mutations"
    __table_args__ = (
        UniqueConstraint("actor_id", "operation", "request_key"),
        choices("actor_role", "owner", "admin", "trainer"),
    )
    operation: Mapped[str] = mapped_column(String(64))
    request_key: Mapped[UUID]
    actor_role: Mapped[str] = mapped_column(String(16))
    trainer_id: Mapped[UUID | None] = mapped_column(ForeignKey("trainers.id"))
    message_id: Mapped[UUID] = mapped_column(ForeignKey("messages.id"), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_xid: Mapped[str] = mapped_column(
        Text, server_default=text("pg_current_xact_id()::text")
    )


class SessionMutationUndo(ActorEvidence, Record, Base):
    __tablename__ = "session_mutation_undos"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    mutation_id: Mapped[UUID] = mapped_column(ForeignKey("session_mutations.id"), unique=True)
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    message_id: Mapped[UUID] = mapped_column(ForeignKey("messages.id"))
    result: Mapped[dict] = mapped_column(JSONB)
    created_xid: Mapped[str] = mapped_column(
        Text, server_default=text("pg_current_xact_id()::text")
    )


class MutationScope(Record, Base):
    __tablename__ = "mutation_scopes"
    __table_args__ = (
        CheckConstraint("num_nonnulls(client_id, trainer_id, session_id) = 1", name="one_target"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="scope_digest"),
    )
    mutation_id: Mapped[UUID] = mapped_column(ForeignKey("session_mutations.id"), index=True)
    client_id: Mapped[UUID | None] = mapped_column(ForeignKey("clients.id"))
    trainer_id: Mapped[UUID | None] = mapped_column(ForeignKey("trainers.id"))
    session_id: Mapped[UUID | None] = mapped_column()
    sha256: Mapped[str] = mapped_column(String(64))


class Snapshot:
    mutation_id: Mapped[UUID] = mapped_column(ForeignKey("session_mutations.id"), primary_key=True)
    entity_id: Mapped[UUID] = mapped_column(primary_key=True)
    side: Mapped[str] = mapped_column(String(8), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)


class MutationSession(Snapshot, Base):
    __tablename__ = "mutation_training_sessions"
    __table_args__ = (choices("side", "before", "after"),)
    client_id: Mapped[UUID] = mapped_column()
    purchase_id: Mapped[UUID] = mapped_column()
    trainer_id: Mapped[UUID] = mapped_column()
    schedule_slot_id: Mapped[UUID | None] = mapped_column()
    schedule_state: Mapped[str] = mapped_column(String(length=16))
    session_number: Mapped[int | None] = mapped_column(Integer())
    training_date: Mapped[date | None] = mapped_column(Date())
    starts_at: Mapped[time | None] = mapped_column(Time())
    ends_at: Mapped[time | None] = mapped_column(Time())
    status: Mapped[str] = mapped_column(String(length=16))
    trainer_comments: Mapped[str] = mapped_column(Text())
    client_summary: Mapped[str] = mapped_column(Text())
    copied_from_session_id: Mapped[UUID | None] = mapped_column()
    whatsapp_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    whatsapp_open_count: Mapped[int] = mapped_column(Integer())


class MutationClient(Snapshot, Base):
    __tablename__ = "mutation_clients"
    __table_args__ = (choices("side", "before", "after"),)
    trainer_id: Mapped[UUID] = mapped_column()
    status: Mapped[str] = mapped_column(String(length=16))
    lifecycle_event_id: Mapped[UUID | None] = mapped_column()


class MutationPurchase(Snapshot, Base):
    __tablename__ = "mutation_package_purchases"
    __table_args__ = (choices("side", "before", "after"),)
    client_id: Mapped[UUID] = mapped_column()
    trainer_id: Mapped[UUID] = mapped_column()
    status: Mapped[str] = mapped_column(String(length=16))
    lifecycle_event_id: Mapped[UUID | None] = mapped_column()


class MutationSlot(Snapshot, Base):
    __tablename__ = "mutation_purchase_schedule_slots"
    __table_args__ = (choices("side", "before", "after"),)
    purchase_id: Mapped[UUID] = mapped_column()
    weekday: Mapped[int] = mapped_column(Integer())
    starts_at: Mapped[time] = mapped_column(Time())
    ends_at: Mapped[time] = mapped_column(Time())


class MutationTrainer(Snapshot, Base):
    __tablename__ = "mutation_trainers"
    __table_args__ = (choices("side", "before", "after"),)
    user_id: Mapped[UUID | None] = mapped_column()
    status: Mapped[str] = mapped_column(String(length=16))


class MutationUser(Snapshot, Base):
    __tablename__ = "mutation_staff_users"
    __table_args__ = (choices("side", "before", "after"),)
    role: Mapped[str] = mapped_column(String(length=16))
    status: Mapped[str] = mapped_column(String(length=16))


class MutationPlan(Snapshot, Base):
    __tablename__ = "mutation_exercise_plan_items"
    __table_args__ = (choices("side", "before", "after"),)
    session_id: Mapped[UUID] = mapped_column()
    exercise_id: Mapped[UUID | None] = mapped_column()
    position: Mapped[int | None] = mapped_column(Integer())
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    name: Mapped[str] = mapped_column(String(length=200))
    weight: Mapped[str] = mapped_column(String(length=100))
    reps: Mapped[str] = mapped_column(String(length=100))
    rounds: Mapped[str] = mapped_column(String(length=100))
    rest: Mapped[str] = mapped_column(String(length=100))
    notes: Mapped[str] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MutationDetail(Snapshot, Base):
    __tablename__ = "mutation_exercise_plan_details"
    __table_args__ = (choices("side", "before", "after"),)
    plan_item_id: Mapped[UUID] = mapped_column()
    detail_key: Mapped[str] = mapped_column(String(length=200))
    position: Mapped[int] = mapped_column(Integer())
    value: Mapped[str] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MutationResult(Snapshot, Base):
    __tablename__ = "mutation_exercise_results"
    __table_args__ = (choices("side", "before", "after"),)
    session_id: Mapped[UUID] = mapped_column()
    plan_item_id: Mapped[UUID | None] = mapped_column()
    name: Mapped[str] = mapped_column(String(length=200))
    load_kg: Mapped[Decimal] = mapped_column(Numeric(precision=9, scale=4))
    reps: Mapped[int] = mapped_column(Integer())
    sets: Mapped[int] = mapped_column(Integer())
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MutationMedia(Snapshot, Base):
    __tablename__ = "mutation_media_assets"
    __table_args__ = (choices("side", "before", "after"),)
    session_id: Mapped[UUID | None] = mapped_column()
    original_session_id: Mapped[UUID | None] = mapped_column()
    original_plan_item_id: Mapped[UUID | None] = mapped_column()
    status: Mapped[str] = mapped_column(String(length=16))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MutationRequest(Snapshot, Base):
    __tablename__ = "mutation_change_requests"
    __table_args__ = (choices("side", "before", "after"),)
    kind: Mapped[str] = mapped_column(String(length=32))
    trainer_id: Mapped[UUID] = mapped_column()
    client_id: Mapped[UUID | None] = mapped_column()
    purchase_id: Mapped[UUID | None] = mapped_column()
    session_id: Mapped[UUID | None] = mapped_column()
    status: Mapped[str] = mapped_column(String(length=16))
