"""Weekly time edits preserve purchased history and enforce current assignment/approval."""

from concurrent.futures import ThreadPoolExecutor
from datetime import time, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.api import client_weekly_schedule_save as command
from app.models.api import ClientWeeklyScheduleReceipt
from app.models.communications import ChangeRequest, RequestSlot, SessionEvent
from app.models.people import Client, Trainer
from app.models.training import PackagePurchase, PurchaseScheduleSlot, TrainingSession
from app.persistence import acknowledge, add_client, add_purchase
from tests.domain_fixtures import person, purchase_parts
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_client_assignment_review import replacement as replacement
from tests.test_client_reactivation_review import snapshot
from tests.test_package_reactivation_review import freeze
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


@pytest.fixture
def future(domain_db, graph):
    with domain_db.transaction() as session:
        today = session.scalar(
            text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date")
        )
        session.get(TrainingSession, graph["second_session_id"]).training_date = today + timedelta(
            days=1
        )


def read(api, graph):
    response = api.get(f"/api/clients/{graph['client_id']}/weekly-schedule-review")
    assert response.status_code == 200, response.text
    return response.json()


def payload(api, graph):
    viewed = read(api, graph)
    return {
        "expected": viewed["expected"],
        "slots": [{**s, "startsAt": "11:00", "endsAt": "12:00"} for s in viewed["slots"]],
    }


def save(api, graph, body, key=None):
    return api.post(
        f"/api/clients/{graph['client_id']}/weekly-schedule",
        json=body,
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_owner_review_preview_and_atomic_save_preserve_purchased_terms(
    api, domain_db, graph, future
):
    before = snapshot(domain_db)
    viewed = read(api, graph)
    assert viewed["outcome"] == "applied"
    assert [s["id"] for s in viewed["sessions"]] == [str(graph["second_session_id"])]
    body, key = payload(api, graph), uuid4()
    preview = api.post(
        f"/api/clients/{graph['client_id']}/weekly-schedule-review",
        json=body,
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert preview.json() == {
        "expected": viewed["expected"],
        "outcome": "applied",
        "updatedSessions": 1,
    }
    assert snapshot(domain_db) == before
    response = save(api, graph, body, key)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "outcome": "applied",
        "client": {"id": str(graph["client_id"]), "version": viewed["version"] + 1},
        "requestId": None,
        "updatedSessions": 1,
    }
    assert save(api, graph, body, key).json() == response.json()
    assert api.get(f"/api/client-weekly-schedules/{key}").json() == response.json()
    with domain_db.transaction() as session:
        slot = session.scalar(
            select(PurchaseScheduleSlot).where(
                PurchaseScheduleSlot.purchase_id == graph["purchase_id"]
            )
        )
        assert slot.starts_at == time(11) and slot.purchased_starts_at == time(10)
        assert slot.version == 2
        old = session.get(TrainingSession, graph["session_id"])
        new = session.get(TrainingSession, graph["second_session_id"])
        assert old.starts_at == time(10) and new.starts_at == time(11)
        assert new.training_date.isoformat() == viewed["sessions"][0]["date"]
        assert session.scalar(select(func.count()).select_from(SessionEvent)) == 1
        assert session.scalar(select(func.count()).select_from(ClientWeeklyScheduleReceipt)) == 1
    changed = {**body, "slots": [{**s, "startsAt": "11:30"} for s in body["slots"]]}
    assert save(api, graph, changed, key).status_code == 409


def test_admin_applies_without_financial_or_clinical_projection(
    api, invitations, domain_db, graph, future, auth_service, auth_settings, fake_cognito
):
    admin = create_admin(api).json()["id"]
    login_admin(api, auth_service, auth_settings, fake_cognito, admin)
    viewed = read(api, graph)
    assert set(viewed) == {
        "id",
        "version",
        "name",
        "purchaseId",
        "purchaseVersion",
        "trainerId",
        "trainerVersion",
        "outcome",
        "expected",
        "slots",
        "sessions",
    }
    assert save(api, graph, payload(api, graph)).status_code == 200


@pytest.mark.parametrize("supervised", [True, False])
def test_current_trainer_follows_current_approval_controls(
    api, domain_db, graph, future, supervised, auth_service, auth_settings, fake_cognito
):
    with domain_db.transaction() as session:
        session.get(Trainer, graph["trainer_id"]).approve_weekly_schedule = supervised
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    before, body = snapshot(domain_db), payload(api, graph)
    result = save(api, graph, body)
    assert result.status_code == 200, result.text
    assert result.json()["outcome"] == ("requested" if supervised else "applied")
    if supervised:
        assert snapshot(domain_db) == before
        duplicate = save(api, graph, body)
        assert duplicate.json() == result.json()
        with domain_db.transaction() as session:
            assert session.scalar(select(func.count()).select_from(ChangeRequest)) == 1
            slots = session.scalars(select(RequestSlot).order_by(RequestSlot.side)).all()
            assert len(slots) == 2 and slots[0].slot_identity == slots[1].slot_identity
            assert {s.starts_at for s in slots} == {time(10), time(11)}
        assert api.get("/api/messages").status_code == 200
    else:
        with domain_db.transaction() as session:
            assert session.scalar(select(ChangeRequest)) is None
            assert session.get(TrainingSession, graph["second_session_id"]).starts_at == time(11)


def test_inactive_current_purchase_retains_sessions_but_updates_standing_times(
    api, domain_db, graph, future
):
    with domain_db.transaction() as session:
        freeze(session, graph, session.get(PackagePurchase, graph["purchase_id"]))
    before = snapshot(domain_db)["training_sessions"]
    assert read(api, graph)["sessions"] == []
    response = save(api, graph, payload(api, graph))
    assert response.status_code == 200, response.text
    assert response.json()["updatedSessions"] == 0
    assert snapshot(domain_db)["training_sessions"] == before
    with domain_db.transaction() as session:
        assert session.get(PackagePurchase, graph["purchase_id"]).status == "inactive"
        assert session.scalar(select(PurchaseScheduleSlot)).starts_at == time(11)


@pytest.mark.parametrize("locked", ["open", "cancelled", "completed"])
def test_open_cancelled_and_completed_sessions_retain_times(api, domain_db, graph, future, locked):
    identity = graph["session_id"] if locked == "completed" else graph["second_session_id"]
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, identity)
        if locked == "open":
            booking.schedule_state = "open"
            booking.training_date = booking.starts_at = booking.ends_at = None
            booking.session_number = booking.schedule_slot_id = None
        elif locked == "cancelled":
            booking.status = "cancelled"
        else:
            acknowledge(
                session, booking.id, booking.version, graph["user_id"], method="late_no_show"
            )
    before = next(b for b in snapshot(domain_db)["training_sessions"] if b["id"] == identity)
    assert save(api, graph, payload(api, graph)).status_code == 200
    assert (
        next(b for b in snapshot(domain_db)["training_sessions"] if b["id"] == identity) == before
    )


@pytest.mark.parametrize("changed", ["client", "purchase", "slot", "session", "approval"])
def test_stale_review_cannot_overwrite_new_evidence(api, domain_db, graph, future, changed):
    body = payload(api, graph)
    with domain_db.transaction() as session:
        if changed == "client":
            session.get(Client, graph["client_id"]).remarks = "Changed"
        elif changed == "purchase":
            session.get(PackagePurchase, graph["purchase_id"]).version += 1
        elif changed == "slot":
            session.scalar(select(PurchaseScheduleSlot)).ends_at = time(11, 30)
        elif changed == "session":
            session.get(TrainingSession, graph["second_session_id"]).training_date += timedelta(
                days=1
            )
        else:
            session.get(Trainer, graph["trainer_id"]).approve_weekly_schedule = False
    before = snapshot(domain_db)
    assert save(api, graph, body).status_code == 409
    assert snapshot(domain_db) == before


def test_competing_occupied_booking_blocks_preview_and_save(api, domain_db, graph, future):
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["second_session_id"])
        client = add_client(
            session,
            Client(name="Other", kind="individual", trainer_id=graph["trainer_id"]),
            [person("Other")],
        )
        purchase, slots, preferences, bookings = purchase_parts(
            graph, booking.training_date, client_id=client.id, stage="current"
        )
        for slot in slots:
            slot.starts_at = slot.purchased_starts_at = time(11)
            slot.ends_at = slot.purchased_ends_at = time(12)
        for row in bookings:
            row.starts_at, row.ends_at = time(11), time(12)
        add_purchase(session, purchase, slots, preferences, bookings, expected_client_version=1)
    before, body = snapshot(domain_db), payload(api, graph)
    response = save(api, graph, body)
    assert response.status_code == 409 and response.json()["error"]["code"] == "SCHEDULE_CONFLICT"
    assert snapshot(domain_db) == before


def test_new_time_cannot_move_today_session_into_elapsed_time(api, domain_db, graph):
    with domain_db.transaction() as session:
        today = session.scalar(
            text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date")
        )
        booking = session.get(TrainingSession, graph["second_session_id"])
        booking.training_date, booking.starts_at, booking.ends_at = (
            today,
            time(23, 58),
            time(23, 59),
        )
    body = payload(api, graph)
    body["slots"] = [{**s, "startsAt": "00:00", "endsAt": "00:01"} for s in body["slots"]]
    assert save(api, graph, body).status_code == 409


@pytest.mark.parametrize("invalid", ["unchanged", "day", "foreign", "duplicate"])
def test_weekly_days_and_slot_identity_cannot_change(api, graph, future, invalid):
    viewed = read(api, graph)
    body = payload(api, graph)
    if invalid == "unchanged":
        body["slots"] = viewed["slots"]
    if invalid == "day":
        body["slots"][0]["weekday"] = (body["slots"][0]["weekday"] + 1) % 7
    if invalid == "foreign":
        body["slots"][0]["id"] = str(uuid4())
    if invalid == "duplicate":
        body["slots"].append(body["slots"][0])
    assert save(api, graph, body).status_code == (
        422 if invalid in {"unchanged", "duplicate"} else 409
    )


def test_failed_notice_rolls_back_times_history_and_receipt(
    api, domain_db, graph, future, monkeypatch
):
    before, body = snapshot(domain_db), payload(api, graph)

    def fail(*args):
        raise RuntimeError("notice failed")

    monkeypatch.setattr(command, "notify", fail)
    assert save(api, graph, body).status_code == 500
    assert snapshot(domain_db) == before
    with domain_db.transaction() as session:
        assert session.scalar(select(SessionEvent)) is None
        assert session.scalar(select(ClientWeeklyScheduleReceipt)) is None


def test_concurrent_identical_request_has_one_effect(api, domain_db, graph, future):
    body, key = payload(api, graph), uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: save(api, graph, body, key), range(2)))
    assert all(r.status_code == 200 for r in results)
    assert results[0].json() == results[1].json()
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ClientWeeklyScheduleReceipt)) == 1


def test_receipt_privacy_and_immutable_populated_downgrade(
    api, invitations, domain_db, graph, future, auth_service, auth_settings, fake_cognito, migrate
):
    admin = create_admin(api).json()["id"]
    key = uuid4()
    assert save(api, graph, payload(api, graph), key).status_code == 200
    login_admin(api, auth_service, auth_settings, fake_cognito, admin)
    assert api.get(f"/api/client-weekly-schedules/{key}").status_code == 404
    with pytest.raises(DBAPIError, match="immutable"), domain_db.transaction() as session:
        session.delete(session.scalar(select(ClientWeeklyScheduleReceipt)))
    with pytest.raises(DBAPIError, match="Client weekly schedule downgrade refused"):
        migrate("downgrade", "20261013_0029")


def test_unassigned_trainer_cannot_review_preview_or_save_another_client(
    api, domain_db, graph, replacement, auth_service, auth_settings, fake_cognito
):
    body = payload(api, graph)
    with domain_db.transaction() as session:
        client = add_client(
            session,
            Client(name="Other", kind="individual", trainer_id=replacement),
            [person("Other")],
        )
        identity = client.id
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    other = {**graph, "client_id": identity}
    assert api.get(f"/api/clients/{identity}/weekly-schedule-review").status_code == 404
    assert save(api, other, body).status_code == 404
    assert (
        api.post(
            f"/api/clients/{identity}/weekly-schedule-review",
            json=body,
            headers={"Idempotency-Key": str(uuid4())},
        ).status_code
        == 404
    )


def test_queued_purchase_schedule_and_bookings_are_unchanged(api, domain_db, graph, future):
    with domain_db.transaction() as session:
        today = session.scalar(
            text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date")
        )
        purchase, slots, preferences, bookings = purchase_parts(
            graph, max(today + timedelta(days=30), graph["end_date"] + timedelta(days=1))
        )
        add_purchase(
            session,
            purchase,
            slots,
            preferences,
            bookings,
            expected_client_version=session.get(Client, graph["client_id"]).version,
        )
        queued = purchase.id
    with domain_db.transaction() as session:
        before = [
            (b.id, b.version, b.training_date, b.starts_at, b.ends_at)
            for b in session.scalars(
                select(TrainingSession)
                .where(TrainingSession.purchase_id == queued)
                .order_by(TrainingSession.id)
            )
        ]
    assert save(api, graph, payload(api, graph)).status_code == 200
    with domain_db.transaction() as session:
        after = [
            (b.id, b.version, b.training_date, b.starts_at, b.ends_at)
            for b in session.scalars(
                select(TrainingSession)
                .where(TrainingSession.purchase_id == queued)
                .order_by(TrainingSession.id)
            )
        ]
        assert before == after
        assert session.scalar(
            select(PurchaseScheduleSlot).where(PurchaseScheduleSlot.purchase_id == queued)
        ).starts_at == time(10)
