"""Portable cryptographic, provider-contract and HTTP security regressions."""

import base64
import json
import time
from pathlib import Path

import pytest
from botocore.stub import Stubber
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.auth.errors import AuthError
from app.auth.jwt import AccessVerifier
from app.auth.security import (
    TokenVault,
    csrf_token,
    handle_hash,
    new_handle,
    require_csrf,
    validate_password,
)
from app.auth.service import AuthResult
from app.config import Settings
from app.main import create_app


@pytest.mark.parametrize(
    "changes",
    [
        {"token_use": "id"},
        {"client_id": "other-client"},
        {"iss": "https://attacker.example"},
        {"exp": 1},
        {"iat": int(time.time()) + 10000},
        {"auth_time": int(time.time()) + 10000},
        {"auth_time": None},
        {"sub": None},
        {"username": None},
        {"scope": "unrelated"},
        {"exp": True},
        {"auth_time": "123"},
        {"exp": int(time.time()) + 7200},
    ],
)
def test_jwt_rejects_wrong_identity_scope_or_time(verifier, signed, changes):
    with pytest.raises(AuthError):
        verifier.verify(signed(changes))


def test_valid_jwt_and_untrusted_role_claims(verifier, signed):
    claims = verifier.verify(signed({"role": "owner", "cognito:groups": ["Administrators"]}))
    assert claims["sub"] == "identity-subject-one"
    assert claims["token_use"] == "access"


def test_jwt_rejects_wrong_signature_and_unsigned_token(verifier, signed):
    wrong = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(AuthError):
        verifier.verify(signed(key=wrong))
    with pytest.raises(AuthError):
        verifier.verify("eyJhbGciOiJub25lIn0.eyJzdWIiOiJvd25lciJ9.")


def test_jwks_cache_bounds_unknown_key_refresh(auth_settings, rsa_keys, signed, monkeypatch):
    fetched = []
    verifier = AccessVerifier(
        auth_settings, fetch=lambda url: fetched.append(url) or {"keys": [rsa_keys[1]]}
    )
    verifier.verify(signed())
    for _ in range(8):
        with pytest.raises(AuthError):
            verifier.verify(signed(header={"kid": "attacker-key"}))
    assert fetched == [auth_settings.cognito_issuer + "/.well-known/jwks.json"]
    monkeypatch.setattr("app.auth.jwt.time.monotonic", lambda: verifier._loaded + 6)
    verifier.fetch = lambda url: {"keys": [{**rsa_keys[1], "kid": "rotated-key"}]}
    assert verifier.verify(signed(header={"kid": "rotated-key"}))["token_use"] == "access"


@pytest.mark.parametrize("keys", [{"keys": []}, {"keys": [{}]}, {"keys": [{"kty": "oct"}]}, {}])
def test_invalid_jwks_fails_closed(auth_settings, signed, keys):
    with pytest.raises(AuthError) as error:
        AccessVerifier(auth_settings, fetch=lambda _: keys).verify(signed())
    assert error.value.status == 503


def test_encryption_binds_row_and_purpose_and_supports_key_rotation(auth_settings):
    old = TokenVault(auth_settings.auth_encryption_keys)
    encrypted = old.seal("private-refresh-sentinel", "one:refresh")
    assert b"private-refresh-sentinel" not in encrypted
    fresh = SecretStr(base64.urlsafe_b64encode(bytes(range(31, -1, -1))).decode())
    rotated = TokenVault([fresh, *auth_settings.auth_encryption_keys])
    assert rotated.open(encrypted, "one:refresh") == "private-refresh-sentinel"
    for context, value in [
        ("two:refresh", encrypted),
        ("one:access", encrypted),
        ("one:refresh", encrypted[:-1] + bytes([encrypted[-1] ^ 1])),
    ]:
        with pytest.raises(AuthError):
            rotated.open(value, context)


@pytest.mark.parametrize(
    "value", ["x" * 14, "x" * 129, "four separate words here", "x" * 15 + "\t", "\n" + "x" * 15]
)
def test_password_bounds_and_provider_whitespace_limit(value):
    with pytest.raises(AuthError):
        validate_password(value)


def test_passphrases_need_no_character_mix_and_are_not_trimmed():
    assert validate_password("four-long-simple-words") == "four-long-simple-words"
    assert validate_password("字" * 15) == "字" * 15
    assert validate_password("x" * 128) == "x" * 128


def test_opaque_handles_and_session_bound_csrf():
    handle, other = new_handle(), new_handle()
    assert len(handle) == 43 and len(handle_hash(handle)) == 64
    require_csrf(handle, csrf_token(handle))
    for supplied in [None, "é", csrf_token(other), "0" * 64]:
        with pytest.raises(AuthError):
            require_csrf(handle, supplied)
    with pytest.raises(AuthError):
        handle_hash("user-owner")


@pytest.mark.parametrize(
    "change",
    [
        {"cognito_pool_id": "us-east-1_Other"},
        {"cognito_client_secret": None},
        {"auth_encryption_keys": []},
        {"auth_encryption_keys": ["broken-key"]},
        {"auth_origins": []},
        {"auth_origins": ["https://staff.example/path"]},
        {"auth_origins": ["https://*.example"]},
        {"auth_origins": ["http://staff.example"]},
        {"auth_origins": ["https://user:password@staff.example"]},
    ],
)
def test_auth_configuration_rejects_unsafe_inputs(auth_settings, change):
    with pytest.raises(ValidationError):
        Settings(**{**auth_settings.model_dump(), **change})


def test_deployed_cookie_requires_secure_and_secrets_are_masked(auth_settings):
    values = {
        **auth_settings.model_dump(),
        "environment": "production",
        "allowed_hosts": ["api.example"],
        "database_url": "postgresql+psycopg://u:p@db/app?sslmode=verify-full",
    }
    with pytest.raises(ValidationError):
        Settings(**{**values, "auth_cookie_secure": False})
    configured = Settings(**values)
    assert configured.session_cookie == "__Host-fitfinity-session"
    assert "unit_test_client_secret_value" not in repr(configured)


def test_cognito_password_challenge_and_rotating_refresh_parameters(sdk):
    state = "provider-session-1234567890"
    with Stubber(sdk.client) as stub:
        stub.add_response(
            "initiate_auth",
            {"ChallengeName": "SOFTWARE_TOKEN_MFA", "Session": state},
            {
                "ClientId": sdk.client_id,
                "AuthFlow": "USER_PASSWORD_AUTH",
                "AuthParameters": {
                    "USERNAME": "canonical-name",
                    "PASSWORD": "password-value",
                    "SECRET_HASH": sdk._hash("canonical-name"),
                },
            },
        )
        assert (
            sdk.begin("canonical-name", "password-value")["ChallengeName"] == "SOFTWARE_TOKEN_MFA"
        )
        stub.add_response(
            "respond_to_auth_challenge",
            {},
            {
                "ClientId": sdk.client_id,
                "ChallengeName": "SOFTWARE_TOKEN_MFA",
                "Session": state,
                "ChallengeResponses": {
                    "USERNAME": "canonical-name",
                    "SECRET_HASH": sdk._hash("canonical-name"),
                    "SOFTWARE_TOKEN_MFA_CODE": "123456",
                },
            },
        )
        sdk.answer("canonical-name", "SOFTWARE_TOKEN_MFA", state, "123456")
        stub.add_response(
            "get_tokens_from_refresh_token",
            {},
            {
                "ClientId": sdk.client_id,
                "ClientSecret": "unit_test_client_secret_value",
                "RefreshToken": "rotating-refresh",
            },
        )
        sdk.refresh("rotating-refresh")
        stub.assert_no_pending_responses()
    assert sdk.client.meta.config.retries["total_max_attempts"] == 1


@pytest.mark.parametrize(
    "provider_error,status",
    [
        ("NotAuthorizedException", 401),
        ("CodeMismatchException", 400),
        ("TooManyRequestsException", 429),
        ("InternalErrorException", 503),
    ],
)
def test_provider_errors_never_echo_secrets(sdk, provider_error, status):
    with Stubber(sdk.client) as stub:
        stub.add_client_error(
            "get_user",
            service_error_code=provider_error,
            service_message="private-provider-sentinel",
        )
        with pytest.raises(AuthError) as error:
            sdk.user("private-access-sentinel")
    assert error.value.status == status
    assert "sentinel" not in str(error.value)


@pytest.mark.parametrize(
    "headers,body,status",
    [
        ({}, {}, 403),
        ({"Origin": "https://evil.example"}, {}, 403),
        ({"Origin": "null"}, {}, 403),
        ({"Origin": "https://staff.example", "Content-Type": "text/plain"}, {}, 415),
        (
            {"Origin": "https://staff.example"},
            {"email": "owner@example", "password": "private-input", "role": "owner"},
            422,
        ),
    ],
)
def test_http_rejects_unsafe_auth_requests_before_provider(auth_settings, headers, body, status):
    with TestClient(create_app(auth_settings)) as client:
        response = client.post("/auth/sign-in", json=body, headers=headers)
    assert response.status_code == status
    assert "private-input" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_deployed_readiness_fails_when_auth_is_disabled(settings):
    configured = settings.model_copy(update={"environment": "production"})
    with TestClient(create_app(configured)) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503


def test_http_body_limit_bearer_rejection_and_cors(auth_settings):
    with TestClient(create_app(auth_settings)) as client:
        large = client.post(
            "/auth/sign-in",
            content='"' + "x" * 17000 + '"',
            headers={"Origin": "https://staff.example", "Content-Type": "application/json"},
        )
        forged = client.get("/me", headers={"Authorization": "Bearer forged-owner"})
        allowed = client.get("/auth/policy", headers={"Origin": "https://staff.example"})
        denied = client.options(
            "/auth/sign-in",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
        )
    assert large.status_code == 413
    assert forged.status_code == 401
    assert allowed.headers["access-control-allow-origin"] == "https://staff.example"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert denied.status_code == 400


def test_http_cookie_security_and_csrf(auth_settings):
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace

    app = create_app(auth_settings)
    handle = new_handle()
    with TestClient(app, base_url="https://testserver") as client:
        original = app.state.auth
        app.state.auth = SimpleNamespace(
            provider=original.provider,
            sign_in=lambda *_: AuthResult(
                {
                    "challenge": "SOFTWARE_TOKEN_MFA",
                    "expiresAt": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                },
                flow_handle=handle,
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            ),
            challenge=lambda *_args, **_kwargs: AuthResult(
                {
                    "user": {
                        "id": "11111111-1111-4111-8111-111111111111",
                        "name": "Test owner",
                        "email": "owner@example.test",
                        "role": "owner",
                        "trainerId": None,
                    },
                    "csrfToken": csrf_token(handle),
                    "expiresAt": (datetime.now(UTC) + timedelta(hours=8)).isoformat(),
                },
                session_handle=handle,
                expires_at=datetime.now(UTC) + timedelta(hours=8),
            ),
            sign_out=lambda *_: AuthResult({"signedOut": True}),
        )
        response = client.post(
            "/auth/sign-in",
            headers={"Origin": "https://staff.example"},
            json={"email": "owner@example", "password": "private-password"},
        )
        assert response.status_code == 200 and response.json()["challenge"] == "SOFTWARE_TOKEN_MFA"
        response = client.post(
            "/auth/challenge", headers={"Origin": "https://staff.example"}, json={"code": "123456"}
        )
        assert response.status_code == 200
        assert handle not in response.text
        cookie = response.headers["set-cookie"]
        for attribute in [
            "__Host-fitfinity-session=",
            "HttpOnly",
            "Secure",
            "SameSite=lax",
            "Path=/",
            "Max-Age=",
        ]:
            assert attribute in cookie
        assert "Domain=" not in cookie
        assert (
            client.post(
                "/auth/sign-out", json={}, headers={"Origin": "https://staff.example"}
            ).status_code
            == 403
        )
        signed_out = client.post(
            "/auth/sign-out",
            json={},
            headers={"Origin": "https://staff.example", "X-CSRF-Token": csrf_token(handle)},
        )
        assert signed_out.status_code == 200 and signed_out.json()["signedOut"]
        assert "set-cookie" not in signed_out.headers


def test_duplicate_security_headers_are_rejected(auth_settings):
    with TestClient(create_app(auth_settings)) as client:
        response = client.post(
            "/auth/sign-in",
            json={},
            headers=[("Origin", "https://staff.example"), ("Origin", "https://evil.example")],
        )
    assert response.status_code == 400


def test_reviewed_template_keeps_staff_pool_private_and_mfa_required():
    template = json.loads((Path(__file__).parents[1] / "infrastructure/cognito.json").read_text())
    pool = template["Resources"]["StaffPool"]["Properties"]
    client = template["Resources"]["StaffClient"]["Properties"]
    # Cognito refresh-token rotation requires Essentials or Plus.
    assert pool["UserPoolTier"] == "ESSENTIALS"
    assert pool["MfaConfiguration"] == "ON"
    assert pool["EnabledMfas"] == ["SOFTWARE_TOKEN_MFA"]
    assert "DeviceConfiguration" not in pool
    assert pool["AdminCreateUserConfig"]["AllowAdminCreateUserOnly"] is True
    assert client["GenerateSecret"] is True
    assert client["WriteAttributes"] == ["email", "name"]
    assert pool["UserAttributeUpdateSettings"] == {
        "AttributesRequireVerificationBeforeUpdate": ["email"]
    }
    assert client["RefreshTokenRotation"] == {"Feature": "ENABLED", "RetryGracePeriodSeconds": 0}
    assert set(template["Outputs"]) == {"PoolId", "ClientId"}


def test_cognito_mfa_setup_password_and_recovery_operations(sdk):
    state = "provider-session-1234567890"
    with Stubber(sdk.client) as stub:
        stub.add_response(
            "associate_software_token",
            {"Session": state, "SecretCode": "ABCDEFGHIJKLMNOP234567"},
            {"Session": state},
        )
        assert sdk.associate(state)["SecretCode"]
        stub.add_response(
            "verify_software_token",
            {"Session": state, "Status": "SUCCESS"},
            {"Session": state, "UserCode": "123456"},
        )
        assert sdk.verify_totp(state, "123456") == state
        stub.add_response(
            "respond_to_auth_challenge",
            {},
            {
                "ClientId": sdk.client_id,
                "Session": state,
                "ChallengeName": "MFA_SETUP",
                "ChallengeResponses": {"USERNAME": "user", "SECRET_HASH": sdk._hash("user")},
            },
        )
        sdk.answer("user", "MFA_SETUP", state, "123456")
        stub.add_response(
            "change_password",
            {},
            {
                "AccessToken": "test-access",
                "PreviousPassword": "current",
                "ProposedPassword": "long-new-passphrase",
            },
        )
        sdk.change_password("test-access", "current", "long-new-passphrase")
        stub.add_response(
            "forgot_password",
            {},
            {"ClientId": sdk.client_id, "Username": "user", "SecretHash": sdk._hash("user")},
        )
        sdk.forgot("user")
        stub.add_response(
            "confirm_forgot_password",
            {},
            {
                "ClientId": sdk.client_id,
                "Username": "user",
                "SecretHash": sdk._hash("user"),
                "ConfirmationCode": "123456",
                "Password": "long-new-passphrase",
            },
        )
        sdk.reset("user", "123456", "long-new-passphrase")
        stub.add_response(
            "revoke_token",
            {},
            {
                "ClientId": sdk.client_id,
                "ClientSecret": "unit_test_client_secret_value",
                "Token": "test-refresh",
            },
        )
        sdk.revoke("test-refresh")
        stub.assert_no_pending_responses()


def test_remote_configuration_audit_rejects_weaker_mfa_or_refresh_policy(auth_settings):
    from types import SimpleNamespace

    from app.auth.admin import check_configuration

    template = json.loads((Path(__file__).parents[1] / "infrastructure/cognito.json").read_text())
    pool = template["Resources"]["StaffPool"]["Properties"]
    app = {
        **template["Resources"]["StaffClient"]["Properties"],
        "ClientSecret": "unit_test_client_secret_value",
        "RefreshTokenValidity": 8,
    }
    mfa = {"MfaConfiguration": "ON", "SoftwareTokenMfaConfiguration": {"Enabled": True}}
    remote = SimpleNamespace(
        describe_user_pool=lambda **_: {"UserPool": pool},
        describe_user_pool_client=lambda **_: {"UserPoolClient": app},
        get_user_pool_mfa_config=lambda **_: mfa,
    )
    assert check_configuration(auth_settings, remote) == 18
    mfa["MfaConfiguration"] = "OPTIONAL"
    with pytest.raises(ValueError, match="required authenticator MFA"):
        check_configuration(auth_settings, remote)
    mfa["MfaConfiguration"] = "ON"
    app["RefreshTokenRotation"]["Feature"] = "DISABLED"
    with pytest.raises(ValueError, match="refresh rotation"):
        check_configuration(auth_settings, remote)
    app["RefreshTokenRotation"]["Feature"] = "ENABLED"
    app["WriteAttributes"] = ["email", "name", "email_verified"]
    with pytest.raises(ValueError, match="limited writable attributes"):
        check_configuration(auth_settings, remote)
    app["WriteAttributes"] = ["name", "email"]
    assert check_configuration(auth_settings, remote) == 18
    pool["UserAttributeUpdateSettings"] = {}
    with pytest.raises(ValueError, match="verify email changes"):
        check_configuration(auth_settings, remote)


def test_auth_gateway_prefix_and_error_logs_hide_credentials(auth_settings):
    import io
    import logging

    from app.observability import JsonFormatter

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("fitfinity")
    logger.addHandler(handler)
    try:
        app = create_app(auth_settings.model_copy(update={"root_path": "/staff-api"}))
        with TestClient(app) as client:
            policy = client.get("/staff-api/auth/policy")
            rejected = client.post(
                "/staff-api/auth/sign-in",
                json={"password": "password-sentinel", "code": "otp-sentinel"},
                headers={"Origin": "https://staff.example", "Cookie": "private-cookie-sentinel"},
            )
        assert policy.status_code == 200 and rejected.status_code == 422
        assert all(
            value not in stream.getvalue() + rejected.text
            for value in ["password-sentinel", "otp-sentinel", "private-cookie-sentinel"]
        )
    finally:
        logger.removeHandler(handler)


@pytest.mark.parametrize("path", ["/me", "/auth/session", "/auth/refresh"])
def test_late_expiry_cannot_delete_a_new_login_cookie(auth_settings, path):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import UTC, datetime, timedelta
    from threading import Event
    from types import SimpleNamespace

    app = create_app(auth_settings)
    old_handle, fresh_handle, flow_handle = new_handle(), new_handle(), new_handle()
    started, release = Event(), Event()
    expires = datetime.now(UTC) + timedelta(hours=8)
    body = {
        "user": {
            "id": "11111111-1111-4111-8111-111111111111",
            "name": "Current owner",
            "email": "owner@example.test",
            "role": "owner",
            "trainerId": None,
        },
        "csrfToken": csrf_token(fresh_handle),
        "expiresAt": expires.isoformat(),
        "accessExpiresAt": expires.isoformat(),
    }

    def read(handle):
        if handle == old_handle:
            started.set()
            assert release.wait(5), "New login was not completed before releasing the old request"
            raise AuthError("SESSION_EXPIRED", "Your session has ended. Sign in again.")
        assert handle == fresh_handle
        return AuthResult(body)

    with TestClient(app, base_url="https://testserver") as client:
        original = app.state.auth
        app.state.auth = SimpleNamespace(
            provider=original.provider,
            me=read,
            bootstrap=read,
            refresh=read,
            challenge=lambda *_args, **_kwargs: AuthResult(
                {key: value for key, value in body.items() if key != "accessExpiresAt"},
                session_handle=fresh_handle,
                expires_at=expires,
            ),
        )
        client.cookies.set(
            auth_settings.session_cookie, old_handle, domain="testserver.local", path="/"
        )
        client.cookies.set(
            auth_settings.flow_cookie, flow_handle, domain="testserver.local", path="/"
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(
                client.post if path == "/auth/refresh" else client.get,
                path,
                **(
                    {
                        "json": {},
                        "headers": {
                            "Origin": "https://staff.example",
                            "X-CSRF-Token": csrf_token(old_handle),
                        },
                    }
                    if path == "/auth/refresh"
                    else {}
                ),
            )
            try:
                assert started.wait(5), "Old request did not reach the authentication boundary"
                signed_in = client.post(
                    "/auth/challenge",
                    headers={"Origin": "https://staff.example"},
                    json={"code": "123456"},
                )
                assert signed_in.status_code == 200
                assert client.cookies.get(auth_settings.session_cookie) == fresh_handle
            finally:
                release.set()
            expired = pending.result(timeout=5)
        assert expired.status_code == 401
        assert expired.json()["error"]["code"] == "SESSION_EXPIRED"
        assert expired.json()["error"]["requestId"]
        assert expired.headers["cache-control"] == "no-store"
        assert "set-cookie" not in expired.headers
        assert client.cookies.get(auth_settings.session_cookie) == fresh_handle
        assert client.get("/me").json()["user"]["name"] == "Current owner"


@pytest.mark.parametrize(
    "path", ["/auth/sign-out", "/auth/change-password", "/auth/reset-password"]
)
def test_late_successful_session_end_preserves_new_login_and_flow(auth_settings, path):
    from concurrent.futures import ThreadPoolExecutor
    from contextlib import contextmanager
    from datetime import UTC, datetime, timedelta
    from threading import Event
    from types import SimpleNamespace

    from app.auth.service import AuthService

    app = create_app(auth_settings)
    old_handle, fresh_handle, flow_handle = new_handle(), new_handle(), new_handle()
    started, release = Event(), Event()
    expires = datetime.now(UTC) + timedelta(hours=8)
    body = {
        "user": {
            "id": "11111111-1111-4111-8111-111111111111",
            "name": "Current owner",
            "email": "owner@example.test",
            "role": "owner",
            "trainerId": None,
        },
        "csrfToken": csrf_token(fresh_handle),
        "expiresAt": expires.isoformat(),
        "accessExpiresAt": expires.isoformat(),
    }

    @contextmanager
    def absent_session():
        yield SimpleNamespace(scalar=lambda _query: None)

    def read(handle):
        if handle in {old_handle, flow_handle}:
            started.set()
            assert release.wait(5), "New login was not completed before releasing the old request"
            # Use the real idempotent logout result (already-revoked handle), including
            # its cookie contract. PostgreSQL cases separately prove durable revocation.
            result = AuthService.sign_out(
                SimpleNamespace(db=SimpleNamespace(transaction=absent_session)), old_handle
            )
            if path == "/auth/change-password":
                result.body["passwordChanged"] = True
            elif path == "/auth/reset-password":
                result.body["passwordReset"] = True
            return result
        assert handle == fresh_handle
        return AuthResult(body)

    with TestClient(app, base_url="https://testserver") as client:
        original = app.state.auth
        app.state.auth = SimpleNamespace(
            provider=original.provider,
            me=read,
            bootstrap=read,
            refresh=read,
            sign_out=lambda handle, everywhere: read(handle),
            change_password=lambda handle, *_: read(handle),
            reset_password=lambda handle, *_: read(handle),
            challenge=lambda *_args, **_kwargs: AuthResult(
                {key: value for key, value in body.items() if key != "accessExpiresAt"},
                session_handle=fresh_handle,
                expires_at=expires,
            ),
        )
        client.cookies.set(
            auth_settings.session_cookie, old_handle, domain="testserver.local", path="/"
        )
        client.cookies.set(
            auth_settings.flow_cookie, flow_handle, domain="testserver.local", path="/"
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(
                client.post,
                path,
                json={"currentPassword": "old-password", "newPassword": "replacement-passphrase"}
                if path == "/auth/change-password"
                else {"code": "123456", "newPassword": "replacement-passphrase"}
                if path == "/auth/reset-password"
                else {},
                headers={"Origin": "https://staff.example", "X-CSRF-Token": csrf_token(old_handle)},
            )
            try:
                assert started.wait(5), "Old request did not reach the authentication boundary"
                fresh_flow = new_handle()
                client.cookies.set(
                    auth_settings.flow_cookie, fresh_flow, domain="testserver.local", path="/"
                )
                signed_in = client.post(
                    "/auth/challenge",
                    headers={"Origin": "https://staff.example"},
                    json={"code": "123456"},
                )
                assert signed_in.status_code == 200
                assert client.cookies.get(auth_settings.session_cookie) == fresh_handle
            finally:
                release.set()
            expired = pending.result(timeout=5)
        assert expired.status_code == 200
        assert expired.json()["signedOut"] is True
        assert expired.headers["cache-control"] == "no-store"
        assert "set-cookie" not in expired.headers
        assert client.cookies.get(auth_settings.session_cookie) == fresh_handle
        assert client.cookies.get(auth_settings.flow_cookie) == fresh_flow
        assert client.get("/me").json()["user"]["name"] == "Current owner"
