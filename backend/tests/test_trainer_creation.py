"""Trainer onboarding is durable, actor-scoped and financially opaque to Admins."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.api import trainer_creation
from app.models.communications import Message
from app.models.people import StaffIdentity, StaffUser, Trainer, TrainerAvailability
from app.models.staff import StaffInvitation
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_admin_security import BODY as ADMIN_BODY
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database
BODY = {
    **ADMIN_BODY,
    "name": "New Trainer",
    "email": "new-trainer@example.test",
    "trainerType": "Personal Trainer",
    "qualifications": "Approved qualifications",
    "publicProfile": "Hidden",
    "rates": {"peak": 9000, "offPeak": 6000},
    "slots": [{"weekday": 0, "startsAt": "09:00", "endsAt": "12:00"}],
    "approvalNeeded": {
        "availability": True,
        "sessionTime": False,
        "trainerReassignment": True,
        "fixedWeeklySchedule": False,
    },
}


def create(api, body=None, key=None):
    return api.post(
        "/api/staff/trainers", json=body or BODY, headers={"Idempotency-Key": str(key or uuid4())}
    )


def receipt(api, key):
    return api.get(f"/api/staff/trainer-creations/{key}")


def counts(db):
    with db.transaction() as session:
        return {
            model.__tablename__: session.scalar(select(func.count()).select_from(model))
            for model in [
                StaffUser,
                Trainer,
                StaffIdentity,
                TrainerAvailability,
                StaffInvitation,
                Message,
            ]
        }


def test_complete_owner_creation_persists_profile_and_exact_retry_once(
    api, domain_db, graph, invitations
):
    before, key = counts(domain_db), uuid4()
    response = create(api, key=key)
    assert response.status_code == 200, response.text
    result = response.json()
    assert set(result) == {"id", "invitation"} and result["invitation"] == "sent"
    assert create(api, key=key).json() == result
    calls = list(invitations.calls)
    assert receipt(api, key).json() == result and invitations.calls == calls
    with domain_db.transaction() as session:
        trainer = session.get(Trainer, UUID(result["id"]))
        user = session.get(StaffUser, trainer.user_id)
        assert user.role == "trainer" and user.status == trainer.status == "active"
        assert user.name == trainer.name == BODY["name"]
        assert user.email == trainer.email == BODY["email"]
        assert trainer.peak_rate_cents == 9000 and trainer.off_peak_rate_cents == 6000
        assert trainer.qualifications == BODY["qualifications"] and not trainer.public_profile
        assert trainer.approve_availability and not trainer.approve_session_time
        assert trainer.approve_session_trainer and not trainer.approve_weekly_schedule
        slots = session.scalars(
            select(TrainerAvailability).where(TrainerAvailability.trainer_id == trainer.id)
        ).all()
        assert len(slots) == 1 and slots[0].weekday == 0 and slots[0].starts_at.hour == 9
        identity = session.scalar(select(StaffIdentity).where(StaffIdentity.user_id == user.id))
        assert identity.subject == str(user.id)
    after = counts(domain_db)
    assert after == {
        **{name: count + 1 for name, count in before.items()},
        "messages": before["messages"] + 2,
    }
    assert invitations.calls.count("ensure") == invitations.calls.count("send") == 1


def test_admin_uses_server_defaults_and_never_receives_rates(
    api, domain_db, graph, invitations, auth_service, auth_settings, fake_cognito
):
    admin = create_admin(api).json()
    login_admin(api, auth_service, auth_settings, fake_cognito, admin["id"])
    body = {k: v for k, v in BODY.items() if k != "rates"}
    key = uuid4()
    response = create(api, body, key)
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"id", "invitation"}
    assert receipt(api, key).json() == response.json()
    with domain_db.transaction() as session:
        trainer = session.get(Trainer, UUID(response.json()["id"]))
        assert trainer.peak_rate_cents == 8000 and trainer.off_peak_rate_cents == 5500
    directory = api.get("/api/directory").json()
    assert "trainerRates" not in directory["trainerOnboardingPolicy"]
    created = next(t for t in directory["trainers"] if t["id"] == response.json()["id"])
    assert not {"peak_rate_cents", "off_peak_rate_cents", "rates"} & created.keys()


@pytest.mark.parametrize("rates", [None, {"peak": 1, "offPeak": 1}])
def test_admin_cannot_supply_even_null_financial_input(
    api, domain_db, graph, invitations, auth_service, auth_settings, fake_cognito, rates
):
    admin = create_admin(api).json()
    login_admin(api, auth_service, auth_settings, fake_cognito, admin["id"])
    before, calls = counts(domain_db), list(invitations.calls)
    assert create(api, {**BODY, "rates": rates}).status_code == 403
    assert counts(domain_db) == before and invitations.calls == calls


@pytest.mark.parametrize(
    "patch",
    [
        {"role": "owner"},
        {"actor_id": str(uuid4())},
        {"trainerType": " "},
        {"slots": []},
        {"rates": {"peak": "90", "offPeak": 6000}},
        {"approvalNeeded": {"availability": False}},
        {"birthday": ""},
        {
            "slots": [
                {"weekday": 0, "startsAt": "09:00", "endsAt": "12:00"},
                {"weekday": 0, "startsAt": "11:00", "endsAt": "13:00"},
            ]
        },
    ],
)
def test_invalid_complete_draft_never_creates_partial_profile(
    api, domain_db, graph, invitations, patch
):
    before = counts(domain_db)
    assert create(api, {**BODY, **patch}).status_code == 422
    assert counts(domain_db) == before and invitations.calls == []


def test_owner_must_review_rates_and_disabled_invitation_configuration_does_not_write(
    api, domain_db, graph, invitations
):
    before = counts(domain_db)
    assert create(api, {k: v for k, v in BODY.items() if k != "rates"}).status_code == 422
    api.app.state.auth_settings.staff_invitations_enabled = False
    assert create(api).status_code == 503
    assert counts(domain_db) == before and invitations.calls == []


def test_ensure_failure_retains_one_profile_and_explicit_retry_finishes_same_identity(
    api, domain_db, graph, invitations
):
    invitations.fail, key = "ensure", uuid4()
    assert create(api, key=key).status_code == 503
    pending = receipt(api, key).json()
    assert pending["invitation"] == "pending"
    before, calls = counts(domain_db), list(invitations.calls)
    assert receipt(api, key).json() == pending and invitations.calls == calls
    invitations.fail = None
    response = create(api, key=key)
    assert response.status_code == 200 and response.json()["id"] == pending["id"]
    assert response.json()["invitation"] == "sent"
    after = counts(domain_db)
    assert after == {**before, "staff_identities": before["staff_identities"] + 1}
    assert invitations.calls.count("send") == 1


def test_uncertain_delivery_is_never_resent_by_creation_retry(api, domain_db, graph, invitations):
    invitations.fail, key = "send", uuid4()
    assert create(api, key=key).status_code == 503
    result = receipt(api, key).json()
    assert result["invitation"] == "unknown"
    invitations.fail = None
    assert create(api, key=key).json() == result
    assert invitations.calls.count("ensure") == invitations.calls.count("send") == 1


def test_changed_key_body_and_existing_email_reject_without_duplicate_records(
    api, domain_db, graph, invitations
):
    key = uuid4()
    assert create(api, key=key).status_code == 200
    before = counts(domain_db)
    assert create(api, {**BODY, "name": "Another"}, key).status_code == 409
    assert create(api).status_code == 409
    assert create(api, {**BODY, "email": "trainer@example.test"}).status_code == 409
    assert counts(domain_db) == before and invitations.calls.count("send") == 1


def test_failed_notice_rolls_back_profile_and_invitation_before_provider_setup(
    api, domain_db, graph, invitations, monkeypatch
):
    before = counts(domain_db)

    def fail(*args):
        raise RuntimeError("notice failed")

    monkeypatch.setattr(trainer_creation, "notify", fail)
    assert create(api).status_code == 500
    assert counts(domain_db) == before and invitations.calls == ["config"]


def test_concurrent_retry_uses_one_profile_and_one_invitation(
    api, domain_db, graph, invitations, monkeypatch
):
    # Other requests may hold connections; the provider's own request must not.
    in_transaction = ContextVar("trainer_creation_transaction", default=False)
    transaction = domain_db.transaction

    @contextmanager
    def tracked_transaction():
        token = in_transaction.set(True)
        try:
            with transaction() as session:
                yield session
        finally:
            in_transaction.reset(token)

    def provider_step(name):
        assert not in_transaction.get()
        invitations.calls.append(name)

    monkeypatch.setattr(domain_db, "transaction", tracked_transaction)
    monkeypatch.setattr(invitations, "step", provider_step)
    key = uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: create(api, key=key), range(2)))
    assert all(r.status_code in {200, 409} for r in responses)
    final = create(api, key=key)
    assert final.status_code == 200
    with domain_db.transaction() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(Trainer).where(Trainer.email == BODY["email"])
            )
            == 1
        )
    assert invitations.calls.count("send") == 1


def test_trainer_and_missing_csrf_cannot_create_or_read_owner_receipt(
    api, domain_db, graph, invitations, auth_settings, auth_service, fake_cognito
):
    key = uuid4()
    assert create(api, key=key).status_code == 200
    api.headers.pop("X-CSRF-Token")
    assert create(api).status_code == 403
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert create(api).status_code == 403
    assert receipt(api, key).status_code == 403


def test_admin_cannot_read_another_actors_creation_receipt_or_replay_it(
    api, domain_db, graph, invitations, auth_settings, auth_service, fake_cognito
):
    key = uuid4()
    assert create(api, key=key).status_code == 200
    admin = create_admin(api).json()
    login_admin(api, auth_service, auth_settings, fake_cognito, admin["id"])
    assert receipt(api, key).status_code == 404
    assert create(api, {k: v for k, v in BODY.items() if k != "rates"}, key).status_code == 409


def test_new_identity_logs_in_as_trainer_even_if_provider_claims_owner(
    api, domain_db, graph, invitations, auth_settings, auth_service, fake_cognito
):
    created = create(api).json()
    with domain_db.transaction() as session:
        user_id = session.get(Trainer, UUID(created["id"])).user_id
    identity = str(user_id)
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
    assert signed.body["user"]["role"] == "trainer"
    assert signed.body["user"]["trainerId"] == created["id"]
