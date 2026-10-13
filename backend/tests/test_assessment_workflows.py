"""Profile reads, interrupted saves and explicitly reviewed reassessment occasions."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.api import assessments
from app.api.schemas import NewAssessment
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.api import ApiReceipt, AssessmentAccess
from app.models.assessments import ClientAssessment, ClientAssessmentRevision
from app.models.people import Client, ClientPerson
from app.persistence import add_client
from tests.domain_fixtures import person
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_staff_api import api as api
from tests.test_staff_api import body, create, trainer_login
from tests.test_staff_api import person_id as person_id

pytestmark = pytest.mark.database


def overview(api, graph):
    return api.get(f"/api/clients/{graph['client_id']}/assessment-records")


def append(api, record, *, answers=None, event="completed", key=None, **extra):
    return api.post(
        f"/api/assessments/{record['assessment_id']}/revisions",
        json={
            "expectedVersion": record["revision"],
            "event": event,
            "answers": record["answers"] if answers is None else answers,
            **extra,
        },
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def reassessment(record, **patch):
    return body(
        previousAssessmentId=record["assessment_id"],
        expectedPreviousVersion=record["revision"],
        **patch,
    )


def test_profile_draft_resume_complete_and_actor_receipt(api, domain_db, graph, person_id):
    empty = overview(api, graph).json()
    assert empty["people"] == [{"id": str(person_id), "version": 1, "records": []}]
    key = uuid4()
    draft = create(api, person_id, body(event="draft", answers={}), key)
    assert draft.status_code == 200, draft.text
    assert draft.json()["status"] == "draft" and draft.json()["answers"] == {}
    assert api.get(f"/api/assessment-saves/{key}").json() == draft.json()
    assert overview(api, graph).json()["people"][0]["records"] == [draft.json()]
    completed_key = uuid4()
    completed = append(
        api, draft.json(), answers={"eyes_open_1": 0}, expectedPersonVersion=1, key=completed_key
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["assessment_id"] == draft.json()["assessment_id"]
    assert completed.json()["revision"] == 2 and completed.json()["answers"] == {"eyes_open_1": 0}
    assert api.get(f"/api/assessment-saves/{completed_key}").json() == completed.json()
    assert overview(api, graph).json()["people"][0]["records"] == [completed.json()]
    # The original receipt remains the original draft even after later completion.
    assert api.get(f"/api/assessment-saves/{key}").json() == draft.json()
    with domain_db.transaction() as session:
        audits = session.scalars(select(AssessmentAccess)).all()
        assert all(a.actor_id == graph["owner_id"] for a in audits)
        assert any(a.action == "replay" for a in audits)


def test_reassessment_keeps_previous_answers_and_history_uses_occasion_order(api, graph, person_id):
    first = create(api, person_id).json()
    newer = create(api, person_id, reassessment(first, answers={"eyes_open_1": 5})).json()
    assert newer["assessment_id"] != first["assessment_id"]
    # Correcting the older occasion later must not make it the overview's newest occasion.
    corrected = append(
        api,
        first,
        answers={"eyes_open_1": 2},
        event="correction",
        reason="Recorded value corrected",
    )
    assert corrected.status_code == 200, corrected.text
    assert overview(api, graph).json()["people"][0]["records"] == [newer]
    history = api.get(f"/api/people/{person_id}/assessments?formId=balance&limit=1").json()
    assert history["items"] == [newer] and history["hasMore"]
    assert api.get(f"/api/people/{person_id}/assessments?formId=balance&offset=1").json()[
        "items"
    ] == [corrected.json()]
    assert (
        api.get(f"/api/people/{person_id}/assessments?formId=health_history").json()["items"] == []
    )
    revisions = api.get(f"/api/assessments/{first['assessment_id']}/revisions").json()["items"]
    assert revisions[1] == first and revisions[0] == corrected.json()


def test_draft_must_resume_and_unreviewed_reassessment_never_creates(api, graph, person_id):
    draft = create(api, person_id, body(event="draft", answers={})).json()
    assert create(api, person_id, reassessment(draft)).status_code == 409
    assert create(api, person_id).status_code == 409
    assert overview(api, graph).json()["people"][0]["records"] == [draft]


def test_voided_occasion_is_retained_when_starting_a_reviewed_reassessment(api, graph, person_id):
    first = create(api, person_id).json()
    voided = append(api, first, event="voided", reason="Wrong assessment occasion").json()
    assert create(api, person_id, reassessment(first)).status_code == 409
    new = create(api, person_id, reassessment(voided, event="draft", answers={}))
    assert new.status_code == 200, new.text
    assert overview(api, graph).json()["people"][0]["records"] == [new.json()]
    assert api.get(f"/api/assessments/{first['assessment_id']}").json() == voided


def test_couple_overview_keeps_each_person_and_form_separate(api, domain_db, graph):
    with domain_db.transaction() as session:
        first, second = person("First Person"), person("Second Person")
        client = add_client(
            session,
            Client(kind="couple", name="Couple", trainer_id=graph["trainer_id"]),
            [first, second],
        )
        client_id, first_id, second_id = client.id, first.id, second.id
    a = create(api, first_id, body(answers={"eyes_open_1": 1})).json()
    b = create(api, second_id, body(answers={"eyes_open_1": 2})).json()
    records = api.get(f"/api/clients/{client_id}/assessment-records").json()["people"]
    assert records == [
        {"id": str(first_id), "version": 1, "records": [a]},
        {"id": str(second_id), "version": 1, "records": [b]},
    ]
    assert a["client_name"] == "First Person" and b["client_name"] == "Second Person"


@pytest.mark.parametrize(
    "patch",
    [
        {"expectedPreviousVersion": 1},
        {"previousAssessmentId": str(uuid4())},
        {"expectedPersonVersion": 9},
    ],
)
def test_stale_reassessment_review_rejected(api, person_id, patch):
    first = create(api, person_id).json()
    assert create(api, person_id, {**reassessment(first), **patch}).status_code == 409


@pytest.mark.parametrize(
    "patch",
    [
        {"previousAssessmentId": str(uuid4())},
        {"expectedPreviousVersion": 1},
        {"previousAssessmentId": str(uuid4()), "expectedPreviousVersion": True},
    ],
)
def test_incomplete_or_untyped_previous_review_rejected(api, person_id, patch):
    assert create(api, person_id, body(**patch)).status_code == 422


def test_reviewed_person_changes_block_draft_completion(api, domain_db, person_id):
    draft = create(api, person_id, body(event="draft", answers={})).json()
    with domain_db.transaction() as session:
        session.get(ClientPerson, person_id).name = "Renamed after review"
    assert (
        append(api, draft, answers={"eyes_open_1": 5}, expectedPersonVersion=1).status_code == 409
    )
    assert api.get(f"/api/assessments/{draft['assessment_id']}").json() == draft


def test_legacy_receipt_digest_remains_compatible(api, domain_db, person_id):
    key = uuid4()
    payload = body()
    result = create(api, person_id, payload, key)
    expected = hashlib.sha256(
        json.dumps(
            {
                "operation": "assessment_create",
                "target": str(person_id),
                "body": {**payload, "event": "completed"},
            },
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    with domain_db.transaction() as session:
        assert (
            session.scalar(select(ApiReceipt).where(ApiReceipt.request_key == key)).request_sha256
            == expected
        )
    assert create(api, person_id, payload, key).json() == result.json()


def test_legacy_revision_digest_keeps_null_reason_and_omits_new_optional_review(
    api, domain_db, person_id
):
    draft = create(api, person_id, body(event="draft", answers={})).json()
    key = uuid4()
    saved = append(api, draft, answers={"eyes_open_1": 1}, key=key)
    payload = {
        "expectedVersion": 1,
        "event": "completed",
        "answers": {"eyes_open_1": 1},
        "reason": None,
    }
    expected = hashlib.sha256(
        json.dumps(
            {"operation": "assessment_save", "target": draft["assessment_id"], "body": payload},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    with domain_db.transaction() as session:
        assert (
            session.scalar(select(ApiReceipt).where(ApiReceipt.request_key == key)).request_sha256
            == expected
        )
    assert append(api, draft, answers={"eyes_open_1": 1}, key=key).json() == saved.json()


def test_other_actor_receipts_hidden_and_admin_can_read_and_reassess(
    api, invitations, domain_db, graph, person_id, auth_service, auth_settings, fake_cognito
):
    admin_id = create_admin(api).json()["id"]
    key = uuid4()
    first = create(api, person_id, key=key).json()
    login_admin(api, auth_service, auth_settings, fake_cognito, admin_id)
    assert api.get(f"/api/assessment-saves/{key}").status_code == 404
    assert overview(api, graph).json()["people"][0]["records"] == [first]
    second = create(api, person_id, reassessment(first))
    assert second.status_code == 200 and second.json()["actor_id"] == admin_id


def test_assigned_trainer_cannot_read_overview_receipts_or_reassess(
    api, domain_db, graph, person_id, auth_service, auth_settings, fake_cognito
):
    key = uuid4()
    first = create(api, person_id, key=key).json()
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert overview(api, graph).status_code == 403
    assert api.get(f"/api/assessment-saves/{key}").status_code == 403
    assert create(api, person_id, reassessment(first)).status_code == 403


def test_concurrent_distinct_reassessments_require_review_of_the_newest_occasion(
    api, domain_db, graph, person_id
):
    first = create(api, person_id).json()
    principal = Principal(graph["owner_id"], "Owner", "owner", None)

    def submit(_):
        try:
            with domain_db.transaction() as session:
                return assessments.create(
                    session, principal, person_id, uuid4(), NewAssessment(**reassessment(first))
                )
        except AuthError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert sum(result == 409 for result in results) == 1
    with domain_db.transaction() as session:
        assert len(session.scalars(select(ClientAssessment)).all()) == 2
        assert len(session.scalars(select(ClientAssessmentRevision)).all()) == 4
