"""Real PostgreSQL session, replay and independent-request regressions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.auth.admin import link_identity, maintain
from app.auth.errors import AuthError, unavailable
from app.auth.security import handle_hash
from app.models.authentication import AuthAccount, AuthFlow, AuthSession
from app.models.people import StaffIdentity, StaffUser, Trainer

pytestmark = pytest.mark.database


def count(service, model):
    with service.db.transaction() as session:
        return session.scalar(select(func.count()).select_from(model))


def test_login_requires_mfa_then_uses_stored_principal(auth_service, fake_cognito, graph):
    first = auth_service.sign_in("owner@example.test", "initial-password")
    assert first.body["challenge"] == "SOFTWARE_TOKEN_MFA"
    assert not first.session_handle and count(auth_service, AuthSession) == 0
    with auth_service.db.transaction() as session:
        flow = session.scalar(select(AuthFlow))
        assert flow.provider_state != b"opaque-provider-session-value"
        assert flow.handle_hash == handle_hash(first.flow_handle)
    fake_cognito.claims.update(role="attacker", user_id="invented-owner")
    done = auth_service.challenge(first.flow_handle, code="123456")
    assert done.body["user"]["id"] == str(graph["owner_id"])
    assert done.body["user"]["role"] == "owner"
    assert not {"AccessToken", "RefreshToken", "IdToken"} & done.body.keys()
    assert auth_service.me(done.session_handle).body["user"] == done.body["user"]
    with pytest.raises(AuthError):
        auth_service.challenge(first.flow_handle, code="123456")
    assert count(auth_service, AuthSession) == 1


@pytest.mark.parametrize("step", ["tokens", "SMS_MFA", "CUSTOM_CHALLENGE", "SELECT_MFA_TYPE"])
def test_unapproved_or_missing_mfa_never_creates_a_session(auth_service, fake_cognito, step):
    fake_cognito.begin_step = step
    with pytest.raises(AuthError):
        auth_service.sign_in("owner@example.test", "initial-password")
    assert count(auth_service, AuthSession) == 0
    with auth_service.db.transaction() as session:
        assert session.scalar(select(AuthFlow.step)) == "ended"


def test_temporary_password_then_totp_enrolment(auth_service, fake_cognito):
    fake_cognito.begin_step = "NEW_PASSWORD_REQUIRED"
    first = auth_service.sign_in("owner@example.test", "temporary-password")
    assert first.body["challenge"] == "NEW_PASSWORD_REQUIRED"
    setup = auth_service.challenge(first.flow_handle, new_password="long-lowercase-passphrase")
    assert setup.body["challenge"] == "MFA_SETUP"
    assert setup.body["secretCode"] == "ABCDEFGHIJKLMNOP234567"
    assert count(auth_service, AuthSession) == 0
    done = auth_service.challenge(first.flow_handle, code="123456")
    assert done.session_handle
    assert fake_cognito.calls == ["begin", "answer", "associate", "verify_totp", "answer", "user"]
    with auth_service.db.transaction() as session:
        assert session.scalar(select(AuthFlow.provider_state)) is None


def test_bad_codes_exhaust_the_durable_attempt_limit(auth_service, fake_cognito):
    first = auth_service.sign_in("owner@example.test", "password")
    fake_cognito.errors["answer"] = AuthError("INVALID_CODE", "Invalid code.", 400)
    for _ in range(6):
        with pytest.raises(AuthError):
            auth_service.challenge(first.flow_handle, code="000000")
    with pytest.raises(AuthError):
        auth_service.challenge(first.flow_handle, code="123456")
    assert fake_cognito.calls.count("answer") == 6
    assert count(auth_service, AuthSession) == 0


def test_expired_challenge_does_not_contact_provider(auth_service, fake_cognito):
    first = auth_service.sign_in("owner@example.test", "password")
    now = auth_service.clock()
    auth_service.clock = lambda: now + timedelta(minutes=6)
    before = list(fake_cognito.calls)
    with pytest.raises(AuthError):
        auth_service.challenge(first.flow_handle, code="123456")
    assert fake_cognito.calls == before


@pytest.mark.parametrize(
    "change", ["unmapped", "inactive", "wrong_subject", "unverified_email", "no_mfa"]
)
def test_provider_success_cannot_bypass_local_identity_or_staff_requirements(
    auth_service, fake_cognito, graph, change
):
    if change == "unmapped":
        with auth_service.db.transaction() as session:
            identity = session.scalar(select(StaffIdentity))
            identity.status = "inactive"
    if change == "inactive":
        with auth_service.db.transaction() as session:
            session.get(StaffUser, graph["owner_id"]).status = "inactive"
    if change == "wrong_subject":
        fake_cognito.claims["sub"] = "someone-else"
        fake_cognito.user_changes["UserAttributes"] = [
            {"Name": "sub", "Value": "someone-else"},
            {"Name": "email_verified", "Value": "true"},
        ]
    if change == "unverified_email":
        fake_cognito.user_changes["UserAttributes"] = [
            {"Name": "sub", "Value": "identity-subject-one"},
            {"Name": "email_verified", "Value": "false"},
        ]
    if change == "no_mfa":
        fake_cognito.user_changes["UserMFASettingList"] = []
    with pytest.raises(AuthError):
        first = auth_service.sign_in("owner@example.test", "password")
        auth_service.challenge(first.flow_handle, code="123456")
    assert count(auth_service, AuthSession) == 0


def test_trainer_role_and_identity_come_from_database(auth_service, fake_cognito, graph):
    with auth_service.db.transaction() as session:
        session.add(
            StaffIdentity(
                user_id=graph["user_id"],
                issuer=auth_service.settings.cognito_issuer,
                subject="trainer-subject",
                provider_username="provider-username-one",
            )
        )
    fake_cognito.claims.update(role="owner", sub="trainer-subject")
    fake_cognito.user_changes["UserAttributes"] = [
        {"Name": "sub", "Value": "trainer-subject"},
        {"Name": "email_verified", "Value": "true"},
    ]
    first = auth_service.sign_in("trainer@example.test", "password")
    done = auth_service.challenge(first.flow_handle, code="123456")
    assert done.body["user"]["role"] == "trainer"
    assert done.body["user"]["trainerId"] == str(graph["trainer_id"])
    with auth_service.db.transaction() as session:
        session.get(Trainer, graph["trainer_id"]).status = "inactive"
        # The core lifecycle trigger requires matching evidence.
        from app.models.people import LifecycleEvent

        session.add(
            LifecycleEvent(
                trainer_id=graph["trainer_id"],
                status="inactive",
                reason="owner",
                actor_id=graph["owner_id"],
                actor_name="Owner Original",
            )
        )
    with pytest.raises(AuthError):
        auth_service.me(done.session_handle)


@pytest.mark.parametrize("change", ["status", "email", "identity"])
def test_identity_changes_revoke_sessions_without_resurrection(auth_service, login, graph, change):
    done = login()
    with auth_service.db.transaction() as session:
        if change == "identity":
            identity = session.scalar(select(StaffIdentity))
            identity.status = "inactive"
        else:
            user = session.get(StaffUser, graph["owner_id"])
            setattr(user, change, "inactive" if change == "status" else "changed@example.test")
    if change == "status":
        with auth_service.db.transaction() as session:
            session.get(StaffUser, graph["owner_id"]).status = "active"
    with pytest.raises(AuthError):
        auth_service.me(done.session_handle)
    with auth_service.db.transaction() as session:
        record = session.scalar(select(AuthSession))
        assert record.closed_at is not None and record.revoke_pending


def test_absolute_expiry_blocks_session_without_provider_call(auth_service, login, fake_cognito):
    done = login()
    before = list(fake_cognito.calls)
    now = auth_service.clock()
    auth_service.clock = lambda: now + timedelta(hours=9)
    with pytest.raises(AuthError):
        auth_service.me(done.session_handle)
    assert fake_cognito.calls == before


def test_refresh_rotates_secret_without_extending_absolute_session(auth_service, login):
    done = login()
    with auth_service.db.transaction() as session:
        original = session.scalar(select(AuthSession))
    refreshed = auth_service.refresh(done.session_handle)
    with auth_service.db.transaction() as session:
        current = session.scalar(select(AuthSession))
    assert current.refresh_cipher != original.refresh_cipher
    assert current.expires_at == original.expires_at
    assert current.handle_hash == original.handle_hash
    assert current.refresh_lease_id is None
    assert refreshed.body["refreshed"] is True


def test_concurrent_refresh_only_calls_provider_once(auth_service, login, fake_cognito):
    done = login()
    entered, release = Event(), Event()

    def pause():
        entered.set()
        assert release.wait(5)

    fake_cognito.before_refresh = pause
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(auth_service.refresh, done.session_handle)
        try:
            assert entered.wait(5)
            with pytest.raises(AuthError) as failure:
                auth_service.refresh(done.session_handle)
            assert failure.value.code == "AUTH_BUSY"
        finally:
            release.set()
        assert first.result().body["refreshed"]
    assert fake_cognito.calls.count("refresh") == 1


def test_concurrent_challenge_is_consumed_only_once(auth_service, fake_cognito):
    first = auth_service.sign_in("owner@example.test", "password")
    entered, release = Event(), Event()
    answer = fake_cognito.answer

    def pause(*args):
        entered.set()
        assert release.wait(5)
        return answer(*args)

    fake_cognito.answer = pause
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(auth_service.challenge, first.flow_handle, code="123456")
        try:
            assert entered.wait(5)
            with pytest.raises(AuthError) as failure:
                auth_service.challenge(first.flow_handle, code="123456")
            assert failure.value.code == "AUTH_BUSY"
        finally:
            release.set()
        assert pending.result().session_handle
    assert count(auth_service, AuthSession) == 1


def test_sign_out_wins_against_inflight_refresh(auth_service, login, fake_cognito):
    done = login()
    replacement = []

    def replace_session():
        auth_service.sign_out(done.session_handle)
        replacement.append(login())

    fake_cognito.before_refresh = replace_session
    with pytest.raises(AuthError):
        auth_service.refresh(done.session_handle)
    with pytest.raises(AuthError):
        auth_service.me(done.session_handle)
    with auth_service.db.transaction() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuthSession)
                .where(AuthSession.closed_at.is_not(None))
            )
            == 1
        )
    assert auth_service.me(replacement[0].session_handle).body["user"]["role"] == "owner"


def test_failed_refresh_closes_the_uncertain_session(auth_service, login, fake_cognito):
    done = login()
    fake_cognito.errors["refresh"] = unavailable()
    with pytest.raises(AuthError):
        auth_service.refresh(done.session_handle)
    with pytest.raises(AuthError):
        auth_service.me(done.session_handle)


def test_abandoned_refresh_lease_cannot_retry_a_consumed_token(auth_service, login, fake_cognito):
    from uuid import uuid4

    done = login()
    with auth_service.db.transaction() as session:
        record = session.scalar(select(AuthSession))
        record.refresh_lease_id = uuid4()
        record.refresh_lease_until = auth_service.clock() - timedelta(seconds=1)
    before = list(fake_cognito.calls)
    with pytest.raises(AuthError) as failure:
        auth_service.refresh(done.session_handle)
    assert failure.value.code == "SESSION_EXPIRED"
    assert fake_cognito.calls == before
    with pytest.raises(AuthError):
        auth_service.me(done.session_handle)


def test_sign_out_is_immediate_with_retryable_provider_revocation(
    auth_service, login, fake_cognito
):
    done = login()
    fake_cognito.errors["revoke"] = unavailable()
    assert auth_service.sign_out(done.session_handle).body["signedOut"]
    with pytest.raises(AuthError):
        auth_service.me(done.session_handle)
    with auth_service.db.transaction() as session:
        record = session.scalar(select(AuthSession))
        assert record.closed_at and record.revoke_pending and record.refresh_cipher
    fake_cognito.errors.clear()
    assert auth_service.drain_revocations() == 1
    with auth_service.db.transaction() as session:
        assert session.scalar(select(AuthSession.refresh_cipher)) is None
    assert auth_service.sign_out(done.session_handle).body["signedOut"]


def test_signed_out_handle_cannot_sign_out_later_sessions(auth_service, login):
    old = login()
    auth_service.sign_out(old.session_handle)
    current = login()
    assert auth_service.sign_out(old.session_handle).body["signedOut"]
    with pytest.raises(AuthError):
        auth_service.sign_out(old.session_handle, everywhere=True)
    assert auth_service.me(current.session_handle).body["user"]["role"] == "owner"


def test_successful_password_change_revokes_all_sessions(auth_service, login):
    one, two = login(), login()
    result = auth_service.change_password(one.session_handle, "old-password", "new-long-passphrase")
    assert result.body["passwordChanged"] and result.body["signedOut"]
    for done in [one, two]:
        with pytest.raises(AuthError):
            auth_service.me(done.session_handle)
    current = login()
    with pytest.raises(AuthError):
        auth_service.change_password(one.session_handle, "old-password", "another-long-passphrase")
    assert auth_service.me(current.session_handle).body["user"]["role"] == "owner"


def test_wrong_current_password_preserves_sessions(auth_service, login, fake_cognito):
    done = login()
    fake_cognito.errors["change_password"] = AuthError()
    with pytest.raises(AuthError):
        auth_service.change_password(done.session_handle, "wrong-password", "new-long-passphrase")
    assert auth_service.me(done.session_handle).body["user"]["role"] == "owner"


def test_logout_during_password_change_cannot_cancel_the_revocation_barrier(
    auth_service, login, fake_cognito
):
    one, two = login(), login()

    def change(*_):
        auth_service.sign_out(one.session_handle)
        with pytest.raises(AuthError) as failure:
            auth_service.me(two.session_handle)
        assert failure.value.code == "AUTH_BUSY"

    fake_cognito.change_password = change
    assert auth_service.change_password(
        one.session_handle, "old-password", "new-long-passphrase"
    ).body["passwordChanged"]
    for done in [one, two]:
        with pytest.raises(AuthError) as failure:
            auth_service.me(done.session_handle)
        assert failure.value.code == "SESSION_EXPIRED"


def test_login_attempt_budget_is_shared_across_requests(auth_service, fake_cognito):
    fake_cognito.errors["begin"] = AuthError()
    for _ in range(10):
        with pytest.raises(AuthError):
            auth_service.sign_in("owner@example.test", "wrong-password")
    with pytest.raises(AuthError) as failure:
        auth_service.sign_in("owner@example.test", "wrong-password")
    assert failure.value.code == "AUTH_RATE_LIMITED"
    assert fake_cognito.calls.count("begin") == 10


def test_ambiguous_password_change_recovers_by_revoking_old_authority(
    auth_service, login, fake_cognito
):
    done = login()
    fake_cognito.errors["change_password"] = unavailable()
    with pytest.raises(AuthError):
        auth_service.change_password(done.session_handle, "old-password", "new-long-passphrase")
    with pytest.raises(AuthError) as failure:
        auth_service.me(done.session_handle)
    assert failure.value.code == "AUTH_BUSY"
    now = auth_service.clock()
    auth_service.clock = lambda: now + timedelta(seconds=31)
    with pytest.raises(AuthError) as failure:
        auth_service.me(done.session_handle)
    assert failure.value.code == "SESSION_EXPIRED"
    with auth_service.db.transaction() as session:
        assert session.scalar(select(AuthAccount.pending_id)) is None


def test_recovery_is_generic_and_resets_revoke_existing_sessions(auth_service, login):
    done = login()
    unknown = auth_service.forgot_password("unknown@example.test")
    known = auth_service.forgot_password("owner@example.test")
    assert unknown.body == known.body
    assert len(unknown.flow_handle) == len(known.flow_handle) == 43
    result = auth_service.reset_password(known.flow_handle, "123456", "a-new-long-password")
    assert result.body["passwordReset"] and result.body["signedOut"]
    with pytest.raises(AuthError):
        auth_service.me(done.session_handle)
    current = login()
    with pytest.raises(AuthError):
        auth_service.reset_password(known.flow_handle, "123456", "another-new-password")
    assert auth_service.me(current.session_handle).body["user"]["role"] == "owner"


def test_wrong_recovery_code_preserves_session_and_can_retry(auth_service, login, fake_cognito):
    done = login()
    recovery = auth_service.forgot_password("owner@example.test")
    fake_cognito.errors["reset"] = AuthError("INVALID_CODE", "Invalid code.", 400)
    with pytest.raises(AuthError):
        auth_service.reset_password(recovery.flow_handle, "000000", "a-new-long-password")
    assert auth_service.me(done.session_handle).body["user"]
    fake_cognito.errors.clear()
    assert auth_service.reset_password(recovery.flow_handle, "123456", "a-new-long-password").body[
        "passwordReset"
    ]


def test_identity_link_requires_explicit_user_and_verified_subject(auth_service, graph):
    remote = {
        "Enabled": True,
        "UserStatus": "CONFIRMED",
        "Username": "another-provider-name",
        "UserAttributes": [
            {"Name": "sub", "Value": "another-subject"},
            {"Name": "email_verified", "Value": "true"},
            {"Name": "email", "Value": "trainer@example.test"},
        ],
    }
    with pytest.raises(ValueError):
        link_identity(
            auth_service.db,
            auth_service.settings,
            remote,
            "another-subject",
            staff_id=graph["owner_id"],
        )
    result = link_identity(
        auth_service.db, auth_service.settings, remote, "another-subject", staff_id=graph["user_id"]
    )
    assert result == str(graph["user_id"])
    assert (
        link_identity(
            auth_service.db,
            auth_service.settings,
            remote,
            "another-subject",
            staff_id=graph["user_id"],
        )
        == result
    )
    with pytest.raises(ValueError):
        link_identity(
            auth_service.db,
            auth_service.settings,
            remote,
            "wrong-subject",
            staff_id=graph["user_id"],
        )


def test_saved_auth_state_blocks_downgrade(auth_service, login, migrate):
    login()
    with pytest.raises(DBAPIError, match="authentication downgrade refused"):
        migrate("downgrade", "20260915_0002")
    assert count(auth_service, AuthSession) == 1
    with auth_service.db.transaction() as session:
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "20260924_0006"


def test_session_identity_foreign_key_rejects_cross_account_link(auth_service, login, graph):
    login()
    with pytest.raises(IntegrityError), auth_service.db.transaction() as session:
        session.scalar(select(AuthSession)).user_id = graph["user_id"]


def test_identity_ownership_remains_immutable_after_enabling_auth(auth_service, graph):
    for attribute, value in [
        ("subject", "replacement"),
        ("user_id", graph["user_id"]),
        ("provider_username", "replacement-provider"),
    ]:
        with pytest.raises(IntegrityError), auth_service.db.transaction() as session:
            setattr(session.scalar(select(StaffIdentity)), attribute, value)
    with pytest.raises(IntegrityError), auth_service.db.transaction() as session:
        session.delete(session.scalar(select(StaffIdentity)))


def test_legacy_identity_can_bind_provider_username_once(domain_db, graph, auth_settings):
    with domain_db.transaction() as session:
        record = StaffIdentity(
            user_id=graph["owner_id"], issuer=auth_settings.cognito_issuer, subject="legacy-subject"
        )
        session.add(record)
        session.flush()
        identity = record.id
    with domain_db.transaction() as session:
        session.get(StaffIdentity, identity).provider_username = "verified-provider-name"
    with domain_db.transaction() as session:
        assert session.get(StaffIdentity, identity).provider_username == "verified-provider-name"
        assert session.scalar(select(AuthAccount.epoch)) == 1
    with pytest.raises(IntegrityError), domain_db.transaction() as session:
        session.get(StaffIdentity, identity).provider_username = None


def test_maintenance_removes_only_expired_challenges_and_closed_revoked_sessions(
    auth_service, login
):
    done = login()
    now = auth_service.clock()
    auth_service.clock = lambda: now + timedelta(hours=9)
    maintain(auth_service)
    with pytest.raises(AuthError):
        auth_service.me(done.session_handle)
    auth_service.clock = lambda: now + timedelta(days=9)
    result = maintain(auth_service)
    assert result["expiredFlowsRemoved"] == 1
    assert result["closedSessionsRemoved"] == 1
