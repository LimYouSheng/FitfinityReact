"""Atomic onboarding, actor receipts, scheduling races and private initial assessments."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import time
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.api.client_creation import CreateClient
from app.api.client_creation import create as command
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.api import ClientCreateReceipt
from app.models.assessments import ClientAssessmentRevision
from app.models.communications import Message
from app.models.people import Client, ClientPerson
from app.models.training import PackagePurchase, TrainingSession
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_client_matching import declared_hours, request_body
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def body(graph):
    value = request_body(graph)
    value["clientPreferences"][0].update({"from": "11:00", "to": "12:00"})
    return {
        **value,
        "type": "Individual",
        "trainerId": str(graph["trainer_id"]),
        "trainerVersion": 1,
        "fixedWeeklySchedule": [
            {"day": value["clientPreferences"][0]["days"][0], "from": "11:00", "to": "12:00"}
        ],
        "remarks": "Reviewed onboarding",
        "people": [
            {
                "name": " New Client ",
                "email": "NEW@EXAMPLE.TEST",
                "birthday": "1990-01-01",
                "gender": "Female",
                "phone": {"countryCode": "+65", "number": "91234567"},
                "emergencyContact": {
                    "name": "Contact",
                    "relationship": "Friend",
                    "countryCode": "+65",
                    "number": "91234568",
                },
                "healthNotes": "General note",
                "assessments": [
                    {
                        "formId": "balance",
                        "formVersion": 1,
                        "assessmentDate": "2026-10-01",
                        "answers": {"eyes_open_1": 0},
                    }
                ],
            }
        ],
    }


def post(api, graph, payload=None, key=None):
    return api.post(
        "/api/clients",
        json=payload or body(graph),
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_create_is_atomic_replayable_and_private(api, domain_db, graph, migrate):
    declared_hours(domain_db, graph)
    key = uuid4()
    response = post(api, graph, key=key)
    assert response.status_code == 200, response.text
    result = response.json()
    assert set(result) == {"id", "version", "purchaseId"} and result["version"] == 2
    assert post(api, graph, key=key).json() == result
    assert api.get(f"/api/client-creations/{key}").json() == result
    directory = api.get("/api/directory").json()
    client = next(c for c in directory["clients"] if c["id"] == result["id"])
    assert client["name"] == "New Client" and client["people"][0]["email"] == "new@example.test"
    assert "answers" not in str(client) and "health_notes" not in str(client)
    with domain_db.transaction() as session:
        purchase = session.get(PackagePurchase, UUID(result["purchaseId"]))
        assert (
            purchase.total_sessions == 2 and purchase.validity_days == 90 and not purchase.free_gym
        )
        assert purchase.stage == "current" and purchase.name == "Two sessions"
        bookings = session.scalars(
            select(TrainingSession)
            .where(TrainingSession.purchase_id == purchase.id)
            .order_by(TrainingSession.session_number)
        ).all()
        assert len(bookings) == 2 and bookings[0].training_date == graph["start_date"]
        assert all(b.starts_at == time(11) and b.ends_at == time(12) for b in bookings)
        person = session.scalar(
            select(ClientPerson).where(ClientPerson.client_id == UUID(result["id"]))
        )
        assert person.health_notes == "General note"
        revision = session.scalar(
            select(ClientAssessmentRevision).where(
                ClientAssessmentRevision.client_name == "New Client",
                ClientAssessmentRevision.status == "completed",
            )
        )
        assert revision.answers == {"eyes_open_1": 0} and revision.actor_id == graph["owner_id"]
        assert str(revision.assessment_date) == "2026-10-01"
        assert session.scalar(select(func.count()).select_from(ClientCreateReceipt)) == 1
        assert set(session.scalars(select(Message.kind))) == {
            "client_created",
            "client_assignment",
            "renewal",
        }
    changed = body(graph)
    changed["remarks"] = "different"
    assert post(api, graph, changed, key).status_code == 409
    with pytest.raises(DBAPIError, match="immutable"):
        with domain_db.transaction() as session:
            session.execute(text("UPDATE client_create_receipts SET result = '{}'::jsonb"))
    with pytest.raises(DBAPIError, match="populated attribution downgrade refused"):
        migrate("downgrade", "20261013_0014")


def test_couple_keeps_each_identity_and_assessment_actor(api, domain_db, graph):
    declared_hours(domain_db, graph)
    payload = body(graph)
    payload["type"] = "Couple"
    second = deepcopy(payload["people"][0])
    second["name"] = "Partner"
    second["assessments"] = []
    payload["people"].append(second)
    response = post(api, graph, payload)
    assert response.status_code == 200, response.text
    client = api.get(f"/api/clients/{response.json()['id']}").json()
    assert client["name"] == "New Client & Partner" and len(client["people"]) == 2
    assert len({p["id"] for p in client["people"]}) == 2


@pytest.mark.parametrize(
    "kind",
    [
        "assessment",
        "schedule",
        "missing_hours",
        "package_version",
        "trainer_version",
        "gender",
        "people",
        "email",
        "phone",
        "actor",
    ],
)
def test_rejections_leave_no_partial_client_or_purchase(api, domain_db, graph, kind):
    if kind != "missing_hours":
        declared_hours(domain_db, graph)
    payload = body(graph)
    if kind == "assessment":
        payload["people"][0]["assessments"][0]["answers"] = {"eyes_open_1": -1}
    if kind == "schedule":
        payload["fixedWeeklySchedule"][0]["from"] = "10:00"
    if kind == "package_version":
        payload["packageVersion"] = 2
    if kind == "trainer_version":
        payload["trainerVersion"] = 2
    if kind == "gender":
        payload["genderPreference"] = "Female trainer preferred"
    if kind == "people":
        payload["type"] = "Couple"
    if kind == "email":
        payload["people"][0]["email"] = "bad"
    if kind == "phone":
        payload["people"][0]["phone"]["number"] = ""
    if kind == "actor":
        payload["actorId"] = str(graph["owner_id"])
    response = post(api, graph, payload)
    assert response.status_code in {409, 422}, response.text
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(Client)) == 1
        assert session.scalar(select(func.count()).select_from(PackagePurchase)) == 1
        assert session.scalar(select(func.count()).select_from(TrainingSession)) == 2
        assert session.scalar(select(func.count()).select_from(ClientCreateReceipt)) == 0


def test_concurrent_exact_retry_creates_once_and_competing_slot_loses(domain_db, graph):
    declared_hours(domain_db, graph)
    principal = Principal(graph["owner_id"], "Owner Original", "owner", None)
    key = uuid4()

    def run(request_key):
        try:
            with domain_db.transaction() as session:
                return command(
                    session, principal, request_key, CreateClient.model_validate(body(graph))
                )
        except AuthError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(run, [key, key]))
    assert first == second
    assert run(uuid4()) == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(Client)) == 2
        assert session.scalar(select(func.count()).select_from(TrainingSession)) == 4
        assert session.scalar(select(func.count()).select_from(ClientCreateReceipt)) == 1


def test_trainer_cannot_create_or_reconcile(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert post(api, graph).status_code == 403
    assert api.get(f"/api/client-creations/{uuid4()}").status_code == 403


def test_admin_actor_and_personal_receipt_scope(
    api, domain_db, graph, invitations, auth_service, auth_settings, fake_cognito
):
    declared_hours(domain_db, graph)
    key = uuid4()
    created = post(api, graph, key=key)
    assert created.status_code == 200
    admin = create_admin(api).json()
    login_admin(api, auth_service, auth_settings, fake_cognito, admin["id"])
    assert api.get(f"/api/client-creations/{key}").status_code == 404
    payload = body(graph)
    payload["clientPreferences"][0].update({"from": "12:00", "to": "13:00"})
    payload["fixedWeeklySchedule"][0].update({"from": "12:00", "to": "13:00"})
    response = post(api, graph, payload)
    assert response.status_code == 200, response.text
    with domain_db.transaction() as session:
        receipt = session.scalar(
            select(ClientCreateReceipt).where(
                ClientCreateReceipt.client_id == UUID(response.json()["id"])
            )
        )
        assert str(receipt.actor_id) == admin["id"]
    api.headers.pop("X-CSRF-Token")
    assert post(api, graph, payload).status_code == 403
