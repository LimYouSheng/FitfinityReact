"""Clock-driven purchase promotion preserves booking history and changes assignment authority."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, time, timedelta
from uuid import UUID

import pytest
from sqlalchemy import event, select

from app.api import purchase_activation
from app.auth.errors import AuthError
from app.models.people import Client, ClientPerson, LifecycleEvent, TrainerAvailability
from app.models.training import PackagePurchase, TrainingSession
from tests.test_client_deactivation_api import command, row_values
from tests.test_client_deactivation_api import review as deactivate_review
from tests.test_client_deactivation_api import save as deactivate
from tests.test_client_renewal_review import another_trainer
from tests.test_client_renewal_save import ready as ready
from tests.test_client_renewal_save import save
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def snapshot(domain_db):
    with domain_db.transaction() as session:
        return {
            model.__tablename__: [
                row_values(row) for row in session.scalars(select(model).order_by(model.id))
            ]
            for model in [Client, ClientPerson, PackagePurchase, TrainingSession]
        }


def advance(monkeypatch, day, hour=16, minute=0, second=0):
    # UTC 16:00 is the following Singapore date; 15:59 remains the preceding date.
    now = datetime.combine(day, time(hour, minute, second), UTC)
    monkeypatch.setattr(purchase_activation, "activation_time", lambda: now)
    return now


def queued(api, graph, ready):
    response = save(api, graph, ready)
    assert response.status_code == 200, response.text
    return UUID(response.json()["purchaseId"])


def test_exact_singapore_midnight_promotes_once_without_touching_bookings(
    api, domain_db, graph, ready, monkeypatch
):
    identity = queued(api, graph, ready)
    before = snapshot(domain_db)
    with domain_db.transaction() as session:
        start = session.get(PackagePurchase, identity).start_date
    advance(monkeypatch, start - timedelta(days=1), 15, 59, 59)
    assert api.get("/api/directory").status_code == 200
    assert snapshot(domain_db) == before
    instant = advance(monkeypatch, start - timedelta(days=1))
    response = api.get("/api/directory")
    assert response.status_code == 200, response.text
    projected = next(c for c in response.json()["clients"] if c["id"] == str(graph["client_id"]))
    assert projected["start_date"] == str(graph["start_date"])
    assert next(p for p in projected["purchases"] if p["stage"] == "current")["id"] == str(identity)
    after = snapshot(domain_db)
    assert after["training_sessions"] == before["training_sessions"]
    assert after["client_people"] == before["client_people"]
    with domain_db.transaction() as session:
        assert session.get(PackagePurchase, identity).activated_at == instant
        assert session.get(PackagePurchase, graph["purchase_id"]).stage == "archived"
        assert (
            session.get(Client, graph["client_id"]).version == before["clients"][0]["version"] + 1
        )
    assert api.get("/api/directory").status_code == 200
    assert snapshot(domain_db) == after


def test_due_purchase_applies_saved_trainer_gender_and_weekly_schedule(
    api, domain_db, graph, ready, monkeypatch
):
    with domain_db.transaction() as session:
        trainer = another_trainer(session)
        trainer.gender = "Female"
        trainer_id = trainer.id
        session.add(
            TrainerAvailability(
                trainer_id=trainer.id,
                weekday=datetime.fromisoformat(ready["startDate"]).weekday(),
                starts_at=time(9),
                ends_at=time(18),
            )
        )
    ready.update(
        {
            "trainerId": str(trainer_id),
            "trainerVersion": 2,
            "genderPreference": "Female trainer preferred",
        }
    )
    identity = queued(api, graph, ready)
    with domain_db.transaction() as session:
        start = session.get(PackagePurchase, identity).start_date
        assert session.get(Client, graph["client_id"]).trainer_id == graph["trainer_id"]
    advance(monkeypatch, start)
    response = api.get("/api/directory")
    assert response.status_code == 200, response.text
    client = next(c for c in response.json()["clients"] if c["id"] == str(graph["client_id"]))
    assert client["trainer_id"] == str(trainer_id) and client["gender_preference"] == "female"
    current = next(p for p in client["purchases"] if p["stage"] == "current")
    assert current["id"] == str(identity)
    assert current["schedule"][0]["starts_at"] == "10:00:00"


@pytest.mark.parametrize("inactive", ["client", "purchase"])
def test_inactive_clients_or_explicitly_inactive_queued_purchases_do_not_promote(
    api, domain_db, graph, ready, monkeypatch, inactive
):
    identity = queued(api, graph, ready)
    if inactive == "client":
        assert deactivate(api, graph, command(deactivate_review(api, graph))).status_code == 200
    else:
        with domain_db.transaction() as session:
            purchase = session.get(PackagePurchase, identity)
            effect = LifecycleEvent(
                purchase_id=identity,
                status="inactive",
                reason="owner",
                actor_id=graph["owner_id"],
                actor_name="Owner Original",
            )
            session.add(effect)
            session.flush()
            purchase.status, purchase.lifecycle_event_id = "inactive", effect.id
    before = snapshot(domain_db)
    advance(monkeypatch, graph["end_date"] + timedelta(days=2))
    assert api.get("/api/directory").status_code == 200
    assert snapshot(domain_db) == before


def test_multiple_due_purchases_promote_in_date_order_once(
    api, domain_db, graph, ready, monkeypatch
):
    first = queued(api, graph, ready)
    viewed = api.get(f"/api/clients/{graph['client_id']}/renewal-review").json()
    second = queued(
        api,
        graph,
        {**ready, "expected": viewed["expected"], "startDate": viewed["minimumStartDate"]},
    )
    with domain_db.transaction() as session:
        start = session.get(PackagePurchase, second).start_date
        version = session.get(Client, graph["client_id"]).version
    advance(monkeypatch, start)
    assert api.get("/api/directory").status_code == 200
    with domain_db.transaction() as session:
        assert session.get(PackagePurchase, first).stage == "archived"
        assert session.get(PackagePurchase, second).stage == "current"
        assert session.get(Client, graph["client_id"]).version == version + 2


def test_concurrent_maintenance_is_idempotent(api, domain_db, graph, ready, monkeypatch):
    identity = queued(api, graph, ready)
    before = snapshot(domain_db)
    advance(monkeypatch, graph["end_date"] + timedelta(days=2))

    def commit():
        with domain_db.transaction() as session:
            purchase_activation.activate_due(session)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: commit(), range(2)))
    with domain_db.transaction() as session:
        assert session.get(PackagePurchase, identity).stage == "current"
        assert (
            session.get(Client, graph["client_id"]).version == before["clients"][0]["version"] + 1
        )


def test_activation_failure_rolls_back_archival_and_client_settings(
    api, domain_db, graph, ready, monkeypatch
):
    identity = queued(api, graph, ready)
    before = snapshot(domain_db)
    advance(monkeypatch, graph["end_date"] + timedelta(days=2))

    def fail(mapper, connection, purchase):
        if purchase.id == identity and purchase.stage == "current":
            raise AuthError("invalid_request", "Fixture rejects activation.", 422)

    event.listen(PackagePurchase, "before_update", fail)
    try:
        assert api.get("/api/directory").status_code == 422
    finally:
        event.remove(PackagePurchase, "before_update", fail)
    assert snapshot(domain_db) == before


def test_old_trainer_loses_current_assignment_before_domain_authorization(
    api, domain_db, graph, ready, monkeypatch, auth_settings, auth_service, fake_cognito
):
    with domain_db.transaction() as session:
        other = another_trainer(session)
        ready["trainerId"] = str(other.id)
        session.add(
            TrainerAvailability(
                trainer_id=other.id,
                weekday=datetime.fromisoformat(ready["startDate"]).weekday(),
                starts_at=time(9),
                ends_at=time(18),
            )
        )
    queued(api, graph, ready)
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    advance(monkeypatch, graph["end_date"] + timedelta(days=2))
    assert api.get(f"/api/clients/{graph['client_id']}/notes").status_code == 404
    assert (
        api.get(f"/api/clients/{graph['client_id']}").status_code == 200
    )  # Historical nonclinical access remains.
    response = api.get("/api/directory")
    assert response.status_code == 200, response.text
    assert response.json()["clients"] == []
