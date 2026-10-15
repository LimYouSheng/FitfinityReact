"""Deactivation reassigns the complete batch and atomically closes application access."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.api import trainer_deactivation_save as command
from app.api.trainer_deactivation import TrainerDeactivationSelection
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.api import TrainerDeactivationReceipt
from app.models.authentication import AuthSession
from app.models.communications import Message, SessionEvent
from app.models.people import Client, StaffIdentity, StaffUser, Trainer
from app.models.training import PackagePurchase, TrainingSession
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_client_assignment_review import replacement as replacement
from tests.test_client_reactivation_review import snapshot
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def read(api, graph):
    response = api.get(f"/api/trainers/{graph['trainer_id']}/deactivation-review")
    assert response.status_code == 200, response.text
    return response.json()


def payload(api, graph, replacement):
    viewed = read(api, graph)
    return {
        "expected": viewed["expected"],
        "replacements": {r["id"]: str(replacement) for r in viewed["sessions"]},
    }


def save(api, graph, body, key=None):
    return api.post(
        f"/api/trainers/{graph['trainer_id']}/deactivation",
        json=body,
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_review_includes_past_uncompleted_and_open_without_writes(
    api, domain_db, graph, replacement
):
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["second_session_id"])
        booking.schedule_state = "open"
        booking.training_date = booking.starts_at = booking.ends_at = None
        booking.session_number = booking.schedule_slot_id = None
    before = snapshot(domain_db)
    viewed = read(api, graph)
    assert {r["id"] for r in viewed["sessions"]} == {
        str(graph["session_id"]),
        str(graph["second_session_id"]),
    }
    row = next(r for r in viewed["sessions"] if r["scheduleState"] == "open")
    assert row["date"] is row["startsAt"] is row["endsAt"] is None
    assert all(
        r["choices"]
        == [{"id": str(replacement), "name": "Replacement", "version": 1, "error": None}]
        for r in viewed["sessions"]
    )
    assert snapshot(domain_db) == before
    assert set(viewed) == {
        "id",
        "version",
        "name",
        "accountId",
        "accountVersion",
        "expected",
        "sessions",
    }


def test_atomic_batch_preserves_permanent_assignment_and_purchased_terms(
    api, domain_db, graph, replacement
):
    before = snapshot(domain_db)
    body, key = payload(api, graph, replacement), uuid4()
    response = save(api, graph, body, key)
    assert response.status_code == 200, response.text
    assert response.json() == {"id": str(graph["trainer_id"]), "version": 2, "status": "inactive"}
    assert save(api, graph, body, key).json() == response.json()
    assert api.get(f"/api/trainer-deactivations/{key}").json() == response.json()
    after = snapshot(domain_db)
    assert (
        before["clients"] == after["clients"]
        and before["package_purchases"] == after["package_purchases"]
    )
    with domain_db.transaction() as session:
        assert session.get(Trainer, graph["trainer_id"]).status == "inactive"
        assert session.get(StaffUser, graph["user_id"]).status == "inactive"
        bookings = session.scalars(select(TrainingSession)).all()
        assert all(b.trainer_id == replacement for b in bookings)
        assert len(bookings) == 2
        assert session.scalar(select(func.count()).select_from(SessionEvent)) == 2
        assert session.scalar(select(func.count()).select_from(TrainerDeactivationReceipt)) == 1
        assert session.scalar(select(func.count()).select_from(Message)) == 1
    assert save(api, graph, {**body, "replacements": {}}, key).status_code == 409


@pytest.mark.parametrize("scope", ["client", "purchase", "cancelled", "completed"])
def test_inactive_and_historical_records_retain_assignment(
    api, domain_db, graph, replacement, scope
):
    from app.persistence import acknowledge

    if scope == "client":
        from tests.test_client_reactivation_review import deactivate

        deactivate(api, graph)
    with domain_db.transaction() as session:
        if scope == "client":
            pass
        elif scope == "purchase":
            from tests.test_package_reactivation_review import freeze

            freeze(session, graph, session.get(PackagePurchase, graph["purchase_id"]))
        elif scope == "cancelled":
            session.get(TrainingSession, graph["session_id"]).status = "cancelled"
        else:
            acknowledge(
                session,
                graph["session_id"],
                actor_id=graph["user_id"],
                expected_version=1,
                method="late_no_show",
            )
    reviewed = read(api, graph)
    assert str(graph["session_id"]) not in {r["id"] for r in reviewed["sessions"]}
    body = payload(api, graph, replacement)
    response = save(api, graph, body)
    assert response.status_code == 200, response.text
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, graph["session_id"]).trainer_id == graph["trainer_id"]


@pytest.mark.parametrize("patch", ["missing", "foreign", "inactive", "self", "stale"])
def test_invalid_and_stale_batches_do_not_partially_deactivate(
    api, domain_db, graph, replacement, patch
):
    body = payload(api, graph, replacement)
    if patch == "missing":
        body["replacements"].pop(str(graph["session_id"]))
    if patch == "foreign":
        body["replacements"][str(uuid4())] = str(replacement)
    if patch == "self":
        body["replacements"][str(graph["session_id"])] = str(graph["trainer_id"])
    if patch in {"inactive", "stale"}:
        with domain_db.transaction() as session:
            if patch == "inactive":
                session.get(Trainer, replacement).status = "inactive"
            else:
                session.get(TrainingSession, graph["session_id"]).training_date += timedelta(days=1)
    before = snapshot(domain_db)
    assert save(api, graph, body).status_code == 409
    assert snapshot(domain_db) == before
    with domain_db.transaction() as session:
        assert session.get(Trainer, graph["trainer_id"]).status == "active"
        assert session.scalar(select(TrainerDeactivationReceipt)) is None


def test_notice_failure_rolls_back_sessions_and_account(
    api, domain_db, graph, replacement, monkeypatch
):
    body, before = payload(api, graph, replacement), snapshot(domain_db)

    def fail(*args, **kwargs):
        raise RuntimeError("notice failed")

    monkeypatch.setattr(command, "notify", fail)
    assert save(api, graph, body).status_code == 500
    assert snapshot(domain_db) == before
    with domain_db.transaction() as session:
        assert session.get(Trainer, graph["trainer_id"]).status == "active"
        assert session.get(StaffUser, graph["user_id"]).status == "active"
        assert session.scalar(select(SessionEvent)) is None
        assert session.scalar(select(TrainerDeactivationReceipt)) is None


def test_concurrent_identical_request_has_one_effect(api, domain_db, graph, replacement):
    body, key = payload(api, graph, replacement), uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: save(api, graph, body, key), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert responses[0].json() == responses[1].json()
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(TrainerDeactivationReceipt)) == 1


def test_deactivation_revokes_existing_application_session(
    api, domain_db, graph, replacement, auth_service, auth_settings, fake_cognito
):
    body = payload(api, graph, replacement)
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    handle = api.cookies.get(auth_settings.session_cookie)
    assert api.get(f"/api/trainers/{graph['trainer_id']}/deactivation-review").status_code == 403
    assert save(api, graph, body).status_code == 403
    assert api.get(f"/api/trainer-deactivations/{uuid4()}").status_code == 403
    with domain_db.transaction() as session:
        command.save(
            session,
            Principal(graph["owner_id"], "Owner", "owner", None),
            graph["trainer_id"],
            uuid4(),
            TrainerDeactivationSelection(**body),
        )
    with pytest.raises(AuthError):
        auth_service.principal(handle)
    with domain_db.transaction() as session:
        old = session.scalar(select(AuthSession).where(AuthSession.user_id == graph["user_id"]))
        assert old.closed_at and old.access_cipher is None
        assert (
            session.scalar(
                select(StaffIdentity).where(StaffIdentity.user_id == graph["user_id"])
            ).status
            == "active"
        )


def test_admin_can_deactivate_but_cannot_read_another_actors_receipt(
    api, invitations, domain_db, graph, replacement, auth_service, auth_settings, fake_cognito
):
    admin_id = create_admin(api).json()["id"]
    body, key = payload(api, graph, replacement), uuid4()
    assert save(api, graph, body, key).status_code == 200
    login_admin(api, auth_service, auth_settings, fake_cognito, admin_id)
    assert api.get(f"/api/trainer-deactivations/{key}").status_code == 404
    other = {**graph, "trainer_id": replacement}
    response = save(api, other, {"expected": read(api, other)["expected"], "replacements": {}})
    assert response.status_code == 409  # Its reassigned sessions still require replacements.


def test_receipts_are_immutable_and_populated_downgrade_refuses(
    api, domain_db, graph, replacement, migrate
):
    assert save(api, graph, payload(api, graph, replacement)).status_code == 200
    with pytest.raises(DBAPIError, match="immutable"), domain_db.transaction() as session:
        session.delete(session.scalar(select(TrainerDeactivationReceipt)))
    with pytest.raises(DBAPIError, match="Trainer deactivation downgrade refused"):
        migrate("downgrade", "20261013_0028")


@pytest.mark.parametrize("batch", [False, True])
def test_preview_and_commit_reject_external_and_provisional_batch_conflicts(
    api, domain_db, graph, replacement, batch
):
    from app.persistence import add_client, add_purchase
    from tests.domain_fixtures import person, purchase_parts

    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["second_session_id"])
        client = add_client(
            session,
            Client(name="Other", kind="individual", trainer_id=replacement),
            [person("Other")],
        )
        purchase, slots, preferences, bookings = purchase_parts(
            {**graph, "trainer_id": replacement},
            booking.training_date,
            client_id=client.id,
            stage="current",
        )
        add_purchase(session, purchase, slots, preferences, bookings, expected_client_version=1)
        if batch:
            # A retained conflicting batch must not be silently accepted by this command.
            bookings[0].trainer_id = graph["trainer_id"]
    body = payload(api, graph, replacement)
    preview = api.post(
        f"/api/trainers/{graph['trainer_id']}/deactivation-review",
        json=body,
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert preview.status_code == 200, preview.text
    assert any(t["error"] for row in preview.json()["sessions"] for t in row["choices"])
    before = snapshot(domain_db)
    assert save(api, graph, body).status_code == 409
    assert snapshot(domain_db) == before


def test_admin_deactivates_unlinked_trainer_with_empty_batch(
    api, invitations, graph, replacement, domain_db, auth_service, auth_settings, fake_cognito
):
    admin_id = create_admin(api).json()["id"]
    login_admin(api, auth_service, auth_settings, fake_cognito, admin_id)
    other = {**graph, "trainer_id": replacement}
    viewed = read(api, other)
    assert viewed["accountId"] is viewed["accountVersion"] is None
    assert viewed["sessions"] == []
    result = save(api, other, {"expected": viewed["expected"], "replacements": {}})
    assert result.status_code == 200, result.text
    with domain_db.transaction() as session:
        assert session.get(Trainer, replacement).status == "inactive"
        assert str(session.scalar(select(TrainerDeactivationReceipt)).actor_id) == admin_id
