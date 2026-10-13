"""Real PostgreSQL/HTTP approval writes, current authority and immutable recovery."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.api import trainer_approvals as commands
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.api import TrainerApprovalReceipt
from app.models.communications import Message, MessageReceipt
from app.models.people import StaffUser, Trainer
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database
CONTROLS = {
    "availability": False,
    "sessionTime": True,
    "trainerReassignment": False,
    "fixedWeeklySchedule": True,
}


def payload(**patch):
    return {"expectedVersion": 1, "approvalNeeded": CONTROLS, **patch}


def save(api, graph, body=None, key=None):
    return api.post(
        f"/api/trainers/{graph['trainer_id']}/approvals",
        json=body if body is not None else payload(),
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_save_persists_only_controls_with_atomic_audit_and_notice(api, domain_db, graph):
    before = api.get("/api/directory").json()
    response = save(api, graph)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "id": str(graph["trainer_id"]),
        "version": 2,
        "approvalNeeded": CONTROLS,
    }
    after = api.get("/api/directory").json()
    assert after["trainerApprovalWrites"] is True
    assert before["clients"] == after["clients"]
    assert before["packages"] == after["packages"]
    first = next(t for t in before["trainers"] if t["id"] == str(graph["trainer_id"]))
    last = next(t for t in after["trainers"] if t["id"] == str(graph["trainer_id"]))
    assert last == {
        **first,
        "version": 2,
        "approve_availability": False,
        "approve_session_trainer": False,
    }
    with domain_db.transaction() as session:
        receipt = session.scalar(select(TrainerApprovalReceipt))
        assert receipt.previous == dict.fromkeys(CONTROLS, True)
        assert receipt.result == response.json()
        assert receipt.actor_id == graph["owner_id"]
        assert session.scalar(select(func.count()).select_from(Message)) == 1
        assert set(session.scalars(select(MessageReceipt.user_id))) == {
            graph["owner_id"],
            graph["user_id"],
        }


def test_reconcile_and_replay_preserve_original_result_after_later_edit(api, graph):
    key = uuid4()
    result = save(api, graph, key=key).json()
    assert save(api, graph, payload(expectedVersion=2)).json()["version"] == 3
    assert save(api, graph, key=key).json() == result
    assert api.get(f"/api/trainer-approval-saves/{key}").json() == result
    assert save(api, graph, payload(expectedVersion=3), key).status_code == 409
    assert save(api, graph).status_code == 409
    assert api.get(f"/api/trainer-approval-saves/{uuid4()}").status_code == 404


@pytest.mark.parametrize(
    "patch",
    [
        {"expectedVersion": True},
        {"expectedVersion": 0},
        {"expectedVersion": "1"},
        {"approvalNeeded": {**CONTROLS, "availability": "false"}},
        {"approvalNeeded": {**CONTROLS, "availability": 0}},
        {"approvalNeeded": {"availability": False}},
        {"approvalNeeded": {**CONTROLS, "rates": 0}},
        {"actor": "owner"},
    ],
)
def test_malformed_or_extra_fields_never_write(api, domain_db, graph, patch):
    assert save(api, graph, payload(**patch)).status_code == 422
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(TrainerApprovalReceipt)) == 0
        assert session.get(Trainer, graph["trainer_id"]).version == 1


def test_exact_transport_and_resource_required(api, graph):
    assert save(api, {"trainer_id": uuid4()}).status_code == 404
    assert (
        api.post(f"/api/trainers/{graph['trainer_id']}/approvals", json=payload()).status_code
        == 422
    )
    api.headers.pop("X-CSRF-Token")
    assert save(api, graph).status_code == 403


def test_trainer_cannot_change_controls_or_read_operations_receipt(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    key = uuid4()
    assert save(api, graph, key=key).status_code == 200
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert save(api, graph, payload(expectedVersion=2)).status_code == 403
    assert api.get(f"/api/trainer-approval-saves/{key}").status_code == 403


def test_admin_has_no_rates_and_actor_scoped_receipts(api, domain_db, graph):
    key = uuid4()
    assert save(api, graph, key=key).status_code == 200
    with domain_db.transaction() as session:
        admin = StaffUser(name="Operations", email="ops@example.test", role="admin")
        session.add(admin)
        session.flush()
        principal = Principal(admin.id, admin.name, "admin", None)
        with pytest.raises(AuthError) as denied:
            commands.reconcile(session, principal, key)
        assert denied.value.status == 404
        result = commands.save(
            session,
            principal,
            graph["trainer_id"],
            key,
            commands.SaveApprovals(**payload(expectedVersion=2)),
        )
        assert set(result.model_dump()) == {"id", "version", "approvalNeeded"}
    with domain_db.transaction() as session:
        assert commands.reconcile(session, principal, key) == result


def test_parallel_identical_retry_has_one_effect_and_competing_versions_conflict(domain_db, graph):
    principal = Principal(graph["owner_id"], "Owner Original", "owner", None)
    key = uuid4()

    def submit(request_key):
        try:
            with domain_db.transaction() as session:
                return commands.save(
                    session,
                    principal,
                    graph["trainer_id"],
                    request_key,
                    commands.SaveApprovals(**payload()),
                ).model_dump(mode="json")
        except AuthError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, [key, key]))
    assert results[0] == results[1] and results[0]["version"] == 2
    assert submit(uuid4()) == "state_conflict"
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(TrainerApprovalReceipt)) == 1


def test_immutable_receipt_and_populated_downgrade_guard(api, domain_db, graph, migrate):
    assert save(api, graph).status_code == 200
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.scalar(select(TrainerApprovalReceipt)))
    with pytest.raises(DBAPIError, match="downgrade refused"):
        migrate("downgrade", "20261013_0007")


def test_rollback_restores_controls_and_removes_notice_and_receipt(domain_db, graph):
    principal = Principal(graph["owner_id"], "Owner Original", "owner", None)
    with pytest.raises(RuntimeError), domain_db.transaction() as session:
        commands.save(
            session, principal, graph["trainer_id"], uuid4(), commands.SaveApprovals(**payload())
        )
        raise RuntimeError("Abort")
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(TrainerApprovalReceipt)) == 0
        assert session.scalar(select(func.count()).select_from(Message)) == 0
        assert session.get(Trainer, graph["trainer_id"]).version == 1
