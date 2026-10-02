"""Per-person assessment occasions and immutable, versioned answer snapshots."""

from datetime import date, datetime
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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import ActorEvidence, Record, Versioned, choices


class AssessmentFormVersion(Base):
    __tablename__ = "assessment_form_versions"
    __table_args__ = (
        CheckConstraint("form_id ~ '^[a-z][a-z0-9_]{0,63}$'", name="form_identity"),
        CheckConstraint("length(btrim(title)) > 0", name="title_required"),
        CheckConstraint("source_sha256 ~ '^[0-9a-f]{64}$'", name="source_digest"),
        CheckConstraint("layout_sha256 ~ '^[0-9a-f]{64}$'", name="layout_digest"),
        CheckConstraint("length(btrim(layout_release)) > 0", name="layout_release_required"),
        CheckConstraint(
            "jsonb_typeof(definition) = 'object' AND octet_length(definition::text) <= 131072",
            name="definition_object",
        ),
    )
    form_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    source_filename: Mapped[str] = mapped_column(String(200))
    source_sha256: Mapped[str] = mapped_column(String(64))
    layout_release: Mapped[str] = mapped_column(String(64))
    layout_sha256: Mapped[str] = mapped_column(String(64))
    definition: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClientAssessment(ActorEvidence, Versioned, Base):
    __tablename__ = "client_assessments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["form_id", "form_version"],
            ["assessment_form_versions.form_id", "assessment_form_versions.version"],
        ),
        UniqueConstraint("id", "form_id", "form_version"),
        # The optimistic version is also the current revision pointer. A transaction
        # cannot commit either half of a save without the other half.
        ForeignKeyConstraint(
            ["id", "version"],
            ["client_assessment_revisions.assessment_id", "client_assessment_revisions.revision"],
            name="fk_assessment_current_revision",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        Index("ix_assessment_person_form_history", "client_person_id", "form_id", "created_at"),
    )
    client_person_id: Mapped[UUID] = mapped_column(ForeignKey("client_people.id"))
    form_id: Mapped[str] = mapped_column(String(64))
    form_version: Mapped[int] = mapped_column(Integer)


class ClientAssessmentRevision(ActorEvidence, Record, Base):
    __tablename__ = "client_assessment_revisions"
    __table_args__ = (
        UniqueConstraint("assessment_id", "revision"),
        ForeignKeyConstraint(
            ["assessment_id", "form_id", "form_version"],
            [
                "client_assessments.id",
                "client_assessments.form_id",
                "client_assessments.form_version",
            ],
        ),
        ForeignKeyConstraint(
            ["assessment_id", "previous_revision"],
            ["client_assessment_revisions.assessment_id", "client_assessment_revisions.revision"],
        ),
        CheckConstraint(
            "(revision = 1 AND previous_revision IS NULL) OR "
            "(revision > 1 AND previous_revision IS NOT NULL AND previous_revision = revision - 1)",
            name="revision_chain",
        ),
        choices("status", "draft", "completed", "voided"),
        choices("event", "draft", "completed", "correction", "voided"),
        CheckConstraint(
            "(event = 'draft' AND status = 'draft') OR "
            "(event IN ('completed', 'correction') AND status = 'completed') OR "
            "(event = 'voided' AND status = 'voided')",
            name="event_status",
        ),
        CheckConstraint(
            "(event IN ('correction', 'voided') AND reason IS NOT NULL "
            "AND length(btrim(reason)) BETWEEN 1 AND 2000) OR "
            "(event IN ('draft', 'completed') AND reason IS NULL)",
            name="reason_required",
        ),
        CheckConstraint(
            "length(btrim(client_name)) > 0 AND length(btrim(assessor_name)) > 0",
            name="snapshot_names",
        ),
        CheckConstraint(
            "jsonb_typeof(answers) = 'object' AND octet_length(answers::text) <= 65536",
            name="answers_object",
        ),
        Index("ix_assessment_revision_date", "assessment_date"),
    )
    assessment_id: Mapped[UUID] = mapped_column()
    revision: Mapped[int] = mapped_column(Integer)
    previous_revision: Mapped[int | None] = mapped_column(Integer)
    form_id: Mapped[str] = mapped_column(String(64))
    form_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    event: Mapped[str] = mapped_column(String(16))
    assessment_date: Mapped[date] = mapped_column(Date)
    assessor_id: Mapped[UUID] = mapped_column(ForeignKey("staff_users.id"), index=True)
    assessor_name: Mapped[str] = mapped_column(String(200))
    client_name: Mapped[str] = mapped_column(String(200))
    client_birthday: Mapped[date] = mapped_column(Date)
    answers: Mapped[dict] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
