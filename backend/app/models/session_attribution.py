"""Stable Trainer attribution survives retirement of a live session booking."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SessionTrainerAttribution(Base):
    __tablename__ = "session_trainer_attributions"
    __table_args__ = (
        CheckConstraint(
            "(original_state = 'captured' AND original_trainer_id IS NOT NULL) OR "
            "(original_state = 'legacy_unresolved' AND original_trainer_id IS NULL)",
            name="original_evidence",
        ),
    )
    session_id: Mapped[UUID] = mapped_column(ForeignKey("session_identities.id"), primary_key=True)
    original_trainer_id: Mapped[UUID | None] = mapped_column(ForeignKey("trainers.id"))
    performed_by_trainer_id: Mapped[UUID | None] = mapped_column(ForeignKey("trainers.id"))
    original_state: Mapped[str] = mapped_column(String(24))


class SessionTrainerAssignmentHistory(Base):
    """One immutable assignment edge references its original actor/time/reason evidence."""

    __tablename__ = "session_trainer_assignment_history"
    event_id: Mapped[UUID] = mapped_column(ForeignKey("session_events.id"), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("session_identities.id"), index=True)
    old_trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"))
    new_trainer_id: Mapped[UUID] = mapped_column(ForeignKey("trainers.id"))
