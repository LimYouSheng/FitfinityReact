"""Cleared profile fields stay missing; assessment identity snapshots remain truthful."""

import copy

import pytest
from sqlalchemy.exc import DBAPIError

from app.models.people import Client
from app.persistence import add_client
from tests.domain_fixtures import person
from tests.test_client_details import payload, save
from tests.test_staff_api import api as api
from tests.test_staff_api import body as assessment_body
from tests.test_staff_api import create as create_assessment

pytestmark = pytest.mark.database


@pytest.mark.parametrize(
    "patch",
    [
        {"email": ""},
        {"birthday": ""},
        {"birthday": None},
        {"gender": ""},
        {"phone": {"countryCode": "+65", "number": ""}},
        {"emergencyContact": {"name": "", "relationship": "", "countryCode": "+65", "number": ""}},
    ],
)
def test_optional_fields_clear_and_read_back_without_fabricated_defaults(api, graph, patch):
    body = payload(api, graph)
    body["people"][0].update(patch)
    response = save(api, graph, body)
    assert response.status_code == 200, response.text
    row = next(
        c for c in api.get("/api/directory").json()["clients"] if c["id"] == str(graph["client_id"])
    )["people"][0]
    for field, value in patch.items():
        if field == "birthday":
            assert row[field] is None
        elif field == "phone":
            assert row["phone_country_code"] == "+65"
            assert row["phone_number"] == ""
        elif field == "emergencyContact":
            assert all(
                row[k] == ""
                for k in [
                    "emergency_name",
                    "emergency_relationship",
                    "emergency_number",
                ]
            )
            assert row["emergency_country_code"] == "+65"
        else:
            assert row[field] == value


def test_missing_birthday_blocks_new_assessment_but_preserves_correction_identity(api, graph):
    body = payload(api, graph)
    person_id = body["people"][0]["id"]
    original = create_assessment(api, person_id)
    assert original.status_code == 200, original.text
    original = original.json()
    body["people"][0]["birthday"] = ""
    assert save(api, graph, body).status_code == 200
    after = payload(api, graph)
    revision = after["people"][0]["expectedVersion"]
    response = create_assessment(
        api,
        person_id,
        assessment_body(
            formId="hurdle_step",
            expectedPersonVersion=revision,
            answers={},
        ),
    )
    assert response.status_code == 409, response.text
    correction = api.post(
        f"/api/assessments/{original['assessment_id']}/revisions",
        json={
            "expectedVersion": original["revision"],
            "event": "correction",
            "answers": {"eyes_open_1": 1},
            "reason": "Corrected observation",
        },
        headers={"Idempotency-Key": "10000000-0000-4000-8000-000000009900"},
    )
    assert correction.status_code == 200, correction.text
    assert correction.json()["client_birthday"] == original["client_birthday"]
    assert correction.json()["client_name"] == original["client_name"]
    after["people"][0]["birthday"] = "1990-01-01"
    assert save(api, graph, after).status_code == 200
    current = payload(api, graph)
    assert (
        create_assessment(
            api,
            person_id,
            assessment_body(
                formId="hurdle_step",
                expectedPersonVersion=current["people"][0]["expectedVersion"],
                answers={},
            ),
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("email", ""),
        ("birthday", None),
        ("gender", ""),
        ("emergency_name", ""),
    ],
)
def test_onboarding_still_requires_complete_identity_and_contact(domain_db, graph, field, value):
    new_person = person()
    setattr(new_person, field, value)
    with (
        pytest.raises(ValueError, match="Complete each client's"),
        domain_db.transaction() as session,
    ):
        add_client(
            session,
            Client(kind="individual", name="New Client", trainer_id=graph["trainer_id"]),
            [new_person],
        )


def test_downgrade_refuses_cleared_contact_fields_without_deleting_any_record(api, graph, migrate):
    body = copy.deepcopy(payload(api, graph))
    body["people"][0]["birthday"] = None
    assert save(api, graph, body).status_code == 200
    with pytest.raises(DBAPIError, match="Optional contacts downgrade refused"):
        migrate("downgrade", "20261013_0009")
    assert payload(api, graph)["people"][0]["birthday"] is None
