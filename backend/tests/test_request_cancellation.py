"""Withdraw only owned pending proposals; preserve decisions, history and read receipts."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.api import request_cancellation as command
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.api import RequestCancellationReceipt
from app.models.communications import ChangeRequest, Message, MessageReceipt, RequestEvent
from app.models.training import TrainingSession
from tests.test_message_api import seed_request
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def cancel(api, identity, version=1, key=None, **extra):
    return api.post(
        f"/api/requests/{identity}/cancel",
        json={"expectedVersion": version, **extra},
        headers={"Idempotency-Key": str(key or uuid4())},
    )


@pytest.fixture
def requesting_trainer(api, domain_db, graph, auth_settings, auth_service, fake_cognito):
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    return api


def actor(graph):
    return Principal(graph["user_id"], "Trainer", "trainer", graph["trainer_id"])


def seed(domain_db, graph, kind="trainer_availability"):
    with domain_db.transaction() as session:
        return seed_request(session, graph, kind)


@pytest.mark.parametrize(
    "kind",
    [
        "trainer_availability",
        "fixed_weekly_schedule",
        "session_time",
        "session_trainer",
        "session_postpone",
    ],
)
def test_owned_cancellation_is_atomic_idempotent_and_never_applies_proposal(
    requesting_trainer, domain_db, graph, kind
):
    identity, notice = seed(domain_db, graph, kind)
    with domain_db.transaction() as session:
        before = [
            (row.id, row.version, row.training_date, row.starts_at, row.trainer_id)
            for row in session.scalars(select(TrainingSession).order_by(TrainingSession.id))
        ]
    key = uuid4()
    response = cancel(requesting_trainer, identity, key=key)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["status"] == "cancelled" and saved["version"] == 2
    assert saved["by"]["id"] == str(graph["user_id"])
    assert cancel(requesting_trainer, identity, key=key).json() == saved
    assert cancel(requesting_trainer, identity).json() == saved
    assert cancel(requesting_trainer, identity, 2).json() == saved
    assert requesting_trainer.get(f"/api/request-cancellations/{key}").json() == saved
    assert cancel(requesting_trainer, identity, 2, key).status_code == 409
    rows = requesting_trainer.get("/api/messages").json()
    original = next(row for row in rows if row["id"] == str(notice))
    assert original["request"]["status"] == "cancelled"
    assert original["request"]["resolved_by"] == saved["by"]
    assert original["read"] is False and original["version"] == 1
    assert len(rows) == 2
    with domain_db.transaction() as session:
        assert before == [
            (row.id, row.version, row.training_date, row.starts_at, row.trainer_id)
            for row in session.scalars(select(TrainingSession).order_by(TrainingSession.id))
        ]
        assert session.scalar(select(func.count()).select_from(RequestEvent)) == 2
        assert session.scalar(select(func.count()).select_from(Message)) == 3
        assert session.scalar(select(func.count()).select_from(MessageReceipt)) == 4
        assert session.scalar(select(func.count()).select_from(RequestCancellationReceipt)) == 3


def test_owner_cannot_cancel_or_read_trainer_receipts(api, domain_db, graph):
    identity, _ = seed(domain_db, graph)
    assert cancel(api, identity).status_code == 403
    assert api.get(f"/api/request-cancellations/{uuid4()}").status_code == 403


def test_wrong_trainer_is_hidden_and_receipts_are_actor_scoped(domain_db, graph):
    identity, _ = seed(domain_db, graph)
    key = uuid4()
    with domain_db.transaction() as session:
        command.save(session, actor(graph), identity, key, command.CancelRequest(expectedVersion=1))
    other = Principal(graph["owner_id"], "Other", "trainer", uuid4())
    for call in [
        lambda s: command.save(
            s, other, identity, uuid4(), command.CancelRequest(expectedVersion=1)
        ),
        lambda s: command.reconcile(s, other, key),
    ]:
        with pytest.raises(AuthError) as failure, domain_db.transaction() as session:
            call(session)
        assert failure.value.status == 404


def test_stale_and_untrusted_fields_do_not_cancel(requesting_trainer, domain_db, graph):
    identity, _ = seed(domain_db, graph)
    assert cancel(requesting_trainer, identity, 2).status_code == 409
    assert cancel(requesting_trainer, identity, actorId=str(graph["owner_id"])).status_code == 422
    assert cancel(requesting_trainer, identity, True).status_code == 422
    with domain_db.transaction() as session:
        assert session.get(ChangeRequest, identity).status == "pending"
        assert session.scalar(select(func.count()).select_from(RequestEvent)) == 1


@pytest.mark.parametrize("status", ["approved", "rejected", "superseded"])
def test_terminal_decision_cannot_be_overwritten(requesting_trainer, domain_db, graph, status):
    identity, _ = seed(domain_db, graph)
    with domain_db.transaction() as session:
        row = session.get(ChangeRequest, identity)
        row.status = status
        row.resolved_by = graph["owner_id"]
        row.resolved_at = session.scalar(text("SELECT clock_timestamp()"))
        row.version += 1
        session.add(
            RequestEvent(
                request_id=identity,
                sequence=2,
                status=status,
                actor_id=graph["owner_id"],
                actor_name="Owner",
            )
        )
    assert cancel(requesting_trainer, identity, 2).status_code == 409
    with domain_db.transaction() as session:
        assert session.get(ChangeRequest, identity).status == status
        assert session.scalar(select(func.count()).select_from(RequestCancellationReceipt)) == 0


def test_notification_failure_rolls_back_entire_cancellation(domain_db, graph, monkeypatch):
    identity, _ = seed(domain_db, graph)

    def fail(*args):
        raise RuntimeError("notification failed")

    monkeypatch.setattr(command, "notify", fail)
    with pytest.raises(RuntimeError), domain_db.transaction() as session:
        command.save(
            session, actor(graph), identity, uuid4(), command.CancelRequest(expectedVersion=1)
        )
    with domain_db.transaction() as session:
        assert session.get(ChangeRequest, identity).status == "pending"
        assert session.scalar(select(func.count()).select_from(RequestEvent)) == 1
        assert session.scalar(select(func.count()).select_from(RequestCancellationReceipt)) == 0


def test_concurrent_retries_create_only_one_decision_and_notice_pair(domain_db, graph):
    identity, _ = seed(domain_db, graph)

    def write(_):
        with domain_db.transaction() as session:
            return command.save(
                session, actor(graph), identity, uuid4(), command.CancelRequest(expectedVersion=1)
            ).model_dump(mode="json")

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(write, range(3)))
    assert results[0] == results[1] == results[2]
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(RequestEvent)) == 2
        assert session.scalar(select(func.count()).select_from(Message)) == 3


def test_cancellation_receipts_are_immutable_and_prevent_lossy_downgrade(domain_db, graph, migrate):
    identity, _ = seed(domain_db, graph)
    with domain_db.transaction() as session:
        command.save(
            session, actor(graph), identity, uuid4(), command.CancelRequest(expectedVersion=1)
        )
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.execute(text("DELETE FROM request_cancellation_receipts"))
    with pytest.raises(DBAPIError, match="Request cancellation downgrade refused"):
        migrate("downgrade", "20261013_0022")
