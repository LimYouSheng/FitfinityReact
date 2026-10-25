"""Reactivation is atomic, versioned and never revives an old authenticated session."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.api import trainer_reactivation as commands
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.api import TrainerReactivationReceipt
from app.models.authentication import AuthSession
from app.models.communications import Message
from app.models.people import LifecycleEvent, StaffIdentity, StaffUser, Trainer
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def deactivate(domain_db, graph):
    with domain_db.transaction() as session:
        session.get(Trainer, graph["trainer_id"]).status = "inactive"
        session.get(StaffUser, graph["user_id"]).status = "inactive"


def body(graph, **patch):
    return {
        "expectedVersion": 2,
        "expectedAccountId": str(graph["user_id"]),
        "expectedAccountVersion": 2,
        **patch,
    }


def save(api, graph, payload=None, key=None):
    return api.post(
        f"/api/trainers/{graph['trainer_id']}/reactivation",
        json=payload if payload is not None else body(graph),
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_review_save_replay_and_unchanged_records(api, domain_db, graph, migrate):
    deactivate(domain_db, graph)
    before = api.get("/api/directory").json()
    review = api.get(f"/api/trainers/{graph['trainer_id']}/reactivation")
    assert review.json() == {
        "id": str(graph["trainer_id"]),
        "version": 2,
        "accountId": str(graph["user_id"]),
        "accountVersion": 2,
    }
    key = uuid4()
    result = save(api, graph, key=key)
    assert result.status_code == 200, result.text
    assert result.json() == {"id": str(graph["trainer_id"]), "version": 3, "status": "active"}
    assert save(api, graph, key=key).json() == result.json()
    assert api.get(f"/api/trainer-reactivations/{key}").json() == result.json()
    assert save(api, graph).status_code == 409
    assert save(api, graph, body(graph, expectedVersion=3), key).status_code == 409
    assert api.get(f"/api/trainers/{graph['trainer_id']}/reactivation").status_code == 409
    after = api.get("/api/directory").json()
    assert before["clients"] == after["clients"] and before["packages"] == after["packages"]
    old = next(t for t in before["trainers"] if t["id"] == str(graph["trainer_id"]))
    new = next(t for t in after["trainers"] if t["id"] == str(graph["trainer_id"]))
    assert new == {**old, "version": 3, "status": "active"}
    with domain_db.transaction() as session:
        user = session.get(StaffUser, graph["user_id"])
        assert user.status == "active" and user.version == 3
        assert len(session.scalars(select(TrainerReactivationReceipt)).all()) == 1
        event = session.scalar(
            select(LifecycleEvent).where(LifecycleEvent.trainer_id == graph["trainer_id"])
        )
        assert event.status == "active" and event.actor_id == graph["owner_id"]
        assert (
            len(session.scalars(select(Message).where(Message.kind == "trainer_status")).all()) == 1
        )
    with pytest.raises(DBAPIError, match="populated attribution downgrade refused"):
        migrate("downgrade", "20261013_0015")
    with pytest.raises(DBAPIError, match="immutable"), domain_db.transaction() as session:
        session.delete(session.scalar(select(TrainerReactivationReceipt)))


@pytest.mark.parametrize(
    "patch",
    [
        {"expectedVersion": 1},
        {"expectedAccountVersion": 1},
        {"expectedAccountId": str(uuid4())},
        {"expectedAccountId": None},
        {"expectedAccountVersion": None},
    ],
)
def test_stale_reviews_have_no_effect(api, domain_db, graph, patch):
    deactivate(domain_db, graph)
    assert save(api, graph, body(graph, **patch)).status_code == 409
    with domain_db.transaction() as session:
        assert session.get(Trainer, graph["trainer_id"]).status == "inactive"
        assert session.get(StaffUser, graph["user_id"]).status == "inactive"
        assert session.scalar(select(TrainerReactivationReceipt)) is None


@pytest.mark.parametrize(
    "patch",
    [
        {"expectedVersion": True},
        {"expectedAccountVersion": "2"},
        {"status": "active"},
        {"actorId": str(uuid4())},
        {"email_verified": True},
    ],
)
def test_strict_input_rejects_identity_and_provider_overrides(api, graph, patch):
    assert save(api, graph, body(graph, **patch)).status_code == 422


def test_admin_receipts_are_private_and_financial_fields_absent(
    api, invitations, domain_db, graph, auth_service, auth_settings, fake_cognito
):
    admin_id = create_admin(api).json()["id"]
    deactivate(domain_db, graph)
    key = uuid4()
    assert save(api, graph, key=key).status_code == 200
    login_admin(api, auth_service, auth_settings, fake_cognito, admin_id)
    assert api.get(f"/api/trainer-reactivations/{key}").status_code == 404
    deactivate(domain_db, graph)
    result = save(api, graph, body(graph, expectedVersion=4, expectedAccountVersion=4))
    assert result.status_code == 200, result.text
    assert set(result.json()) == {"id", "version", "status"}
    assert "peak_rate" not in api.get("/api/directory").text


def test_trainer_cannot_review_reactivate_or_reconcile(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get(f"/api/trainers/{graph['trainer_id']}/reactivation").status_code == 403
    assert save(api, graph).status_code == 403
    assert api.get(f"/api/trainer-reactivations/{uuid4()}").status_code == 403


def test_old_session_stays_closed_and_active_identity_requires_new_signin(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    old_handle = api.cookies.get(auth_settings.session_cookie)
    deactivate(domain_db, graph)
    with domain_db.transaction() as session:
        commands.save(
            session,
            Principal(graph["owner_id"], "Owner", "owner", None),
            graph["trainer_id"],
            uuid4(),
            commands.ReactivateTrainer(**body(graph)),
        )
    with pytest.raises(AuthError):
        auth_service.principal(old_handle)
    with domain_db.transaction() as session:
        old = session.scalar(select(AuthSession).where(AuthSession.user_id == graph["user_id"]))
        assert old.closed_at and old.access_cipher is None
        assert (
            session.scalar(
                select(StaffIdentity).where(StaffIdentity.user_id == graph["user_id"])
            ).status
            == "active"
        )
    flow = auth_service.sign_in("trainer@example.test", "initial-password-value")
    fresh = auth_service.challenge(flow.flow_handle, code="123456")
    assert fresh.session_handle != old_handle
    assert auth_service.principal(fresh.session_handle)[1].user_id == graph["user_id"]


def test_concurrent_duplicate_has_one_effect_and_disabled_identity_stays_disabled(
    api, domain_db, graph, auth_settings
):
    deactivate(domain_db, graph)
    with domain_db.transaction() as session:
        session.add(
            StaffIdentity(
                user_id=graph["user_id"],
                issuer=auth_settings.cognito_issuer,
                subject="disabled-trainer",
                status="inactive",
            )
        )
    key = uuid4()

    def submit(_):
        with domain_db.transaction() as session:
            return commands.save(
                session,
                Principal(graph["owner_id"], "Owner", "owner", None),
                graph["trainer_id"],
                key,
                commands.ReactivateTrainer(**body(graph)),
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert results[0] == results[1]
    with domain_db.transaction() as session:
        assert session.get(Trainer, graph["trainer_id"]).version == 3
        assert len(session.scalars(select(TrainerReactivationReceipt)).all()) == 1
        assert (
            session.scalar(
                select(StaffIdentity).where(StaffIdentity.user_id == graph["user_id"])
            ).status
            == "inactive"
        )


def test_unlinked_trainer_can_reactivate_without_creating_an_account(api, domain_db, graph):
    with domain_db.transaction() as session:
        trainer = session.get(Trainer, graph["trainer_id"])
        trainer.user_id, trainer.status = None, "inactive"
    result = save(api, graph, body(graph, expectedAccountId=None, expectedAccountVersion=None))
    assert result.status_code == 200, result.text
    with domain_db.transaction() as session:
        assert session.get(Trainer, graph["trainer_id"]).user_id is None


def test_missing_target_and_missing_receipt_are_unavailable(api, graph):
    assert api.get(f"/api/trainers/{uuid4()}/reactivation").status_code == 404
    assert api.get(f"/api/trainer-reactivations/{uuid4()}").status_code == 404


def test_transaction_failure_rolls_back_account_and_all_evidence(api, domain_db, graph):
    deactivate(domain_db, graph)
    with pytest.raises(RuntimeError), domain_db.transaction() as session:
        commands.save(
            session,
            Principal(graph["owner_id"], "Owner", "owner", None),
            graph["trainer_id"],
            uuid4(),
            commands.ReactivateTrainer(**body(graph)),
        )
        raise RuntimeError("rollback")
    with domain_db.transaction() as session:
        assert session.get(Trainer, graph["trainer_id"]).status == "inactive"
        assert session.get(StaffUser, graph["user_id"]).status == "inactive"
        assert session.scalar(select(TrainerReactivationReceipt)) is None
