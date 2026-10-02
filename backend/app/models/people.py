"""Staff identities and single/couple client accounts; clients are not login users."""

from datetime import date, time
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import ActorEvidence, Record, Versioned, choices


class StaffUser(Versioned, Base):
    __tablename__ = "staff_users"
    __table_args__ = (
        choices("role", "owner", "admin", "trainer"),
        choices("status", "active", "inactive"),
        CheckConstraint("length(btrim(name)) > 0", name="name_required"),
        CheckConstraint(
            "email = lower(btrim(email)) AND position('@' in email) > 1", name="email_normalized"
        ),
        UniqueConstraint("id", "role"),
    )
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    role: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), server_default="active")


class StaffIdentity(Record, Base):
    __tablename__ = "staff_identities"
    __table_args__ = (
        choices("status", "active", "inactive"),
        UniqueConstraint("issuer", "subject"),
        UniqueConstraint("user_id", "issuer"),
        UniqueConstraint("id", "user_id"),
        CheckConstraint(
            "provider_username IS NULL OR length(btrim(provider_username)) > 0",
            name="provider_username_required",
        ),
        CheckConstraint(
            "length(btrim(issuer)) > 0 AND length(btrim(subject)) > 0", name="identity_required"
        ),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("staff_users.id"), index=True)
    issuer: Mapped[str] = mapped_column(String(512))
    subject: Mapped[str] = mapped_column(String(256))
    provider_username: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), server_default="active")


class Trainer(Versioned, Base):
    __tablename__ = "trainers"
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "user_role"], ["staff_users.id", "staff_users.role"]),
        CheckConstraint("user_role = 'trainer'", name="trainer_role"),
        choices("status", "active", "inactive"),
        choices("gender", "Female", "Male", "Other", "Prefer not to say"),
        CheckConstraint(
            "peak_rate_cents >= 0 AND off_peak_rate_cents >= 0", name="nonnegative_rates"
        ),
        CheckConstraint(
            "length(btrim(name)) > 0 AND length(btrim(trainer_type)) > 0", name="profile_required"
        ),
        CheckConstraint(
            "email = lower(btrim(email)) AND position('@' in email) > 1", name="email_normalized"
        ),
    )
    user_id: Mapped[UUID | None] = mapped_column(unique=True)
    user_role: Mapped[str] = mapped_column(String(16), server_default="trainer")
    name: Mapped[str] = mapped_column(String(200), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    phone_country_code: Mapped[str] = mapped_column(String(4))
    phone_number: Mapped[str] = mapped_column(String(32))
    birthday: Mapped[date] = mapped_column(Date)
    gender: Mapped[str] = mapped_column(String(24))
    trainer_type: Mapped[str] = mapped_column(String(120))
    qualifications: Mapped[str] = mapped_column(Text, server_default="")
    public_profile: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    status: Mapped[str] = mapped_column(String(16), server_default="active")
    peak_rate_cents: Mapped[int] = mapped_column(BigInteger)
    off_peak_rate_cents: Mapped[int] = mapped_column(BigInteger)
    approve_availability: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    approve_session_time: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    approve_session_trainer: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    approve_weekly_schedule: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class TrainerAvailability(Versioned, Base):
    __tablename__ = "trainer_availability"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6 AND starts_at < ends_at", name="valid_slot"),
        UniqueConstraint("trainer_id", "weekday", "starts_at", "ends_at"),
    )
    trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)  # ISO weekday: Monday=0.
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)


class Client(Versioned, Base):
    __tablename__ = "clients"
    __table_args__ = (
        choices("kind", "individual", "couple"),
        choices("status", "active", "inactive"),
        choices("gender_preference", "any", "female", "male"),
        CheckConstraint("length(btrim(name)) > 0", name="name_required"),
    )
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(400), index=True)
    status: Mapped[str] = mapped_column(String(16), server_default="active")
    trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"), index=True)
    gender_preference: Mapped[str] = mapped_column(String(16), server_default="any")
    remarks: Mapped[str] = mapped_column(Text, server_default="")
    lifecycle_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("lifecycle_events.id", use_alter=True)
    )


class ClientPerson(Versioned, Base):
    __tablename__ = "client_people"
    __table_args__ = (
        UniqueConstraint("client_id", "position"),
        CheckConstraint("position IN (1, 2)", name="person_position"),
        choices("gender", "Female", "Male", "Other", "Prefer not to say"),
        CheckConstraint(
            "length(btrim(name)) > 0 AND length(btrim(emergency_name)) > 0", name="names_required"
        ),
        CheckConstraint(
            "email = lower(btrim(email)) AND position('@' in email) > 1", name="email_normalized"
        ),
        choices(
            "emergency_relationship",
            "Spouse",
            "Parent",
            "Sibling",
            "Child",
            "Partner",
            "Friend",
            "Guardian",
            "Other",
        ),
    )
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200), index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    phone_country_code: Mapped[str] = mapped_column(String(4))
    phone_number: Mapped[str] = mapped_column(String(32))
    birthday: Mapped[date] = mapped_column(Date)
    gender: Mapped[str] = mapped_column(String(24))
    health_notes: Mapped[str] = mapped_column(Text, server_default="")
    emergency_name: Mapped[str] = mapped_column(String(200))
    emergency_relationship: Mapped[str] = mapped_column(String(24))
    emergency_country_code: Mapped[str] = mapped_column(String(4))
    emergency_number: Mapped[str] = mapped_column(String(32))


class LifecycleEvent(ActorEvidence, Record, Base):
    __tablename__ = "lifecycle_events"
    __table_args__ = (
        CheckConstraint("num_nonnulls(client_id, purchase_id, trainer_id) = 1", name="one_target"),
        choices("status", "active", "inactive"),
        choices("reason", "owner", "client", "client_reactivated"),
    )
    client_id: Mapped[UUID | None] = mapped_column(ForeignKey("clients.id"), index=True)
    purchase_id: Mapped[UUID | None] = mapped_column(ForeignKey("package_purchases.id"), index=True)
    trainer_id: Mapped[UUID | None] = mapped_column(ForeignKey("trainers.id"), index=True)
    status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(24))
    note: Mapped[str] = mapped_column(Text, server_default="")
    cause_id: Mapped[UUID | None] = mapped_column(ForeignKey("lifecycle_events.id"), index=True)


# Email matching is normalized at the write boundary; names remain searchable, not identities.
Index("ix_clients_name_folded", func.lower(Client.name))
Index("ix_trainers_name_folded", func.lower(Trainer.name))
