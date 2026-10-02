"""Shared storage types; domain records keep their own explicit columns and constraints."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


def choices(column: str, *values: str) -> CheckConstraint:
    return CheckConstraint(
        f"{column} IN ({', '.join(repr(value) for value in values)})", name=f"{column}_values"
    )


class Record:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Versioned(Record):
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @declared_attr.directive
    def __mapper_args__(cls):
        return {"version_id_col": cls.version}


class ActorEvidence:
    """Identity remains referential; the name records what the actor was called then."""

    actor_id: Mapped[UUID] = mapped_column(ForeignKey("staff_users.id"), index=True)
    actor_name: Mapped[str] = mapped_column(String(200))
