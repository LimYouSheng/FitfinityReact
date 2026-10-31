"""Replacement review excludes retained history and checks real approved hours/occupancy."""

from datetime import time, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.models.people import Client, Trainer, TrainerAvailability
from app.models.training import PackagePurchase, TrainingSession
from app.persistence import acknowledge, add_client, add_purchase
from tests.domain_fixtures import person, purchase_parts
from tests.test_client_reactivation_review import snapshot
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


@pytest.fixture
def replacement(domain_db, graph):
    with domain_db.transaction() as session:
        trainer = Trainer(
            name="Replacement",
            email="assignment-replacement@example.test",
            gender="Female",
            phone_country_code="+65",
            phone_number="91234567",
            trainer_type="Personal Trainer",
            peak_rate_cents=9000,
            off_peak_rate_cents=6500,
        )
        session.add(trainer)
        session.flush()
        for weekday in range(7):
            session.add(
                TrainerAvailability(
                    trainer_id=trainer.id, weekday=weekday, starts_at=time(9), ends_at=time(12)
                )
            )
        today = session.scalar(
            text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date")
        )
        booking = session.get(TrainingSession, graph["second_session_id"])
        booking.training_date = today + timedelta(days=1)
        return trainer.id


def read(api, graph):
    response = api.get(f"/api/clients/{graph['client_id']}/trainer-assignment-review")
    assert response.status_code == 200, response.text
    return response.json()


def test_review_exact_future_scope_and_no_writes(api, domain_db, graph, replacement):
    before = snapshot(domain_db)
    result = read(api, graph)
    assert result["current"] == {"id": str(graph["trainer_id"]), "name": "Trainer One"}
    assert [b["id"] for b in result["sessions"]] == [str(graph["second_session_id"])]
    assert [p["id"] for p in result["purchases"]] == [str(graph["purchase_id"])]
    assert result["choices"] == [
        {"id": str(replacement), "name": "Replacement", "version": 1, "error": None}
    ]
    assert len(result["expected"]) == 64 and result["history"] == []
    assert snapshot(domain_db) == before
    assert not {"rates", "healthNotes", "assessments"} & result.keys()


def test_open_sessions_are_eligible_without_an_invented_date(api, domain_db, graph, replacement):
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        booking.schedule_state = "open"
        booking.training_date = booking.starts_at = booking.ends_at = None
        booking.session_number = booking.schedule_slot_id = None
    result = read(api, graph)
    row = next(r for r in result["sessions"] if r["id"] == str(graph["session_id"]))
    assert row["scheduleState"] == "open" and row["date"] is None
    assert row["startsAt"] is None and row["endsAt"] is None


@pytest.mark.parametrize("selected", [True, False])
def test_only_selected_purchase_preference_constrains_replacement(
    api, domain_db, graph, replacement, selected
):
    with domain_db.transaction() as session:
        client = session.get(Client, graph["client_id"])
        client.gender_preference = "male"
        session.flush()
        purchase, slots, preferences, bookings = purchase_parts(graph)
        purchase.gender_preference = "male"
        add_purchase(
            session,
            purchase,
            slots,
            preferences,
            bookings,
            expected_client_version=client.version,
        )
        purchase_id = purchase.id
    before = snapshot(domain_db)
    path = f"/api/clients/{graph['client_id']}/trainer-assignment-review"
    response = api.get(path, params={"purchaseId": str(purchase_id)} if selected else {})
    assert response.status_code == 200, response.text
    error = response.json()["choices"][0]["error"]
    if selected:
        assert "preference" in error
    else:
        assert error is None
    assert snapshot(domain_db) == before


def test_saved_weekly_hours_are_required_even_without_future_sessions(
    api, domain_db, graph, replacement
):
    with domain_db.transaction() as session:
        session.get(TrainingSession, graph["second_session_id"]).training_date = graph[
            "start_date"
        ] + timedelta(days=7)
        for window in session.scalars(
            select(TrainerAvailability).where(TrainerAvailability.trainer_id == replacement)
        ):
            window.ends_at = time(10)
    result = read(api, graph)
    assert result["sessions"] == []
    assert "weekly schedule" in result["choices"][0]["error"]


def test_real_competing_booking_excludes_replacement(api, domain_db, graph, replacement):
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["second_session_id"])
        client = add_client(
            session,
            Client(name="Other", kind="individual", trainer_id=replacement),
            [person("Other")],
        )
        purchase, slots, preferences, bookings = purchase_parts(
            {**graph, "trainer_id": replacement},
            booking.training_date,
            client_id=client.id,
            stage="current",
        )
        add_purchase(session, purchase, slots, preferences, bookings, expected_client_version=1)
    assert "another booking" in read(api, graph)["choices"][0]["error"]


def test_acknowledged_sessions_keep_historical_assignment(api, domain_db, graph, replacement):
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        acknowledge(session, booking.id, booking.version, graph["user_id"], method="late_no_show")
    assert [b["id"] for b in read(api, graph)["sessions"]] == [str(graph["second_session_id"])]


def test_trainer_and_guessed_clients_cannot_read_assignment_review(
    api, domain_db, graph, replacement, auth_settings, auth_service, fake_cognito
):
    assert api.get(f"/api/clients/{uuid4()}/trainer-assignment-review").status_code == 404
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert (
        api.get(f"/api/clients/{graph['client_id']}/trainer-assignment-review").status_code == 403
    )


def test_review_digest_changes_with_original_assignment_evidence(
    api, domain_db, graph, replacement
):
    before = read(api, graph)
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["second_session_id"])
        booking.training_date += timedelta(days=1)
    assert read(api, graph)["expected"] != before["expected"]


@pytest.mark.parametrize("covered", [True, False])
def test_inactive_purchase_cannot_be_reassigned_even_when_trainer_is_available(
    api, domain_db, graph, replacement, covered
):
    from tests.test_package_reactivation_review import freeze

    with domain_db.transaction() as session:
        freeze(session, graph, session.get(PackagePurchase, graph["purchase_id"]))
        if not covered:
            for window in session.scalars(
                select(TrainerAvailability).where(TrainerAvailability.trainer_id == replacement)
            ):
                window.ends_at = time(10)
    before = snapshot(domain_db)
    response = api.get(f"/api/clients/{graph['client_id']}/trainer-assignment-review")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "state_conflict"
    assert snapshot(domain_db) == before
