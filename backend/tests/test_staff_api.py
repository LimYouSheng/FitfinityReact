"""Real PostgreSQL + real HTTP/auth services; deterministic Cognito provider, no live AWS."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import Barrier
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.api.schemas import AssessmentRevision
from app.auth.errors import AuthError
from app.authorization import Principal, client_write, session_record, trainer_record
from app.main import create_app
from app.models.api import ApiReceipt, AssessmentAccess
from app.models.assessments import ClientAssessment, ClientAssessmentRevision
from app.models.people import (
    Client,
    ClientPerson,
    LifecycleEvent,
    StaffIdentity,
    StaffUser,
    Trainer,
)
from app.models.training import AssignmentEvent, PackagePurchase, TrainingSession
from app.persistence import add_client, add_purchase
from tests.domain_fixtures import person, purchase_parts

pytestmark = pytest.mark.database
ORIGIN = "https://staff.example"


@pytest.fixture
def api(auth_service, login, auth_settings, domain_db):
    result = login()
    app = create_app(auth_settings)
    with TestClient(app, base_url="https://testserver") as client:
        app.state.auth.provider.close()
        app.state.database.close()
        app.state.auth = auth_service
        app.state.database = domain_db
        client.cookies.set(auth_settings.session_cookie, result.session_handle)
        client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": result.body["csrfToken"]})
        yield client


@pytest.fixture
def person_id(domain_db, graph):
    with domain_db.transaction() as session:
        return session.scalar(
            select(ClientPerson.id).where(ClientPerson.client_id == graph["client_id"])
        )


def body(**patch):
    return {
        "formId": "balance",
        "formVersion": 1,
        "expectedPersonVersion": 1,
        "answers": {"eyes_open_1": 0},
        **patch,
    }


def create(api, person_id, payload=None, key=None):
    return api.post(
        f"/api/people/{person_id}/assessments",
        json=payload or body(),
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito):
    with domain_db.transaction() as session:
        user = session.get(StaffUser, graph["user_id"])
        email = user.email
        session.add(
            StaffIdentity(
                user_id=user.id,
                issuer=auth_settings.cognito_issuer,
                subject="trainer-subject",
                provider_username="trainer-username",
            )
        )
    fake_cognito.claims = {"sub": "trainer-subject", "username": "trainer-username"}
    fake_cognito.user_changes = {
        "Username": "trainer-username",
        "UserAttributes": [
            {"Name": "sub", "Value": "trainer-subject"},
            {"Name": "email_verified", "Value": "true"},
        ],
    }
    flow = auth_service.sign_in(email, "initial-password-value")
    signed = auth_service.challenge(flow.flow_handle, code="123456")
    api.cookies.clear()
    api.cookies.set(auth_settings.session_cookie, signed.session_handle)
    api.headers["X-CSRF-Token"] = signed.body["csrfToken"]


def test_owner_records_reads_and_audits_without_health_in_general_projection(
    api, domain_db, graph, person_id
):
    response = create(api, person_id)
    assert response.status_code == 200, response.text
    record = AssessmentRevision.model_validate(response.json())
    assert record.answers == {"eyes_open_1": 0}
    assert record.assessor_name == record.actor_name == "Owner Original"
    assert record.client_name == "Client One" and record.client_birthday == date(1990, 1, 1)
    assert record.status == "completed" and record.revision == 2
    assert record.assessment_date == datetime.now(UTC).astimezone(ZoneInfo("Asia/Singapore")).date()
    detail = api.get(f"/api/clients/{graph['client_id']}")
    assert detail.status_code == 200
    assert "health_notes" not in detail.text and "answers" not in detail.text
    assert detail.json()["people"][0]["id"] == str(person_id)
    assert api.get(f"/api/assessments/{record.assessment_id}").json() == response.json()
    history = api.get(f"/api/assessments/{record.assessment_id}/revisions?limit=1")
    assert history.json()["hasMore"] and len(history.json()["items"]) == 1
    assert api.get(f"/api/people/{person_id}/assessments").json()["items"] == [response.json()]
    assert api.get("/api/assessment-forms").json()["items"][0]["version"] == 1
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ApiReceipt)) == 1
        assert session.scalar(select(func.count()).select_from(AssessmentAccess)) == 4
        for event in session.scalars(select(AssessmentAccess)):
            assert event.actor_id == graph["owner_id"]
            assert not hasattr(event, "answers")


def test_duplicate_retry_returns_original_result_and_conflicting_reuse_never_mutates(
    api, domain_db, person_id
):
    key = uuid4()
    first = create(api, person_id, key=key)
    assert first.status_code == 200
    again = create(api, person_id, key=key)
    assert again.status_code == 200 and again.json() == first.json()
    changed = create(api, person_id, body(answers={"eyes_open_1": 9}), key)
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "idempotency_conflict"
    assert create(api, person_id).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ClientAssessmentRevision)) == 2
        assert session.scalar(select(func.count()).select_from(ApiReceipt)) == 1


def test_draft_completion_correction_void_and_historical_retry_are_atomic(
    api, domain_db, person_id
):
    initial = create(api, person_id, body(event="draft", answers={})).json()
    path = f"/api/assessments/{initial['assessment_id']}/revisions"
    key = str(uuid4())
    payload = {"expectedVersion": 1, "event": "completed", "answers": {"eyes_open_1": 0}}
    completed = api.post(path, json=payload, headers={"Idempotency-Key": key})
    assert completed.status_code == 200
    saved = completed.json()
    stale = api.post(path, json=payload, headers={"Idempotency-Key": str(uuid4())})
    assert stale.status_code == 409
    corrected = api.post(
        path,
        json={
            "expectedVersion": 2,
            "event": "correction",
            "answers": {"eyes_open_1": 3},
            "reason": "Transcription correction",
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert corrected.status_code == 200
    assert corrected.json()["assessment_date"] == saved["assessment_date"]
    assert api.post(path, json=payload, headers={"Idempotency-Key": key}).json() == saved
    void = api.post(
        path,
        json={
            "expectedVersion": 3,
            "event": "voided",
            "answers": {"eyes_open_1": 3},
            "reason": "Wrong occasion",
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert void.status_code == 200 and void.json()["status"] == "voided"
    assert (
        api.post(
            path,
            json={"expectedVersion": 4, "event": "draft", "answers": {}},
            headers={"Idempotency-Key": str(uuid4())},
        ).status_code
        == 409
    )
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ClientAssessmentRevision)) == 4


@pytest.mark.parametrize(
    "payload",
    [
        body(answers={}),
        body(answers={"eyes_open_1": "0"}),
        body(answers={"eyes_open_1": -1}),
        body(answers={"secret": "private-health-sentinel"}),
        body(formVersion=999),
        body(expectedPersonVersion=2),
    ],
)
def test_invalid_or_stale_creation_rolls_back_all_records(api, domain_db, person_id, payload):
    response = create(api, person_id, payload)
    assert response.status_code in {409, 422}
    assert "private-health-sentinel" not in response.text
    with domain_db.transaction() as session:
        for model in [ClientAssessment, ClientAssessmentRevision, ApiReceipt, AssessmentAccess]:
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_unchecked_hurdle_completion_and_couple_person_ids_stay_independent(api, domain_db, graph):
    with domain_db.transaction() as session:
        first, second = person("Partner One"), person("Partner Two")
        add_client(
            session,
            Client(kind="couple", name="Couple", trainer_id=graph["trainer_id"]),
            [first, second],
        )
        ids = [first.id, second.id]
    one = create(api, ids[0], body(formId="hurdle_step", answers={}))
    two = create(api, ids[1], body(formId="hurdle_step", answers={}))
    assert one.status_code == two.status_code == 200
    assert one.json()["assessment_id"] != two.json()["assessment_id"]
    assert one.json()["client_name"] == "Partner One" and two.json()["client_name"] == "Partner Two"


def test_inactive_clients_retain_owner_history_and_reject_writes(api, domain_db, graph, person_id):
    saved = create(api, person_id).json()
    with domain_db.transaction() as session:
        event = LifecycleEvent(
            client_id=graph["client_id"],
            status="inactive",
            reason="owner",
            actor_id=graph["owner_id"],
            actor_name="Owner Original",
        )
        session.add(event)
        session.flush()
        effect = LifecycleEvent(
            purchase_id=graph["purchase_id"],
            status="inactive",
            reason="client",
            cause_id=event.id,
            actor_id=graph["owner_id"],
            actor_name="Owner Original",
        )
        session.add(effect)
        session.flush()
        purchase = session.get(PackagePurchase, graph["purchase_id"])
        client = session.get(Client, graph["client_id"])
        client.status, client.lifecycle_event_id = "inactive", event.id
        purchase.status, purchase.lifecycle_event_id = "inactive", effect.id
    assert api.get(f"/api/assessments/{saved['assessment_id']}").status_code == 200
    assert create(api, person_id, body(formId="hurdle_step", answers={})).status_code == 409


def test_trainers_are_scoped_and_sensitive_forms_are_denied(
    api, domain_db, graph, person_id, auth_settings, auth_service, fake_cognito
):
    saved = create(api, person_id).json()
    with domain_db.transaction() as session:
        stranger = add_client(
            session,
            Client(kind="individual", name="Stranger", trainer_id=graph["trainer_id"]),
            [person("Stranger")],
        )
        # Another trainer establishes a different assignment.
        source = session.get(Trainer, graph["trainer_id"])
        other = Trainer(
            **{
                column.name: getattr(source, column.name)
                for column in Trainer.__table__.columns
                if column.name
                not in {"id", "user_id", "email", "created_at", "updated_at", "version"}
            }
        )
        other.email = "other@example.test"
        session.add(other)
        session.flush()
        stranger.trainer_id = other.id
        other_id, stranger_id = other.id, stranger.id
        session.flush()
        purchase, slots, preferences, bookings = purchase_parts(
            {**graph, "trainer_id": other.id}, client_id=stranger.id
        )
        add_purchase(
            session,
            purchase,
            slots,
            preferences,
            bookings,
            expected_client_version=stranger.version,
        )
        foreign_session = bookings[0].id
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    listed = api.get("/api/clients?role=owner")
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [str(graph["client_id"])]
    assert api.get(f"/api/clients/{graph['client_id']}").status_code == 200
    assert api.get(f"/api/sessions/{graph['session_id']}").status_code == 200
    assert api.get(f"/api/trainers/{graph['trainer_id']}").status_code == 200
    assert api.get(f"/api/trainers/{other_id}").status_code == 404
    assert api.get(f"/api/sessions/{foreign_session}").status_code == 404
    assert {item["id"] for item in api.get("/api/sessions?role=owner").json()["items"]} == {
        str(graph["session_id"]),
        str(graph["second_session_id"]),
    }
    hidden = api.get(f"/api/clients/{stranger_id}")
    missing = api.get(f"/api/clients/{uuid4()}")
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json()["error"]["code"] == missing.json()["error"]["code"]
    assert "Stranger" not in hidden.text
    with domain_db.transaction() as session:
        session.add(
            AssignmentEvent(
                client_id=stranger_id,
                old_trainer_id=graph["trainer_id"],
                new_trainer_id=other_id,
                old_trainer_name="Trainer One",
                new_trainer_name="Other",
                client_version=1,
                actor_id=graph["owner_id"],
                actor_name="Owner Original",
            )
        )
    assert api.get(f"/api/clients/{stranger_id}").status_code == 200
    assert api.get(f"/api/sessions/{foreign_session}").status_code == 404
    for path in [
        "/api/assessment-forms",
        f"/api/people/{person_id}/assessments",
        f"/api/assessments/{saved['assessment_id']}",
        f"/api/assessments/{saved['assessment_id']}/revisions",
    ]:
        assert api.get(path).status_code == 403
    assert create(api, person_id).status_code == 403
    with domain_db.transaction() as session:
        session.get(Client, graph["client_id"]).trainer_id = other_id
    # Historical session assignment permits basic history, never coaching edits or health access.
    assert api.get(f"/api/clients/{graph['client_id']}").status_code == 200
    with pytest.raises(AuthError) as error, domain_db.transaction() as session:
        client_write(
            session,
            Principal(graph["user_id"], "Trainer", "trainer", graph["trainer_id"]),
            graph["client_id"],
            coaching=True,
        )
    assert error.value.status == 404


@pytest.mark.parametrize("change", ["role", "staff_inactive", "identity_inactive", "logout"])
def test_authority_is_rechecked_after_provider_verification_before_domain_use(
    api, domain_db, graph, person_id, auth_service, change, monkeypatch
):
    original = auth_service.principal

    def race(handle):
        result = original(handle)
        with domain_db.transaction() as session:
            if change == "role":
                session.get(StaffUser, graph["owner_id"]).role = "trainer"
            elif change == "staff_inactive":
                session.get(StaffUser, graph["owner_id"]).status = "inactive"
            elif change == "identity_inactive":
                session.get(StaffIdentity, result[1].identity_id).status = "inactive"
        if change == "logout":
            auth_service.sign_out(handle)
        return result

    monkeypatch.setattr(auth_service, "principal", race)
    assert create(api, person_id).status_code == 401
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ClientAssessment)) == 0


def test_missing_csrf_and_client_supplied_metadata_fail_without_writes(api, domain_db, person_id):
    saved = api.headers.pop("X-CSRF-Token")
    assert create(api, person_id).status_code == 403
    api.headers["X-CSRF-Token"] = saved
    for extra in [
        {"actorId": str(uuid4())},
        {"assessor": "Other"},
        {"assessmentDate": "2000-01-01"},
    ]:
        assert create(api, person_id, body(**extra)).status_code == 422
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ApiReceipt)) == 0


def test_access_and_retry_evidence_prevent_destructive_downgrade(
    api, domain_db, person_id, migrate
):
    saved = create(api, person_id).json()
    with pytest.raises(DBAPIError, match="downgrade refused"):
        migrate("downgrade", "20260921_0004")
    with pytest.raises(IntegrityError, match="immutable"), domain_db.transaction() as session:
        session.execute(text("DELETE FROM api_receipts"))
    with pytest.raises(IntegrityError, match="immutable"), domain_db.transaction() as session:
        session.execute(text("UPDATE assessment_access SET action='list'"))
    assert api.get(f"/api/assessments/{saved['assessment_id']}").status_code == 200


def test_owner_only_and_terminal_session_write_policy(domain_db, graph):
    principal = Principal(graph["user_id"], "Trainer", "trainer", graph["trainer_id"])
    with pytest.raises(AuthError) as error, domain_db.transaction() as session:
        client_write(session, principal, graph["client_id"])
    assert error.value.status == 403
    with domain_db.transaction() as session:
        assert client_write(session, principal, graph["client_id"], coaching=True)
        assert trainer_record(session, principal, graph["trainer_id"], write=True)
        session.get(TrainingSession, graph["session_id"]).status = "cancelled"
    with pytest.raises(AuthError) as error, domain_db.transaction() as session:
        session_record(session, principal, graph["session_id"], write=True)
    assert error.value.status == 409


def test_two_native_http_duplicate_saves_commit_once(api, person_id):
    key = str(uuid4())
    barrier = Barrier(2)

    def submit():
        barrier.wait(timeout=3)
        return create(api, person_id, key=key)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert [response.status_code for response in results] == [200, 200]
    assert results[0].json() == results[1].json()
