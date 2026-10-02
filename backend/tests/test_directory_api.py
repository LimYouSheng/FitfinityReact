"""Real HTTP/PostgreSQL directory scope, purchase evidence and temporary cover access."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.auth.errors import AuthError
from app.authorization import Principal, session_record
from app.models.people import Client, ClientPerson, Trainer
from app.models.training import PackageTemplateRevision, TrainingSession
from app.persistence import acknowledge, add_client, add_purchase
from tests.domain_fixtures import person, purchase_parts
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def covered_session(db, graph):
    with db.transaction() as session:
        source = session.get(Trainer, graph["trainer_id"])
        other = Trainer(
            **{
                c.name: getattr(source, c.name)
                for c in Trainer.__table__.columns
                if c.name not in {"id", "user_id", "email", "created_at", "updated_at", "version"}
            }
        )
        other.email = "permanent@example.test"
        other.name = "Permanent Coach"
        session.add(other)
        session.flush()
        client = add_client(
            session,
            Client(kind="couple", name="Covered Couple", trainer_id=other.id),
            [person("Person First"), person("Person Second")],
        )
        session.flush()
        purchase, slots, preferences, bookings = purchase_parts(
            {**graph, "trainer_id": other.id},
            graph["start_date"],
            client_id=client.id,
            stage="current",
        )
        add_purchase(
            session, purchase, slots, preferences, bookings, expected_client_version=client.version
        )
        session.flush()
        bookings[0].trainer_id = graph["trainer_id"]
        return client.id, bookings[0].id, other.id


def test_directory_uses_purchased_terms_and_real_credit_evidence(api, domain_db, graph):
    with domain_db.transaction() as session:
        row = session.get(TrainingSession, graph["session_id"])
        acknowledge(session, row.id, row.version, graph["owner_id"], method="late_no_show")
        p = session.scalar(select(ClientPerson).where(ClientPerson.client_id == graph["client_id"]))
        p.health_notes = "private historical health"
        session.add(
            PackageTemplateRevision(
                template_id=graph["template_id"],
                revision=2,
                name="Changed template",
                total_sessions=24,
                validity_days=180,
                actor_id=graph["owner_id"],
                actor_name="Owner Original",
            )
        )
    response = api.get("/api/directory")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["viewerId"] == str(graph["owner_id"]) and result["schemaVersion"] == 1
    client = result["clients"][0]
    assert client["people"][0]["emergency_name"] == "Contact One"
    purchase = client["purchases"][0]
    assert purchase["used"] == 1 and purchase["total_sessions"] == 2
    assert purchase["trainer_name"] == "Trainer One" and purchase["stage"] == "current"
    assert len(purchase["schedule"]) == 1
    assert result["trainers"][0]["peak_rate_cents"] == 8000
    assert result["packages"][0]["validity_days"] == 180
    assert result["packages"][0]["revision"] == 2 and result["packages"][0]["version"] == 1
    assert "private historical health" not in response.text and "health_notes" not in response.text
    assert "assessments" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_couple_people_and_client_without_purchase_remain_explicit(api, domain_db, graph):
    client_id, _, _ = covered_session(domain_db, graph)
    with domain_db.transaction() as session:
        empty = add_client(
            session,
            Client(kind="individual", name="No Purchase", trainer_id=graph["trainer_id"]),
            [person("No Purchase")],
        )
        empty_id = empty.id
    clients = {c["id"]: c for c in api.get("/api/directory").json()["clients"]}
    assert [p["name"] for p in clients[str(client_id)]["people"]] == [
        "Person First",
        "Person Second",
    ]
    assert clients[str(empty_id)]["purchases"] == []


def test_directory_follows_current_permanent_relationship_only(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    client_id, session_id, _ = covered_session(domain_db, graph)
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    result = api.get("/api/directory?role=owner").json()
    assert result["viewerId"] == str(graph["user_id"])
    assert [c["id"] for c in result["clients"]] == [str(graph["client_id"])]
    assert [t["id"] for t in result["trainers"]] == [str(graph["trainer_id"])]
    assert result["packages"] == []
    assert api.get(f"/api/clients/{client_id}").status_code == 404
    assert api.get(f"/api/sessions/{session_id}").status_code == 200
    limited = api.get(f"/api/sessions/{session_id}/client")
    assert limited.status_code == 200
    assert set(limited.json()) == {"session_id", "client_id", "name", "kind", "person_names"}
    assert limited.json()["person_names"] == ["Person First", "Person Second"]


def test_completion_ends_temporary_client_access_but_keeps_both_trainers_history(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    client_id, session_id, original_id = covered_session(domain_db, graph)
    with domain_db.transaction() as session:
        row = session.get(TrainingSession, session_id)
        acknowledge(session, row.id, row.version, graph["user_id"], method="late_no_show")
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get(f"/api/sessions/{session_id}/client").status_code == 404
    assert api.get(f"/api/clients/{client_id}").status_code == 404
    assert api.get(f"/api/sessions/{session_id}").json()["status"] == "completed"
    for trainer_id in [graph["trainer_id"], original_id]:
        principal = Principal(graph["user_id"], "Coach", "trainer", trainer_id)
        with domain_db.transaction() as session:
            assert session_record(session, principal, session_id).status == "completed"
        with pytest.raises(AuthError), domain_db.transaction() as session:
            session_record(session, principal, session_id, write=True)


def test_original_trainer_can_read_cover_but_not_mutate_it_and_guessed_ids_are_hidden(
    api, domain_db, graph
):
    _, session_id, original_id = covered_session(domain_db, graph)
    principal = Principal(graph["user_id"], "Original", "trainer", original_id)
    with domain_db.transaction() as session:
        assert session_record(session, principal, session_id)
    with pytest.raises(AuthError), domain_db.transaction() as session:
        session_record(session, principal, session_id, write=True)
    assert api.get(f"/api/sessions/{uuid4()}/client").status_code == 404


def test_directory_does_not_load_assessment_answers_or_manufacture_other_domains(api):
    data = api.get("/api/directory").json()
    assert set(data) == {
        "schemaVersion",
        "viewerId",
        "serverAt",
        "businessDate",
        "timeZone",
        "clients",
        "trainers",
        "packages",
    }
    assert data["timeZone"] == "Asia/Singapore"
    assert all("health_notes" not in p for c in data["clients"] for p in c["people"])


def test_unrelated_trainer_cannot_read_session_or_limited_client(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    client_id, _, _ = covered_session(domain_db, graph)
    with domain_db.transaction() as session:
        foreign_id = session.scalar(
            select(TrainingSession.id).where(
                TrainingSession.client_id == client_id,
                TrainingSession.trainer_id != graph["trainer_id"],
            )
        )
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get(f"/api/sessions/{foreign_id}").status_code == 404
    assert api.get(f"/api/sessions/{foreign_id}/client").status_code == 404


def test_queued_purchases_are_read_from_database_in_date_order(api, domain_db, graph):
    with domain_db.transaction() as session:
        client = session.get(Client, graph["client_id"])
        purchase, slots, preferences, bookings = purchase_parts(graph)
        add_purchase(
            session, purchase, slots, preferences, bookings, expected_client_version=client.version
        )
        next_id = purchase.id
    rows = api.get("/api/directory").json()["clients"][0]["purchases"]
    assert [p["stage"] for p in rows] == ["current", "queued"]
    assert rows[1]["id"] == str(next_id) and rows[1]["used"] == 0
