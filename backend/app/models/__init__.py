"""Register the complete canonical M5.2 metadata for migrations and repositories."""

from sqlalchemy import CheckConstraint

from app.database import Base
from app.models import (
    api,
    assessments,
    authentication,
    communications,
    evidence,
    media,
    people,
    staff,
    training,
)

for table in Base.metadata.tables.values():
    if "version" in table.c:
        table.append_constraint(CheckConstraint("version > 0", name="positive_version"))
    if "actor_name" in table.c:
        table.append_constraint(
            CheckConstraint("length(btrim(actor_name)) > 0", name="actor_name_required")
        )
    for prefix in ("phone", "emergency"):
        code, number = f"{prefix}_country_code", f"{prefix}_number"
        if prefix == "emergency":
            code = "emergency_country_code"
        if code in table.c and number in table.c:
            table.append_constraint(
                CheckConstraint(
                    f"{code} ~ '^\\+[1-9][0-9]{{0,2}}$' AND {number} ~ '^[0-9 ()-]+$' "
                    f"AND length(regexp_replace({number}, '[^0-9]', '', 'g')) >= 6 "
                    f"AND length(regexp_replace({code} || {number}, '[^0-9]', '', 'g')) <= 15",
                    name=f"{prefix}_format",
                )
            )

__all__ = [
    "api",
    "assessments",
    "authentication",
    "communications",
    "evidence",
    "media",
    "people",
    "staff",
    "training",
]
