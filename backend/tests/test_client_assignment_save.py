"""Permanent reassignment is scoped, atomic, historical and safely repeatable."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.api import client_assignment_save as command
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.api import ClientAssignmentReceipt
from app.models.communications import ChangeRequest, RequestEvent, SessionEvent
from app.models.people import Client
from app.models.training import AssignmentChange, AssignmentEvent, PackagePurchase, TrainingSession
from tests.test_client_assignment_review import read
from tests.test_client_assignment_review import replacement as replacement
from tests.test_client_reactivation_review import snapshot
from tests.test_message_api import seed_request
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def payload(api, graph, replacement):
    return {"expected": read(api, graph)["expected"], "trainerId": str(replacement)}


def save(api, graph, body, key=None):
    return api.post(
        f"/api/clients/{graph['client_id']}/trainer-assignment",
        json=body,
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_atomic_reassignment_preserves_purchased_terms_and_historical_sessions(
    api, domain_db, graph, replacement
):
    with domain_db.transaction() as session:
        historical = session.get(TrainingSession, graph["session_id"])
        original = (historical.trainer_id, historical.version, historical.training_date)
    body, key = payload(api, graph, replacement), uuid4()
    response = save(api, graph, body, key)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["trainerId"] == str(replacement)
    assert save(api, graph, body, key).json() == result
    assert api.get(f"/api/client-trainer-assignments/{key}").json() == result
    with domain_db.transaction() as session:
        client = session.get(Client, graph["client_id"])
        purchase = session.get(PackagePurchase, graph["purchase_id"])
        historical = session.get(TrainingSession, graph["session_id"])
        future = session.get(TrainingSession, graph["second_session_id"])
        assert client.trainer_id == purchase.trainer_id == future.trainer_id == replacement
        assert purchase.purchased_trainer_id == graph["trainer_id"]
        assert (historical.trainer_id, historical.version, historical.training_date) == original
        assert session.scalar(select(func.count()).select_from(AssignmentEvent)) == 1
        assert session.scalar(select(func.count()).select_from(AssignmentChange)) == 2
        assert session.scalar(select(func.count()).select_from(SessionEvent)) == 1
        assert session.scalar(select(func.count()).select_from(ClientAssignmentReceipt)) == 1
    history = read(api, graph)["history"]
    assert history[0]["id"] == result["eventId"]
    assert history[0]["previous"]["id"] == str(graph["trainer_id"])


def test_stale_review_and_changed_idempotency_body_never_overwrite(
    api, domain_db, graph, replacement
):
    body = payload(api, graph, replacement)
    with domain_db.transaction() as session:
        session.get(TrainingSession, graph["second_session_id"]).training_date += timedelta(days=1)
    before = snapshot(domain_db)
    assert save(api, graph, body).status_code == 409
    assert snapshot(domain_db) == before
    fresh, key = payload(api, graph, replacement), uuid4()
    assert save(api, graph, fresh, key).status_code == 200
    assert (
        save(api, graph, {**fresh, "trainerId": str(graph["trainer_id"])}, key).status_code == 409
    )


def test_failed_notice_rolls_back_assignment_and_all_evidence(
    api, domain_db, graph, replacement, monkeypatch
):
    body, before = payload(api, graph, replacement), snapshot(domain_db)

    def fail(*args):
        raise RuntimeError("notice failed")

    monkeypatch.setattr(command, "notify", fail)
    assert save(api, graph, body).status_code == 500
    assert snapshot(domain_db) == before
    with domain_db.transaction() as session:
        for model in [AssignmentEvent, AssignmentChange, SessionEvent, ClientAssignmentReceipt]:
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_concurrent_identical_retry_has_one_assignment(api, domain_db, graph, replacement):
    body, key = payload(api, graph, replacement), uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: save(api, graph, body, key), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert responses[0].json() == responses[1].json()
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(AssignmentEvent)) == 1


@pytest.mark.parametrize(
    "kind", ["session_time", "session_trainer", "session_postpone", "fixed_weekly_schedule"]
)
def test_reassignment_rejects_superseded_proposals_atomically(
    api, domain_db, graph, replacement, kind
):
    with domain_db.transaction() as session:
        identity, _ = seed_request(
            session, {**graph, "session_id": graph["second_session_id"]}, kind
        )
        unrelated, _ = seed_request(session, graph, "trainer_availability")
    assert save(api, graph, payload(api, graph, replacement)).status_code == 200
    with domain_db.transaction() as session:
        proposal = session.get(ChangeRequest, identity)
        assert proposal.status == "rejected" and proposal.version == 2
        assert proposal.resolution_note == "Superseded by permanent trainer reassignment."
        assert session.get(ChangeRequest, unrelated).status == "pending"
        event = session.scalar(
            select(RequestEvent).where(
                RequestEvent.request_id == identity, RequestEvent.sequence == 2
            )
        )
        assert event.status == "rejected" and event.actor_id == graph["owner_id"]


def test_trainer_cannot_save_or_reconcile_and_receipts_are_actor_scoped(
    api, domain_db, graph, replacement, auth_settings, auth_service, fake_cognito
):
    body, key = payload(api, graph, replacement), uuid4()
    assert save(api, graph, body, key).status_code == 200
    other = Principal(graph["user_id"], "Other", "admin", None)
    with pytest.raises(AuthError) as failure, domain_db.transaction() as session:
        command.reconcile(session, other, key)
    assert failure.value.status == 404
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert save(api, graph, body, key).status_code == 403
    assert api.get(f"/api/client-trainer-assignments/{key}").status_code == 403


def test_immutable_receipt_and_populated_downgrade_guard(api, domain_db, graph, replacement):
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    from sqlalchemy import text

    result = save(api, graph, payload(api, graph, replacement)).json()
    UUID(result["eventId"])
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.scalar(select(ClientAssignmentReceipt)))
    path = Path(__file__).parents[1] / "migrations/versions/20261013_0028_client_assignment.py"
    spec = spec_from_file_location("assignment_receipts", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.execute(text(migration.DOWNGRADE_SQL))
