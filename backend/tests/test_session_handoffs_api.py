"""Compatibility opening evidence through actual routes and isolated PostgreSQL transactions."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.api import session_handoffs
from app.models.api import SessionHandoffReceipt
from app.models.communications import Message, MessageReceipt, SessionEvent
from app.models.training import Acknowledgement, CreditDebit, TrainingSession
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


def review(api, identity):
    response = api.get(f"/api/sessions/{identity}/handoff-review")
    assert response.status_code == 200, response.text
    return response.json()


def mark(api, identity, viewed, key=None, **patch):
    return api.post(
        f"/api/sessions/{identity}/handoff",
        headers={"Idempotency-Key": str(key or uuid4())},
        json={"expected": viewed["expected"], **patch},
    )


def test_opening_replay_and_repeat_have_truthful_counts_without_completion_or_credit(
    api, domain_db, graph
):
    identity, key = graph["session_id"], uuid4()
    viewed = review(api, identity)
    saved = mark(api, identity, viewed, key)
    assert saved.status_code == 200, saved.text
    assert saved.json()["whatsappOpenCount"] == 1
    assert mark(api, identity, viewed, key).json() == saved.json()
    assert api.get(f"/api/session-handoffs/{key}").json() == saved.json()
    assert mark(api, identity, viewed).status_code == 409
    assert mark(api, identity, viewed, key, expected="0" * 64).status_code == 409
    second = mark(api, identity, review(api, identity))
    assert second.status_code == 200 and second.json()["whatsappOpenCount"] == 2
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, identity)
        assert booking.whatsapp_open_count == 2 and booking.status == "scheduled"
        assert session.scalar(select(func.count()).select_from(CreditDebit)) == 0
        assert session.scalar(select(func.count()).select_from(Acknowledgement)) == 0
        assert session.scalar(select(func.count()).select_from(SessionHandoffReceipt)) == 2
        events = list(
            session.scalars(select(SessionEvent).where(SessionEvent.kind == "whatsapp_opened"))
        )
        assert len(events) == 2 and all("delivery is not verified" in row.note for row in events)
        notices = list(
            session.scalars(select(Message).where(Message.title == "Session opening recorded"))
        )
        assert len(notices) == 2
        for notice in notices:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(MessageReceipt)
                    .where(
                        MessageReceipt.message_id == notice.id,
                        MessageReceipt.user_id == graph["owner_id"],
                    )
                )
                == 1
            )
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.scalar(select(SessionHandoffReceipt)))


def test_original_receipt_survives_later_session_edits_and_is_actor_private(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    from tests.test_staff_api import trainer_login

    identity, key = graph["session_id"], uuid4()
    saved = mark(api, identity, review(api, identity), key)
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, identity)
        booking.client_summary = "Later summary"
        booking.version += 1
    assert api.get(f"/api/session-handoffs/{key}").json() == saved.json()
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get(f"/api/session-handoffs/{key}").status_code == 404
    own = mark(api, identity, review(api, identity), key)
    assert own.status_code == 200 and own.json()["whatsappOpenCount"] == 2


@pytest.mark.parametrize(
    "patch", [{"delivered": True}, {"actorId": "forged"}, {"expected": "invalid"}]
)
def test_forged_or_delivery_claims_are_rejected_without_effect(api, domain_db, graph, patch):
    assert (
        mark(api, graph["session_id"], review(api, graph["session_id"]), **patch).status_code == 422
    )
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, graph["session_id"]).whatsapp_open_count == 0
        assert session.scalar(select(SessionHandoffReceipt)) is None


@pytest.mark.parametrize("kind", ["future", "open"])
def test_future_and_open_sessions_cannot_record_openings(api, domain_db, graph, kind):
    from app.session_numbering import renumber_purchase

    identity = graph["session_id"]
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, identity)
        if kind == "future":
            # Keep the purchased validity and all booking constraints intact.
            day = session.scalar(
                text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date")
            )
            booking.training_date = day + timedelta(days=1)
        else:
            booking.schedule_state = "open"
            booking.training_date = booking.starts_at = booking.ends_at = None
            booking.session_number = booking.schedule_slot_id = None
        booking.version += 1
        session.flush()
        renumber_purchase(session, graph["purchase_id"])
    assert api.get(f"/api/sessions/{identity}/handoff-review").status_code == 409
    assert mark(api, identity, {"expected": "a" * 64}).status_code == 409


def test_inactive_purchase_rejects_new_opening_but_keeps_original_receipt(api, graph):
    from tests.test_client_reactivation_review import deactivate

    identity, key = graph["session_id"], uuid4()
    viewed = review(api, identity)
    first = mark(api, identity, viewed, key)
    deactivate(api, graph)
    assert mark(api, identity, viewed).status_code == 409
    assert mark(api, identity, viewed, key).json() == first.json()


def test_terminal_cover_and_foreign_records_remain_read_only(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    from app.persistence import acknowledge
    from tests.test_directory_api import covered_session
    from tests.test_staff_api import trainer_login

    _, identity, _ = covered_session(domain_db, graph)
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, identity)
        acknowledge(session, identity, booking.version, graph["owner_id"], method="late_no_show")
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get(f"/api/sessions/{identity}").status_code == 200
    assert api.get(f"/api/sessions/{identity}/handoff-review").status_code == 404
    assert mark(api, identity, {"expected": "a" * 64}).status_code == 404
    assert mark(api, uuid4(), {"expected": "a" * 64}).status_code == 404


def test_receipt_failure_rolls_back_counter_timestamp_and_event(api, domain_db, graph, monkeypatch):
    viewed = review(api, graph["session_id"])

    def fail(**kwargs):
        raise RuntimeError("Interrupted before original receipt")

    monkeypatch.setattr(session_handoffs, "MessageReceipt", fail)
    assert mark(api, graph["session_id"], viewed).status_code == 500
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        assert booking.whatsapp_open_count == 0 and booking.whatsapp_opened_at is None
        assert booking.version == viewed["version"]
        assert (
            session.scalar(select(SessionEvent).where(SessionEvent.kind == "whatsapp_opened"))
            is None
        )
        assert (
            session.scalar(select(Message).where(Message.title == "Session opening recorded"))
            is None
        )
        assert session.scalar(select(SessionHandoffReceipt)) is None


@pytest.mark.parametrize("duplicate", [True, False])
def test_competing_connections_preserve_one_opening_for_one_review(
    api, domain_db, database_settings, graph, duplicate
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from app.auth.errors import AuthError
    from app.authorization import Principal
    from app.database import Database

    viewed = review(api, graph["session_id"])
    request_key, ready = uuid4(), Barrier(2)
    principal = Principal(graph["owner_id"], "Owner Original", "owner", None)
    replicas = [Database(database_settings), Database(database_settings)]

    def apply(pair):
        db, index = pair
        with db.transaction() as session:
            pid = session.scalar(text("SELECT pg_backend_pid()"))
            ready.wait(timeout=5)
            try:
                result = session_handoffs.save(
                    session,
                    principal,
                    graph["session_id"],
                    request_key if duplicate or index == 0 else uuid4(),
                    session_handoffs.MarkHandoff(expected=viewed["expected"]),
                )
                return pid, result.model_dump(mode="json")
            except AuthError as error:
                return pid, error.status

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(apply, zip(replicas, [0, 1], strict=True)))
    finally:
        for db in replicas:
            db.close()
    assert len({r[0] for r in results}) == 2
    if duplicate:
        assert results[0][1] == results[1][1]
    else:
        assert sum(r[1] == 409 for r in results) == 1
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, graph["session_id"]).whatsapp_open_count == 1
        assert session.scalar(select(func.count()).select_from(SessionHandoffReceipt)) == 1


def test_populated_handoff_evidence_refuses_destructive_downgrade(api, domain_db, graph, migrate):
    assert mark(api, graph["session_id"], review(api, graph["session_id"])).status_code == 200
    with pytest.raises(DBAPIError):
        migrate("downgrade", "20261024_0039")
    with domain_db.transaction() as session:
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "20261101_0052"
        assert session.scalar(select(func.count()).select_from(SessionHandoffReceipt)) == 1
