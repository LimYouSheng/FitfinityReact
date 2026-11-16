"""Load and validate AWS-managed configuration.

Only complete same-account, configured-region ARNs are accepted. IAM still owns authorization.
Secret changes require a reviewed restart/redeployment; this is not a rotation worker.
"""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Literal

import boto3
from botocore.config import Config
from pydantic import BaseModel, ConfigDict, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

CA_SHA256 = "90a6f1a7978a1b1b096dca6c57511ca48d3b8cf052f8e704baf358f34ea2f21b"
DatabasePurpose = Literal["runtime", "migration"]


class ConfigurationError(RuntimeError):
    """Configuration error without provider exceptions or secret values."""


class _References(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FITFINITY_", hide_input_in_errors=True)

    config_source: Literal["direct", "aws-secrets-manager"] = "direct"
    environment: str = "local"
    aws_account_id: str = ""
    aws_region: str = "ap-southeast-1"
    database_secret_arn: str = ""
    auth_secret_arn: str = ""
    db_host: str = ""
    db_name: str = "fitfinity"
    auth_enabled: bool = False
    cognito_pool_id: str = ""
    cognito_client_id: str = ""


class _DatabaseSecret(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    username: str
    password: SecretStr


class _AuthSecret(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    cognito_pool_id: str
    cognito_client_id: str
    cognito_client_secret: SecretStr
    auth_encryption_keys: list[SecretStr]


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate secret field")
        result[key] = value
    return result


def _read(client, arn, schema):
    try:
        response = client.get_secret_value(SecretId=arn, VersionStage="AWSCURRENT")
        value = response.get("SecretString")
        if (
            response.get("ARN") != arn
            or "AWSCURRENT" not in response.get("VersionStages", [])
            or "SecretBinary" in response
            or not isinstance(value, str)
            or not 1 <= len(value.encode()) <= 65536
        ):
            raise ValueError("Invalid secret response")
        return schema.model_validate(json.loads(value, object_pairs_hook=_unique_object))
    except Exception:
        raise ConfigurationError("Managed secret retrieval or validation failed") from None


def _validate_references(refs, purpose):
    if refs.environment not in {"staging", "production"}:
        raise ConfigurationError("AWS secrets require staging or production settings")
    if not re.fullmatch(r"[0-9]{12}", refs.aws_account_id):
        raise ConfigurationError("Configure the target AWS account ID")
    if not re.fullmatch(r"(?:af|ap|ca|eu|il|me|mx|sa|us)-[a-z]+-[1-9]", refs.aws_region):
        raise ConfigurationError("Configure the commercial AWS region")
    arn_pattern = (
        rf"arn:aws:secretsmanager:{refs.aws_region}:{refs.aws_account_id}:secret:"
        r"[A-Za-z0-9/_+=.@-]{1,512}-[A-Za-z0-9]{6}"
    )
    arns = [refs.database_secret_arn]
    if purpose == "runtime":
        if not refs.auth_enabled:
            raise ConfigurationError("AWS application startup requires staff authentication")
        arns.append(refs.auth_secret_arn)
    if any(not re.fullmatch(arn_pattern, arn) for arn in arns) or len(set(arns)) != len(arns):
        raise ConfigurationError("Configure distinct full secret ARNs in the target account/region")
    if not re.fullmatch(
        rf"[a-z0-9][a-z0-9-]{{0,62}}\.[a-z0-9]+\.{refs.aws_region}\.rds\.amazonaws\.com",
        refs.db_host,
    ) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,62}", refs.db_name):
        raise ConfigurationError(
            "Configure the private target-region RDS endpoint and database name"
        )
    if purpose == "runtime" and (
        not re.fullmatch(rf"{re.escape(refs.aws_region)}_[A-Za-z0-9]{{1,64}}", refs.cognito_pool_id)
        or not re.fullmatch(r"[A-Za-z0-9]{1,128}", refs.cognito_client_id)
    ):
        raise ConfigurationError("Configure the staff Cognito pool and client")
    # Fail on ambiguous sources, including empty variables. Do not silently override credentials.
    forbidden = {
        "FITFINITY_DATABASE_URL",
        "FITFINITY_COGNITO_CLIENT_SECRET",
        "FITFINITY_AUTH_ENCRYPTION_KEYS",
        "FITFINITY_SECRETS_DIR",
    }
    if forbidden.intersection(key.upper() for key in os.environ):
        raise ConfigurationError("AWS secret mode cannot mix direct or mounted credentials")


def managed_values(purpose: DatabasePurpose) -> dict:
    """Return validated secret settings, or no overrides for explicit direct mode."""
    if purpose not in {"runtime", "migration"}:
        raise ConfigurationError("Unknown database credential purpose")
    try:
        refs = _References()
    except Exception:
        raise ConfigurationError("Invalid managed-secret configuration") from None
    if refs.config_source == "direct":
        if refs.database_secret_arn or refs.auth_secret_arn:
            raise ConfigurationError("Secret ARNs require explicit aws-secrets-manager mode")
        return {}
    _validate_references(refs, purpose)
    ca_path = Path(__file__).with_name("certificates") / "global-bundle.pem"
    try:
        if hashlib.sha256(ca_path.read_bytes()).hexdigest() != CA_SHA256:
            raise ValueError("Changed CA material")
    except Exception:
        raise ConfigurationError("The reviewed RDS CA bundle is missing or changed") from None
    try:
        client = boto3.client(
            "secretsmanager",
            region_name=refs.aws_region,
            endpoint_url=f"https://secretsmanager.{refs.aws_region}.amazonaws.com",
            verify=True,
            config=Config(
                connect_timeout=2,
                read_timeout=3,
                retries={"total_max_attempts": 2, "mode": "standard"},
                max_pool_connections=2,
            ),
        )
    except Exception:
        raise ConfigurationError("Managed secret client initialization failed") from None
    try:
        database = _read(client, refs.database_secret_arn, _DatabaseSecret)
        expected_user = "fitfinity_app" if purpose == "runtime" else "fitfinity_migrator"
        password = database.password.get_secret_value()
        if (
            database.username != expected_user
            or not 32 <= len(password) <= 128
            or any(ord(char) < 32 or ord(char) == 127 for char in password)
        ):
            raise ConfigurationError("Database secret must match its restricted credential purpose")
        values = {
            "aws_region": refs.aws_region,
            "database_url": SecretStr(
                URL.create(
                    "postgresql+psycopg",
                    username=database.username,
                    password=password,
                    host=refs.db_host,
                    port=5432,
                    database=refs.db_name,
                    query={"sslmode": "verify-full", "sslrootcert": str(ca_path)},
                ).render_as_string(hide_password=False)
            ),
            "auth_enabled": purpose == "runtime",
        }
        if purpose == "runtime":
            auth = _read(client, refs.auth_secret_arn, _AuthSecret)
            if (auth.cognito_pool_id, auth.cognito_client_id) != (
                refs.cognito_pool_id,
                refs.cognito_client_id,
            ):
                raise ConfigurationError(
                    "Authentication secret does not match the configured pool/client"
                )
            values.update(
                cognito_client_secret=auth.cognito_client_secret,
                auth_encryption_keys=auth.auth_encryption_keys,
            )
        return values
    finally:
        client.close()
