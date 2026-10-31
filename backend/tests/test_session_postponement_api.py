"""Postponement persists an Open record or a supervised proposal in isolated PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.api import session_postponement as command
from app.models.api import SessionPostponementReceipt
from app.models.communications import ChangeRequest, Message, SessionEvent
from app.models.people import Client, Trainer
from app.models.training import CreditDebit, PackagePurchase, TrainingSession
from app.persistence import add_purchase
from tests.domain_fixtures import purchase_parts
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_client_assignment_review import replacement as replacement
from tests.test_client_reactivation_review import deactivate, snapshot
from tests.test_message_api import seed_request
from tests.test_open_sessions import make_open
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


@pytest.fixture
def future(domain_db, graph):
    with domain_db.transaction() as session:
        today = session.scalar(
            text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date")
        )
        for index, key in enumerate(["session_id", "second_session_id"]):
            session.get(TrainingSession, graph[key]).training_date = today + timedelta(
                days=1 + index * 7
            )


def review(api, graph):
    response = api.get(f"/api/sessions/{graph['session_id']}/postponement-review")
    assert response.status_code == 200, response.text
    return response.json()


def save(api, graph, viewed, key=None):
    return api.post(
        f"/api/sessions/{graph['session_id']}/postponement",
        json={"expected": viewed["expected"]},
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_owner_releases_only_booking_and_renumbers_without_changing_credits(
    api, domain_db, graph, future
):
    viewed, before, key = review(api, graph), snapshot(domain_db), uuid4()
    response = save(api, graph, viewed, key)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["outcome"] == "applied" and saved["requestId"] is None
    assert saved["session"]["id"] == str(graph["session_id"])
    assert saved["session"]["scheduleState"] == "open"
    assert all(
        saved["session"][k] is None
        for k in ["date", "startsAt", "endsAt", "sessionNumber", "slotId"]
    )
    assert saved["changedPositions"] == 1
    assert save(api, graph, viewed, key).json() == saved
    assert api.get(f"/api/session-postponements/{key}").json() == saved
    with domain_db.transaction() as session:
        other = session.get(TrainingSession, graph["second_session_id"])
        old = next(r for r in before["training_sessions"] if r["id"] == other.id)
        assert other.training_date == old["training_date"] and other.starts_at == old["starts_at"]
        assert other.session_number == 1
        purchase = session.get(PackagePurchase, graph["purchase_id"])
        assert purchase.total_sessions == 2 and purchase.end_date == graph["end_date"]
        assert session.scalar(select(CreditDebit)) is None
        assert session.scalar(select(func.count()).select_from(SessionEvent)) == 1
        assert session.scalar(select(func.count()).select_from(SessionPostponementReceipt)) == 1


@pytest.mark.parametrize("supervised", [True, False])
def test_assigned_trainer_uses_current_approval_policy(
    api, domain_db, graph, future, supervised, auth_settings, auth_service, fake_cognito
):
    with domain_db.transaction() as session:
        session.get(Trainer, graph["trainer_id"]).approve_session_time = supervised
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    viewed, before = review(api, graph), snapshot(domain_db)
    response = save(api, graph, viewed)
    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == ("requested" if supervised else "applied")
    if supervised:
        assert snapshot(domain_db) == before
    with domain_db.transaction() as session:
        proposal = session.scalar(select(ChangeRequest))
        if supervised:
            assert proposal.kind == "session_postpone" and proposal.status == "pending"
            assert proposal.old_date.isoformat() == viewed["session"]["date"]
            assert proposal.new_date is None
            assert session.get(TrainingSession, graph["session_id"]).schedule_state == "booked"
        else:
            assert proposal is None
            assert session.get(TrainingSession, graph["session_id"]).schedule_state == "open"


def test_policy_change_after_review_rejects_instead_of_applying_wrong_path(
    api, domain_db, graph, future, auth_settings, auth_service, fake_cognito
):
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    viewed = review(api, graph)
    with domain_db.transaction() as session:
        session.get(Trainer, graph["trainer_id"]).approve_session_time = False
    before = snapshot(domain_db)
    assert save(api, graph, viewed).status_code == 409
    assert snapshot(domain_db) == before


@pytest.mark.parametrize("blocked", ["open", "cancelled", "past", "trainer"])
def test_ineligible_booking_rejects_review_and_old_save(api, domain_db, graph, future, blocked):
    viewed = review(api, graph)
    with domain_db.transaction() as session:
        row = session.get(TrainingSession, graph["session_id"])
        if blocked == "open":
            make_open(session, row.id)
        elif blocked == "cancelled":
            row.status = "cancelled"
        elif blocked == "past":
            row.training_date = graph["start_date"]
        else:
            session.get(Trainer, graph["trainer_id"]).approve_session_time = False
            # Current authority is also bound for an operations actor.
    before = snapshot(domain_db)
    if blocked != "trainer":
        assert (
            api.get(f"/api/sessions/{graph['session_id']}/postponement-review").status_code == 409
        )
    assert save(api, graph, viewed).status_code == 409
    assert snapshot(domain_db) == before


def test_inactive_client_cannot_release_retained_booking(api, domain_db, graph, future):
    viewed = review(api, graph)
    deactivate(api, graph)
    before = snapshot(domain_db)
    assert save(api, graph, viewed).status_code == 409
    assert snapshot(domain_db) == before


@pytest.mark.parametrize("kind", ["session_time", "fixed_weekly_schedule"])
def test_pending_session_or_weekly_request_blocks_postponement(api, domain_db, graph, future, kind):
    viewed = review(api, graph)
    with domain_db.transaction() as session:
        seed_request(session, graph, kind)
    before = snapshot(domain_db)
    assert save(api, graph, viewed).status_code == 409
    assert snapshot(domain_db) == before


def test_failed_notice_rolls_back_open_state_positions_and_receipt(
    api, domain_db, graph, future, monkeypatch
):
    viewed, before = review(api, graph), snapshot(domain_db)

    def fail(*args):
        raise RuntimeError("interrupted notice")

    monkeypatch.setattr(command, "notify", fail)
    assert save(api, graph, viewed).status_code == 500
    assert snapshot(domain_db) == before
    with domain_db.transaction() as session:
        assert session.scalar(select(SessionEvent)) is None
        assert session.scalar(select(SessionPostponementReceipt)) is None
        assert session.scalar(select(Message)) is None


def test_duplicate_concurrent_requests_have_one_result(api, domain_db, graph, future):
    viewed, key = review(api, graph), uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: save(api, graph, viewed, key), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    assert save(api, graph, {"expected": "f" * 64}, key).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(SessionPostponementReceipt)) == 1


def test_populated_receipt_cannot_be_deleted_or_downgraded(api, domain_db, graph, future, migrate):
    assert save(api, graph, review(api, graph)).status_code == 200
    with pytest.raises(DBAPIError, match="immutable"), domain_db.transaction() as session:
        session.delete(session.scalar(select(SessionPostponementReceipt)))
    with pytest.raises(DBAPIError, match="populated attribution downgrade refused"):
        migrate("downgrade", "20261023_0032")


def test_cover_history_is_not_authority_to_postpone_and_receipt_is_private(
    api, domain_db, graph, future, replacement, auth_service, auth_settings, fake_cognito
):
    viewed, key = review(api, graph), uuid4()
    assert save(api, graph, viewed, key).status_code == 200
    with domain_db.transaction() as session:
        session.get(TrainingSession, graph["second_session_id"]).trainer_id = replacement
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    foreign = {**graph, "session_id": graph["second_session_id"]}
    before = snapshot(domain_db)
    assert api.get(f"/api/sessions/{foreign['session_id']}/postponement-review").status_code == 404
    assert save(api, foreign, viewed).status_code == 404
    assert api.get(f"/api/session-postponements/{key}").status_code == 404
    assert snapshot(domain_db) == before


def test_admin_can_apply_without_trainer_approval(
    api, invitations, graph, future, auth_service, auth_settings, fake_cognito
):
    admin = create_admin(api).json()["id"]
    login_admin(api, auth_service, auth_settings, fake_cognito, admin)
    viewed = review(api, graph)
    assert viewed["outcome"] == "applied"
    assert save(api, graph, viewed).status_code == 200


def test_additional_purchase_postponement_preserves_default_purchase_bookings(
    api, domain_db, graph
):
    with domain_db.transaction() as session:
        purchase, slots, preferences, bookings = purchase_parts(graph)
        add_purchase(
            session,
            purchase,
            slots,
            preferences,
            bookings,
            expected_client_version=session.get(Client, graph["client_id"]).version,
        )
        identity = bookings[0].id
    before = snapshot(domain_db)
    scoped = {**graph, "session_id": identity}
    viewed = review(api, scoped)
    assert viewed["id"] == str(identity)
    assert snapshot(domain_db) == before
    changed = save(api, scoped, viewed)
    assert changed.status_code == 200, changed.text
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, identity).schedule_state == "open"
        for original in [graph["session_id"], graph["second_session_id"]]:
            row = session.get(TrainingSession, original)
            assert row.purchase_id == graph["purchase_id"]
            assert row.schedule_state == "booked" and row.version == 1


def test_supervised_notice_failure_rolls_back_proposal(
    api, domain_db, graph, future, auth_service, auth_settings, fake_cognito, monkeypatch
):
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    viewed, before = review(api, graph), snapshot(domain_db)

    def fail(*args):
        raise RuntimeError("proposal notice failed")

    monkeypatch.setattr(command, "notify", fail)
    assert save(api, graph, viewed).status_code == 500
    assert snapshot(domain_db) == before
    with domain_db.transaction() as session:
        assert session.scalar(select(ChangeRequest)) is None
        assert session.scalar(select(SessionPostponementReceipt)) is None
