"""Durable retry receipts and sensitive-access audit; never duplicate assessment answers."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import ActorEvidence, Record, choices


class SessionBookingReceipt(ActorEvidence, Record, Base):
    __tablename__ = "session_booking_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("training_sessions.id"))
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"))
    purchase_id: Mapped[UUID] = mapped_column(ForeignKey("package_purchases.id"))
    message_id: Mapped[UUID | None] = mapped_column(ForeignKey("messages.id"))
    previous: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)


class SessionPostponementReceipt(ActorEvidence, Record, Base):
    __tablename__ = "session_postponement_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("training_sessions.id"))
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"))
    purchase_id: Mapped[UUID] = mapped_column(ForeignKey("package_purchases.id"))
    message_id: Mapped[UUID | None] = mapped_column(ForeignKey("messages.id"))
    request_id: Mapped[UUID | None] = mapped_column(ForeignKey("change_requests.id"))
    previous: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)


class SessionChangeReceipt(ActorEvidence, Record, Base):
    __tablename__ = "session_change_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("training_sessions.id"))
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"))
    purchase_id: Mapped[UUID] = mapped_column(ForeignKey("package_purchases.id"))
    message_id: Mapped[UUID | None] = mapped_column(ForeignKey("messages.id"))
    request_id: Mapped[UUID | None] = mapped_column(ForeignKey("change_requests.id"))
    previous: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)


class ApiReceipt(ActorEvidence, Record, Base):
    __tablename__ = "api_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        choices("operation", "assessment_create", "assessment_save"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    operation: Mapped[str] = mapped_column(String(32))
    request_sha256: Mapped[str] = mapped_column(String(64))
    revision_id: Mapped[UUID] = mapped_column(ForeignKey("client_assessment_revisions.id"))


class AssessmentAccess(ActorEvidence, Record, Base):
    __tablename__ = "assessment_access"
    __table_args__ = (choices("action", "list", "view", "history", "create", "save", "replay"),)
    client_person_id: Mapped[UUID] = mapped_column(ForeignKey("client_people.id"), index=True)
    action: Mapped[str] = mapped_column(String(16))
    assessment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("client_assessments.id"), index=True
    )


class PackageSaveReceipt(ActorEvidence, Record, Base):
    __tablename__ = "package_save_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    template_id: Mapped[UUID] = mapped_column(ForeignKey("package_templates.id"))
    result: Mapped[dict] = mapped_column(JSONB)


class TrainerApprovalReceipt(ActorEvidence, Record, Base):
    __tablename__ = "trainer_approval_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"))
    previous: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)


class ClientDetailReceipt(ActorEvidence, Record, Base):
    __tablename__ = "client_detail_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"))
    result: Mapped[dict] = mapped_column(JSONB)


class ClientNoteReceipt(ActorEvidence, Record, Base):
    __tablename__ = "client_note_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"))
    result: Mapped[dict] = mapped_column(JSONB)


class ClientNoteAccess(ActorEvidence, Record, Base):
    __tablename__ = "client_note_access"
    __table_args__ = (choices("action", "view", "save", "replay"),)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    action: Mapped[str] = mapped_column(String(16))


class TrainerRateReceipt(ActorEvidence, Record, Base):
    __tablename__ = "trainer_rate_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"))
    previous: Mapped[dict] = mapped_column(JSONB)
    rates: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)


class TrainerDetailReceipt(ActorEvidence, Record, Base):
    __tablename__ = "trainer_detail_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"))
    result: Mapped[dict] = mapped_column(JSONB)


class ClientCreateReceipt(ActorEvidence, Record, Base):
    __tablename__ = "client_create_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"))
    result: Mapped[dict] = mapped_column(JSONB)


class TrainerReactivationReceipt(ActorEvidence, Record, Base):
    __tablename__ = "trainer_reactivation_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"))
    result: Mapped[dict] = mapped_column(JSONB)


class ContentSaveReceipt(ActorEvidence, Record, Base):
    __tablename__ = "content_save_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    content_id: Mapped[UUID] = mapped_column(ForeignKey("content_entries.id"))
    previous: Mapped[dict | None] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)


class MessageReadReceipt(ActorEvidence, Record, Base):
    __tablename__ = "message_read_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    message_id: Mapped[UUID] = mapped_column(ForeignKey("messages.id"))
    result: Mapped[dict] = mapped_column(JSONB)


class RenewalDismissal(ActorEvidence, Record, Base):
    __tablename__ = "renewal_dismissals"
    message_id: Mapped[UUID] = mapped_column(ForeignKey("messages.id"), unique=True)


class RenewalDismissalReceipt(ActorEvidence, Record, Base):
    __tablename__ = "renewal_dismissal_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    message_id: Mapped[UUID] = mapped_column(ForeignKey("messages.id"))
    result: Mapped[dict] = mapped_column(JSONB)


class ClientDeactivationReceipt(ActorEvidence, Record, Base):
    __tablename__ = "client_deactivation_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"))
    previous: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)


class ClientReactivationReceipt(ActorEvidence, Record, Base):
    __tablename__ = "client_reactivation_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"))
    previous: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)


class RequestResolutionReceipt(ActorEvidence, Record, Base):
    __tablename__ = "request_resolution_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    change_request_id: Mapped[UUID] = mapped_column(ForeignKey("change_requests.id"))
    result: Mapped[dict] = mapped_column(JSONB)


class RequestCancellationReceipt(ActorEvidence, Record, Base):
    __tablename__ = "request_cancellation_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    change_request_id: Mapped[UUID] = mapped_column(ForeignKey("change_requests.id"))
    result: Mapped[dict] = mapped_column(JSONB)


class TrainerAvailabilityReceipt(ActorEvidence, Record, Base):
    __tablename__ = "trainer_availability_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"))
    previous: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)


class ClientRenewalReceipt(ActorEvidence, Record, Base):
    __tablename__ = "client_renewal_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"))
    purchase_id: Mapped[UUID] = mapped_column(ForeignKey("package_purchases.id"), unique=True)
    result: Mapped[dict] = mapped_column(JSONB)


class PackageReactivationReceipt(ActorEvidence, Record, Base):
    __tablename__ = "package_reactivation_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"))
    purchase_id: Mapped[UUID] = mapped_column(ForeignKey("package_purchases.id"))
    previous: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)


class ClientAssignmentReceipt(ActorEvidence, Record, Base):
    __tablename__ = "client_assignment_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"))
    event_id: Mapped[UUID] = mapped_column(ForeignKey("assignment_events.id"))
    previous: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)


class TrainerDeactivationReceipt(ActorEvidence, Record, Base):
    __tablename__ = "trainer_deactivation_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"))
    previous: Mapped[dict] = mapped_column(JSONB)
    replacements: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)


class ClientWeeklyScheduleReceipt(ActorEvidence, Record, Base):
    __tablename__ = "client_weekly_schedule_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "request_key"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    request_key: Mapped[UUID]
    request_sha256: Mapped[str] = mapped_column(String(64))
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"))
    purchase_id: Mapped[UUID] = mapped_column(ForeignKey("package_purchases.id"))
    previous: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)
