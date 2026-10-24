"""Real DB/HTTP email verification with a deterministic provider; never sends real mail."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.auth.errors import AuthError, unavailable
from app.models.email_changes import StaffEmailChange
from app.models.people import StaffIdentity, StaffUser, Trainer
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database
NEW_EMAIL = "verified-new@example.test"


@pytest.fixture
def email_flow(api, auth_service, auth_settings, domain_db, graph, fake_cognito, monkeypatch):
    with domain_db.transaction() as session:
        session.add(
            StaffIdentity(
                user_id=graph["user_id"],
                issuer=auth_settings.cognito_issuer,
                subject="email-trainer",
                provider_username="email-trainer-name",
            )
        )
        old = session.get(StaffUser, graph["user_id"]).email
    state = {"email": old, "pending": None, "sent": 0, "verified": 0}

    def send(access, email):
        fake_cognito._call("request_email_change")
        state["pending"] = email
        state["sent"] += 1

    def verify(access, code):
        fake_cognito._call("verify_email_change")
        if code != "123456":
            raise AuthError("INVALID_CODE", "The code is invalid or expired.", 400)
        state["email"] = state["pending"]
        state["verified"] += 1
        fake_cognito.user_changes["UserAttributes"] = [
            {"Name": "sub", "Value": "email-trainer"},
            {"Name": "email_verified", "Value": "true"},
            {"Name": "email", "Value": state["email"]},
        ]

    monkeypatch.setattr(fake_cognito, "request_email_change", send, raising=False)
    monkeypatch.setattr(fake_cognito, "verify_email_change", verify, raising=False)

    def login():
        fake_cognito.claims = {"sub": "email-trainer", "username": "email-trainer-name"}
        fake_cognito.user_changes = {
            "Username": "email-trainer-name",
            "UserAttributes": [
                {"Name": "sub", "Value": "email-trainer"},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "email", "Value": state["email"]},
            ],
        }
        with domain_db.transaction() as session:
            local_email = session.get(StaffUser, graph["user_id"]).email
        flow = auth_service.sign_in(local_email, "initial-password-value")
        signed = auth_service.challenge(flow.flow_handle, code="123456")
        api.cookies.clear()
        api.cookies.set(auth_settings.session_cookie, signed.session_handle)
        api.headers["X-CSRF-Token"] = signed.body["csrfToken"]
        return signed

    state.update(login=login, old=old, verify=verify, send=send)
    return state


def request_email(api, graph, *, email=NEW_EMAIL, key=None, version=1):
    return api.post(
        f"/api/trainers/{graph['trainer_id']}/email-change",
        json={"email": email, "expectedVersion": version},
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def post(api, change, action, **body):
    return api.post(f"/auth/email-change/{change['id']}/{action}", json=body)


def test_verified_switch_is_atomic_and_revokes_sessions(api, graph, email_flow, domain_db):
    key = uuid4()
    created = request_email(api, graph, key=key)
    assert created.status_code == 200, created.text
    change = created.json()
    assert request_email(api, graph, key=key).json() == change
    assert request_email(api, graph, key=key, email="different@example.test").status_code == 409
    assert request_email(api, graph).status_code == 409
    assert email_flow["sent"] == 0
    # A manager cannot send or confirm using their own token for another account.
    assert post(api, change, "send").status_code == 404
    assert post(api, change, "verify", code="123456").status_code == 404
    assert api.get("/auth/email-change").json() == {"change": None}
    email_flow["login"]()
    assert api.get("/auth/email-change").json()["change"] == change
    assert post(api, change, "send").json()["state"] == "pending"
    with domain_db.transaction() as session:
        assert session.get(StaffUser, graph["user_id"]).email == email_flow["old"]
        assert session.get(Trainer, graph["trainer_id"]).email == email_flow["old"]
    done = post(api, change, "verify", code="123456")
    assert done.status_code == 200, done.text
    assert done.json()["state"] == "completed" and done.json()["signedOut"] is True
    assert api.get("/me").status_code == 401
    with domain_db.transaction() as session:
        assert session.get(StaffUser, graph["user_id"]).email == NEW_EMAIL
        assert session.get(Trainer, graph["trainer_id"]).email == NEW_EMAIL
        assert session.scalar(select(StaffEmailChange)).completed_at is not None
    email_flow["login"]()
    assert api.get("/me").json()["user"]["email"] == NEW_EMAIL
    assert post(api, change, "reconcile").json()["state"] == "completed"
    assert email_flow["sent"] == email_flow["verified"] == 1


def test_pending_address_is_reserved_against_onboarding(api, graph, email_flow, domain_db, migrate):
    assert request_email(api, graph).status_code == 200
    with (
        pytest.raises(DBAPIError, match="staff email reserved"),
        domain_db.transaction() as session,
    ):
        session.add(StaffUser(name="Competing Admin", email=NEW_EMAIL, role="admin"))
    with (
        pytest.raises(DBAPIError, match="immutable email change"),
        domain_db.transaction() as session,
    ):
        change = session.scalar(select(StaffEmailChange))
        session.delete(change)
    with pytest.raises(DBAPIError, match="Email correction downgrade refused"):
        migrate("downgrade", "20261013_0012")
    assert email_flow["sent"] == 0


@pytest.mark.parametrize("email", ["owner@example.test", "not-an-email", "a\n@example.test"])
def test_conflicting_or_invalid_address_never_sends(api, graph, email_flow, email):
    assert request_email(api, graph, email=email).status_code in {409, 422}
    assert email_flow["sent"] == 0


def test_invalid_code_is_bounded_and_does_not_switch(api, graph, email_flow, domain_db):
    change = request_email(api, graph).json()
    email_flow["login"]()
    assert post(api, change, "send").status_code == 200
    for _ in range(6):
        assert post(api, change, "verify", code="000000").status_code == 400
    assert post(api, change, "verify", code="123456").status_code == 429
    with domain_db.transaction() as session:
        assert session.get(StaffUser, graph["user_id"]).email == email_flow["old"]
        assert session.scalar(select(StaffEmailChange)).state == "pending"


def test_lost_verification_response_reconciles_without_repeating_code(
    api, graph, email_flow, auth_service, fake_cognito, monkeypatch, domain_db
):
    change = request_email(api, graph).json()
    email_flow["login"]()
    assert post(api, change, "send").status_code == 200

    def lost(access, code):
        email_flow["verify"](access, code)
        raise unavailable()

    monkeypatch.setattr(fake_cognito, "verify_email_change", lost)
    assert post(api, change, "verify", code="123456").status_code == 503
    assert post(api, change, "reconcile").status_code == 409
    now = auth_service.clock()
    auth_service.clock = lambda: now + timedelta(seconds=31)
    completed = post(api, change, "reconcile")
    assert completed.status_code == 200, completed.text
    assert completed.json()["state"] == "completed"
    assert email_flow["verified"] == 1
    with domain_db.transaction() as session:
        assert session.get(StaffUser, graph["user_id"]).email == NEW_EMAIL


def test_lost_send_needs_explicit_action_and_preserves_old_address(
    api, graph, email_flow, auth_service, fake_cognito, monkeypatch, domain_db
):
    change = request_email(api, graph).json()
    email_flow["login"]()

    def lost(access, email):
        email_flow["send"](access, email)
        raise unavailable()

    monkeypatch.setattr(fake_cognito, "request_email_change", lost)
    assert post(api, change, "send").status_code == 503
    now = auth_service.clock()
    auth_service.clock = lambda: now + timedelta(seconds=31)
    assert post(api, change, "reconcile").json()["state"] == "sending"
    assert email_flow["sent"] == 1
    with domain_db.transaction() as session:
        assert session.get(StaffUser, graph["user_id"]).email == email_flow["old"]
    assert post(api, change, "verify", code="123456").json()["state"] == "completed"


def test_deactivation_during_provider_confirmation_cannot_commit(
    api, graph, email_flow, fake_cognito, monkeypatch, domain_db
):
    change = request_email(api, graph).json()
    email_flow["login"]()
    assert post(api, change, "send").status_code == 200

    def deactivate(access, code):
        email_flow["verify"](access, code)
        with domain_db.transaction() as session:
            session.get(StaffUser, graph["user_id"]).status = "inactive"

    monkeypatch.setattr(fake_cognito, "verify_email_change", deactivate)
    assert post(api, change, "verify", code="123456").status_code == 401
    with domain_db.transaction() as session:
        assert session.get(StaffUser, graph["user_id"]).email == email_flow["old"]
        assert session.scalar(select(StaffEmailChange)).state == "verifying"


def test_request_rechecks_version_role_and_csrf(api, graph, email_flow):
    assert request_email(api, graph, version=2).status_code == 409
    token = api.headers.pop("X-CSRF-Token")
    assert request_email(api, graph).status_code == 403
    api.headers["X-CSRF-Token"] = token
    email_flow["login"]()
    assert request_email(api, graph).status_code == 403
