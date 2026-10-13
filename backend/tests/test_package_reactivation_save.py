"""Atomic selected-purchase restoration preserves history and immutable retry evidence."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.api import package_reactivation_save as commands
from app.api.client_reactivation import ReactivationDates
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.api import PackageReactivationReceipt
from app.models.communications import Message, SessionEvent
from app.models.people import Client, LifecycleEvent
from app.models.training import PackagePurchase, TrainingSession
from app.persistence import acknowledge, used_credits
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_client_deactivation_api import row_values
from tests.test_client_reactivation_review import snapshot
from tests.test_package_reactivation_review import freeze, next_purchase, read
from tests.test_package_reactivation_review import frozen as frozen
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def save(api, graph, body, key=None, purchase_id=None):
    purchase = purchase_id or graph["purchase_id"]
    return api.post(
        f"/api/clients/{graph['client_id']}/packages/{purchase}/reactivation",
        json=body,
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def payload(api, graph, dates=None):
    return {"expected": read(api, graph)["expected"], "dates": dates or {}}


def test_restore_preserves_terms_completed_credit_and_other_purchase(api, domain_db, graph):
    with domain_db.transaction() as session:
        b = session.get(TrainingSession, graph["session_id"])
        acknowledge(session, b.id, b.version, graph["owner_id"], method="late_no_show")
        session.flush()
        completed = row_values(b)
        purchase = session.get(PackagePurchase, graph["purchase_id"])
        freeze(session, graph, purchase)
        old = row_values(purchase)
        other, _ = next_purchase(session, graph)
        session.flush()
        other_id, other_before = other.id, row_values(other)
        client_before = row_values(session.get(Client, graph["client_id"]))
    body, key = payload(api, graph), uuid4()
    response = save(api, graph, body, key)
    assert response.status_code == 200, response.text
    assert response.json()["packageId"] == str(graph["purchase_id"])
    assert response.json()["version"] == client_before["version"] + 1
    assert save(api, graph, body, key).json() == response.json()
    assert api.get(f"/api/package-reactivations/{key}").json() == response.json()
    with domain_db.transaction() as session:
        purchase = session.get(PackagePurchase, graph["purchase_id"])
        assert purchase.status == "active" and used_credits(session, purchase.id) == 1
        assert session.get(LifecycleEvent, purchase.lifecycle_event_id).reason == "owner"
        for name, value in old.items():
            if name not in {"status", "version", "lifecycle_event_id", "updated_at"}:
                assert getattr(purchase, name) == value
        assert row_values(session.get(PackagePurchase, other_id)) == other_before
        assert row_values(session.get(TrainingSession, graph["session_id"])) == completed
        client = session.get(Client, graph["client_id"])
        for name, value in client_before.items():
            if name not in {"version", "updated_at"}:
                assert getattr(client, name) == value
        assert session.scalar(select(func.count()).select_from(PackageReactivationReceipt)) == 1
        assert session.scalar(select(func.count()).select_from(Message)) == 1
        freeze(session, graph, purchase)
    assert save(api, graph, body, key).json() == response.json()
    with domain_db.transaction() as session:
        assert session.get(PackagePurchase, graph["purchase_id"]).status == "inactive"


def test_changed_dates_have_immutable_history_and_keep_booking_terms(api, domain_db, graph, frozen):
    with domain_db.transaction() as session:
        before = row_values(session.get(TrainingSession, graph["session_id"]))
    day = str(graph["end_date"] + timedelta(days=50))
    response = save(api, graph, payload(api, graph, {str(graph["session_id"]): day}))
    assert response.status_code == 200, response.text
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        assert str(booking.training_date) == day
        for name, value in before.items():
            if name not in {"training_date", "version", "updated_at"}:
                assert getattr(booking, name) == value
        event = session.scalar(select(SessionEvent))
        assert event.kind == "package_reactivation_date"
        assert event.old_date == before["training_date"] and str(event.new_date) == day


def test_fresh_conflict_and_stale_review_cannot_partially_restore(api, domain_db, graph, frozen):
    with domain_db.transaction() as session:
        _, bookings = next_purchase(session, graph)
        day = bookings[0].training_date
    body = payload(api, graph, {str(graph["session_id"]): str(day)})
    before = snapshot(domain_db)
    assert save(api, graph, body).status_code == 409
    assert snapshot(domain_db) == before
    body["dates"] = {}
    with domain_db.transaction() as session:
        session.get(TrainingSession, graph["session_id"]).version += 1
    assert save(api, graph, body).status_code == 409


def test_concurrent_identical_retries_commit_once_and_changed_key_use_rejects(
    api, domain_db, graph, frozen
):
    body, key = payload(api, graph), uuid4()
    principal = Principal(graph["owner_id"], "Owner", "owner", None)

    def invoke():
        with domain_db.transaction() as session:
            return commands.save(
                session,
                principal,
                graph["client_id"],
                graph["purchase_id"],
                key,
                ReactivationDates(**body),
            ).model_dump(mode="json")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: invoke(), range(2)))
    assert results[0] == results[1]
    assert (
        save(
            api, graph, {**body, "dates": {str(graph["session_id"]): str(graph["start_date"])}}, key
        ).status_code
        == 409
    )
    assert save(api, graph, body, key, uuid4()).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(PackageReactivationReceipt)) == 1
        assert session.scalar(select(func.count()).select_from(Message)) == 1


def test_failed_notice_rolls_back_every_change(api, domain_db, graph, frozen, monkeypatch):
    body = payload(
        api, graph, {str(graph["session_id"]): str(graph["start_date"] + timedelta(days=1))}
    )
    before = snapshot(domain_db)

    def fail(*args):
        raise RuntimeError("notice unavailable")

    monkeypatch.setattr(commands, "notify", fail)
    assert save(api, graph, body).status_code == 500
    assert snapshot(domain_db) == before
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(PackageReactivationReceipt)) == 0
        assert session.scalar(select(func.count()).select_from(SessionEvent)) == 0


def test_admin_can_restore_but_receipt_stays_actor_scoped(
    api, domain_db, graph, frozen, invitations, auth_settings, auth_service, fake_cognito
):
    created = create_admin(api).json()
    login_admin(api, auth_service, auth_settings, fake_cognito, created["id"])
    key = uuid4()
    body = payload(api, graph)
    assert save(api, graph, body, key).status_code == 200
    assert api.get(f"/api/package-reactivations/{key}").status_code == 200
    with pytest.raises(AuthError), domain_db.transaction() as session:
        commands.reconcile(session, Principal(graph["owner_id"], "Owner", "owner", None), key)
    api.headers.pop("X-CSRF-Token")
    assert save(api, graph, body).status_code == 403


def test_assigned_trainer_cannot_save_or_read_owner_receipt(
    api, domain_db, graph, frozen, auth_settings, auth_service, fake_cognito
):
    body, key = payload(api, graph), uuid4()
    assert save(api, graph, body, key).status_code == 200
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert save(api, graph, body).status_code == 403
    assert api.get(f"/api/package-reactivations/{key}").status_code == 403


def test_open_and_cancelled_sessions_are_not_scheduled_or_recreated(api, domain_db, graph):
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        booking.schedule_state = "open"
        booking.session_number = booking.training_date = booking.starts_at = booking.ends_at = (
            booking.schedule_slot_id
        ) = None
        session.get(TrainingSession, graph["second_session_id"]).status = "cancelled"
        freeze(session, graph, session.get(PackagePurchase, graph["purchase_id"]))
        before = {b.id: row_values(b) for b in session.scalars(select(TrainingSession))}
    assert save(api, graph, payload(api, graph)).status_code == 200
    with domain_db.transaction() as session:
        assert {b.id: row_values(b) for b in session.scalars(select(TrainingSession))} == before


def test_receipt_is_immutable_and_populated_downgrade_refuses(api, domain_db, graph, frozen):
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    from sqlalchemy import text

    assert save(api, graph, payload(api, graph)).status_code == 200
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.scalar(select(PackageReactivationReceipt)))
    path = Path(__file__).parents[1] / "migrations/versions/20261013_0027_package_reactivation.py"
    spec = spec_from_file_location("package_receipts", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.execute(text(migration.DOWNGRADE_SQL))
