"""Strict answers against the immutable database registry, independent of paper coordinates."""

import json
import math

from pydantic import (
    RootModel,
    StrictFloat,
    StrictInt,
    StrictStr,
    ValidationError,
    ValidationInfo,
    model_validator,
)


class AssessmentAnswers(RootModel[dict[str, StrictStr | StrictInt | StrictFloat]]):
    @model_validator(mode="after")
    def validate_definition(self, info: ValidationInfo):
        definition = (info.context or {}).get("definition")
        if not isinstance(definition, dict):
            raise ValueError("An approved assessment definition is required")
        fields = definition["fields"]
        for key, value in self.root.items():
            field = fields.get(key)
            if field is None:
                raise ValueError("Unsupported assessment field")
            if field["type"] == "number":
                try:
                    finite = type(value) in (int, float) and math.isfinite(value)
                except OverflowError:
                    finite = False
                if not finite:
                    raise ValueError("A finite JSON number is required")
                if value < field["min"] or ("max" in field and value > field["max"]):
                    raise ValueError("Assessment number is out of range")
            elif not isinstance(value, str) or not value.strip() or "\x00" in value:
                raise ValueError("Omit unanswered fields; use nonblank text for answers")
            elif "options" in field:
                if value not in field["options"]:
                    raise ValueError("Unsupported assessment choice")
            elif len(value) > field["max_length"]:
                raise ValueError("Assessment text is too long")
        # PostgreSQL JSONB adds spaces after separators and outputs Unicode literally.
        # The DB check is authoritative for its serialized representation as well.
        try:
            encoded = json.dumps(self.root, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (ValueError, UnicodeError):
            raise ValueError("Assessment answers must be finite UTF-8 JSON") from None
        if len(encoded) > definition["max_bytes"]:
            raise ValueError("Assessment answers are too large")
        if (
            (info.context or {}).get("completed")
            and not self.root
            and not definition["allow_empty_completion"]
        ):
            raise ValueError("Record at least one answer before completing this form")
        return self


def validate_answers(answers: object, definition: dict, *, completed: bool) -> dict:
    try:
        return AssessmentAnswers.model_validate(
            answers, strict=True, context={"definition": definition, "completed": completed}
        ).root
    except ValidationError:
        # Keep answer contents out of error messages/logs at this internal boundary.
        raise ValueError("Invalid assessment answers for this form version") from None
