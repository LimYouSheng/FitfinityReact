"""Outcome corrections and derived charts use actual routes and isolated PostgreSQL."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.models.api import SessionOutcomeReceipt
from app.models.training import (
    Acknowledgement,
    CreditDebit,
    ExerciseResult,
    ExerciseResultRevision,
    TrainingSession,
)
from app.persistence import acknowledge
from tests.test_session_plans_api import item
from tests.test_session_plans_api import review as plan_review
from tests.test_session_plans_api import save as save_plan
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database
STROKES = [[{"x": 10, "y": 10}, {"x": 30, "y": 30}, {"x": 60, "y": 10}]]


def review(api, identity):
    response = api.get(f"/api/sessions/{identity}/outcome-review")
    assert response.status_code == 200, response.text
    return response.json()


def setup_plan(api, graph):
    identity = graph["session_id"]
    response = save_plan(
        api, identity, {"expected": plan_review(api, identity)["expected"], "items": [item()]}
    )
    assert response.status_code == 200, response.text
    return identity, response.json()["items"][0]["id"]


def save(api, identity, viewed, measurements, key=None, comments="Measured today"):
    return api.post(
        f"/api/sessions/{identity}/outcome",
        json={
            "expected": viewed["expected"],
            "trainerComments": comments,
            "measurements": measurements,
        },
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def measurement(identity, load=20):
    return {"id": identity, "loadKg": load, "reps": 8, "sets": 3}


def test_outcome_correction_retirement_and_restore_keep_identity_and_immutable_history(
    api, domain_db, graph
):
    identity, plan_id = setup_plan(api, graph)
    initial = review(api, identity)
    assert initial["durationMinutes"] == 60
    assert initial["rows"][0]["id"] == plan_id
    assert initial["rows"][0]["loadKg"] is None
    assert initial["draftRows"][0]["loadKg"] == 12
    key = uuid4()
    saved = save(api, identity, initial, [measurement(plan_id)], key)
    assert saved.status_code == 200, saved.text
    result_id = saved.json()["rows"][0]["resultId"]
    assert save(api, identity, initial, [measurement(plan_id)], key).json() == saved.json()
    assert api.get(f"/api/session-outcomes/{key}").json() == saved.json()
    assert save(api, identity, initial, [measurement(plan_id, 30)], key).status_code == 409
    corrected = save(api, identity, review(api, identity), [measurement(plan_id, 30)])
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["rows"][0]["resultId"] == result_id
    removed = save(api, identity, review(api, identity), [])
    assert removed.status_code == 200, removed.text
    assert removed.json()["rows"][0]["loadKg"] is None
    assert review(api, identity)["draftRows"][0]["loadKg"] is None
    assert api.get(f"/api/sessions/{identity}/details").json()["exerciseResults"] == []
    restored = save(api, identity, review(api, identity), [measurement(plan_id, 25)])
    assert restored.status_code == 200, restored.text
    assert restored.json()["rows"][0]["resultId"] == result_id
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ExerciseResult)) == 1
        changes = list(
            session.scalars(
                select(ExerciseResultRevision).order_by(ExerciseResultRevision.result_version)
            )
        )
        assert [float(row.load_kg) for row in changes] == [20, 30, 30]
        assert changes[-1].retired_at is not None
        assert session.scalar(select(func.count()).select_from(CreditDebit)) == 0
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.scalar(select(ExerciseResultRevision)).name = "Tampered"
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.get(ExerciseResult, UUID(result_id)))
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.scalar(select(SessionOutcomeReceipt)).result = {}


def test_signed_corrections_update_progress_without_rewriting_signature_or_credit(
    api, domain_db, graph
):
    identity, plan_id = setup_plan(api, graph)
    assert save(api, identity, review(api, identity), [measurement(plan_id)]).status_code == 200
    url = f"/api/clients/{graph['client_id']}/progress"
    assert api.get(url).json()["exercises"] == []
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, identity)
        acknowledge(
            session,
            identity,
            booking.version,
            graph["owner_id"],
            method="signature",
            signer_name="Client One",
            strokes=STROKES,
        )
        signature_id = session.scalar(select(Acknowledgement.id))
        debit_id = session.scalar(select(CreditDebit.id))
    progress = api.get(url)
    assert progress.status_code == 200, progress.text
    assert progress.json()["exercises"][0]["points"][0]["load"] == 20
    changed = save(api, identity, review(api, identity), [measurement(plan_id, 32.5)])
    assert changed.status_code == 200, changed.text
    point = api.get(url).json()["exercises"][0]["points"][0]
    assert point["load"] == 32.5 and point["sessionId"] == str(identity)
    assert point["packageId"] == str(graph["purchase_id"])
    with domain_db.transaction() as session:
        assert session.scalar(select(Acknowledgement.id)) == signature_id
        assert session.scalar(select(CreditDebit.id)) == debit_id
        assert session.scalar(select(func.count()).select_from(Acknowledgement)) == 1
        assert session.scalar(select(func.count()).select_from(CreditDebit)) == 1
        assert session.get(TrainingSession, identity).status == "completed"


def test_no_show_measurements_are_excluded_from_strength_progress(api, domain_db, graph):
    identity, plan_id = setup_plan(api, graph)
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, identity)
        acknowledge(session, identity, booking.version, graph["owner_id"], method="late_no_show")
    assert save(api, identity, review(api, identity), [measurement(plan_id)]).status_code == 200
    assert api.get(f"/api/clients/{graph['client_id']}/progress").json()["exercises"] == []


def test_stale_and_foreign_measurements_cannot_partially_change_outcome(api, graph):
    identity, plan_id = setup_plan(api, graph)
    viewed = review(api, identity)
    assert save(api, identity, viewed, [measurement(str(uuid4()))]).status_code == 404
    saved = save(api, identity, viewed, [measurement(plan_id)])
    assert saved.status_code == 200
    assert save(api, identity, viewed, [measurement(plan_id, 50)]).status_code == 409
    assert review(api, identity)["rows"][0]["loadKg"] == 20
    other = graph["second_session_id"]
    assert save(api, other, review(api, other), [measurement(plan_id)]).status_code == 404


def test_current_trainer_can_correct_but_foreign_and_historical_scope_cannot(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    from tests.test_directory_api import covered_session
    from tests.test_staff_api import trainer_login

    _, foreign, other_trainer = covered_session(domain_db, graph)
    identity, plan_id = setup_plan(api, graph)
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    viewed = review(api, identity)
    saved = save(api, identity, viewed, [measurement(plan_id)])
    assert saved.status_code == 200, saved.text
    with domain_db.transaction() as session:
        session.get(TrainingSession, identity).trainer_id = other_trainer
        session.get(TrainingSession, foreign).trainer_id = other_trainer
    for target in (identity, foreign, uuid4()):
        assert api.get(f"/api/sessions/{target}/outcome-review").status_code == 404
        assert save(api, target, viewed, []).status_code == 404
    # The original actor retains receipt readership after assignment changes.
    with domain_db.transaction() as session:
        key = session.scalar(select(SessionOutcomeReceipt.request_key))
    assert api.get(f"/api/session-outcomes/{key}").json() == saved.json()


@pytest.mark.parametrize("frozen", ["client", "purchase"])
def test_inactive_records_reject_outcome_and_keep_old_measurements(api, domain_db, graph, frozen):
    from app.models.training import PackagePurchase
    from tests.test_client_reactivation_review import deactivate
    from tests.test_package_reactivation_review import freeze

    identity, plan_id = setup_plan(api, graph)
    viewed = review(api, identity)
    if frozen == "client":
        deactivate(api, graph)
    else:
        with domain_db.transaction() as session:
            freeze(session, graph, session.get(PackagePurchase, graph["purchase_id"]))
    assert save(api, identity, viewed, [measurement(plan_id)]).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(ExerciseResult)) is None
        assert session.scalar(select(SessionOutcomeReceipt)) is None


@pytest.mark.parametrize(
    "patch", [{"loadKg": -1}, {"loadKg": 2001}, {"loadKg": 0.00001}, {"reps": 0}, {"sets": 101}]
)
def test_invalid_measurement_bounds_never_persist(api, domain_db, graph, patch):
    identity, plan_id = setup_plan(api, graph)
    response = save(api, identity, review(api, identity), [{**measurement(plan_id), **patch}])
    assert response.status_code == 422, response.text
    with domain_db.transaction() as session:
        assert session.scalar(select(ExerciseResult)) is None


@pytest.mark.parametrize(
    "extra", [{"actor": "forged"}, {"durationMinutes": 999}, {"status": "completed"}]
)
def test_outcome_payload_cannot_assign_identity_duration_or_completion(api, graph, extra):
    identity, _ = setup_plan(api, graph)
    response = api.post(
        f"/api/sessions/{identity}/outcome",
        json={
            "expected": review(api, identity)["expected"],
            "trainerComments": "Forged",
            "measurements": [],
            **extra,
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422, response.text


def test_failed_outcome_receipt_rolls_back_comments_measurements_and_revisions(
    api, domain_db, graph, monkeypatch
):
    from app.api import session_outcomes

    identity, plan_id = setup_plan(api, graph)
    assert save(api, identity, review(api, identity), [measurement(plan_id)]).status_code == 200
    viewed = review(api, identity)

    def fail(**kwargs):
        raise RuntimeError("Interrupted before receipt")

    monkeypatch.setattr(session_outcomes, "SessionOutcomeReceipt", fail)
    monkeypatch.setattr(session_outcomes, "receipt", lambda *args: None)
    # Existing result state avoids the first-save default query during this injected failure.
    assert (
        save(api, identity, viewed, [measurement(plan_id, 40)], comments="Uncommitted").status_code
        == 500
    )
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, identity).trainer_comments == "Measured today"
        assert float(session.scalar(select(ExerciseResult)).load_kg) == 20
        assert session.scalar(select(ExerciseResultRevision)) is None
        assert session.scalar(select(func.count()).select_from(SessionOutcomeReceipt)) == 1


def test_independent_connections_duplicate_outcome_has_one_result_and_receipt(
    api, domain_db, database_settings, graph
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import text

    from app.api import session_outcomes
    from app.authorization import Principal
    from app.database import Database
    from app.models.people import StaffUser

    identity, plan_id = setup_plan(api, graph)
    viewed, key = review(api, identity), uuid4()
    body = session_outcomes.SaveOutcome(
        expected=viewed["expected"],
        trainerComments="Concurrent",
        measurements=[session_outcomes.Measurement(**measurement(plan_id))],
    )
    with domain_db.transaction() as session:
        user = session.get(StaffUser, graph["owner_id"])
        principal = Principal(user.id, user.name, user.role, None)
    replicas, ready = [Database(database_settings), Database(database_settings)], Barrier(2)

    def apply(db):
        with db.transaction() as session:
            pid = session.scalar(text("SELECT pg_backend_pid()"))
            ready.wait(timeout=5)
            return pid, session_outcomes.save(session, principal, identity, key, body).model_dump(
                mode="json"
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(apply, replicas))
    finally:
        for db in replicas:
            db.close()
    assert results[0][0] != results[1][0]
    assert results[0][1] == results[1][1]
    assert save(api, identity, viewed, [measurement(plan_id)]).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ExerciseResult)) == 1
        assert session.scalar(select(func.count()).select_from(SessionOutcomeReceipt)) == 1


def test_empty_first_outcome_does_not_resurrect_prescription_defaults(api, graph):
    identity, _ = setup_plan(api, graph)
    assert review(api, identity)["draftRows"][0]["loadKg"] == 12
    assert save(api, identity, review(api, identity), []).status_code == 200
    assert review(api, identity)["draftRows"][0]["loadKg"] is None


def test_populated_outcome_migration_refuses_lossy_downgrade(api, domain_db, graph):
    import runpy

    from sqlalchemy import text

    identity, plan_id = setup_plan(api, graph)
    assert save(api, identity, review(api, identity), [measurement(plan_id)]).status_code == 200
    sql = runpy.run_path("migrations/versions/20261023_0037_session_outcomes.py")["DOWNGRADE_SQL"]
    with pytest.raises(DBAPIError, match="downgrade refused"), domain_db.transaction() as session:
        session.execute(text(sql))


def test_cancelled_note_correction_never_completes_or_debits_the_session(api, domain_db, graph):
    identity, plan_id = setup_plan(api, graph)
    with domain_db.transaction() as session:
        session.get(TrainingSession, identity).status = "cancelled"
    assert (
        save(
            api,
            identity,
            review(api, identity),
            [measurement(plan_id)],
            comments="Cancellation note",
        ).status_code
        == 200
    )
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, identity).status == "cancelled"
        assert session.scalar(select(CreditDebit)) is None
        assert session.scalar(select(Acknowledgement)) is None
    assert api.get(f"/api/clients/{graph['client_id']}/progress").json()["exercises"] == []


@pytest.mark.parametrize("status", ["completed", "cancelled"])
def test_terminal_cover_outcome_is_read_only(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito, status
):
    from tests.test_directory_api import covered_session
    from tests.test_staff_api import trainer_login

    client_id, identity, _ = covered_session(domain_db, graph)
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, identity)
        if status == "completed":
            acknowledge(
                session, identity, booking.version, graph["owner_id"], method="late_no_show"
            )
        else:
            booking.status = "cancelled"
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get(f"/api/sessions/{identity}/details").status_code == 200
    assert api.get(f"/api/sessions/{identity}/outcome-review").status_code == 404
    assert save(api, identity, {"expected": "a" * 64}, []).status_code == 404
    assert api.get(f"/api/clients/{client_id}/progress").status_code == 404


def test_independent_conflicting_outcomes_have_one_winner(api, domain_db, database_settings, graph):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import text

    from app.api import session_outcomes
    from app.auth.errors import AuthError
    from app.authorization import Principal
    from app.database import Database
    from app.models.people import StaffUser

    identity, plan_id = setup_plan(api, graph)
    viewed = review(api, identity)
    with domain_db.transaction() as session:
        user = session.get(StaffUser, graph["owner_id"])
        principal = Principal(user.id, user.name, user.role, None)
    replicas, ready = [Database(database_settings), Database(database_settings)], Barrier(2)

    def apply(pair):
        db, load = pair
        with db.transaction() as session:
            pid = session.scalar(text("SELECT pg_backend_pid()"))
            ready.wait(timeout=5)
            body = session_outcomes.SaveOutcome(
                expected=viewed["expected"],
                trainerComments=f"Measured {load}",
                measurements=[session_outcomes.Measurement(**measurement(plan_id, load))],
            )
            try:
                result = session_outcomes.save(session, principal, identity, uuid4(), body)
                return pid, 200, result.rows[0].loadKg
            except AuthError as error:
                return pid, error.status, None

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(apply, zip(replicas, [20, 40], strict=True)))
    finally:
        for db in replicas:
            db.close()
    assert len({r[0] for r in results}) == 2
    assert sorted(r[1] for r in results) == [200, 409]
    winner = next(r[2] for r in results if r[1] == 200)
    with domain_db.transaction() as session:
        assert float(session.scalar(select(ExerciseResult)).load_kg) == winner
        assert session.scalar(select(func.count()).select_from(SessionOutcomeReceipt)) == 1
        assert session.scalar(select(ExerciseResultRevision)) is None
        assert session.scalar(select(CreditDebit)) is None
