"""Independent PostgreSQL writers, current permission and immutable media/history boundaries."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from app.api import session_undo_review, session_undo_save
from app.api.request_cancellation import DECISION_LOCK
from app.api.session_undo_routes import UndoChange
from app.auth.errors import AuthError
from app.authorization import Principal
from app.database import Database
from app.models.people import StaffUser
from app.models.session_mutations import SessionMutation, SessionMutationUndo
from app.models.training import Acknowledgement, CreditDebit, TrainingSession
from app.persistence import acknowledge
from tests.test_session_undo_api import change_summary, undo, undo_review
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


@pytest.mark.parametrize("duplicate", [False, True])
def test_independent_undo_writers_commit_one_compensation(
    api, graph, domain_db, database_settings, duplicate
):
    identity, mutation, _ = change_summary(api, graph, domain_db)
    viewed = undo_review(api, mutation)
    first = uuid4()
    keys = [first, first if duplicate else uuid4()]
    principal = Principal(graph["owner_id"], "Owner Original", "owner", None)
    ready, pids = Barrier(2), []

    def apply(key):
        database = Database(database_settings)
        try:
            with database.transaction() as session:
                pids.append(session.scalar(text("SELECT pg_backend_pid()")))
                ready.wait(timeout=4)
                session.execute(
                    text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": DECISION_LOCK}
                )
                return 200, session_undo_save.commit(
                    session, principal, mutation, key, UndoChange(expected=viewed["expected"]), []
                )
        except AuthError as error:
            return error.status, None
        finally:
            database.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(apply, keys))
    assert len(set(pids)) == 2
    assert sorted(status for status, _ in results) == ([200, 200] if duplicate else [200, 409])
    if duplicate:
        assert results[0][1] == results[1][1]
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(SessionMutationUndo)) == 1
        assert session.get(TrainingSession, identity).client_summary == ""


def test_exact_original_key_cannot_be_reused_for_a_changed_undo(api, graph, domain_db):
    _, mutation, _ = change_summary(api, graph, domain_db)
    viewed, key = undo_review(api, mutation), uuid4()
    assert undo(api, mutation, viewed, key).status_code == 200
    assert undo(api, mutation, {**viewed, "expected": "0" * 64}, key).status_code == 409
    assert undo(api, uuid4(), viewed, key).status_code == 409


def test_assigned_trainer_cannot_undo_an_owner_command_or_read_owner_recovery(
    api, graph, domain_db, auth_settings, auth_service, fake_cognito
):
    _, mutation, _ = change_summary(api, graph, domain_db)
    viewed, key = undo_review(api, mutation), uuid4()
    assert undo(api, mutation, viewed, key).status_code == 200
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get(f"/api/session-changes/{mutation}/undo-review").status_code == 404
    assert api.get(f"/api/session-undos/{key}").status_code == 404
    assert undo(api, mutation, viewed).status_code == 404


def test_deactivated_actor_cannot_commit_a_previously_reviewed_undo(api, graph, domain_db):
    identity, mutation, version = change_summary(api, graph, domain_db)
    viewed = undo_review(api, mutation)
    with domain_db.transaction() as session:
        session.get(StaffUser, graph["owner_id"]).status = "inactive"
    assert undo(api, mutation, viewed).status_code == 401
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, identity).version == version
        assert session.scalar(select(func.count()).select_from(SessionMutationUndo)) == 0


def test_original_twenty_four_hour_deadline_is_checked_at_commit(
    api, graph, domain_db, monkeypatch
):
    _, mutation, _ = change_summary(api, graph, domain_db)
    viewed = undo_review(api, mutation)
    with domain_db.transaction() as session:
        expires = session.get(SessionMutation, mutation).expires_at
    monkeypatch.setattr(
        session_undo_review, "clock", lambda session: expires + timedelta(seconds=1)
    )
    assert undo(api, mutation, viewed).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(SessionMutationUndo)) == 0


def test_post_completion_summary_undo_never_reverses_acknowledgement_or_credit(
    api, graph, domain_db
):
    identity = graph["session_id"]
    with domain_db.transaction() as session:
        row = session.get(TrainingSession, identity)
        acknowledge(session, identity, row.version, graph["owner_id"], method="late_no_show")
        session.flush()
        ack = session.scalar(select(Acknowledgement)).id
        debit = session.scalar(select(CreditDebit)).id
    identity, mutation, _ = change_summary(api, graph, domain_db)
    result = undo(api, mutation, undo_review(api, mutation))
    assert result.status_code == 200, result.text
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, identity).status == "completed"
        assert session.scalar(select(Acknowledgement)).id == ack
        assert session.scalar(select(CreditDebit)).id == debit
        assert session.scalar(select(func.count()).select_from(SessionMutation)) == 1


def test_original_trainer_can_undo_own_summary_without_access_to_foreign_records(
    api, graph, domain_db, auth_settings, auth_service, fake_cognito
):
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    identity, mutation, _ = change_summary(api, graph, domain_db)
    result = undo(api, mutation, undo_review(api, mutation))
    assert result.status_code == 200, result.text
    assert api.get(f"/api/session-changes/{uuid4()}/undo-review").status_code == 404
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, identity).client_summary == ""
