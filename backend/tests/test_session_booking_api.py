"""Actual HTTP booking commands commit atomically to isolated PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.api import session_booking_save as command
from app.models.api import SessionBookingReceipt
from app.models.communications import Message, SessionEvent
from app.models.people import Client
from app.models.training import PackagePurchase, TrainingSession
from app.persistence import acknowledge, add_client, add_purchase
from tests.domain_fixtures import person, purchase_parts
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_client_assignment_review import replacement as replacement
from tests.test_client_reactivation_review import deactivate, snapshot
from tests.test_message_api import seed_request
from tests.test_open_sessions import make_open
from tests.test_package_reactivation_review import freeze
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def review(api, identity):
    response = api.get(f"/api/sessions/{identity}/booking-review")
    assert response.status_code == 200, response.text
    return response.json()


def payload(api, identity, **changes):
    viewed = review(api, identity)
    return {
        "expected": viewed["expected"],
        "date": viewed["session"]["date"],
        "startsAt": "12:00",
        "endsAt": "13:00",
        "trainerId": viewed["session"]["trainerId"],
        **changes,
    }


def save(api, identity, body, key=None):
    return api.post(
        f"/api/sessions/{identity}/booking",
        json=body,
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_save_reorders_existing_ids_and_replays_original_result(api, domain_db, graph):
    identity = graph["second_session_id"]
    first = review(api, graph["session_id"])["session"]
    body = payload(api, identity, date=first["date"], startsAt="08:00", endsAt="09:00")
    key = uuid4()
    response = save(api, identity, body, key)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["session"]["sessionNumber"] == 1
    assert {r["id"]: r["sessionNumber"] for r in result["positions"]} == {
        str(identity): 1,
        str(graph["session_id"]): 2,
    }
    assert review(api, identity)["session"] == result["session"]
    assert save(api, identity, body, key).json() == result
    assert api.get(f"/api/session-booking-saves/{key}").json() == result
    assert save(api, identity, {**body, "endsAt": "09:30"}, key).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(SessionBookingReceipt)) == 1
        assert session.scalar(select(func.count()).select_from(SessionEvent)) == 1
        assert session.scalar(select(func.count()).select_from(Message)) == 1
        assert (
            session.get(PackagePurchase, graph["purchase_id"]).purchased_trainer_id
            == graph["trainer_id"]
        )


def test_noop_retains_versions_and_creates_no_notice(api, domain_db, graph):
    identity = graph["second_session_id"]
    viewed = review(api, identity)
    before = snapshot(domain_db)
    response = save(api, identity, payload(api, identity, startsAt="10:00", endsAt="11:00"))
    assert response.status_code == 200, response.text
    assert response.json()["session"] == viewed["session"]
    assert response.json()["messageId"] is None
    assert snapshot(domain_db) == before
    with domain_db.transaction() as session:
        assert session.scalar(select(SessionEvent)) is None
        assert session.scalar(select(Message)) is None


@pytest.mark.parametrize("changed", ["session", "client", "purchase"])
def test_stale_review_cannot_overwrite_newer_state(api, domain_db, graph, changed):
    identity = graph["second_session_id"]
    body = payload(api, identity)
    with domain_db.transaction() as session:
        model, key = {
            "session": (TrainingSession, "second_session_id"),
            "client": (Client, "client_id"),
            "purchase": (PackagePurchase, "purchase_id"),
        }[changed]
        session.get(model, graph[key]).version += 1
    before = snapshot(domain_db)
    assert save(api, identity, body).status_code == 409
    assert snapshot(domain_db) == before


def test_overlapping_booking_rejected_without_changes(api, domain_db, graph):
    identity = graph["second_session_id"]
    first = review(api, graph["session_id"])["session"]
    body = payload(api, identity, date=first["date"], startsAt="10:30", endsAt="11:30")
    before = snapshot(domain_db)
    assert save(api, identity, body).status_code == 409
    assert snapshot(domain_db) == before


def test_notice_failure_rolls_back_booking_numbering_and_receipt(
    api, domain_db, graph, monkeypatch
):
    identity = graph["second_session_id"]
    body = payload(api, identity)
    before = snapshot(domain_db)

    def fail(*args):
        raise RuntimeError("notice interrupted")

    monkeypatch.setattr(command, "notify", fail)
    assert save(api, identity, body).status_code == 500
    assert snapshot(domain_db) == before
    with domain_db.transaction() as session:
        assert session.scalar(select(SessionEvent)) is None
        assert session.scalar(select(SessionBookingReceipt)) is None


def test_concurrent_duplicate_has_one_effect(api, domain_db, graph):
    identity = graph["second_session_id"]
    body, key = payload(api, identity), uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: save(api, identity, body, key), range(2)))
    assert [r.status_code for r in results] == [200, 200]
    assert results[0].json() == results[1].json()
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(SessionBookingReceipt)) == 1
        assert session.scalar(select(func.count()).select_from(SessionEvent)) == 1


def test_open_booking_requires_future_then_persists(api, domain_db, graph):
    identity = graph["second_session_id"]
    with domain_db.transaction() as session:
        make_open(session, identity)
        today = session.scalar(
            text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date")
        )
    body = payload(api, identity, date=(today - timedelta(days=1)).isoformat())
    assert save(api, identity, body).status_code == 409
    response = save(api, identity, {**body, "date": (today + timedelta(days=1)).isoformat()})
    assert response.status_code == 200, response.text
    assert response.json()["session"]["scheduleState"] == "booked"
    assert response.json()["session"]["slotId"] is None
    assert review(api, identity)["session"] == response.json()["session"]


def test_trainer_cannot_use_owner_booking_commands(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    identity = graph["second_session_id"]
    body, key = payload(api, identity), uuid4()
    assert save(api, identity, body, key).status_code == 200
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    before = snapshot(domain_db)
    assert api.get(f"/api/sessions/{identity}/booking-review").status_code == 403
    assert save(api, identity, body).status_code == 403
    assert api.get(f"/api/session-booking-saves/{key}").status_code == 403
    assert snapshot(domain_db) == before


@pytest.mark.parametrize(
    "changes",
    [
        {"date": "2026-02-30"},
        {"startsAt": "25:00"},
        {"startsAt": "13:00", "endsAt": "12:00"},
        {"actorId": "forged"},
    ],
)
def test_invalid_input_is_rejected_before_writes(api, domain_db, graph, changes):
    identity = graph["second_session_id"]
    body = payload(api, identity, **changes)
    before = snapshot(domain_db)
    assert save(api, identity, body).status_code == 422
    assert snapshot(domain_db) == before


def test_receipts_are_immutable_and_block_lossy_downgrade(api, domain_db, graph, migrate):
    identity = graph["second_session_id"]
    assert save(api, identity, payload(api, identity)).status_code == 200
    with pytest.raises(DBAPIError, match="immutable"), domain_db.transaction() as session:
        session.delete(session.scalar(select(SessionBookingReceipt)))
    with pytest.raises(DBAPIError, match="Session booking downgrade refused"):
        migrate("downgrade", "20261023_0031")


def test_admin_can_save_but_cannot_read_another_actors_receipt(
    api, invitations, domain_db, graph, auth_service, auth_settings, fake_cognito
):
    admin = create_admin(api).json()["id"]
    identity, key = graph["second_session_id"], uuid4()
    assert save(api, identity, payload(api, identity), key).status_code == 200
    login_admin(api, auth_service, auth_settings, fake_cognito, admin)
    assert api.get(f"/api/session-booking-saves/{key}").status_code == 404
    viewed = review(api, identity)
    assert set(viewed) == {
        "id",
        "version",
        "clientId",
        "clientVersion",
        "purchaseId",
        "purchaseVersion",
        "expected",
        "session",
        "trainers",
    }
    assert (
        save(api, identity, payload(api, identity, startsAt="14:00", endsAt="15:00")).status_code
        == 200
    )


@pytest.mark.parametrize("locked", ["client", "purchase", "cancelled", "completed"])
def test_final_or_inactive_records_reject_old_review(api, domain_db, graph, locked):
    identity = graph["session_id"]
    body = payload(api, identity)
    if locked == "client":
        deactivate(api, graph)
    with domain_db.transaction() as session:
        if locked == "client":
            assert session.get(Client, graph["client_id"]).status == "inactive"
        elif locked == "purchase":
            freeze(session, graph, session.get(PackagePurchase, graph["purchase_id"]))
        elif locked == "cancelled":
            session.get(TrainingSession, identity).status = "cancelled"
        else:
            acknowledge(
                session,
                identity,
                session.get(TrainingSession, identity).version,
                graph["user_id"],
                method="late_no_show",
            )
    before = snapshot(domain_db)
    assert api.get(f"/api/sessions/{identity}/booking-review").status_code == 409
    assert save(api, identity, body).status_code == 409
    assert snapshot(domain_db) == before


def test_foreign_client_booking_blocks_trainer_overlap(api, domain_db, graph):
    identity = graph["second_session_id"]
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, identity)
        client = add_client(
            session,
            Client(name="Foreign", kind="individual", trainer_id=graph["trainer_id"]),
            [person("Foreign")],
        )
        purchase, slots, preferences, bookings = purchase_parts(
            graph, booking.training_date, client_id=client.id, stage="current"
        )
        for row in bookings:
            row.starts_at = row.starts_at.replace(hour=12)
            row.ends_at = row.ends_at.replace(hour=13)
        add_purchase(session, purchase, slots, preferences, bookings, expected_client_version=1)
    body, before = payload(api, identity), snapshot(domain_db)
    assert save(api, identity, body).status_code == 409
    assert snapshot(domain_db) == before


def test_reassignment_changes_session_only_and_preserves_purchased_trainer(
    api, domain_db, graph, replacement
):
    identity = graph["second_session_id"]
    response = save(api, identity, payload(api, identity, trainerId=str(replacement)))
    assert response.status_code == 200, response.text
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, identity).trainer_id == replacement
        assert session.get(Client, graph["client_id"]).trainer_id == graph["trainer_id"]
        assert (
            session.get(PackagePurchase, graph["purchase_id"]).purchased_trainer_id
            == graph["trainer_id"]
        )
        event = session.scalar(select(SessionEvent))
        assert event.old_trainer_id == graph["trainer_id"] and event.new_trainer_id == replacement


def test_pending_request_blocks_booking_change(api, domain_db, graph):
    identity = graph["session_id"]
    with domain_db.transaction() as session:
        seed_request(session, graph, "session_time")
    body, before = payload(api, identity), snapshot(domain_db)
    assert save(api, identity, body).status_code == 409
    assert snapshot(domain_db) == before
