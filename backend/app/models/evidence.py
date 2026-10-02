"""Approved pay and export evidence use typed, immutable snapshots and integer cents."""

from datetime import date, time
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import ActorEvidence, Record, choices


class RemunerationApproval(ActorEvidence, Record, Base):
    __tablename__ = "remuneration_approvals"
    __table_args__ = (
        UniqueConstraint("trainer_id", "cycle_key"),
        UniqueConstraint("id", "trainer_id"),
        CheckConstraint(
            "cycle_key ~ '^[0-9]{4}-(0[1-9]|1[0-2])$' AND cycle_start < cycle_end AND "
            "payout_date > cycle_end",
            name="cycle_dates",
        ),
        CheckConstraint(
            "amount_cents >= 0 AND total_minutes >= 0 AND session_count > 0", name="pay_bounds"
        ),
        CheckConstraint(
            "currency = 'SGD' AND source_sha256 ~ '^[0-9a-f]{64}$'", name="evidence_format"
        ),
    )
    trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"), index=True)
    trainer_name: Mapped[str] = mapped_column(String(200))
    cycle_key: Mapped[str] = mapped_column(String(7))
    cycle_start: Mapped[date] = mapped_column(Date)
    cycle_end: Mapped[date] = mapped_column(Date)
    payout_date: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), server_default="SGD")
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    total_minutes: Mapped[int] = mapped_column(Integer)
    session_count: Mapped[int] = mapped_column(Integer)
    source_sha256: Mapped[str] = mapped_column(String(64))
    # Set and checked by the database: approval rows cannot be appended in a later transaction.
    created_xid: Mapped[str] = mapped_column(
        Text, server_default=text("pg_current_xact_id()::text")
    )


class RemunerationLine(Record, Base):
    __tablename__ = "remuneration_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["approval_id", "trainer_id"],
            ["remuneration_approvals.id", "remuneration_approvals.trainer_id"],
        ),
        ForeignKeyConstraint(
            ["session_id", "purchase_id", "client_id"],
            [
                "training_sessions.id",
                "training_sessions.purchase_id",
                "training_sessions.client_id",
            ],
        ),
        ForeignKeyConstraint(
            ["acknowledgement_id", "session_id"],
            ["acknowledgements.id", "acknowledgements.session_id"],
        ),
        UniqueConstraint("approval_id", "session_id"),
        UniqueConstraint("session_id"),
        choices("band", "peak", "off_peak"),
        choices("acknowledgement_method", "signature", "late_no_show"),
        CheckConstraint(
            "amount_cents >= 0 AND minutes >= 0 AND starts_at < ends_at AND session_version > 0",
            name="pay_bounds",
        ),
        CheckConstraint("source_sha256 ~ '^[0-9a-f]{64}$'", name="evidence_digest"),
    )
    approval_id: Mapped[UUID] = mapped_column(index=True)
    trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"), index=True)
    session_id: Mapped[UUID] = mapped_column(index=True)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"))
    purchase_id: Mapped[UUID] = mapped_column(ForeignKey("package_purchases.id"))
    client_name: Mapped[str] = mapped_column(String(400))
    client_kind: Mapped[str] = mapped_column(String(16))
    training_date: Mapped[date] = mapped_column(Date)
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)
    session_version: Mapped[int] = mapped_column(Integer)
    acknowledgement_id: Mapped[UUID] = mapped_column()
    acknowledgement_method: Mapped[str] = mapped_column(String(16))
    band: Mapped[str] = mapped_column(String(16))
    minutes: Mapped[int] = mapped_column(Integer)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    source_sha256: Mapped[str] = mapped_column(String(64))


class ReportAudit(ActorEvidence, Record, Base):
    __tablename__ = "report_audit"
    __table_args__ = (
        ForeignKeyConstraint(
            ["purchase_id", "client_id"], ["package_purchases.id", "package_purchases.client_id"]
        ),
        choices("kind", "pdf_export", "pdf_share_opened", "whatsapp_opened", "csv_export"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_digest"),
    )
    client_id: Mapped[UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    purchase_id: Mapped[UUID | None] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(String(24))
    request_sha256: Mapped[str] = mapped_column(String(64))
