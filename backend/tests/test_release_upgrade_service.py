"""Verify private migration intent, expiry, credential and sanitized-response boundaries."""

import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app import release_upgrade_service as service
from app.main import create_app
from app.release_upgrade import UpgradeRefused

START = "20260924_0006"
END = "20261101_0052"
IDENTITY = dict(operation_id="a" * 32, source_sha="b" * 40, from_revision=START, to_revision=END)
INTENT = json.dumps(
    {"operation": "upgrade-existing", "operation_id": "a" * 32}, separators=(",", ":")
).encode()


def configure(monkeypatch):
    for key, value in {
        "CONFIG_SOURCE": "aws-secrets-manager",
        "DB_NAME": "fitfinity",
        "UPGRADE_OPERATION_ID": "a" * 32,
        "UPGRADE_SOURCE_SHA": "b" * 40,
        "UPGRADE_FROM": START,
        "UPGRADE_TO": END,
        "UPGRADE_EXPIRES_AT": "200",
    }.items():
        monkeypatch.setenv("FITFINITY_" + key, value)


def test_private_upgrade_binds_success_and_recovery_receipts():
    apply = Mock(
        side_effect=[
            {"outcome": "upgraded", "schema": END},
            {"outcome": "already_at_target", "schema": END},
        ]
    )
    with TestClient(service.create_upgrade(apply, **IDENTITY)) as client:
        assert client.get("/health/live").status_code == 200
        apply.assert_not_called()
        for outcome in ("upgraded", "already_at_target"):
            response = client.post("/events", content=INTENT)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            assert response.json() == {
                "operation_id": "a" * 32,
                "source_sha": "b" * 40,
                "from_revision": START,
                "outcome": outcome,
                "schema": END,
            }
        assert apply.call_count == 2
        assert client.get("/events").status_code == 405
        assert client.get("/docs").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        b"{}",
        INTENT.replace(b"a" * 32, b"c" * 32),
        INTENT[:-1] + b',"sql":"DROP TABLE staff_users"}',
        b"x" * 1000,
    ],
)
def test_unreviewed_upgrade_payload_never_reaches_credentials_or_database(body):
    apply = Mock()
    with TestClient(service.create_upgrade(apply, **IDENTITY)) as client:
        assert client.post("/events", content=body).status_code == 400
    apply.assert_not_called()


def test_refusal_unknown_error_and_invalid_receipt_are_sanitized():
    for result, status, code in [
        (UpgradeRefused("private database identity"), 409, "migration_refused"),
        (RuntimeError("password customer SQL"), 503, "migration_failed_or_uncertain"),
        (
            {"outcome": "upgraded", "schema": "foreign", "secret": "password"},
            503,
            "migration_failed_or_uncertain",
        ),
    ]:
        apply = (
            Mock(side_effect=result) if isinstance(result, Exception) else Mock(return_value=result)
        )
        with TestClient(service.create_upgrade(apply, **IDENTITY)) as client:
            response = client.post("/events", content=INTENT)
            assert response.status_code == status
            assert response.headers["cache-control"] == "no-store"
            assert response.json() == {"error": code}


def test_expiry_before_or_during_credential_fetch_prevents_database_access(monkeypatch):
    configure(monkeypatch)
    credentials = Mock(return_value={"database_url": SecretStr("synthetic")})
    engine = Mock()
    monkeypatch.setattr(service, "managed_values", credentials)
    monkeypatch.setattr(service, "create_engine", engine)
    for expiry, times, expected_calls in [(200, [200], 0), (200, [199, 200], 1), (5000, [100], 0)]:
        monkeypatch.setenv("FITFINITY_UPGRADE_EXPIRES_AT", str(expiry))
        credentials.reset_mock()
        monkeypatch.setattr(service.time, "time", Mock(side_effect=times))
        with TestClient(service.create_app()) as client:
            assert client.post("/events", content=INTENT).status_code == 409
        assert credentials.call_count == expected_calls
        engine.assert_not_called()


def test_managed_factory_uses_only_migrator_and_always_disposes_engine(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(service.time, "time", lambda: 100)
    credentials = Mock(return_value={"database_url": SecretStr("synthetic")})
    engine = Mock()
    create = Mock(return_value=engine)
    apply = Mock(side_effect=RuntimeError("uncertain outcome"))
    monkeypatch.setattr(service, "managed_values", credentials)
    monkeypatch.setattr(service, "create_engine", create)
    monkeypatch.setattr(service, "upgrade_existing", apply)
    with TestClient(service.create_app()) as client:
        assert client.post("/events", content=INTENT).status_code == 503
    credentials.assert_called_once_with("migration")
    assert create.call_args.kwargs["hide_parameters"] is True
    assert create.call_args.kwargs["connect_args"] == {"connect_timeout": 5}
    apply.assert_called_once_with(
        engine,
        expected_database="fitfinity",
        expected_user="fitfinity_migrator",
        from_revision=START,
        to_revision=END,
        deadline=200,
        runtime_role="fitfinity_app",
    )
    engine.dispose.assert_called_once_with()


def test_missing_configuration_and_staff_routes_never_expose_upgrade(monkeypatch, settings):
    configure(monkeypatch)
    monkeypatch.setenv("FITFINITY_CONFIG_SOURCE", "direct")
    with pytest.raises(UpgradeRefused):
        service.create_app()
    monkeypatch.setenv("FITFINITY_CONFIG_SOURCE", "aws-secrets-manager")
    for key in (
        "DB_NAME",
        "UPGRADE_OPERATION_ID",
        "UPGRADE_SOURCE_SHA",
        "UPGRADE_FROM",
        "UPGRADE_TO",
        "UPGRADE_EXPIRES_AT",
    ):
        with monkeypatch.context() as context:
            context.delenv("FITFINITY_" + key)
            with pytest.raises(UpgradeRefused):
                service.create_app()
    assert "/events" not in {route.path for route in create_app(settings).routes}
