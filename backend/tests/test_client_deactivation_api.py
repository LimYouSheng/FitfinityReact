"""Reviewed client/purchase lifecycle changes retain immutable training and retry evidence."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.api import client_deactivation
from app.api.client_deactivation import DeactivateClient
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.api import ClientDeactivationReceipt
from app.models.communications import Message, MessageReceipt
from app.models.people import Client, ClientPerson, LifecycleEvent
from app.models.training import PackagePurchase, TrainingSession
from app.persistence import acknowledge, add_purchase, used_credits
from tests.domain_fixtures import purchase_parts
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def review(api, graph):
    response = api.get(f"/api/clients/{graph['client_id']}/deactivation")
    assert response.status_code == 200, response.text
    return response.json()


def command(value):
    return {
        "expectedVersion": value["version"],
        "expectedTrainerId": value["trainerId"],
        "purchases": [{k: p[k] for k in ["id", "version", "status"]} for p in value["purchases"]],
    }


def save(api, graph, body, key=None):
    return api.post(
        f"/api/clients/{graph['client_id']}/deactivation",
        json=body,
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def row_values(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def test_deactivation_atomically_freezes_purchases_and_preserves_sessions_people_credits(
    api, domain_db, graph
):
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        acknowledge(session, booking.id, booking.version, graph["owner_id"], method="late_no_show")
        session.flush()
        before_sessions = [
            row_values(s)
            for s in session.scalars(select(TrainingSession).order_by(TrainingSession.id))
        ]
        before_people = [
            row_values(p) for p in session.scalars(select(ClientPerson).order_by(ClientPerson.id))
        ]
        before_purchase = row_values(session.get(PackagePurchase, graph["purchase_id"]))
    viewed = review(api, graph)
    body = command(viewed)
    key = uuid4()
    result = save(api, graph, body, key)
    assert result.status_code == 200, result.text
    assert result.json() == {
        "id": str(graph["client_id"]),
        "version": viewed["version"] + 1,
        "status": "inactive",
    }
    assert save(api, graph, body, key).json() == result.json()
    assert api.get(f"/api/client-deactivations/{key}").json() == result.json()
    with domain_db.transaction() as session:
        client = session.get(Client, graph["client_id"])
        purchase = session.get(PackagePurchase, graph["purchase_id"])
        cause = session.get(LifecycleEvent, client.lifecycle_event_id)
        effect = session.get(LifecycleEvent, purchase.lifecycle_event_id)
        assert client.status == purchase.status == "inactive"
        assert (
            cause.client_id == client.id
            and effect.cause_id == cause.id
            and effect.reason == "client"
        )
        assert used_credits(session, purchase.id) == 1
        assert [
            row_values(s)
            for s in session.scalars(select(TrainingSession).order_by(TrainingSession.id))
        ] == before_sessions
        assert [
            row_values(p) for p in session.scalars(select(ClientPerson).order_by(ClientPerson.id))
        ] == before_people
        for field, value in before_purchase.items():
            if field not in {"version", "status", "lifecycle_event_id", "updated_at"}:
                assert getattr(purchase, field) == value
        assert session.scalar(select(func.count()).select_from(ClientDeactivationReceipt)) == 1
        assert (
            session.scalar(
                select(func.count()).select_from(Message).where(Message.kind == "client_status")
            )
            == 2
        )
        recipients = set(
            session.scalars(
                select(MessageReceipt.user_id).join(Message).where(Message.kind == "client_status")
            )
        )
        assert recipients == {graph["owner_id"], graph["user_id"]}
    assert api.get(f"/api/clients/{graph['client_id']}/deactivation").status_code == 409
    assert api.get("/api/directory").json()["clients"][0]["status"] == "inactive"


def test_previously_inactive_purchase_retains_its_independent_lifecycle(api, domain_db, graph):
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
        purchase_id = purchase.id
        before = row_values(purchase)
    assert save(api, graph, command(review(api, graph))).status_code == 200
    with domain_db.transaction() as session:
        assert row_values(session.get(PackagePurchase, purchase_id)) == before


@pytest.mark.parametrize("change", ["version", "trainer", "purchase_version", "missing_purchase"])
def test_stale_or_incomplete_review_rejects_without_writes(api, domain_db, graph, change):
    body = command(review(api, graph))
    if change == "version":
        body["expectedVersion"] += 1
    if change == "trainer":
        body["expectedTrainerId"] = str(uuid4())
    if change == "purchase_version":
        body["purchases"][0]["version"] += 1
    if change == "missing_purchase":
        body["purchases"] = []
    assert save(api, graph, body).status_code == 409
    with domain_db.transaction() as session:
        assert session.get(Client, graph["client_id"]).status == "active"
        assert session.scalar(select(func.count()).select_from(ClientDeactivationReceipt)) == 0
        assert session.scalar(select(func.count()).select_from(LifecycleEvent)) == 0


def test_new_purchase_after_review_cannot_be_silently_frozen(api, domain_db, graph):
    body = command(review(api, graph))
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
        body["expectedVersion"] = session.get(Client, graph["client_id"]).version
    assert save(api, graph, body).status_code == 409


@pytest.mark.parametrize("action", ["review", "save", "receipt"])
def test_assigned_trainer_cannot_review_deactivate_or_read_owner_receipt(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito, action
):
    body = command(review(api, graph))
    key = uuid4()
    if action == "receipt":
        assert save(api, graph, body, key).status_code == 200
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    response = (
        save(api, graph, body)
        if action == "save"
        else api.get(
            f"/api/client-deactivations/{key}"
            if action == "receipt"
            else f"/api/clients/{graph['client_id']}/deactivation"
        )
    )
    assert response.status_code == 403


def test_admin_can_deactivate_but_cannot_read_another_actor_receipt(
    api, invitations, domain_db, graph, auth_service, auth_settings, fake_cognito
):
    body = command(review(api, graph))
    admin_id = create_admin(api).json()["id"]
    login_admin(api, auth_service, auth_settings, fake_cognito, admin_id)
    key = uuid4()
    result = save(api, graph, body, key)
    assert result.status_code == 200, result.text
    assert api.get(f"/api/client-deactivations/{key}").json() == result.json()
    with domain_db.transaction() as session:
        evidence = session.scalar(select(ClientDeactivationReceipt))
        assert str(evidence.actor_id) == admin_id
        with pytest.raises(AuthError) as error:
            client_deactivation.reconcile(
                session, Principal(graph["owner_id"], "Owner", "owner", None), key
            )
        assert error.value.code == "not_found"


def test_parallel_same_key_has_one_effect_and_changed_body_conflicts(api, domain_db, graph):
    body = command(review(api, graph))
    principal = Principal(graph["owner_id"], "Owner", "owner", None)
    key = uuid4()

    def invoke():
        with domain_db.transaction() as session:
            return client_deactivation.save(
                session, principal, graph["client_id"], key, DeactivateClient(**body)
            ).model_dump(mode="json")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: invoke(), range(2)))
    assert results[0] == results[1]
    body["expectedVersion"] += 1
    assert save(api, graph, body, key).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ClientDeactivationReceipt)) == 1
        assert session.scalar(select(func.count()).select_from(LifecycleEvent)) == 2


def test_notice_failure_rolls_back_entire_lifecycle_and_receipt(api, domain_db, graph, monkeypatch):
    body = command(review(api, graph))

    def fail(*args):
        raise RuntimeError("notice failed")

    monkeypatch.setattr(client_deactivation, "notify", fail)
    assert save(api, graph, body).status_code == 500
    with domain_db.transaction() as session:
        assert session.get(Client, graph["client_id"]).status == "active"
        assert session.get(PackagePurchase, graph["purchase_id"]).status == "active"
        assert session.scalar(select(func.count()).select_from(LifecycleEvent)) == 0
        assert session.scalar(select(func.count()).select_from(ClientDeactivationReceipt)) == 0


def test_immutable_receipt_and_populated_downgrade_refuse(api, domain_db, graph, migrate):
    assert save(api, graph, command(review(api, graph))).status_code == 200
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.scalar(select(ClientDeactivationReceipt)))
    with pytest.raises(DBAPIError, match="populated attribution downgrade refused"):
        migrate("downgrade", "20261013_0019")


@pytest.mark.parametrize("change", ["actor", "boolean", "duplicate"])
def test_strict_commands_reject_spoofed_or_duplicate_review(api, graph, change):
    body = command(review(api, graph))
    if change == "actor":
        body["actor"] = "Owner"
    if change == "boolean":
        body["expectedVersion"] = True
    if change == "duplicate":
        body["purchases"].append(body["purchases"][0])
    assert save(api, graph, body).status_code == 422


def test_missing_client_and_unknown_receipt_are_unavailable(api):
    assert api.get(f"/api/clients/{uuid4()}/deactivation").status_code == 404
    assert api.get(f"/api/client-deactivations/{uuid4()}").status_code == 404
