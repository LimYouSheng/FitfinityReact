"""Actual HTTP/PostgreSQL summary saves preserve immutable audit and completion evidence."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.models.api import SessionSummaryReceipt
from app.models.communications import SessionEvent
from app.models.training import Acknowledgement, CreditDebit, TrainingSession
from app.persistence import acknowledge
from tests.test_session_outcomes_api import STROKES
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


def review(api, identity):
    response = api.get(f"/api/sessions/{identity}/summary-review")
    assert response.status_code == 200, response.text
    return response.json()


def save(api, identity, viewed, summary="A measured and reviewed session.", key=None):
    return api.post(
        f"/api/sessions/{identity}/summary",
        json={"expected": viewed["expected"], "summary": summary},
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_summary_corrections_replay_and_immutable_prior_text(api, domain_db, graph):
    identity = graph["session_id"]
    viewed, key = review(api, identity), uuid4()
    saved = save(api, identity, viewed, "  First summary  ", key)
    assert saved.status_code == 200, saved.text
    assert saved.json()["summary"] == "First summary"
    assert save(api, identity, viewed, "First summary", key).json() == saved.json()
    assert api.get(f"/api/session-summaries/{key}").json() == saved.json()
    assert save(api, identity, viewed, "Different", key).status_code == 409
    assert save(api, identity, viewed, "Stale").status_code == 409
    assert save(api, identity, review(api, identity), "Corrected summary").status_code == 200
    assert (
        api.get(f"/api/sessions/{identity}/details").json()["clientSummary"] == "Corrected summary"
    )
    with domain_db.transaction() as session:
        receipts = list(
            session.scalars(
                select(SessionSummaryReceipt).order_by(SessionSummaryReceipt.created_at)
            )
        )
        assert [r.previous["summary"] for r in receipts] == ["", "First summary"]
        assert [r.result["summary"] for r in receipts] == ["First summary", "Corrected summary"]
        assert session.scalar(select(func.count()).select_from(CreditDebit)) == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(SessionEvent)
                .where(SessionEvent.kind == "session_summary")
            )
            == 2
        )
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.scalar(select(SessionSummaryReceipt)).previous = {}
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.scalar(select(SessionSummaryReceipt)))


@pytest.mark.parametrize("terminal", ["completed", "cancelled"])
def test_terminal_summary_preserves_status_signature_credit_and_handoff(
    api, domain_db, graph, terminal
):
    identity = graph["session_id"]
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, identity)
        if terminal == "completed":
            acknowledge(
                session,
                identity,
                booking.version,
                graph["owner_id"],
                method="signature",
                signer_name="Client",
                strokes=STROKES,
            )
        else:
            booking.status = terminal
        signature_ids = list(session.scalars(select(Acknowledgement.id)))
        debit_ids = list(session.scalars(select(CreditDebit.id)))
    before = api.get(f"/api/sessions/{identity}/details").json()
    assert save(api, identity, review(api, identity)).status_code == 200
    after = api.get(f"/api/sessions/{identity}/details").json()
    assert after["session"]["status"] == before["session"]["status"]
    for field in (
        "acknowledgementHistory",
        "purchase",
        "exerciseResults",
        "whatsappOpenedAt",
        "whatsappOpenCount",
    ):
        assert after[field] == before[field]
    with domain_db.transaction() as session:
        assert list(session.scalars(select(Acknowledgement.id))) == signature_ids
        assert list(session.scalars(select(CreditDebit.id))) == debit_ids


@pytest.mark.parametrize("summary", ["", "   ", "x" * 20001, 123])
def test_invalid_summary_never_persists(api, domain_db, graph, summary):
    identity = graph["session_id"]
    assert save(api, identity, review(api, identity), summary).status_code == 422
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, identity).client_summary == ""
        assert session.scalar(select(SessionSummaryReceipt)) is None


@pytest.mark.parametrize(
    "extra", [{"actorId": "forged"}, {"status": "completed"}, {"whatsappOpenedAt": "now"}]
)
def test_summary_rejects_forged_authority_or_delivery_fields(api, graph, extra):
    identity = graph["session_id"]
    response = api.post(
        f"/api/sessions/{identity}/summary",
        json={"expected": review(api, identity)["expected"], "summary": "Reviewed", **extra},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422


def test_failed_summary_receipt_rolls_back_text_event_and_version(
    api, domain_db, graph, monkeypatch
):
    from app.api import session_summaries

    identity = graph["session_id"]
    viewed = review(api, identity)

    def fail(**kwargs):
        raise RuntimeError("Interrupted before receipt")

    monkeypatch.setattr(session_summaries, "SessionSummaryReceipt", fail)
    monkeypatch.setattr(session_summaries, "receipt", lambda *args: None)
    assert save(api, identity, viewed).status_code == 500
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, identity)
        assert booking.client_summary == "" and booking.version == viewed["version"]
        assert session.scalar(select(SessionSummaryReceipt)) is None
        assert (
            session.scalar(select(SessionEvent).where(SessionEvent.kind == "session_summary"))
            is None
        )


@pytest.mark.parametrize("terminal", [None, "completed", "cancelled"])
def test_trainer_scope_and_original_receipt_after_reassignment(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito, terminal
):
    from tests.test_directory_api import covered_session
    from tests.test_staff_api import trainer_login

    _, cover, other_trainer = covered_session(domain_db, graph)
    with domain_db.transaction() as session:
        if terminal == "completed":
            booking = session.get(TrainingSession, cover)
            acknowledge(session, cover, booking.version, graph["owner_id"], method="late_no_show")
        elif terminal:
            session.get(TrainingSession, cover).status = terminal
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    if terminal:
        assert api.get(f"/api/sessions/{cover}/summary-review").status_code == 404
        assert save(api, cover, {"expected": "a" * 64}).status_code == 404
    else:
        assert save(api, cover, review(api, cover)).status_code == 200
    identity, key = graph["session_id"], uuid4()
    viewed = review(api, identity)
    saved = save(api, identity, viewed, key=key)
    assert saved.status_code == 200
    with domain_db.transaction() as session:
        session.get(TrainingSession, identity).trainer_id = other_trainer
    assert save(api, identity, viewed).status_code == 404
    assert api.get(f"/api/sessions/{identity}/summary-review").status_code == 404
    assert api.get(f"/api/session-summaries/{key}").json() == saved.json()
    assert api.get(f"/api/session-summaries/{uuid4()}").status_code == 404


@pytest.mark.parametrize("frozen", ["client", "purchase"])
def test_inactive_summary_is_rejected(api, domain_db, graph, frozen):
    from app.models.training import PackagePurchase
    from tests.test_client_reactivation_review import deactivate
    from tests.test_package_reactivation_review import freeze

    identity = graph["session_id"]
    viewed = review(api, identity)
    if frozen == "client":
        deactivate(api, graph)
    else:
        with domain_db.transaction() as session:
            freeze(session, graph, session.get(PackagePurchase, graph["purchase_id"]))
    assert save(api, identity, viewed).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(SessionSummaryReceipt)) is None


@pytest.mark.parametrize("duplicate", [True, False])
def test_independent_summary_writes_have_one_effect(
    api, domain_db, database_settings, graph, duplicate
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import text

    from app.api import session_summaries
    from app.auth.errors import AuthError
    from app.authorization import Principal
    from app.database import Database
    from app.models.people import StaffUser

    identity, key = graph["session_id"], uuid4()
    viewed = review(api, identity)
    with domain_db.transaction() as session:
        user = session.get(StaffUser, graph["owner_id"])
        principal = Principal(user.id, user.name, user.role, None)
    replicas, ready = [Database(database_settings), Database(database_settings)], Barrier(2)

    def apply(pair):
        db, index = pair
        with db.transaction() as session:
            pid = session.scalar(text("SELECT pg_backend_pid()"))
            ready.wait(timeout=5)
            body = session_summaries.SaveSummary(
                expected=viewed["expected"], summary="Same" if duplicate else str(index)
            )
            try:
                result = session_summaries.save(
                    session, principal, identity, key if duplicate else uuid4(), body
                )
                return pid, 200, result.model_dump(mode="json")
            except AuthError as error:
                return pid, error.status, None

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(apply, zip(replicas, [1, 2], strict=True)))
    finally:
        for db in replicas:
            db.close()
    assert len({r[0] for r in results}) == 2
    assert sorted(r[1] for r in results) == ([200, 200] if duplicate else [200, 409])
    if duplicate:
        assert results[0][2] == results[1][2]
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(SessionSummaryReceipt)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(SessionEvent)
                .where(SessionEvent.kind == "session_summary")
            )
            == 1
        )
        assert session.get(TrainingSession, identity).version == viewed["version"] + 1


def test_populated_summary_downgrade_refuses_history_loss(api, domain_db, graph):
    import runpy

    from sqlalchemy import text

    identity = graph["session_id"]
    assert save(api, identity, review(api, identity)).status_code == 200
    statement = runpy.run_path("migrations/versions/20261024_0038_session_summaries.py")[
        "DOWNGRADE_SQL"
    ]
    with pytest.raises(DBAPIError, match="downgrade refused"), domain_db.transaction() as session:
        session.execute(text(statement))
