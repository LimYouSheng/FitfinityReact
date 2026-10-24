"""Package commands preserve history and unrelated purchases in isolated PostgreSQL."""

from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import DBAPIError

from app.auth.errors import AuthError
from app.models.package_actions import PackageActionReceipt, SessionArchive
from app.models.training import ExercisePlanItem, PackagePurchase, TrainingSession
from app.persistence import add_purchase
from tests.domain_fixtures import purchase_parts
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


@pytest.fixture
def future(domain_db, graph):
    with domain_db.transaction() as session:
        purchase, slots, preferences, bookings = purchase_parts(graph)
        add_purchase(
            session,
            purchase,
            slots,
            preferences,
            bookings,
            expected_client_version=graph["client_version"],
        )
        session.add(ExercisePlanItem(session_id=bookings[0].id, position=1, name="Retain squat"))
        return purchase.id, [row.id for row in bookings]


def review(api, graph, purchase_id, operation="deactivate"):
    response = api.get(
        f"/api/clients/{graph['client_id']}/purchases/{purchase_id}/action-review",
        params={"operation": operation},
    )
    assert response.status_code == 200, response.text
    return response.json()


def save(api, graph, viewed, *, delete=False, key=None):
    return api.post(
        f"/api/clients/{graph['client_id']}/purchases/{viewed['purchaseId']}/actions",
        json={
            "operation": viewed["operation"],
            "expected": viewed["expected"],
            "deleteUpcomingSessions": delete,
        },
        headers={"Idempotency-Key": str(key or uuid4())},
    )


@pytest.mark.parametrize("delete", [False, True])
def test_deactivation_preserves_history_other_purchase_and_original_receipt(
    api, domain_db, graph, future, delete
):
    identity, bookings = future
    viewed = review(api, graph, identity)
    assert {row["id"] for row in viewed["eligible"]} == {str(x) for x in bookings}
    key = uuid4()
    response = save(api, graph, viewed, delete=delete, key=key)
    assert response.status_code == 200, response.text
    assert response.json()["undoUntil"] is None
    assert save(api, graph, viewed, delete=delete, key=key).json() == response.json()
    assert api.get(f"/api/package-actions/{key}").json() == response.json()
    assert save(api, graph, viewed, delete=not delete, key=key).status_code == 409
    with domain_db.transaction() as session:
        assert session.get(PackagePurchase, identity).status == "inactive"
        assert session.get(PackagePurchase, graph["purchase_id"]).status == "active"
        assert session.get(TrainingSession, graph["session_id"]) is not None
        assert (
            session.scalar(
                select(ExercisePlanItem).where(ExercisePlanItem.session_id == bookings[0])
            ).name
            == "Retain squat"
        )
        assert (session.get(TrainingSession, bookings[0]) is None) == delete
        assert len(session.scalars(select(SessionArchive)).all()) == (2 if delete else 0)


def test_separate_deletion_requires_inactive_purchase_and_retains_undo_receipt(
    api, domain_db, graph, future
):
    identity, bookings = future
    path = f"/api/clients/{graph['client_id']}/purchases/{identity}/action-review"
    assert api.get(path, params={"operation": "delete_sessions"}).status_code == 409
    assert save(api, graph, review(api, graph, identity)).status_code == 200
    viewed = review(api, graph, identity, "delete_sessions")
    response = save(api, graph, viewed)
    assert response.status_code == 200, response.text
    assert response.json()["undoUntil"]
    assert set(response.json()["deletedSessionIds"]) == {str(x) for x in bookings}
    assert response.json()["status"] == "inactive"
    with domain_db.transaction() as session:
        assert len(session.scalars(select(SessionArchive)).all()) == 2
        assert len(session.scalars(select(PackageActionReceipt)).all()) == 2


def test_stale_review_is_rejected_without_partial_archive(api, domain_db, graph, future):
    identity, bookings = future
    viewed = review(api, graph, identity)
    with domain_db.transaction() as session:
        session.get(TrainingSession, bookings[0]).trainer_comments = "Changed after review"
    response = save(api, graph, viewed, delete=True)
    assert response.status_code == 409, response.text
    with domain_db.transaction() as session:
        assert session.get(PackagePurchase, identity).status == "active"
        assert session.scalars(select(SessionArchive)).all() == []


def test_interrupted_delete_rolls_back_lifecycle_archives_and_notice(api, domain_db, graph, future):
    identity, bookings = future
    viewed = review(api, graph, identity)

    def fail(mapper, connection, row):
        raise AuthError("invalid_request", "Synthetic interrupted deletion", 422)

    event.listen(TrainingSession, "before_delete", fail)
    try:
        response = save(api, graph, viewed, delete=True)
        assert response.status_code == 422, response.text
    finally:
        event.remove(TrainingSession, "before_delete", fail)
    with domain_db.transaction() as session:
        assert session.get(PackagePurchase, identity).status == "active"
        assert all(session.get(TrainingSession, x) is not None for x in bookings)
        assert session.scalars(select(SessionArchive)).all() == []
        assert session.scalars(select(PackageActionReceipt)).all() == []


def test_trainer_cannot_review_save_or_read_owner_receipt(
    api, domain_db, graph, future, auth_settings, auth_service, fake_cognito
):
    identity, _ = future
    viewed = review(api, graph, identity)
    key = uuid4()
    assert save(api, graph, viewed, key=key).status_code == 200
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    path = f"/api/clients/{graph['client_id']}/purchases/{identity}/action-review"
    assert api.get(path, params={"operation": "deactivate"}).status_code == 403
    assert save(api, graph, viewed).status_code == 403
    assert api.get(f"/api/package-actions/{key}").status_code == 403


def test_archived_history_cannot_be_deleted_without_command(api, domain_db, graph, future):
    _, bookings = future
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.get(TrainingSession, bookings[0]))
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, bookings[0]) is not None


def test_undo_restores_same_ids_increasing_versions_and_retained_plan(
    api, domain_db, graph, future
):
    identity, bookings = future
    assert save(api, graph, review(api, graph, identity)).status_code == 200
    deleted = save(api, graph, review(api, graph, identity, "delete_sessions")).json()
    path = f"/api/package-actions/{deleted['id']}"
    viewed = api.get(path + "/undo-review")
    assert viewed.status_code == 200, viewed.text
    key = uuid4()
    response = api.post(
        path + "/undo",
        json={"expected": viewed.json()["expected"]},
        headers={"Idempotency-Key": str(key)},
    )
    assert response.status_code == 200, response.text
    assert (
        api.post(
            path + "/undo",
            json={"expected": viewed.json()["expected"]},
            headers={"Idempotency-Key": str(key)},
        ).json()
        == response.json()
    )
    assert api.get(f"/api/package-undos/{key}").json() == response.json()
    assert api.get(path + "/undo-review").status_code == 409
    with domain_db.transaction() as session:
        assert session.get(PackagePurchase, identity).status == "inactive"
        for booking in bookings:
            restored = session.get(TrainingSession, booking)
            archive = session.scalar(
                select(SessionArchive).where(SessionArchive.session_id == booking)
            )
            assert restored.version > archive.original_version
            assert restored.created_at == archive.original_created_at
        assert (
            session.scalar(
                select(ExercisePlanItem).where(ExercisePlanItem.session_id == bookings[0])
            ).name
            == "Retain squat"
        )


def test_archive_migration_round_trip_retains_empty_schema(migrate):
    migrate()
    migrate("downgrade", "20261024_0042")
    migrate()


def test_populated_archive_downgrade_refuses_without_removing_history(
    api, domain_db, graph, future, migrate
):
    identity, bookings = future
    assert save(api, graph, review(api, graph, identity), delete=True).status_code == 200
    with pytest.raises(DBAPIError, match="retained deletion evidence"):
        migrate("downgrade", "20261024_0042")
    with domain_db.transaction() as session:
        assert len(session.scalars(select(SessionArchive)).all()) == 2
        assert session.get(TrainingSession, bookings[0]) is None


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_commands_use_distinct_connections_and_one_effect(
    api, domain_db, database_settings, graph, future, same_key
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import text

    from app.api.package_action_save import save as persist
    from app.api.package_action_schemas import SavePackageAction
    from app.authorization import Principal
    from app.database import Database

    identity, _ = future
    viewed = review(api, graph, identity)
    command = SavePackageAction(
        expected=viewed["expected"], operation="deactivate", deleteUpcomingSessions=True
    )
    principal = Principal(graph["owner_id"], "Owner Original", "owner", None)
    gate, original = Barrier(2), uuid4()

    def run(index):
        independent = Database(database_settings)
        try:
            with independent.transaction() as session:
                pid = session.scalar(text("SELECT pg_backend_pid()"))
                gate.wait(timeout=4)
                result = persist(
                    session,
                    principal,
                    graph["client_id"],
                    identity,
                    original if same_key or index == 0 else uuid4(),
                    command,
                )
                return pid, result.model_dump(mode="json")
        except AuthError as error:
            return pid, error.status
        finally:
            independent.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(run, range(2)))
    assert len({pid for pid, _ in outcomes}) == 2
    values = [value for _, value in outcomes]
    if same_key:
        assert values[0] == values[1]
    else:
        assert sum(value == 409 for value in values) == 1
    with domain_db.transaction() as session:
        assert len(session.scalars(select(PackageActionReceipt)).all()) == 1
        assert len(session.scalars(select(SessionArchive)).all()) == 2


def test_foreign_purchase_pair_and_unrelated_receipt_are_unavailable(api, graph, future):
    identity, _ = future
    response = api.get(
        f"/api/clients/{uuid4()}/purchases/{identity}/action-review",
        params={"operation": "deactivate"},
    )
    assert response.status_code == 404
    assert api.get(f"/api/package-actions/{uuid4()}").status_code == 404


def test_expired_undo_leaves_archived_bookings_deleted(api, domain_db, graph, future, monkeypatch):
    from datetime import timedelta

    from app.api import package_action_review

    identity, bookings = future
    assert save(api, graph, review(api, graph, identity)).status_code == 200
    deleted = save(api, graph, review(api, graph, identity, "delete_sessions")).json()
    future_clock = package_action_review.clock() + timedelta(hours=25)
    monkeypatch.setattr(package_action_review, "clock", lambda: future_clock)
    response = api.get(f"/api/package-actions/{deleted['id']}/undo-review")
    assert response.status_code == 409, response.text
    with domain_db.transaction() as session:
        assert all(session.get(TrainingSession, identity) is None for identity in bookings)


def test_deletion_rejects_pending_request_and_undo_projects_retained_reversal(
    api, domain_db, graph, future
):
    from app.models.communications import ChangeRequest, RequestEvent
    from tests.test_message_api import seed_request

    identity, bookings = future
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, bookings[0])
        proposal, _ = seed_request(
            session,
            {
                **graph,
                "purchase_id": identity,
                "session_id": booking.id,
                "start_date": booking.training_date,
            },
            "session_postpone",
        )
    assert save(api, graph, review(api, graph, identity)).status_code == 200
    deleted = save(api, graph, review(api, graph, identity, "delete_sessions"))
    assert deleted.status_code == 200, deleted.text
    with domain_db.transaction() as session:
        assert session.get(ChangeRequest, proposal).status == "rejected"
        assert [
            row.status
            for row in session.scalars(
                select(RequestEvent)
                .where(RequestEvent.request_id == proposal)
                .order_by(RequestEvent.sequence)
            )
        ] == ["pending", "rejected"]
    path = f"/api/package-actions/{deleted.json()['id']}"
    viewed = api.get(path + "/undo-review").json()
    saved = api.post(
        path + "/undo",
        json={"expected": viewed["expected"]},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert saved.status_code == 200, saved.text
    notices = [row for row in api.get("/api/messages").json() if row["requestId"] == str(proposal)]
    assert notices and all(row["reversedAt"] for row in notices)
    with domain_db.transaction() as session:
        assert session.get(ChangeRequest, proposal).status == "rejected"
        assert (
            len(
                session.scalars(
                    select(RequestEvent).where(RequestEvent.request_id == proposal)
                ).all()
            )
            == 2
        )
