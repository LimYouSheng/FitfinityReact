"""Contact-only edits preserve assessment evidence and current role/record authority."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.api import client_details as commands
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.api import ClientDetailReceipt
from app.models.people import Client, ClientPerson, LifecycleEvent, StaffUser
from app.models.training import PackagePurchase
from tests.test_staff_api import api as api
from tests.test_staff_api import create as create_assessment
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def payload(api, graph):
    row = next(
        c for c in api.get("/api/directory").json()["clients"] if c["id"] == str(graph["client_id"])
    )
    people = [
        {
            "id": p["id"],
            "expectedVersion": p["version"],
            "name": p["name"],
            "email": p["email"],
            "birthday": p["birthday"],
            "gender": p["gender"],
            "phone": {"countryCode": p["phone_country_code"], "number": p["phone_number"]},
            "emergencyContact": {
                "name": p["emergency_name"],
                "relationship": p["emergency_relationship"],
                "countryCode": p["emergency_country_code"],
                "number": p["emergency_number"],
            },
        }
        for p in row["people"]
    ]
    return {
        "expectedVersion": row["version"],
        "people": people,
        "remarks": "Updated remarks",
        "genderPreference": "Female trainer preferred",
    }


def save(api, graph, body, key=None):
    return api.post(
        f"/api/clients/{graph['client_id']}/personal-details",
        json=body,
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_general_edit_persists_versions_and_preserves_sensitive_notes_and_purchases(
    api, domain_db, graph
):
    body = payload(api, graph)
    assessment = create_assessment(api, body["people"][0]["id"]).json()
    before = api.get("/api/directory").json()
    with domain_db.transaction() as session:
        person = session.get(ClientPerson, body["people"][0]["id"])
        person.health_notes = "Private limitation history"
    body = payload(api, graph)
    body["people"][0]["name"] = "Updated Client"
    result = save(api, graph, body)
    assert result.status_code == 200, result.text
    assert set(result.json()) == {"id", "version", "people"}
    assert result.json()["version"] == body["expectedVersion"] + 1
    after = api.get("/api/directory").json()
    assert after["clients"][0]["purchases"] == before["clients"][0]["purchases"]
    assert after["clients"][0]["name"] == "Updated Client"
    assert after["clients"][0]["remarks"] == "Updated remarks"
    assert api.get(f"/api/assessments/{assessment['assessment_id']}").json() == assessment
    with domain_db.transaction() as session:
        assert (
            session.get(ClientPerson, body["people"][0]["id"]).health_notes
            == "Private limitation history"
        )
        receipt = session.scalar(select(ClientDetailReceipt))
        assert receipt.result == result.json() and receipt.actor_id == graph["owner_id"]
        assert "Private limitation" not in str(receipt.result)


def test_couple_people_are_independently_versioned_and_cannot_be_reordered(api, domain_db, graph):
    with domain_db.transaction() as session:
        first = session.scalar(
            select(ClientPerson).where(ClientPerson.client_id == graph["client_id"])
        )
        values = {
            c.key: getattr(first, c.key)
            for c in first.__table__.columns
            if c.key not in {"id", "created_at", "updated_at", "version"}
        }
        session.add(ClientPerson(**{**values, "position": 2, "name": "Second Client"}))
        session.get(Client, graph["client_id"]).kind = "couple"
    body = payload(api, graph)
    assert save(api, graph, {**body, "people": list(reversed(body["people"]))}).status_code == 409
    result = save(api, graph, body)
    assert result.status_code == 200, result.text
    assert len(result.json()["people"]) == 2
    assert api.get("/api/directory").json()["clients"][0]["name"].endswith(" & Second Client")


def test_retry_and_reconciliation_return_original_versions(api, graph):
    key = uuid4()
    body = payload(api, graph)
    result = save(api, graph, body, key).json()
    assert save(api, graph, payload(api, graph)).status_code == 200
    assert save(api, graph, body, key).json() == result
    assert api.get(f"/api/client-detail-saves/{key}").json() == result
    assert save(api, graph, {**body, "remarks": "Changed"}, key).status_code == 409
    assert save(api, graph, body).status_code == 409


@pytest.mark.parametrize(
    "field,value",
    [
        ("healthNotes", "Forbidden"),
        ("assessments", {}),
        ("actor", "owner"),
        ("status", "inactive"),
        ("trainerId", "forged"),
        ("expectedVersion", True),
    ],
)
def test_extra_or_malformed_command_cannot_write(api, domain_db, graph, field, value):
    body = payload(api, graph)
    assert save(api, graph, {**body, field: value}).status_code == 422
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ClientDetailReceipt)) == 0


def test_person_health_answers_and_stale_person_identity_cannot_be_overwritten(api, graph):
    body = payload(api, graph)
    first = body["people"][0]
    for field in ["healthNotes", "assessments"]:
        bad = {**body, "people": [{**first, field: {}}]}
        assert save(api, graph, bad).status_code == 422
    assert save(api, graph, {**body, "people": [{**first, "id": str(uuid4())}]}).status_code == 409
    assert (
        save(api, graph, {**body, "people": [{**first, "expectedVersion": 100}]}).status_code == 409
    )


def test_invalid_contact_and_missing_transport_are_rejected(api, graph):
    body = payload(api, graph)
    first = body["people"][0]
    for patch in [
        {"email": "invalid"},
        {"birthday": 1},
        {"birthday": "2026-02-30"},
        {"phone": {"countryCode": "+65", "number": "123"}},
    ]:
        assert save(api, graph, {**body, "people": [{**first, **patch}]}).status_code == 422
    assert (
        api.post(f"/api/clients/{graph['client_id']}/personal-details", json=body).status_code
        == 422
    )
    api.headers.pop("X-CSRF-Token")
    assert save(api, graph, body).status_code == 403


def test_inactive_clients_and_trainers_cannot_use_general_edit(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    body = payload(api, graph)
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
        client = session.get(Client, graph["client_id"])
        purchase = session.get(PackagePurchase, graph["purchase_id"])
        client.status, client.lifecycle_event_id = "inactive", event.id
        purchase.status, purchase.lifecycle_event_id = "inactive", effect.id
    assert save(api, graph, body).status_code == 409
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert save(api, graph, body).status_code == 403
    assert api.get(f"/api/client-detail-saves/{uuid4()}").status_code == 403


def test_admin_command_and_actor_scoped_receipt(api, domain_db, graph):
    body = payload(api, graph)
    key = uuid4()
    assert save(api, graph, body, key).status_code == 200
    body = payload(api, graph)
    with domain_db.transaction() as session:
        admin = StaffUser(name="Operations", email="ops@example.test", role="admin")
        session.add(admin)
        session.flush()
        principal = Principal(admin.id, admin.name, "admin", None)
        with pytest.raises(AuthError) as denied:
            commands.reconcile(session, principal, key)
        assert denied.value.status == 404
        result = commands.save(
            session, principal, graph["client_id"], key, commands.SaveClientDetails(**body)
        )
    with domain_db.transaction() as session:
        assert commands.reconcile(session, principal, key) == result


def test_parallel_retry_is_single_effect(api, domain_db, graph):
    body = commands.SaveClientDetails(**payload(api, graph))
    key = uuid4()
    principal = Principal(graph["owner_id"], "Owner Original", "owner", None)

    def submit(_):
        with domain_db.transaction() as session:
            return commands.save(session, principal, graph["client_id"], key, body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert results[0] == results[1]
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ClientDetailReceipt)) == 1


def test_receipts_immutable_and_populated_downgrade_refused(api, domain_db, graph, migrate):
    assert save(api, graph, payload(api, graph)).status_code == 200
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.scalar(select(ClientDetailReceipt)))
    with pytest.raises(DBAPIError, match="downgrade refused"):
        migrate("downgrade", "20261013_0008")
