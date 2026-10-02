"""Startup credentials fail closed without AWS calls or a real database in these tests."""

import base64
import json
import os
import traceback
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError
from cryptography import x509
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from app.config import load_settings
from app.main import create_app
from app.managed_secrets import ConfigurationError

DB_ARN = "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:fitfinity/db-abcdef"
AUTH_ARN = "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:fitfinity/auth-abcdef"
HOST = "fitfinity-test-db.example.ap-southeast-1.rds.amazonaws.com"
PASSWORD = "synthetic-password:/@%?#&+" + "x" * 32
CLIENT_SECRET = "synthetic_client_secret_" + "x" * 20
KEY = base64.urlsafe_b64encode(bytes(range(32))).decode()


@pytest.fixture
def managed(monkeypatch):
    for name in list(os.environ):
        if name.upper().startswith("FITFINITY_"):
            monkeypatch.delenv(name)
    for name, value in {
        "CONFIG_SOURCE": "aws-secrets-manager",
        "ENVIRONMENT": "staging",
        "AWS_ACCOUNT_ID": "123456789012",
        "DATABASE_SECRET_ARN": DB_ARN,
        "AUTH_SECRET_ARN": AUTH_ARN,
        "DB_HOST": HOST,
        "ALLOWED_HOSTS": '["testserver"]',
        "AUTH_ENABLED": "true",
        "AUTH_ORIGINS": '["https://staff.example"]',
        "COGNITO_POOL_ID": "ap-southeast-1_Example",
        "COGNITO_CLIENT_ID": "exampleclient",
    }.items():
        monkeypatch.setenv("FITFINITY_" + name, value)
    bodies = {
        DB_ARN: {"username": "fitfinity_app", "password": PASSWORD},
        AUTH_ARN: {
            "cognito_pool_id": "ap-southeast-1_Example",
            "cognito_client_id": "exampleclient",
            "cognito_client_secret": CLIENT_SECRET,
            "auth_encryption_keys": [KEY],
        },
    }
    client = Mock()
    client.get_secret_value.side_effect = lambda **params: {
        "ARN": params["SecretId"],
        "VersionStages": ["AWSCURRENT"],
        "SecretString": json.dumps(bodies[params["SecretId"]]),
    }
    factory = Mock(return_value=client)
    monkeypatch.setattr("app.managed_secrets.boto3.client", factory)
    return bodies, client, factory


def test_runtime_reads_current_secrets_once_and_preserves_password_characters(managed):
    _, client, factory = managed
    settings = load_settings()
    url = make_url(settings.database_url.get_secret_value())
    assert (url.username, url.password, url.host, url.port, url.database) == (
        "fitfinity_app",
        PASSWORD,
        HOST,
        5432,
        "fitfinity",
    )
    assert url.query["sslmode"] == "verify-full"
    assert Path(url.query["sslrootcert"]).is_file()
    assert settings.auth_encryption_keys[0].get_secret_value() == KEY
    assert settings.cognito_client_secret.get_secret_value() == CLIENT_SECRET
    assert client.get_secret_value.call_args_list == [
        ((), {"SecretId": DB_ARN, "VersionStage": "AWSCURRENT"}),
        ((), {"SecretId": AUTH_ARN, "VersionStage": "AWSCURRENT"}),
    ]
    client.close.assert_called_once_with()
    options = factory.call_args.kwargs
    assert options["verify"] is True
    assert options["endpoint_url"] == "https://secretsmanager.ap-southeast-1.amazonaws.com"
    assert options["config"].connect_timeout == 2
    assert options["config"].read_timeout == 3
    assert options["config"].retries["total_max_attempts"] == 2
    for secret in [PASSWORD, CLIENT_SECRET, KEY]:
        assert secret not in repr(settings)
        assert secret not in settings.model_dump_json()
    with TestClient(create_app(settings)) as browser:
        assert browser.get("/health/live").status_code == 200
        assert browser.get("/health/live").status_code == 200
    assert client.get_secret_value.call_count == 2


def test_migration_loads_only_migration_credentials_without_auth_permissions(managed, monkeypatch):
    bodies, client, _ = managed
    bodies[DB_ARN]["username"] = "fitfinity_migrator"
    # Migration deliberately ignores runtime auth configuration and needs no auth secret IAM grant.
    monkeypatch.delenv("FITFINITY_AUTH_SECRET_ARN")
    settings = load_settings(purpose="migration")
    assert make_url(settings.database_url.get_secret_value()).username == "fitfinity_migrator"
    assert settings.auth_enabled is False
    assert settings.cognito_client_secret is None
    assert settings.auth_encryption_keys == []
    client.get_secret_value.assert_called_once_with(SecretId=DB_ARN, VersionStage="AWSCURRENT")


@pytest.mark.parametrize(
    "purpose,username",
    [
        ("runtime", "postgres"),
        ("runtime", "fitfinity_migrator"),
        ("migration", "fitfinity_app"),
        ("migration", "fitfinity_admin"),
    ],
)
def test_admin_and_wrong_purpose_credentials_are_rejected(managed, purpose, username):
    bodies, client, _ = managed
    bodies[DB_ARN]["username"] = username
    with pytest.raises(ConfigurationError, match="restricted credential purpose"):
        load_settings(purpose=purpose)
    assert client.get_secret_value.call_count == 1
    client.close.assert_called_once_with()


@pytest.mark.parametrize(
    "name,value",
    [
        ("ENVIRONMENT", "test"),
        ("AWS_ACCOUNT_ID", "unknown"),
        ("DATABASE_SECRET_ARN", DB_ARN.replace("123456789012", "111111111111")),
        ("DATABASE_SECRET_ARN", DB_ARN.replace("ap-southeast-1", "us-east-1")),
        ("DATABASE_SECRET_ARN", "fitfinity/db"),
        ("AUTH_SECRET_ARN", DB_ARN),
        ("AUTH_ENABLED", "false"),
        ("DB_HOST", "127.0.0.1"),
        ("DB_HOST", HOST + "/?sslmode=disable"),
        ("DB_NAME", "fitfinity?sslmode=disable"),
        ("COGNITO_CLIENT_ID", ""),
        ("DATABASE_URL", ""),
        ("COGNITO_CLIENT_SECRET", CLIENT_SECRET),
        ("AUTH_ENCRYPTION_KEYS", json.dumps([KEY])),
        ("SECRETS_DIR", "/tmp"),
        ("CONFIG_SOURCE", "direct"),
        ("CONFIG_SOURCE", "typo"),
    ],
)
def test_invalid_or_mixed_sources_stop_before_aws(managed, monkeypatch, name, value):
    _, _, factory = managed
    monkeypatch.setenv("FITFINITY_" + name, value)
    with pytest.raises(ConfigurationError):
        load_settings()
    factory.assert_not_called()


@pytest.mark.parametrize(
    "mutation", ["wrong_arn", "previous", "binary", "large", "duplicate", "extra"]
)
def test_untrusted_secret_responses_stop_without_returning_credentials(managed, mutation):
    bodies, client, _ = managed
    response = {
        "ARN": DB_ARN,
        "VersionStages": ["AWSCURRENT"],
        "SecretString": json.dumps(bodies[DB_ARN]),
    }
    if mutation == "wrong_arn":
        response["ARN"] = AUTH_ARN
    elif mutation == "previous":
        response["VersionStages"] = ["AWSPREVIOUS"]
    elif mutation == "binary":
        response["SecretBinary"] = b"unexpected"
    elif mutation == "large":
        response["SecretString"] = "x" * 65537
    elif mutation == "duplicate":
        response["SecretString"] = '{"username":"fitfinity_app","username":"postgres"}'
    else:
        response["SecretString"] = json.dumps({**bodies[DB_ARN], "sslmode": "disable"})
    client.get_secret_value.side_effect = None
    client.get_secret_value.return_value = response
    with pytest.raises(ConfigurationError):
        load_settings()
    client.close.assert_called_once_with()


@pytest.mark.parametrize(
    "failure", ["provider", "json", "password", "client", "key", "pool", "settings"]
)
def test_startup_errors_do_not_disclose_secret_values(managed, monkeypatch, failure, caplog):
    bodies, client, _ = managed
    sentinel = "private-value-must-not-appear"
    if failure == "provider":
        client.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": sentinel}}, "GetSecretValue"
        )
    elif failure == "json":
        client.get_secret_value.side_effect = None
        client.get_secret_value.return_value = {
            "ARN": DB_ARN,
            "VersionStages": ["AWSCURRENT"],
            "SecretString": sentinel,
        }
    elif failure == "password":
        bodies[DB_ARN]["password"] = sentinel + "\n"
    elif failure == "client":
        bodies[AUTH_ARN]["cognito_client_secret"] = "bad-" + sentinel
    elif failure == "key":
        bodies[AUTH_ARN]["auth_encryption_keys"] = [sentinel]
    elif failure == "pool":
        bodies[AUTH_ARN]["cognito_pool_id"] = sentinel
    else:
        monkeypatch.setenv("FITFINITY_AUTH_ORIGINS", '["http://untrusted.example"]')
    with pytest.raises(ConfigurationError) as error:
        load_settings()
    rendered = "".join(traceback.format_exception(error.value)) + caplog.text
    for private in [sentinel, PASSWORD, CLIENT_SECRET, KEY]:
        assert private not in rendered
    client.close.assert_called_once_with()


def test_ca_bundle_is_current_singapore_root_material(managed):
    settings = load_settings()
    path = make_url(settings.database_url.get_secret_value()).query["sslrootcert"]
    certificates = x509.load_pem_x509_certificates(Path(path).read_bytes())
    assert len(certificates) == 3
    for certificate in certificates:
        assert certificate.subject == certificate.issuer
        assert "ap-southeast-1" in certificate.subject.rfc4514_string()
        assert (
            certificate.not_valid_before_utc < datetime.now(UTC) < certificate.not_valid_after_utc
        )
        assert certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca


def test_changed_ca_bundle_stops_before_secret_access(managed, monkeypatch):
    _, _, factory = managed
    monkeypatch.setattr("app.managed_secrets.CA_SHA256", "0" * 64)
    with pytest.raises(ConfigurationError, match="CA bundle"):
        load_settings()
    factory.assert_not_called()


def test_fresh_startup_observes_updated_credentials_without_global_stale_cache(managed):
    bodies, client, _ = managed
    first = load_settings()
    bodies[DB_ARN]["password"] = "changed-synthetic-password" + "y" * 32
    second = load_settings()
    assert first.database_url != second.database_url
    assert client.get_secret_value.call_count == 4


def test_direct_local_configuration_never_initializes_aws(managed, monkeypatch):
    _, _, factory = managed
    for name in ["CONFIG_SOURCE", "DATABASE_SECRET_ARN", "AUTH_SECRET_ARN"]:
        monkeypatch.delenv("FITFINITY_" + name)
    monkeypatch.setenv("FITFINITY_ENVIRONMENT", "test")
    monkeypatch.setenv("FITFINITY_AUTH_ENABLED", "false")
    monkeypatch.setenv("FITFINITY_DATABASE_URL", "postgresql+psycopg://u:p@localhost/unit")
    settings = load_settings()
    assert make_url(settings.database_url.get_secret_value()).host == "localhost"
    factory.assert_not_called()
