"""Real HTTP/PostgreSQL acceptance for assigned Trainer time and replacement commands."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.api import session_booking_save
from app.api import session_changes as command
from app.authorization import Principal
from app.database import Database
from app.models.api import SessionChangeReceipt
from app.models.communications import (
    ChangeRequest,
    Message,
    MessageReceipt,
    RequestEvent,
    SessionEvent,
)
from app.models.people import StaffUser, Trainer
from app.models.training import TrainingSession
from tests import test_client_assignment_review as assignment_fixtures
from tests.test_client_reactivation_review import snapshot
from tests.test_open_sessions import make_open
from tests.test_session_postponement_api import future as future
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

candidate = assignment_fixtures.replacement
pytestmark = pytest.mark.database


@pytest.fixture
def replacement(candidate, future, domain_db, graph):
    # The assignment fixture moves the second booking onto tomorrow; scheduling
    # cases need distinct intervals unless they deliberately create a conflict.
    with domain_db.transaction() as session:
        first = session.get(TrainingSession, graph["session_id"])
        second = session.get(TrainingSession, graph["second_session_id"])
        second.training_date = first.training_date + timedelta(days=7)
        trainer = session.get(Trainer, candidate)
        user = StaffUser(name=trainer.name, email=trainer.email, role="trainer")
        session.add(user)
        session.flush()
        trainer.user_id = user.id
    return candidate


@pytest.fixture
def trainer_api(api, domain_db, graph, auth_settings, auth_service, fake_cognito):
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    return api


def review(api, graph, kind):
    response = api.get(f"/api/sessions/{graph['session_id']}/change-review", params={"kind": kind})
    assert response.status_code == 200, response.text
    return response.json()


def body_for(viewed, replacement):
    if viewed["kind"] == "trainer":
        return {"expected": viewed["expected"], "trainerId": str(replacement)}
    return {
        "expected": viewed["expected"],
        "date": viewed["session"]["date"],
        "startsAt": "12:00",
        "endsAt": "13:00",
    }


def save(api, graph, kind, body, key=None):
    return api.post(
        f"/api/sessions/{graph['session_id']}/{kind}-change",
        json=body,
        headers={"Idempotency-Key": str(key or uuid4())},
    )


@pytest.mark.parametrize("kind", ["time", "trainer"])
@pytest.mark.parametrize("supervised", [False, True])
def test_policy_controls_atomic_change_and_original_private_receipt(
    trainer_api, domain_db, graph, future, replacement, kind, supervised
):
    with domain_db.transaction() as session:
        row = session.get(Trainer, graph["trainer_id"])
        setattr(
            row, "approve_session_time" if kind == "time" else "approve_session_trainer", supervised
        )
    viewed, before, key = review(trainer_api, graph, kind), snapshot(domain_db), uuid4()
    body = body_for(viewed, replacement)
    result = save(trainer_api, graph, kind, body, key)
    assert result.status_code == 200, result.text
    value = result.json()
    assert value["outcome"] == ("requested" if supervised else "applied")
    assert save(trainer_api, graph, kind, body, key).json() == value
    assert trainer_api.get(f"/api/session-changes/{key}").json() == value
    changed = {**body, "expected": "0" * 64}
    assert save(trainer_api, graph, kind, changed, key).status_code == 409
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        assert session.scalar(select(func.count()).select_from(SessionChangeReceipt)) == 1
        request = session.scalar(select(ChangeRequest))
        if supervised:
            assert request.kind == f"session_{kind}" and request.status == "pending"
            assert booking.version == viewed["version"]
            assert session.scalar(select(func.count()).select_from(RequestEvent)) == 1
            assert session.scalar(select(SessionEvent)) is None
        else:
            assert request is None and booking.version > viewed["version"]
            assert session.scalar(select(func.count()).select_from(SessionEvent)) == 1
            if kind == "time":
                assert booking.starts_at.strftime("%H:%M") == "12:00"
            else:
                assert booking.trainer_id == replacement
        receipt = session.scalar(select(SessionChangeReceipt))
        assert receipt.previous["review"] == viewed
    if supervised:
        assert snapshot(domain_db) == before


@pytest.mark.parametrize("kind", ["time", "trainer"])
def test_operations_accounts_cannot_impersonate_trainer_commands(api, graph, future, kind):
    assert (
        api.get(
            f"/api/sessions/{graph['session_id']}/change-review", params={"kind": kind}
        ).status_code
        == 403
    )
    payload = (
        {"expected": "0" * 64, "trainerId": str(uuid4())}
        if kind == "trainer"
        else {"expected": "0" * 64, "date": "2030-01-01", "startsAt": "12:00", "endsAt": "13:00"}
    )
    assert save(api, graph, kind, payload).status_code == 403
    assert api.get(f"/api/session-changes/{uuid4()}").status_code == 403


@pytest.mark.parametrize("kind", ["time", "trainer"])
@pytest.mark.parametrize("change", ["policy", "assignment", "pending"])
def test_stale_or_foreign_commands_leave_no_partial_write(
    trainer_api, domain_db, graph, future, replacement, kind, change
):
    viewed = review(trainer_api, graph, kind)
    if change == "pending":
        assert save(trainer_api, graph, kind, body_for(viewed, replacement)).status_code == 200
    else:
        with domain_db.transaction() as session:
            if change == "policy":
                trainer = session.get(Trainer, graph["trainer_id"])
                field = "approve_session_time" if kind == "time" else "approve_session_trainer"
                setattr(trainer, field, not getattr(trainer, field))
            else:
                session.get(TrainingSession, graph["session_id"]).trainer_id = replacement
    before = snapshot(domain_db)
    result = save(trainer_api, graph, kind, body_for(viewed, replacement))
    assert result.status_code in {404, 409}, result.text
    assert snapshot(domain_db) == before
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(SessionChangeReceipt)) == (
            1 if change == "pending" else 0
        )


@pytest.mark.parametrize("kind", ["time", "trainer"])
@pytest.mark.parametrize("supervised", [False, True])
def test_interrupted_transaction_rolls_back_proposal_notice_receipt(
    trainer_api, domain_db, graph, future, replacement, kind, supervised, monkeypatch
):
    with domain_db.transaction() as session:
        trainer = session.get(Trainer, graph["trainer_id"])
        setattr(
            trainer,
            "approve_session_time" if kind == "time" else "approve_session_trainer",
            supervised,
        )
    viewed, before = review(trainer_api, graph, kind), snapshot(domain_db)

    def fail(*args, **kwargs):
        raise RuntimeError("Interrupted before notice")

    monkeypatch.setattr(command, "notify", fail)
    monkeypatch.setattr(session_booking_save, "notify", fail)
    response = save(trainer_api, graph, kind, body_for(viewed, replacement))
    assert response.status_code == 500
    assert snapshot(domain_db) == before
    with domain_db.transaction() as session:
        assert session.scalar(select(ChangeRequest)) is None
        assert session.scalar(select(SessionChangeReceipt)) is None
        assert session.scalar(select(Message)) is None


@pytest.mark.parametrize("kind", ["time", "trainer"])
def test_open_session_retains_identity_through_autonomous_change(
    trainer_api, domain_db, graph, future, replacement, kind
):
    with domain_db.transaction() as session:
        row = session.get(TrainingSession, graph["session_id"])
        day = row.training_date.isoformat()
        make_open(session, row.id)
        trainer = session.get(Trainer, graph["trainer_id"])
        trainer.approve_session_time = trainer.approve_session_trainer = False
    viewed = review(trainer_api, graph, kind)
    body = body_for(viewed, replacement)
    if kind == "time":
        body["date"] = day
    response = save(trainer_api, graph, kind, body)
    assert response.status_code == 200, response.text
    saved = response.json()["session"]
    assert saved["id"] == str(graph["session_id"])
    assert saved["scheduleState"] == ("booked" if kind == "time" else "open")
    if kind == "trainer":
        assert saved["date"] is None and saved["sessionNumber"] is None
        assert saved["trainerId"] == str(replacement)
        # The original actor may recover their receipt after losing current assignment.
        with domain_db.transaction() as session:
            receipt = session.scalar(select(SessionChangeReceipt))
            key = receipt.request_key
        assert trainer_api.get(f"/api/session-changes/{key}").status_code == 200


def test_receipt_is_immutable_and_populated_downgrade_refuses(
    trainer_api, domain_db, graph, future, replacement, migrate
):
    viewed = review(trainer_api, graph, "time")
    assert save(trainer_api, graph, "time", body_for(viewed, replacement)).status_code == 200
    with pytest.raises(DBAPIError, match="immutable"):
        with domain_db.transaction() as session:
            session.delete(session.scalar(select(SessionChangeReceipt)))

    with pytest.raises(DBAPIError, match="Session change downgrade refused"):
        migrate("downgrade", "20261023_0034")


@pytest.mark.parametrize("target", ["past", "collision"])
def test_time_change_revalidates_clock_and_client_occupancy(
    trainer_api, domain_db, graph, future, replacement, target
):
    viewed = review(trainer_api, graph, "time")
    body = body_for(viewed, replacement)
    with domain_db.transaction() as session:
        other = session.get(TrainingSession, graph["second_session_id"])
        body["date"] = "2000-01-01" if target == "past" else other.training_date.isoformat()
        body["startsAt"] = other.starts_at.strftime("%H:%M")
        body["endsAt"] = other.ends_at.strftime("%H:%M")
    before = snapshot(domain_db)
    assert save(trainer_api, graph, "time", body).status_code == 409
    assert snapshot(domain_db) == before
    with domain_db.transaction() as session:
        assert session.scalar(select(ChangeRequest)) is None
        assert session.scalar(select(SessionChangeReceipt)) is None


def test_replacement_is_not_notified_of_an_unapproved_proposal(
    trainer_api, domain_db, graph, future, replacement
):
    viewed = review(trainer_api, graph, "trainer")
    response = save(trainer_api, graph, "trainer", body_for(viewed, replacement))
    assert response.status_code == 200, response.text
    with domain_db.transaction() as session:
        original = session.get(Trainer, graph["trainer_id"])
        recipients = set(
            session.scalars(
                select(MessageReceipt.user_id).where(
                    MessageReceipt.message_id == UUID(response.json()["messageId"])
                )
            )
        )
        assert original.user_id in recipients
        target = session.get(Trainer, replacement)
        assert target.user_id not in recipients


@pytest.mark.parametrize("kind", ["time", "trainer"])
def test_concurrent_duplicate_and_competing_intents_have_one_proposal(
    trainer_api, domain_db, database_settings, graph, future, replacement, kind
):
    """Separate connection pools model independent API replicas, not a one-connection queue."""
    viewed, key = review(trainer_api, graph, kind), uuid4()
    body = body_for(viewed, replacement)
    with domain_db.transaction() as session:
        user = session.get(StaffUser, graph["user_id"])
        principal = Principal(user.id, user.name, user.role, graph["trainer_id"])
    typed = command.ChangeTime(**body) if kind == "time" else command.ChangeTrainer(**body)
    replicas = [Database(database_settings), Database(database_settings)]
    ready = Barrier(2)

    def apply(db):
        with db.transaction() as session:
            connection = session.scalar(text("SELECT pg_backend_pid()"))
            ready.wait(timeout=5)
            result = command.save(session, principal, graph["session_id"], key, kind, typed)
            return connection, result.model_dump(mode="json")

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(apply, replicas))
    finally:
        for db in replicas:
            db.close()
    assert results[0][0] != results[1][0]
    assert results[0][1] == results[1][1]
    assert trainer_api.get(f"/api/session-changes/{key}").json() == results[0][1]
    assert save(trainer_api, graph, kind, body).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ChangeRequest)) == 1
        assert session.scalar(select(func.count()).select_from(RequestEvent)) == 1
        assert session.scalar(select(func.count()).select_from(Message)) == 1
        assert session.scalar(select(func.count()).select_from(SessionChangeReceipt)) == 1


def test_noop_time_change_has_receipt_without_proposal_or_version_change(
    trainer_api, domain_db, graph, future, replacement
):
    viewed = review(trainer_api, graph, "time")
    current = viewed["session"]
    key = uuid4()
    response = save(
        trainer_api,
        graph,
        "time",
        {
            "expected": viewed["expected"],
            "date": current["date"],
            "startsAt": current["startsAt"],
            "endsAt": current["endsAt"],
        },
        key,
    )
    assert response.status_code == 200, response.text
    assert trainer_api.get(f"/api/session-changes/{key}").json() == response.json()
    assert save(trainer_api, graph, "time", body_for(viewed, replacement), key).status_code == 409
    assert response.json() == {
        "kind": "time",
        "outcome": "applied",
        "session": current,
        "requestId": None,
        "messageId": None,
    }
    with domain_db.transaction() as session:
        assert session.scalar(select(ChangeRequest)) is None
        assert session.scalar(select(SessionEvent)) is None
