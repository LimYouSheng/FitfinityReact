"""Exercise explicit email intent through real HTTP and isolated PostgreSQL."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.email_delivery import EmailDelivery, EmailReportReceipt
from app.models.people import ClientPerson
from app.models.training import TrainingSession
from app.persistence import acknowledge
from tests.test_admin_api import invitations as invitations
from tests.test_admin_approvals import identities as identities
from tests.test_session_outcomes_api import STROKES, measurement, setup_plan
from tests.test_session_outcomes_api import review as outcome_review
from tests.test_session_outcomes_api import save as outcome_save
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def post(api, path, body, key=None):
    return api.post(path, json=body, headers={"Idempotency-Key": str(key or uuid4())})


@pytest.fixture
def email_selection(api, graph, domain_db):
    identity, plan_id = setup_plan(api, graph)
    result = outcome_save(api, identity, outcome_review(api, identity), [measurement(plan_id)])
    assert result.status_code == 200, result.text
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
        person = session.scalar(
            select(ClientPerson).where(ClientPerson.client_id == graph["client_id"])
        )
        person.email = "synthetic-client@example.test"
    api.app.state.auth_settings.transactional_email_enabled = True
    domain_db.sessions.configure(info={"transactional_email_enabled": True})
    return {
        "kind": "progress",
        "targetId": str(graph["client_id"]),
        "purchaseId": str(graph["purchase_id"]),
        "includeSummary": True,
        "videoIds": [],
    }


def reviewed(api, selection):
    response = post(api, "/api/report-email/review", selection)
    assert response.status_code == 200, response.text
    return {**selection, "expected": response.json()["expected"]}


def test_review_does_not_queue_and_explicit_send_recovers_without_duplicate(
    api, domain_db, email_selection
):
    body = reviewed(api, email_selection)
    with domain_db.transaction() as session:
        assert session.scalar(select(EmailDelivery)) is None
    key = uuid4()
    result = post(api, "/api/report-email", body, key)
    assert result.status_code == 200, result.text
    assert result.json() == {"requestId": str(key), "queued": 1}
    assert api.get(f"/api/report-email/{key}").json() == result.json()
    assert post(api, "/api/report-email", body, key).json() == result.json()
    assert post(api, "/api/report-email", body).json() == result.json()
    assert post(api, "/api/report-email", {**body, "expected": "0" * 64}, key).status_code == 409
    with domain_db.transaction() as session:
        rows = list(session.scalars(select(EmailDelivery)))
        assert len(rows) == 1
        assert rows[0].recipient == "synthetic-client@example.test"
        assert rows[0].state == "pending" and rows[0].attempts == 0
        assert "20" in rows[0].body
        assert len(list(session.scalars(select(EmailReportReceipt)))) == 1


def test_changed_recipient_rejects_stale_send_without_queue(api, domain_db, email_selection):
    body = reviewed(api, email_selection)
    with domain_db.transaction() as session:
        session.scalar(
            select(ClientPerson).where(ClientPerson.client_id == email_selection["targetId"])
        ).email = "changed@example.test"
    response = post(api, "/api/report-email", body)
    assert response.status_code == 409, response.text
    with domain_db.transaction() as session:
        assert session.scalar(select(EmailDelivery)) is None
        assert session.scalar(select(EmailReportReceipt)) is None


def test_disabled_and_foreign_report_cannot_queue(api, domain_db, email_selection):
    assert (
        post(
            api, "/api/report-email/review", {**email_selection, "purchaseId": str(uuid4())}
        ).status_code
        == 404
    )
    body = reviewed(api, email_selection)
    api.app.state.auth_settings.transactional_email_enabled = False
    assert post(api, "/api/report-email", body).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(EmailDelivery)) is None


def test_email_receipt_is_private_to_original_actor(
    api, domain_db, graph, email_selection, auth_settings, auth_service, fake_cognito
):
    body = reviewed(api, email_selection)
    key = uuid4()
    assert post(api, "/api/report-email", body, key).status_code == 200
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get(f"/api/report-email/{key}").status_code == 404
    assert api.get(f"/api/report-email/{uuid4()}").status_code == 404


def test_required_admin_approval_cannot_be_bypassed_by_email_route(
    api, graph, domain_db, email_selection, identities
):
    from tests.test_admin_domain_approvals import enable

    enable(api, identities, "progressReportSharing")
    response = post(api, "/api/report-email/review", email_selection)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "REPORT_APPROVAL_REQUIRED"
    with domain_db.transaction() as session:
        assert session.scalar(select(EmailDelivery)) is None


def test_failed_receipt_commit_rolls_back_email_intent(
    api, domain_db, email_selection, monkeypatch
):
    from app.api import report_email

    body = reviewed(api, email_selection)

    def interrupted(**kwargs):
        raise RuntimeError("Synthetic interruption before receipt commit")

    monkeypatch.setattr(report_email, "EmailReportReceipt", interrupted)
    response = post(api, "/api/report-email", body)
    assert response.status_code == 500, response.text
    with domain_db.transaction() as session:
        assert session.scalar(select(EmailDelivery)) is None


def test_dispatch_requires_purpose_bound_signature_and_never_accepts_mail_content(
    api, domain_db, monkeypatch
):
    import hashlib
    import hmac
    import json
    import time

    from app import email_dispatch
    from tests.test_transactional_email import queued

    identity = queued(domain_db)
    calls = []

    class Provider:
        def __init__(self, *args):
            pass

        def send(self, recipient, content, delivery_id):
            calls.append((recipient, delivery_id))
            return "synthetic-ses-id"

        def close(self):
            pass

    key = bytes(range(32))
    monkeypatch.setattr(email_dispatch, "signing_key", lambda settings: key)
    monkeypatch.setattr(email_dispatch, "SesEmail", Provider)
    api.app.state.auth_settings.transactional_email_enabled = True
    api.cookies.clear()
    api.headers.pop("X-CSRF-Token", None)
    body = json.dumps({"at": int(time.time()), "id": str(uuid4())}).encode()
    assert api.post("/internal/email-dispatch", content=body).status_code == 403

    def signed(value):
        signature = hmac.new(
            key, b"fitfinity.email.dispatch.v1\n" + value, hashlib.sha256
        ).hexdigest()
        return api.post(
            "/internal/email-dispatch",
            content=value,
            headers={"x-fitfinity-email-signature": signature},
        )

    injected = json.dumps(
        {"at": int(time.time()), "id": str(uuid4()), "recipient": "other@example.test"}
    ).encode()
    assert signed(injected).status_code == 403
    assert calls == []
    response = signed(body)
    assert response.status_code == 200, response.text
    assert response.json() == {"delivery": {"id": str(identity), "state": "accepted"}}
    assert signed(body).json() == {"delivery": None}
    assert calls == [("one@example.test", identity)]
