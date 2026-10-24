"""Correct only reviewed stable requests; provider ambiguity and old addresses stay guarded."""

from copy import deepcopy
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.models.email_changes import StaffEmailChange
from app.models.people import StaffUser, Trainer
from tests.test_email_changes import email_flow as email_flow
from tests.test_email_changes import post, request_email
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


@pytest.fixture(autouse=True)
def enable_corrections(auth_settings):
    auth_settings.staff_email_corrections_enabled = True


def correct(api, graph, original, *, email="corrected@example.test", key=None, version=1):
    return api.post(
        f"/api/trainers/{graph['trainer_id']}/email-change",
        json={"email": email, "expectedVersion": version, "supersedes": original["id"]},
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def manager_context(api, provider):
    cookies, csrf = dict(api.cookies), api.headers["X-CSRF-Token"]
    changes, claims = deepcopy(provider.user_changes), deepcopy(provider.claims)

    def restore():
        api.cookies.clear()
        api.cookies.update(cookies)
        api.headers["X-CSRF-Token"] = csrf
        provider.user_changes, provider.claims = deepcopy(changes), deepcopy(claims)

    return restore


@pytest.mark.parametrize("sent", [False, True])
def test_correction_preserves_login_and_old_reservation_until_verified(
    api, graph, email_flow, domain_db, auth_service, fake_cognito, sent
):
    manager = manager_context(api, fake_cognito)
    original = request_email(api, graph, email="wrong@example.test").json()
    if sent:
        email_flow["login"]()
        assert post(api, original, "send").status_code == 200
        manager()
    key = uuid4()
    changed = correct(api, graph, original, key=key)
    assert changed.status_code == 200, changed.text
    current = changed.json()
    assert correct(api, graph, original, key=key).json() == current
    assert correct(api, graph, original).status_code == 409
    assert email_flow["sent"] == int(sent)
    with domain_db.transaction() as session:
        prior = session.get(StaffEmailChange, UUID(original["id"]))
        assert prior.state == "superseded" and prior.reservation_released_at is None
        assert session.get(Trainer, graph["trainer_id"]).email == email_flow["old"]
        assert session.get(StaffUser, graph["user_id"]).email == email_flow["old"]
    with pytest.raises(DBAPIError, match="reserved"), domain_db.transaction() as session:
        session.add(
            StaffUser(name="Foreign reservation probe", email="wrong@example.test", role="admin")
        )
    email_flow["login"]()
    assert api.get("/auth/email-change").json()["change"]["id"] == current["id"]
    for action in ["send", "reconcile"]:
        assert post(api, original, action).status_code == 409
    assert post(api, original, "verify", code="123456").status_code == 409
    assert email_flow["sent"] == int(sent) and email_flow["verified"] == 0
    assert post(api, current, "verify", code="123456").status_code == 409
    if sent:
        assert post(api, current, "send").status_code == 429
        now = auth_service.clock()
        auth_service.clock = lambda: now + timedelta(seconds=61)
    assert post(api, current, "send").status_code == 200
    saved = post(api, current, "verify", code="123456")
    assert saved.status_code == 200 and saved.json()["signedOut"] is True
    with domain_db.transaction() as session:
        prior = session.get(StaffEmailChange, UUID(original["id"]))
        assert prior.state == "superseded" and prior.reservation_released_at is not None
        assert session.get(StaffUser, graph["user_id"]).email == "corrected@example.test"
        session.add(StaffUser(name="Released address", email="wrong@example.test", role="admin"))


@pytest.mark.parametrize("state", ["sending", "verifying"])
def test_uncertain_provider_state_cannot_be_superseded(api, graph, email_flow, domain_db, state):
    original = request_email(api, graph).json()
    with domain_db.transaction() as session:
        session.get(StaffEmailChange, UUID(original["id"])).state = state
    result = correct(api, graph, original)
    assert result.status_code == 409 and result.json()["error"]["code"] == "EMAIL_CHANGE_UNCERTAIN"
    with domain_db.transaction() as session:
        rows = list(session.scalars(select(StaffEmailChange)))
        assert len(rows) == 1 and rows[0].state == state
    assert email_flow["sent"] == 0


@pytest.mark.parametrize("duplicate", [False, True])
def test_competing_corrections_keep_one_current_request(
    api, graph, email_flow, domain_db, database_settings, auth_settings, auth_service, duplicate
):
    """Separate application pools exercise real database serialization, not pool queuing."""
    from concurrent.futures import ThreadPoolExecutor
    from contextlib import ExitStack
    from copy import copy
    from threading import Barrier

    from fastapi.testclient import TestClient
    from sqlalchemy import event

    from app.database import Database
    from app.main import create_app

    original = request_email(api, graph).json()
    ready, pids, key = Barrier(2), [], uuid4()

    def observe(engine):
        seen = False

        def before(connection, cursor, statement, parameters, context, many):
            nonlocal seen
            if not seen and "FROM staff_users" in statement and "FOR SHARE" in statement:
                seen = True
                pids.append(connection.exec_driver_sql("SELECT pg_backend_pid()").scalar())
                ready.wait(timeout=5)

        event.listen(engine, "before_cursor_execute", before)

    with ExitStack() as resources:
        clients = []
        for _ in range(2):
            app = create_app(auth_settings)
            client = resources.enter_context(TestClient(app, base_url="https://testserver"))
            app.state.auth.provider.close()
            app.state.database.close()
            replica = Database(database_settings)
            observe(replica.engine)
            app.state.database = replica
            app.state.auth = copy(auth_service)
            app.state.auth.db = replica
            client.cookies.update(dict(api.cookies))
            client.headers.update(
                {"Origin": "https://staff.example", "X-CSRF-Token": api.headers["X-CSRF-Token"]}
            )
            # Each TestClient has its own event-loop thread. Initialize FastAPI's lazy
            # validation before racing business transactions: Python 3.12 warning filters
            # are process-global, so concurrent first-use TypeAdapter construction races.
            invalid = client.post(
                f"/api/trainers/{graph['trainer_id']}/email-change",
                json={},
                headers={"Idempotency-Key": str(uuid4())},
            )
            assert invalid.status_code == 422
            assert pids == []  # Invalid setup never reaches the transaction barrier.
            clients.append(client)

        def apply(index):
            return correct(
                clients[index],
                graph,
                original,
                email="first@example.test" if duplicate or index == 0 else "second@example.test",
                key=key if duplicate else uuid4(),
            )

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(apply, [0, 1]))
    assert len(set(pids)) == 2
    assert sorted(response.status_code for response in results) == (
        [200, 200] if duplicate else [200, 409]
    )
    if duplicate:
        assert results[0].json() == results[1].json()
    accepted = next(response.json() for response in results if response.status_code == 200)
    with domain_db.transaction() as session:
        rows = list(session.scalars(select(StaffEmailChange)))
        assert len(rows) == 2
        assert [(row.new_email, row.state) for row in rows if row.state != "superseded"] == [
            (accepted["email"], "requested")
        ]
    assert email_flow["sent"] == 0


def test_correction_failure_rolls_back_predecessor_and_new_request(
    api, graph, email_flow, domain_db, monkeypatch
):
    from app.api import email_changes
    from app.auth.errors import AuthError

    original = request_email(api, graph).json()
    real_result = email_changes.result

    def fail(change, **kwargs):
        if change.supersedes_id is not None:
            raise AuthError("injected_failure", "Interrupted before commit", 503)
        return real_result(change, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(email_changes, "result", fail)
        assert correct(api, graph, original).status_code == 503
    with domain_db.transaction() as session:
        rows = list(session.scalars(select(StaffEmailChange)))
        assert len(rows) == 1 and rows[0].state == "requested"
        assert rows[0].superseded_at is None and rows[0].reservation_released_at is None
    assert correct(api, graph, original).status_code == 200
    assert email_flow["sent"] == 0


def test_superseded_evidence_and_reservation_cannot_be_rewritten(api, graph, email_flow, domain_db):
    original = request_email(api, graph).json()
    assert correct(api, graph, original).status_code == 200
    for attribute, value in [("state", "requested"), ("new_email", "forged@example.test")]:
        with pytest.raises(DBAPIError, match="immutable"), domain_db.transaction() as session:
            setattr(session.get(StaffEmailChange, UUID(original["id"])), attribute, value)
    with pytest.raises(DBAPIError, match="immutable"), domain_db.transaction() as session:
        prior = session.get(StaffEmailChange, UUID(original["id"]))
        prior.reservation_released_at = prior.superseded_at
    with pytest.raises(DBAPIError, match="immutable"), domain_db.transaction() as session:
        session.delete(session.get(StaffEmailChange, UUID(original["id"])))


def test_correction_rechecks_version_identity_and_command_body(api, graph, email_flow, domain_db):
    original = request_email(api, graph).json()
    assert correct(api, graph, original, version=2).status_code == 409
    assert correct(api, graph, {"id": str(uuid4())}).status_code == 409
    key = uuid4()
    assert correct(api, graph, original, key=key).status_code == 200
    assert (
        correct(api, graph, original, key=key, email="changed-intent@example.test").status_code
        == 409
    )
    assert correct(api, graph, original).status_code == 409
    with domain_db.transaction() as session:
        rows = list(session.scalars(select(StaffEmailChange)))
        assert len(rows) == 2
        assert session.get(StaffUser, graph["user_id"]).email == email_flow["old"]
    assert email_flow["sent"] == 0


def test_deactivated_trainer_cannot_receive_corrected_request(api, graph, email_flow, domain_db):
    original = request_email(api, graph).json()
    with domain_db.transaction() as session:
        session.get(Trainer, graph["trainer_id"]).status = "inactive"
    assert correct(api, graph, original).status_code == 404
    with domain_db.transaction() as session:
        rows = list(session.scalars(select(StaffEmailChange)))
        assert len(rows) == 1 and rows[0].state == "requested"
    assert email_flow["sent"] == 0


def test_multiple_corrections_release_all_predecessors_only_after_verified_completion(
    api, graph, email_flow, domain_db
):
    first = request_email(api, graph, email="first-wrong@example.test").json()
    second = correct(api, graph, first, email="second-wrong@example.test").json()
    final = correct(api, graph, second, email="final-correct@example.test").json()
    for address in (first["email"], second["email"]):
        with pytest.raises(DBAPIError, match="reserved"), domain_db.transaction() as session:
            session.add(StaffUser(name="Foreign claimant", email=address, role="admin"))
    email_flow["login"]()
    assert post(api, final, "send").status_code == 200
    assert post(api, final, "verify", code="123456").status_code == 200
    with domain_db.transaction() as session:
        for change in (first, second):
            retained = session.get(StaffEmailChange, UUID(change["id"]))
            assert retained.state == "superseded" and retained.reservation_released_at is not None
            session.add(StaffUser(name="Released claimant", email=change["email"], role="admin"))
        assert session.get(StaffUser, graph["user_id"]).email == final["email"]
    assert email_flow["sent"] == 1 and email_flow["verified"] == 1


def test_correction_inherits_exhausted_send_budget(api, graph, email_flow, domain_db, auth_service):
    original = request_email(api, graph).json()
    with domain_db.transaction() as session:
        pending = session.get(StaffEmailChange, UUID(original["id"]))
        pending.state, pending.sends = "pending", 6
        pending.last_sent_at = auth_service.clock() - timedelta(seconds=61)
    current = correct(api, graph, original).json()
    email_flow["login"]()
    assert post(api, current, "send").status_code == 429
    assert post(api, current, "verify", code="123456").status_code == 409
    assert email_flow["sent"] == 0


def test_migration_preserves_prior_completed_evidence_and_outgoing_code_completion(
    api, graph, email_flow, domain_db, migrate
):
    from sqlalchemy import text

    from app.models.people import StaffIdentity

    migrate("downgrade", "20261024_0041")
    ids = [uuid4(), uuid4()]
    with domain_db.transaction() as session:
        identity = session.scalar(
            select(StaffIdentity.id).where(StaffIdentity.user_id == graph["user_id"])
        )
        for index, change_id in enumerate(ids):
            session.execute(
                text("""
                INSERT INTO staff_email_changes
                (id, request_key, trainer_version, user_id, identity_id, old_email,
                 new_email, actor_id, actor_name, state, completed_at)
                VALUES (:id, :key, 1, :user, :identity, :old, :new, :actor, 'Migration actor',
                        :state, CASE WHEN :done THEN now() ELSE NULL END)
            """),
                {
                    "id": change_id,
                    "key": uuid4(),
                    "user": graph["user_id"],
                    "identity": identity,
                    "old": email_flow["old"],
                    "new": f"legacy-{index}@example.test",
                    "actor": graph["user_id"],
                    "state": "completed" if index == 0 else "pending",
                    "done": index == 0,
                },
            )
        prior = session.execute(
            text(
                "SELECT id, request_key, new_email, actor_id, actor_name, created_at, completed_at "
                "FROM staff_email_changes WHERE id = :id"
            ),
            {"id": ids[0]},
        ).one()
    migrate()
    with domain_db.transaction() as session:
        preserved = session.execute(
            text(
                "SELECT id, request_key, new_email, actor_id, actor_name, created_at, completed_at "
                "FROM staff_email_changes WHERE id = :id"
            ),
            {"id": ids[0]},
        ).one()
        assert preserved == prior
        completed = session.get(StaffEmailChange, ids[0])
        assert completed.reservation_released_at == completed.completed_at
        # Simulate the outgoing application, which knows no reservation-release column.
        session.execute(
            text(
                "UPDATE staff_email_changes SET state = 'completed', completed_at = now() "
                "WHERE id = :id"
            ),
            {"id": ids[1]},
        )
    with domain_db.transaction() as session:
        completed = session.get(StaffEmailChange, ids[1])
        assert completed.reservation_released_at == completed.completed_at
    with pytest.raises(DBAPIError, match="Email correction downgrade refused"):
        migrate("downgrade", "20261024_0041")


def test_outgoing_completion_releases_correction_chain_in_database(
    api, graph, email_flow, domain_db
):
    from sqlalchemy import text

    original = request_email(api, graph).json()
    current = correct(api, graph, original).json()
    # The prior application updates only its known completion fields. The forward
    # migration must retain one transactional reservation owner during rollback.
    with domain_db.transaction() as session:
        session.execute(
            text(
                "UPDATE staff_email_changes SET state = 'completed', completed_at = now() "
                "WHERE id = :id"
            ),
            {"id": UUID(current["id"])},
        )
    with domain_db.transaction() as session:
        finished = session.get(StaffEmailChange, UUID(current["id"]))
        prior = session.get(StaffEmailChange, UUID(original["id"]))
        assert finished.reservation_released_at == finished.completed_at
        assert prior.reservation_released_at == finished.completed_at
        assert prior.state == "superseded"


def test_disabled_correction_cannot_create_superseded_evidence(
    api, graph, email_flow, auth_settings, domain_db
):
    original = request_email(api, graph).json()
    auth_settings.staff_email_corrections_enabled = False
    assert api.get("/api/directory").json()["trainerEmailCorrections"] is False
    blocked = correct(api, graph, original)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "EMAIL_CORRECTION_UNAVAILABLE"
    with domain_db.transaction() as session:
        rows = list(session.scalars(select(StaffEmailChange)))
        assert len(rows) == 1 and rows[0].state == "requested"
    auth_settings.staff_email_corrections_enabled = True
    assert api.get("/api/directory").json()["trainerEmailCorrections"] is True
    assert correct(api, graph, original).status_code == 200
