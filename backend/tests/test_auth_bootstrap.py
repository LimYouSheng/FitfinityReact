"""Reload-safe CSRF recovery never substitutes for provider-verified authority."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.errors import AuthError
from app.auth.security import csrf_token, new_handle
from app.auth.service import AuthResult
from app.main import create_app
from app.models.authentication import AuthAccount, AuthSession
from app.models.people import StaffIdentity, StaffUser


def test_bootstrap_http_shape_no_store_and_credentialed_exact_origin(auth_settings):
    app = create_app(auth_settings)
    handle = new_handle()
    with TestClient(app, base_url="https://testserver") as client:
        app.state.auth = SimpleNamespace(
            provider=app.state.auth.provider,
            bootstrap=lambda supplied: AuthResult(
                {
                    "csrfToken": csrf_token(supplied),
                    "expiresAt": datetime.now(UTC) + timedelta(hours=1),
                }
            ),
        )
        client.cookies.set(auth_settings.session_cookie, handle)
        response = client.get("/auth/session", headers={"Origin": "https://staff.example"})
        assert response.status_code == 200
        assert set(response.json()) == {"csrfToken", "expiresAt"}
        assert response.json()["csrfToken"] == csrf_token(handle)
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["access-control-allow-origin"] == "https://staff.example"
        assert response.headers["access-control-allow-credentials"] == "true"
        denied = client.get("/auth/session", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in denied.headers


@pytest.mark.parametrize("header", [{}, {"Authorization": "Bearer forged"}])
def test_bootstrap_requires_real_cookie_and_rejects_bearer_substitution(auth_settings, header):
    with TestClient(create_app(auth_settings), base_url="https://testserver") as client:
        response = client.get("/auth/session", headers=header)
        assert response.status_code == 401
        assert set(response.json()) == {"error"}
        assert "csrfToken" not in response.text


@pytest.mark.database
def test_expired_access_bootstrap_permits_refresh_but_never_grants_principal(
    auth_service, login, fake_cognito
):
    result = login()
    with auth_service.db.transaction() as session:
        record = session.scalar(select(AuthSession))
        record.access_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    fake_cognito.calls.clear()
    bootstrap = auth_service.bootstrap(result.session_handle)
    assert set(bootstrap.body) == {"csrfToken", "expiresAt"}
    assert bootstrap.body["csrfToken"] == result.body["csrfToken"]
    assert fake_cognito.calls == []
    with pytest.raises(AuthError, match="Refresh your session"):
        auth_service.me(result.session_handle)
    auth_service.refresh(result.session_handle)
    assert auth_service.me(result.session_handle).body["user"] == result.body["user"]


@pytest.mark.database
@pytest.mark.parametrize("reason", ["closed", "absolute_expiry", "epoch", "inactive", "identity"])
def test_bootstrap_rejects_retired_or_inactive_sessions(auth_service, login, reason):
    result = login()
    with auth_service.db.transaction() as session:
        record = session.scalar(select(AuthSession))
        if reason == "closed":
            record.closed_at = datetime.now(UTC)
        elif reason == "absolute_expiry":
            auth_service.clock = lambda: datetime.now(UTC) + timedelta(hours=9)
        elif reason == "epoch":
            session.get(AuthAccount, record.user_id).epoch += 1
        elif reason == "inactive":
            session.get(StaffUser, record.user_id).status = "inactive"
        else:
            session.get(StaffIdentity, record.identity_id).status = "inactive"
    with pytest.raises(AuthError) as failure:
        auth_service.bootstrap(result.session_handle)
    assert failure.value.code == "SESSION_EXPIRED"
