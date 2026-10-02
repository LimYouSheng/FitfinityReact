"""Paper-version type boundaries, missing values and bounded health answers."""

import json
from pathlib import Path

import pytest

from app.assessment_validation import validate_answers

CATALOG = {
    row["form_id"]: row
    for row in json.loads(
        (
            Path(__file__).parents[1] / "migrations/definitions/20260921_assessments_v1.json"
        ).read_text()
    )
}


@pytest.mark.parametrize("form_id", sorted(CATALOG))
def test_each_form_accepts_only_its_typed_paper_answers(form_id):
    schema = CATALOG[form_id]["definition"]
    answers = {}
    for key, field in schema["fields"].items():
        answers[key] = (
            field["min"]
            if field["type"] == "number"
            else field["options"][0]
            if "options" in field
            else "Recorded observation"
        )
    assert validate_answers(answers, schema, completed=True) == answers
    assert validate_answers({}, schema, completed=False) == {}
    if form_id != "hurdle_step":
        with pytest.raises(ValueError):
            validate_answers({}, schema, completed=True)


@pytest.mark.parametrize(
    "value", ["0", True, None, [], {}, float("nan"), float("inf"), -1, 10**400]
)
def test_balance_numbers_are_strict_finite_nonnegative(value):
    with pytest.raises(ValueError, match="Invalid assessment answers"):
        validate_answers({"eyes_open_1": value}, CATALOG["balance"]["definition"], completed=True)


@pytest.mark.parametrize(
    "answers",
    [
        {"invented_question": "secret patient details"},
        {"health": "Unknown"},  # Not an option printed on the current physical form.
        {"medications": 42},
        {"medications": " \n\t"},
        {"medications": "x\x00y"},
        {"medications": "\ud800"},
        {"medications": "x" * 4001},
        {"stress": 11},
        {"sleep_hours": 25},
        {"condition_0": True},
        {"condition_0": "No"},
        [],
        None,
    ],
)
def test_invalid_health_answers_are_rejected_without_echoing_payloads(answers):
    with pytest.raises(ValueError) as result:
        validate_answers(answers, CATALOG["health_history"]["definition"], completed=True)
    assert str(result.value) == "Invalid assessment answers for this form version"


def test_realistic_long_answers_and_utf8_payload_limit():
    schema = CATALOG["health_history"]["definition"]
    answers = {"medications": "Owner recorded observation. " * 100, "sleep_hours": 0}
    assert validate_answers(answers, schema, completed=True) == answers
    fields = [key for key, field in schema["fields"].items() if field["type"] == "textarea"]
    with pytest.raises(ValueError):
        validate_answers({key: "🙂" * 4000 for key in fields[:5]}, schema, completed=True)


def test_unchecked_hurdle_and_zero_balance_are_explicit_valid_completions():
    schema = CATALOG["hurdle_step"]["definition"]
    assert len(schema["fields"]) == 6
    assert validate_answers({}, schema, completed=True) == {}
    assert validate_answers(
        {"eyes_open_1": 0}, CATALOG["balance"]["definition"], completed=True
    ) == {"eyes_open_1": 0}
    with pytest.raises(ValueError):
        validate_answers({"notes": "Old supplementary answer"}, schema, completed=True)
