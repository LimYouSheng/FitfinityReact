"""Real PostgreSQL/HTTP creation, retry, revocation and Admin data isolation."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.auth.errors import AuthError
from app.authorization import Principal, client_write, session_record
from app.models.people import StaffIdentity, StaffUser, Trainer
from app.models.staff import AdminProfile, StaffInvitation
from app.models.training import TrainingSession
from app.persistence import acknowledge
from tests.test_admin_security import BODY
from tests.test_staff_api import api as api
from tests.test_staff_api import body as assessment_body
from tests.test_staff_api import person_id as person_id
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


class FakeInvitations:
    def __init__(self, database):
        self.db, self.calls, self.fail, self.hook = database, [], None, None
        self.remote = {}

    def step(self, name):
        assert self.db.engine.pool.checkedout() == 0
        self.calls.append(name)
        if self.hook:
            self.hook(name)
        if self.fail == name:
            raise AuthError("INVITATION_RETRY", "Retry setup.", 503)

    def check_configuration(self):
        self.step("config")

    def ensure(self, user_id, name, email):
        self.step("ensure")
        self.remote.setdefault(
            user_id,
            {"subject": str(user_id), "username": str(user_id), "status": "FORCE_CHANGE_PASSWORD"},
        )
        return self.remote[user_id]

    def send(self, user_id, email):
        self.step("send")
        return True

    def close(self):
        pass


@pytest.fixture
def invitations(api, domain_db):
    settings = api.app.state.auth_settings
    settings.staff_invitations_enabled = True
    settings.staff_portal_url = "https://staff.example/"
    provider = FakeInvitations(domain_db)
    api.app.state.invitations = provider
    return provider


def create_admin(api, key=None, patch=None):
    return api.post(
        "/api/staff/admins",
        json={**BODY, **(patch or {})},
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def login_admin(api, auth_service, auth_settings, fake_cognito, identity):
    fake_cognito.claims = {"sub": identity, "username": identity, "role": "owner"}
    fake_cognito.user_changes = {
        "Username": identity,
        "UserAttributes": [
            {"Name": "sub", "Value": identity},
            {"Name": "email_verified", "Value": "true"},
        ],
    }
    flow = auth_service.sign_in(BODY["email"], "initial-password-value")
    signed = auth_service.challenge(flow.flow_handle, code="123456")
    api.cookies.clear()
    api.cookies.set(auth_settings.session_cookie, signed.session_handle)
    api.headers["X-CSRF-Token"] = signed.body["csrfToken"]
    assert signed.body["user"]["role"] == "admin" and signed.body["user"]["trainerId"] is None


def test_owner_creates_contact_identity_and_receipt_before_requesting_email(
    api, invitations, domain_db, graph
):
    response = create_admin(api)
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"id", "name", "email", "role", "invitation"}
    assert response.json()["role"] == "admin" and response.json()["invitation"] == "sent"
    assert invitations.calls == ["config", "ensure", "send"]
    identity = UUID(response.json()["id"])
    with domain_db.transaction() as session:
        profile = session.scalar(select(AdminProfile).where(AdminProfile.user_id == identity))
        assert profile.phone_country_code == "+65" and profile.phone_number == "91234567"
        assert profile.birthday.isoformat() == BODY["birthday"] and profile.gender == "Female"
        receipt = session.scalar(select(StaffInvitation))
        assert receipt.actor_id == graph["owner_id"] and receipt.actor_name == "Owner Original"
        assert receipt.status == "sent" and receipt.lease_id is None
        assert session.scalar(
            select(StaffIdentity.subject).where(StaffIdentity.user_id == identity)
        ) == str(identity)
        assert session.scalar(select(func.count()).select_from(Trainer)) == 1
    assert response.headers["cache-control"] == "no-store"


def test_exact_replay_does_not_duplicate_account_or_send_another_email(api, invitations, domain_db):
    key = uuid4()
    first = create_admin(api, key)
    assert first.status_code == 200
    assert create_admin(api, key).json() == first.json()
    assert invitations.calls.count("send") == 1
    assert create_admin(api, key, {"name": "Changed"}).status_code == 409
    assert create_admin(api).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(AdminProfile)) == 1
        assert session.scalar(select(func.count()).select_from(StaffInvitation)) == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"role": "owner"},
        {"rates": {}},
        {"trainer_id": str(uuid4())},
        {"email": "bad"},
        {"birthday": "2026-02-30"},
    ],
)
def test_invalid_or_privileged_payload_creates_nothing(api, invitations, domain_db, patch):
    assert create_admin(api, patch=patch).status_code == 422
    assert invitations.calls == []
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(AdminProfile)) == 0


def test_invitation_switch_and_provider_configuration_fail_before_creating_account(
    api, invitations, domain_db
):
    api.app.state.auth_settings.staff_invitations_enabled = False
    assert create_admin(api).status_code == 503 and invitations.calls == []
    api.app.state.auth_settings.staff_invitations_enabled = True
    invitations.fail = "config"
    assert create_admin(api).status_code == 503
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(AdminProfile)) == 0


def test_missing_csrf_and_wrong_origin_cannot_provision(api, invitations):
    for headers in [{"Origin": "https://attacker.example"}, {"X-CSRF-Token": "invalid"}]:
        response = api.post(
            "/api/staff/admins", json=BODY, headers={**headers, "Idempotency-Key": str(uuid4())}
        )
        assert response.status_code == 403
    assert invitations.calls == []


def test_suppressed_provider_failure_can_resume_with_same_account(api, invitations, domain_db):
    key = uuid4()
    invitations.fail = "ensure"
    assert create_admin(api, key).status_code == 503
    with domain_db.transaction() as session:
        row = session.scalar(select(StaffInvitation))
        identity = row.user_id
        assert row.status == "pending" and row.lease_id is None
    invitations.fail = None
    assert create_admin(api, key).json()["id"] == str(identity)
    assert invitations.calls.count("send") == 1


def test_ambiguous_email_failure_is_preserved_without_automatic_resend(api, invitations, domain_db):
    key = uuid4()
    invitations.fail = "send"
    assert create_admin(api, key).status_code == 503
    invitations.fail = None
    response = create_admin(api, key)
    assert response.status_code == 200 and response.json()["invitation"] == "unknown"
    assert invitations.calls.count("send") == 1
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(StaffIdentity)) == 2


def test_admin_signin_is_local_role_and_all_directory_responses_omit_rates(
    api, invitations, domain_db, graph, auth_service, auth_settings, fake_cognito
):
    identity = create_admin(api).json()["id"]
    login_admin(api, auth_service, auth_settings, fake_cognito, identity)
    assert api.get("/me").json()["user"]["role"] == "admin"
    for path in [
        "/api/directory?role=owner",
        "/api/trainers",
        f"/api/trainers/{graph['trainer_id']}",
        "/api/clients",
        f"/api/clients/{graph['client_id']}",
        "/api/sessions",
        f"/api/sessions/{graph['session_id']}",
    ]:
        response = api.get(path)
        assert response.status_code == 200, response.text
        assert not any(
            key in response.text for key in ["peak_rate", "off_peak_rate", "rates", "remuneration"]
        )
    data = api.get("/api/directory").json()
    assert len(data["clients"]) == len(data["trainers"]) == len(data["packages"]) == 1
    for path in ["/api/remuneration", f"/api/trainers/{graph['trainer_id']}/rates"]:
        assert api.get(path).status_code == 404
    prior = list(invitations.calls)
    assert create_admin(api, patch={"email": "escalate@example.test"}).status_code == 403
    assert invitations.calls == prior


def test_admin_assessments_record_the_actual_admin_and_completed_sessions_remain_read_only(
    api, invitations, domain_db, graph, person_id, auth_service, auth_settings, fake_cognito
):
    identity = create_admin(api).json()["id"]
    login_admin(api, auth_service, auth_settings, fake_cognito, identity)
    response = api.post(
        f"/api/people/{person_id}/assessments",
        json=assessment_body(),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200 and response.json()["actor_id"] == identity
    assert response.json()["actor_name"] == BODY["name"]
    assert api.get("/api/assessment-forms").status_code == 200
    principal = Principal(UUID(identity), BODY["name"], "admin", None)
    with domain_db.transaction() as session:
        client_write(session, principal, graph["client_id"])
        record = session.get(TrainingSession, graph["session_id"])
        acknowledge(session, record.id, record.version, graph["owner_id"], method="late_no_show")
    with pytest.raises(AuthError), domain_db.transaction() as session:
        session_record(session, principal, graph["session_id"], write=True)


def test_inactive_admin_loses_existing_session(
    api, invitations, domain_db, auth_service, auth_settings, fake_cognito
):
    identity = create_admin(api).json()["id"]
    login_admin(api, auth_service, auth_settings, fake_cognito, identity)
    with domain_db.transaction() as session:
        session.get(StaffUser, UUID(identity)).status = "inactive"
    assert api.get("/me").status_code == 401
    assert api.get("/api/directory").status_code == 401


def test_trainer_cannot_create_admin_even_with_forged_role_header(
    api, invitations, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    response = api.post(
        "/api/staff/admins", json=BODY, headers={"X-Role": "owner", "Idempotency-Key": str(uuid4())}
    )
    assert response.status_code == 403 and invitations.calls == []


def test_downgrade_and_direct_role_promotion_preserve_admin_records(
    api, invitations, domain_db, migrate
):
    identity = UUID(create_admin(api).json()["id"])
    with pytest.raises(DBAPIError, match="downgrade refused"):
        migrate("downgrade", "20260921_0005")
    with pytest.raises(IntegrityError), domain_db.transaction() as session:
        session.get(StaffUser, identity).role = "owner"
    with domain_db.transaction() as session:
        assert session.get(StaffUser, identity).role == "admin"
        assert session.scalar(select(func.count()).select_from(AdminProfile)) == 1


def test_expired_sending_lease_is_unknown_not_sent_again(api, invitations, domain_db):
    key = uuid4()
    assert create_admin(api, key).status_code == 200
    with domain_db.transaction() as session:
        row = session.scalar(select(StaffInvitation))
        row.status, row.lease_id = "sending", uuid4()
        row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    assert create_admin(api, key).json()["invitation"] == "unknown"
    assert invitations.calls.count("send") == 1
