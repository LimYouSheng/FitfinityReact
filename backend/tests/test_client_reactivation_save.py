"""Transactional reactivation retains credits/history and rechecks all competing bookings."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.api import client_reactivation_save as commands
from app.api.client_reactivation import ReactivationDates
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.api import ClientReactivationReceipt
from app.models.communications import SessionEvent
from app.models.people import Client, LifecycleEvent
from app.models.training import PackagePurchase, TrainingSession
from app.persistence import acknowledge, add_client, add_purchase, used_credits
from tests.domain_fixtures import person, purchase_parts
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_client_deactivation_api import row_values
from tests.test_client_reactivation_review import deactivate, read, snapshot
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def save(api, graph, body, key=None):
    return api.post(
        f"/api/clients/{graph['client_id']}/reactivation",
        json=body,
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def body(api, graph, dates=None):
    return {"expected": read(api, graph)["expected"], "dates": dates or {}}


def test_restore_is_atomic_idempotent_and_retains_completed_credits_and_terms(
    api, domain_db, graph
):
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        acknowledge(session, booking.id, booking.version, graph["owner_id"], method="late_no_show")
        session.flush()
        before = row_values(booking)
        purchase_before = row_values(session.get(PackagePurchase, graph["purchase_id"]))
    deactivate(api, graph)
    payload = body(api, graph)
    key = uuid4()
    result = save(api, graph, payload, key)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "active"
    assert save(api, graph, payload, key).json() == result.json()
    assert api.get(f"/api/client-reactivations/{key}").json() == result.json()
    with domain_db.transaction() as session:
        client = session.get(Client, graph["client_id"])
        purchase = session.get(PackagePurchase, graph["purchase_id"])
        assert client.status == purchase.status == "active"
        effect = session.get(LifecycleEvent, purchase.lifecycle_event_id)
        assert (
            effect.reason == "client_reactivated" and effect.cause_id == client.lifecycle_event_id
        )
        assert row_values(session.get(TrainingSession, graph["session_id"])) == before
        assert used_credits(session, purchase.id) == 1
        for key_name, value in purchase_before.items():
            if key_name not in {"status", "version", "lifecycle_event_id", "updated_at"}:
                assert getattr(purchase, key_name) == value
        assert session.scalar(select(func.count()).select_from(ClientReactivationReceipt)) == 1
    # Replay is original evidence even after a later deactivation.
    deactivate(api, graph)
    assert save(api, graph, payload, key).json() == result.json()
    with domain_db.transaction() as session:
        assert session.get(Client, graph["client_id"]).status == "inactive"


def test_date_changes_keep_booking_identity_terms_and_immutable_history(api, domain_db, graph):
    deactivate(api, graph)
    with domain_db.transaction() as session:
        before = row_values(session.get(TrainingSession, graph["session_id"]))
    day = str(graph["end_date"] + timedelta(days=20))
    result = save(api, graph, body(api, graph, {str(graph["session_id"]): day}))
    assert result.status_code == 200, result.text
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        assert str(booking.training_date) == day
        for name, value in before.items():
            if name not in {"training_date", "version", "updated_at"}:
                assert getattr(booking, name) == value
        event = session.scalar(select(SessionEvent).where(SessionEvent.session_id == booking.id))
        assert event.old_date == before["training_date"] and str(event.new_date) == day
        assert event.actor_id == graph["owner_id"] and event.kind == "client_reactivation_date"
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.scalar(select(SessionEvent)))


def test_new_competing_booking_rejects_entire_save_then_original_dates_can_be_reviewed(
    api, domain_db, graph
):
    deactivate(api, graph)
    payload = body(api, graph)
    with domain_db.transaction() as session:
        other = add_client(
            session,
            Client(kind="individual", name="Other", trainer_id=graph["trainer_id"]),
            [person("Other")],
        )
        purchase, slots, preferences, bookings = purchase_parts(
            graph, graph["start_date"], client_id=other.id, stage="current"
        )
        add_purchase(
            session, purchase, slots, preferences, bookings, expected_client_version=other.version
        )
    before = snapshot(domain_db)
    assert save(api, graph, payload).status_code == 409
    assert snapshot(domain_db) == before
    payload["dates"] = {
        str(graph["session_id"]): str(graph["start_date"] + timedelta(days=1)),
        str(graph["second_session_id"]): str(graph["start_date"] + timedelta(days=2)),
    }
    assert save(api, graph, payload).status_code == 200


@pytest.mark.parametrize(
    "model,key",
    [(Client, "client_id"), (PackagePurchase, "purchase_id"), (TrainingSession, "session_id")],
)
def test_stale_save_changes_nothing(api, domain_db, graph, model, key):
    deactivate(api, graph)
    payload = body(api, graph)
    with domain_db.transaction() as session:
        session.get(model, graph[key]).version += 1
    before = snapshot(domain_db)
    assert save(api, graph, payload).status_code == 409
    assert snapshot(domain_db) == before


def test_concurrent_duplicate_has_one_effect_and_changed_body_is_rejected(api, domain_db, graph):
    deactivate(api, graph)
    payload = body(api, graph)
    key = uuid4()
    principal = Principal(graph["owner_id"], "Owner", "owner", None)

    def invoke():
        with domain_db.transaction() as session:
            return commands.save(
                session, principal, graph["client_id"], key, ReactivationDates(**payload)
            ).model_dump(mode="json")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: invoke(), range(2)))
    assert results[0] == results[1]
    payload["dates"] = {str(graph["session_id"]): str(graph["start_date"])}
    assert save(api, graph, payload, key).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ClientReactivationReceipt)) == 1


def test_notice_failure_rolls_back_dates_lifecycle_and_receipt(api, domain_db, graph, monkeypatch):
    deactivate(api, graph)
    payload = body(
        api, graph, {str(graph["session_id"]): str(graph["start_date"] + timedelta(days=1))}
    )
    before = snapshot(domain_db)

    def fail(*args):
        raise RuntimeError("notice failed")

    monkeypatch.setattr(commands, "notify", fail)
    assert save(api, graph, payload).status_code == 500
    assert snapshot(domain_db) == before
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ClientReactivationReceipt)) == 0
        assert session.scalar(select(func.count()).select_from(SessionEvent)) == 0


def test_admin_can_restore_but_receipt_remains_actor_scoped(
    api, invitations, domain_db, graph, auth_service, auth_settings, fake_cognito
):
    deactivate(api, graph)
    payload = body(api, graph)
    admin_id = create_admin(api).json()["id"]
    login_admin(api, auth_service, auth_settings, fake_cognito, admin_id)
    key = uuid4()
    assert save(api, graph, payload, key).status_code == 200
    assert api.get(f"/api/client-reactivations/{key}").status_code == 200
    with pytest.raises(AuthError), domain_db.transaction() as session:
        commands.reconcile(session, Principal(graph["owner_id"], "Owner", "owner", None), key)


@pytest.mark.parametrize("action", ["save", "receipt"])
def test_trainer_cannot_restore_or_read_owner_receipt(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito, action
):
    deactivate(api, graph)
    payload = body(api, graph)
    key = uuid4()
    if action == "receipt":
        assert save(api, graph, payload, key).status_code == 200
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    response = (
        save(api, graph, payload, key)
        if action == "save"
        else api.get(f"/api/client-reactivations/{key}")
    )
    assert response.status_code == 403


def test_immutable_receipt_and_populated_downgrade_refuse(api, domain_db, graph, migrate):
    deactivate(api, graph)
    assert save(api, graph, body(api, graph)).status_code == 200
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.scalar(select(ClientReactivationReceipt)))
    with pytest.raises(DBAPIError, match="Client reactivation downgrade refused"):
        migrate("downgrade", "20261013_0020")


def test_separately_inactive_purchase_and_its_bookings_stay_unchanged(api, domain_db, graph):
    with domain_db.transaction() as session:
        purchase, slots, preferences, bookings = purchase_parts(graph)
        add_purchase(
            session,
            purchase,
            slots,
            preferences,
            bookings,
            expected_client_version=graph["client_version"],
        )
        session.flush()
        event = LifecycleEvent(
            purchase_id=purchase.id,
            status="inactive",
            reason="owner",
            actor_id=graph["owner_id"],
            actor_name="Owner",
        )
        session.add(event)
        session.flush()
        purchase.status, purchase.lifecycle_event_id = "inactive", event.id
        session.flush()
        other_id, before = purchase.id, row_values(purchase)
        before_bookings = [row_values(b) for b in bookings]
    deactivate(api, graph)
    assert save(api, graph, body(api, graph)).status_code == 200
    with domain_db.transaction() as session:
        assert row_values(session.get(PackagePurchase, other_id)) == before
        assert [
            row_values(session.get(TrainingSession, b["id"])) for b in before_bookings
        ] == before_bookings


@pytest.mark.parametrize("invalid", ["trainer", "mutual"])
def test_unresolved_calendar_errors_reject_without_lifecycle_effects(
    api, domain_db, graph, invalid
):
    from app.models.people import Trainer

    deactivate(api, graph)
    if invalid == "trainer":
        with domain_db.transaction() as session:
            session.get(Trainer, graph["trainer_id"]).status = "inactive"
    dates = (
        {} if invalid == "trainer" else {str(graph["second_session_id"]): str(graph["start_date"])}
    )
    before = snapshot(domain_db)
    assert save(api, graph, body(api, graph, dates)).status_code == 409
    assert snapshot(domain_db) == before
