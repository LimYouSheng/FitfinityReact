import io
import json
import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, load_settings
from app.main import create_app
from app.observability import JsonFormatter
from tests.conftest import test_control_url as control_url


def test_liveness_is_independent_of_database(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert response.headers["cache-control"] == "no-store"


def test_unavailable_database_returns_safe_503(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "not_ready"
    assert "unit" not in response.text
    assert response.json()["error"]["requestId"] == response.headers["x-request-id"]


@pytest.mark.parametrize(
    "method,path,status,code",
    [
        ("GET", "/missing", 404, "not_found"),
        ("POST", "/health/live", 405, "method_not_allowed"),
    ],
)
def test_http_error_contract(settings, method, path, status, code):
    with TestClient(create_app(settings)) as client:
        response = client.request(method, path)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["requestId"] == response.headers["x-request-id"]


def test_validation_and_internal_errors_do_not_expose_input(settings):
    app = create_app(settings)

    @app.get("/test-validation")
    def validation(value: int):
        return {"value": value}

    @app.get("/test-error")
    def failure():
        raise RuntimeError("private-password-sentinel")

    with TestClient(app) as client:
        invalid = client.get("/test-validation", params={"value": "private-password-sentinel"})
        failed = client.get("/test-error")
    assert invalid.status_code == 422
    assert failed.status_code == 500
    for response in (invalid, failed):
        assert "private-password-sentinel" not in response.text
        assert response.json()["error"]["requestId"] == response.headers["x-request-id"]


def test_request_ids_are_generated_per_request(settings):
    with TestClient(create_app(settings)) as client:
        one = client.get("/health/live", headers={"X-Request-ID": "attacker-controlled"})
        two = client.get("/health/live")
    assert len(one.headers["x-request-id"]) == 32
    assert one.headers["x-request-id"] != two.headers["x-request-id"]
    assert one.headers["x-request-id"] != "attacker-controlled"


def test_logs_use_routes_and_omit_sensitive_request_values(settings):
    logger = logging.getLogger("fitfinity")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    try:
        with TestClient(create_app(settings)) as client:
            client.get(
                "/secret-in-path?token=secret-in-query",
                headers={"Authorization": "Bearer secret-in-header"},
            )
    finally:
        logger.removeHandler(handler)
    log = stream.getvalue()
    assert all(
        secret not in log for secret in ["secret-in-path", "secret-in-query", "secret-in-header"]
    )
    event = next(json.loads(line) for line in log.splitlines() if "request_completed" in line)
    assert event["route"] == "unmatched"
    assert event["status"] == 404


def test_untrusted_host_rejected(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/live", headers={"Host": "unexpected.example"}).status_code == 400


def test_shutdown_disposes_database_pool(settings):
    app = create_app(settings)
    with TestClient(app):
        pool = app.state.database.engine.pool
    assert app.state.database.engine.pool is not pool


def test_disabled_auth_exposes_only_health_routes(settings):
    app = create_app(settings)
    assert {route.path for route in app.routes} == {"/health/live", "/health/ready"}


def test_gateway_root_path_preserves_health_routes(settings):
    app = create_app(settings.model_copy(update={"root_path": "/staff-api"}))
    with TestClient(app) as client:
        assert client.get("/staff-api/health/live").status_code == 200


@pytest.mark.parametrize(
    "change",
    [
        {"database_url": "sqlite:///unsafe.db"},
        {"db_pool_size": 0},
        {"db_statement_timeout_ms": 0},
        {"allowed_hosts": []},
        {"root_path": "bad-prefix"},
        {"environment": "production"},
    ],
)
def test_invalid_configuration_fails_closed(settings, change):
    with pytest.raises(ValidationError):
        Settings(**{**settings.model_dump(), **change})


def test_production_requires_tls_and_explicit_hosts():
    url = "postgresql+psycopg://app:secret@db.example/fitfinity?sslmode=verify-full"
    with pytest.raises(ValidationError):
        Settings(environment="production", database_url=url)
    with pytest.raises(ValidationError):
        Settings(environment="production", database_url=url, allowed_hosts=["*"])
    settings = Settings(environment="production", database_url=url, allowed_hosts=["api.example"])
    assert settings.environment == "production"
    assert "secret" not in repr(settings)


def test_validation_errors_hide_database_credentials():
    with pytest.raises(ValidationError) as result:
        Settings(database_url="postgresql+psycopg://user:private-password@db/app", db_pool_size=0)
    assert "private-password" not in str(result.value)


def test_mounted_secrets_load_and_environment_takes_precedence(tmp_path, monkeypatch):
    monkeypatch.delenv("FITFINITY_DATABASE_URL", raising=False)
    monkeypatch.setenv("FITFINITY_SECRETS_DIR", str(tmp_path))
    (tmp_path / "FITFINITY_DATABASE_URL").write_text("postgresql+psycopg://u:mounted@db/fitfinity")
    assert "mounted" in load_settings().database_url.get_secret_value()
    monkeypatch.setenv("FITFINITY_DATABASE_URL", "postgresql+psycopg://u:injected@db/fitfinity")
    assert "injected" in load_settings().database_url.get_secret_value()


@pytest.mark.parametrize(
    "value", [None, "sqlite:///test.db", "postgresql+psycopg://u:p@db/production"]
)
def test_database_harness_rejects_missing_or_live_database(value):
    with pytest.raises(ValueError):
        control_url(value)
