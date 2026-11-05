"""Private probe request/expiry/error boundaries; provider access is substituted."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app import schema_probe
from app.main import create_app


def client(observer):
    return TestClient(schema_probe.create_probe(observer, source_sha="a" * 40, sql_sha256="b" * 64))


def test_private_probe_accepts_only_fixed_intent_and_binds_receipt():
    observer = Mock(return_value={"transaction_read_only": "on"})
    with client(observer) as browser:
        assert browser.get("/health/live").status_code == 200
        observer.assert_not_called()
        response = browser.post("/events", content=b'{"operation":"observe-schema"}')
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {
            "source_sha": "a" * 40,
            "sql_sha256": "b" * 64,
            "catalog": {"transaction_read_only": "on"},
        }
        observer.assert_called_once_with()


@pytest.mark.parametrize(
    "payload",
    [
        b"{}",
        b'{"operation":"observe-schema","sql":"DELETE FROM staff_users"}',
        b"x" * 65,
        b'{"operation":"observe-schema","operation":"other"}',
    ],
)
def test_private_probe_rejects_untrusted_payload_before_access(payload):
    observer = Mock()
    with client(observer) as browser:
        assert browser.post("/events", content=payload).status_code == 400
        assert browser.get("/events").status_code == 405
        assert browser.get("/docs").status_code == 404
        assert browser.post("/api/probe", content=payload).status_code == 404
    observer.assert_not_called()


def test_probe_failure_does_not_leak_provider_or_database_exception():
    with client(Mock(side_effect=RuntimeError("secret-password customer-marker"))) as browser:
        response = browser.post("/events", content=b'{"operation":"observe-schema"}')
        assert response.status_code == 503
        assert response.json() == {"error": "catalog_observation_failed"}
        assert "secret-password" not in response.text
        assert "customer-marker" not in response.text


def test_probe_routes_are_not_registered_in_staff_application(settings):
    app = create_app(settings)
    assert "/events" not in {route.path for route in app.routes}


def test_probe_requires_managed_mode_source_sql_and_expiry(monkeypatch):
    monkeypatch.setenv("FITFINITY_CONFIG_SOURCE", "direct")
    with pytest.raises(schema_probe.ObservationRefused):
        schema_probe.create_app()
    monkeypatch.setenv("FITFINITY_CONFIG_SOURCE", "aws-secrets-manager")
    monkeypatch.delenv("FITFINITY_PROBE_EXPIRES_AT", raising=False)
    with pytest.raises(schema_probe.ObservationRefused):
        schema_probe.create_app()
    for source, sql_hash in [("", "b" * 64), ("a" * 40, "")]:
        with pytest.raises(schema_probe.ObservationRefused):
            schema_probe.create_probe(Mock(), source_sha=source, sql_sha256=sql_hash)


def test_expired_probe_cannot_retrieve_credentials(monkeypatch):
    for key, value in {
        "CONFIG_SOURCE": "aws-secrets-manager",
        "PROBE_SOURCE_SHA": "a" * 40,
        "PROBE_SQL_SHA256": "b" * 64,
        "PROBE_EXPIRES_AT": "1",
    }.items():
        monkeypatch.setenv("FITFINITY_" + key, value)
    secrets = Mock()
    monkeypatch.setattr(schema_probe, "managed_values", secrets)
    with TestClient(schema_probe.create_app()) as browser:
        assert browser.post("/events", content=b'{"operation":"observe-schema"}').status_code == 503
    secrets.assert_not_called()
