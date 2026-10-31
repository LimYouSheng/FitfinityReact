"""Real database completion evidence, concurrency and transaction rollback."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models.api import SessionAcknowledgementReceipt
from app.models.communications import SessionEvent
from app.models.training import Acknowledgement, CreditDebit, TrainingSession
from tests.competing_writers import contend_at_commit
from tests.test_session_outcomes_api import STROKES
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


def review(api, identity):
    response = api.get(f"/api/sessions/{identity}/acknowledgement-review")
    assert response.status_code == 200, response.text
    return response.json()


def save(api, identity, viewed, key=None, **body):
    return api.post(
        f"/api/sessions/{identity}/acknowledgement",
        json={"expected": viewed["expected"], "method": "late_no_show", **body},
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_no_show_correction_preserves_both_signatures_and_one_credit(api, domain_db, graph):
    identity, key = graph["session_id"], uuid4()
    viewed = review(api, identity)
    first = save(api, identity, viewed, key)
    assert first.status_code == 200, first.text
    assert first.json()["sequence"] == 1 and first.json()["used"] == 1
    assert save(api, identity, viewed, key).json() == first.json()
    assert api.get(f"/api/session-acknowledgements/{key}").json() == first.json()
    assert save(api, identity, viewed, key, note="Other").status_code == 409
    assert save(api, identity, viewed).status_code == 409
    corrected = save(
        api,
        identity,
        review(api, identity),
        method="signature",
        signerName="Client",
        signature=STROKES,
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["sequence"] == 2 and corrected.json()["used"] == 1
    assert api.get(f"/api/sessions/{identity}/acknowledgement-review").status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(CreditDebit)) == 1
        assert session.scalar(select(func.count()).select_from(Acknowledgement)) == 2
        assert session.get(TrainingSession, identity).status == "completed"


def test_receipt_failure_rolls_back_completion_credit_and_signature(
    api, domain_db, graph, monkeypatch
):
    from app.api import session_acknowledgements

    identity = graph["session_id"]
    viewed = review(api, identity)

    def fail(**kwargs):
        raise RuntimeError("Interrupted before receipt")

    monkeypatch.setattr(session_acknowledgements, "receipt", lambda *args: None)
    monkeypatch.setattr(session_acknowledgements, "SessionAcknowledgementReceipt", fail)
    assert (
        save(
            api, identity, viewed, method="signature", signerName="Client", signature=STROKES
        ).status_code
        == 500
    )
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(CreditDebit)) == 0
        assert session.scalar(select(func.count()).select_from(Acknowledgement)) == 0
        assert session.get(TrainingSession, identity).version == viewed["version"]


@pytest.mark.parametrize(
    "body",
    [
        {"actorId": "forged"},
        {"method": "unknown"},
        {"signature": STROKES},
        {"method": "signature", "signerName": "Client", "signature": []},
        {"method": "signature", "signerName": "", "signature": STROKES},
    ],
)
def test_invalid_acknowledgement_has_no_effect(api, domain_db, graph, body):
    identity = graph["session_id"]
    assert save(api, identity, review(api, identity), **body).status_code == 422
    with domain_db.transaction() as session:
        assert session.scalar(select(CreditDebit)) is None
        assert session.scalar(select(Acknowledgement)) is None


@pytest.mark.parametrize("duplicate", [True, False])
def test_independent_acknowledgement_writes_have_one_effect(
    api, domain_db, database_settings, graph, duplicate
):
    from app.api import session_acknowledgements
    from app.auth.errors import AuthError
    from app.authorization import Principal
    from app.models.people import StaffUser

    identity, key = graph["session_id"], uuid4()
    viewed = review(api, identity)
    with domain_db.transaction() as session:
        user = session.get(StaffUser, graph["owner_id"])
        principal = Principal(user.id, user.name, user.role, None)

    def apply(session, index):
        body = session_acknowledgements.SaveAcknowledgement(
            expected=viewed["expected"], method="late_no_show"
        )
        try:
            result = session_acknowledgements.save(
                session, principal, identity, key if duplicate else uuid4(), body
            )
            return 200, result.model_dump(mode="json")
        except AuthError as error:
            return error.status, None

    results = [(pid, *result) for pid, result in contend_at_commit(database_settings, apply)]
    assert len({r[0] for r in results}) == 2
    assert sorted(r[1] for r in results) == ([200, 200] if duplicate else [200, 409])
    if duplicate:
        assert results[0][2] == results[1][2]
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(SessionAcknowledgementReceipt)) == 1
        assert session.scalar(select(func.count()).select_from(CreditDebit)) == 1
        assert session.scalar(select(func.count()).select_from(Acknowledgement)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(SessionEvent)
                .where(SessionEvent.kind == "session_acknowledgement")
            )
            == 1
        )
        assert session.get(TrainingSession, identity).version == viewed["version"] + 1


@pytest.mark.parametrize("recorded", [False, True])
def test_signature_preserves_explicit_empty_outcome_or_uses_numeric_plan(api, graph, recorded):
    from tests.test_session_outcomes_api import review as outcome_review
    from tests.test_session_outcomes_api import save as save_outcome
    from tests.test_session_outcomes_api import setup_plan

    identity, _ = setup_plan(api, graph)
    if recorded:
        assert save_outcome(api, identity, outcome_review(api, identity), []).status_code == 200
    response = save(
        api,
        identity,
        review(api, identity),
        method="signature",
        signerName="Client",
        signature=STROKES,
    )
    assert response.status_code == 200, response.text
    details = api.get(f"/api/sessions/{identity}/details").json()
    assert len(details["exerciseResults"]) == (0 if recorded else 1)
    if not recorded:
        assert details["exerciseResults"][0]["loadKg"] == 12


@pytest.mark.parametrize("terminal", [None, "completed", "cancelled"])
def test_trainer_foreign_and_terminal_cover_cannot_complete(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito, terminal
):
    from app.persistence import acknowledge
    from tests.test_directory_api import covered_session
    from tests.test_staff_api import trainer_login

    _, cover, _ = covered_session(domain_db, graph)
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, cover)
        if terminal == "completed":
            acknowledge(session, cover, booking.version, graph["owner_id"], method="late_no_show")
        elif terminal:
            booking.status = terminal
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    if terminal:
        assert api.get(f"/api/sessions/{cover}/acknowledgement-review").status_code == 404
        assert save(api, cover, {"expected": "a" * 64}).status_code == 404
    else:
        response = save(api, cover, review(api, cover))
        assert response.status_code == 200, response.text
    assert api.get(f"/api/sessions/{uuid4()}/acknowledgement-review").status_code == 404


@pytest.mark.parametrize("frozen", ["client", "purchase"])
def test_inactive_completion_is_rejected(api, domain_db, graph, frozen):
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
        assert session.scalar(select(CreditDebit)) is None


def test_completion_receipt_is_private_and_immutable(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    from sqlalchemy.exc import DBAPIError

    from tests.test_staff_api import trainer_login

    identity, key = graph["session_id"], uuid4()
    assert save(api, identity, review(api, identity), key).status_code == 200
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get(f"/api/session-acknowledgements/{key}").status_code == 404
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.scalar(select(SessionAcknowledgementReceipt)).previous = {}
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.scalar(select(SessionAcknowledgementReceipt)))


def test_populated_acknowledgement_downgrade_refuses_history_loss(api, domain_db, graph):
    import runpy

    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    identity = graph["session_id"]
    assert save(api, identity, review(api, identity)).status_code == 200
    statement = runpy.run_path("migrations/versions/20261024_0039_session_acknowledgements.py")[
        "DOWNGRADE_SQL"
    ]
    with (
        pytest.raises(DBAPIError, match="retained acknowledgement evidence"),
        domain_db.transaction() as session,
    ):
        session.execute(text(statement))


@pytest.mark.parametrize("blocked", ["open", "future", "cancelled"])
def test_server_date_and_schedule_reject_ineligible_completion(api, domain_db, graph, blocked):
    from datetime import timedelta

    from sqlalchemy import text

    identity = graph["session_id"]
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, identity)
        if blocked == "open":
            booking.schedule_state = "open"
            booking.training_date = booking.starts_at = booking.ends_at = booking.session_number = (
                booking.schedule_slot_id
            ) = None
        elif blocked == "future":
            booking.training_date = session.scalar(
                text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date")
            ) + timedelta(days=1)
        else:
            booking.status = "cancelled"
    assert api.get(f"/api/sessions/{identity}/acknowledgement-review").status_code == 409
    assert save(api, identity, {"expected": "a" * 64}).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(CreditDebit)) is None


@pytest.mark.parametrize("renewed", [False, True, "overlapping"])
def test_two_remaining_credits_notify_once_unless_already_renewed(api, domain_db, graph, renewed):
    from datetime import time

    from app.models.communications import Message, MessageReceipt
    from app.models.people import Client
    from app.models.training import PackageTemplate, PackageTemplateRevision
    from app.persistence import add_client, add_purchase
    from tests.domain_fixtures import person, purchase_parts

    with domain_db.transaction() as session:
        client = add_client(
            session,
            Client(kind="individual", name="Renewal Client", trainer_id=graph["trainer_id"]),
            [person()],
        )
        template = PackageTemplate()
        session.add(template)
        session.flush()
        session.add(
            PackageTemplateRevision(
                template_id=template.id,
                revision=1,
                name="Three",
                total_sessions=3,
                validity_days=90,
                actor_id=graph["owner_id"],
                actor_name="Owner Original",
            )
        )
        session.flush()
        values = {**graph, "client_id": client.id, "template_id": template.id}
        purchase, slots, preferences, bookings = purchase_parts(
            values, graph["start_date"], stage="current"
        )
        purchase.total_sessions = 3
        purchase.name = "Three"
        for slot in slots:
            slot.starts_at = slot.purchased_starts_at = time(12)
            slot.ends_at = slot.purchased_ends_at = time(13)
        for booking in bookings:
            booking.starts_at, booking.ends_at = time(12), time(13)
        # Purchase persistence accepts its full typed schedule; add the third occurrence.
        from datetime import timedelta

        bookings.append(
            TrainingSession(
                client_id=client.id,
                trainer_id=graph["trainer_id"],
                session_number=3,
                schedule_slot_id=slots[0].id,
                training_date=graph["start_date"] + timedelta(days=14),
                starts_at=time(12),
                ends_at=time(13),
            )
        )
        add_purchase(
            session, purchase, slots, preferences, bookings, expected_client_version=client.version
        )
        identity, purchase_id = bookings[0].id, purchase.id
        if renewed:
            next_purchase, slots, preferences, bookings = purchase_parts(
                {**values, "template_id": graph["template_id"]},
                graph["start_date"] + timedelta(days=1) if renewed == "overlapping" else None,
            )
            add_purchase(
                session,
                next_purchase,
                slots,
                preferences,
                bookings,
                expected_client_version=client.version,
            )
    assert save(api, identity, review(api, identity)).status_code == 200
    assert (
        save(
            api,
            identity,
            review(api, identity),
            method="signature",
            signerName="Client",
            signature=STROKES,
        ).status_code
        == 200
    )
    with domain_db.transaction() as session:
        notices = list(
            session.scalars(
                select(Message).where(Message.kind == "renewal", Message.purchase_id == purchase_id)
            )
        )
        assert len(notices) == (0 if renewed else 1)
        if not renewed:
            assert "1/3 sessions used" in notices[0].body
            recipients = set(
                session.scalars(
                    select(MessageReceipt.user_id).where(MessageReceipt.message_id == notices[0].id)
                )
            )
            assert recipients == {graph["owner_id"], graph["user_id"]}


def test_acknowledgement_lock_timeout_preserves_credit_and_original_key(api, graph, domain_db):
    from sqlalchemy import text

    from app.api.request_cancellation import DECISION_LOCK

    identity, key = graph["session_id"], uuid4()
    viewed = review(api, identity)
    with domain_db.transaction() as blocker:
        blocker.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": DECISION_LOCK})
        response = save(api, identity, viewed, key, method="late_no_show")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "service_unavailable"
        assert blocker.scalar(select(func.count()).select_from(CreditDebit)) == 0
        assert blocker.scalar(select(func.count()).select_from(Acknowledgement)) == 0
        assert blocker.get(TrainingSession, identity).version == viewed["version"]
    first = save(api, identity, viewed, key, method="late_no_show")
    assert first.status_code == 200, first.text
    assert save(api, identity, viewed, key, method="late_no_show").json() == first.json()
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(CreditDebit)) == 1
        assert session.scalar(select(func.count()).select_from(Acknowledgement)) == 1
        assert session.scalar(select(func.count()).select_from(SessionAcknowledgementReceipt)) == 1
