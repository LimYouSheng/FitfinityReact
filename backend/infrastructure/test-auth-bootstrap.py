"""Private, once-only auth secret initialization and independent startup proof."""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import boto3
import fitfinity_db_shared as shared
from botocore.config import Config
from sqlalchemy.engine import make_url

from app.auth.admin import check_configuration
from app.auth.security import TokenVault
from app.config import Settings, load_settings
from app.managed_secrets import _AuthSecret, _unique_object

CONTRACT = json.loads(FITFINITY_AUTH_CONTRACT)  # noqa: F821
ROOT = Path("/app")
STAGE = "initialization"
require = shared.require


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def client(service):
    return closing(
        boto3.client(
            service,
            region_name=shared.REGION,
            endpoint_url=f"https://{service}.{shared.REGION}.amazonaws.com",
            verify=True,
            config=Config(connect_timeout=3, read_timeout=4, retries={"total_max_attempts": 2}),
        )
    )


def version_token(arn):
    return hashlib.sha256(("fitfinity-auth-initial-v1:" + arn).encode()).hexdigest()


def metadata(sm, arn):
    row = sm.describe_secret(SecretId=arn)
    require(
        row.get("ARN") == arn
        and row.get("Name") == "fitfinity/test/auth"
        and not row.get("DeletedDate")
        and not row.get("RotationEnabled")
        and not row.get("OwningService")
        and not row.get("ReplicationStatus")
        and row.get("KmsKeyId") in {None, "alias/aws/secretsmanager"},
        "auth secret metadata",
    )
    tags = {x["Key"]: x["Value"] for x in row.get("Tags", [])}
    require(all(tags.get(k) == v for k, v in CONTRACT["tags"].items()), "auth secret ownership")
    versions = row.get("VersionIdsToStages", {})
    require(versions in ({}, {version_token(arn): ["AWSCURRENT"]}), "auth secret version drift")
    return bool(versions)


def read_auth(sm, arn):
    response = sm.get_secret_value(
        SecretId=arn, VersionId=version_token(arn), VersionStage="AWSCURRENT"
    )
    require(
        response.get("ARN") == arn
        and response.get("VersionId") == version_token(arn)
        and response.get("VersionStages") == ["AWSCURRENT"]
        and "SecretBinary" not in response,
        "auth secret response",
    )
    raw = response.get("SecretString")
    require(isinstance(raw, str) and len(raw.encode()) <= 4096, "auth secret size")
    parsed = _AuthSecret.model_validate(json.loads(raw, object_pairs_hook=_unique_object))
    require(
        (parsed.cognito_pool_id, parsed.cognito_client_id)
        == (CONTRACT["pool_id"], CONTRACT["client_id"]),
        "auth secret pool/client",
    )
    require(len(parsed.auth_encryption_keys) == 1, "initial encryption key count")
    return parsed


def settings_for(auth):
    # This non-routable origin is only a temporary settings proof, never a deployed staff origin.
    return Settings(
        environment="staging",
        database_url=f"postgresql+psycopg://fitfinity_app@{shared.HOST}/fitfinity?sslmode=verify-full",
        allowed_hosts=["bootstrap.invalid"],
        auth_enabled=True,
        cognito_pool_id=CONTRACT["pool_id"],
        cognito_client_id=CONTRACT["client_id"],
        cognito_client_secret=auth.cognito_client_secret,
        auth_encryption_keys=auth.auth_encryption_keys,
        auth_origins=["https://bootstrap.invalid"],
        auth_cookie_secure=True,
        staff_invitations_enabled=False,
        auth_session_hours=8,
    )


def verify_auth(auth, cognito):
    settings = settings_for(auth)
    count = check_configuration(settings, cognito)
    vault = TokenVault(settings.auth_encryption_keys)
    require(
        vault.open(vault.seal("bootstrap-proof", "auth-bootstrap"), "auth-bootstrap")
        == "bootstrap-proof",
        "encryption round trip",
    )
    return count


def initialize(arn):
    global STAGE
    with client("secretsmanager") as sm, client("cognito-idp") as cognito:
        STAGE = "secret_state"
        exists = metadata(sm, arn)
        if not exists:
            STAGE = "cognito_configuration"
            remote = cognito.describe_user_pool_client(
                UserPoolId=CONTRACT["pool_id"], ClientId=CONTRACT["client_id"]
            )["UserPoolClient"]
            require(
                (remote.get("UserPoolId"), remote.get("ClientId"))
                == (CONTRACT["pool_id"], CONTRACT["client_id"]),
                "confidential client identity",
            )
            value = {
                "cognito_pool_id": CONTRACT["pool_id"],
                "cognito_client_id": CONTRACT["client_id"],
                "cognito_client_secret": remote["ClientSecret"],
                "auth_encryption_keys": [
                    base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
                ],
            }
            verify_auth(_AuthSecret.model_validate(value), cognito)
            STAGE = "secret_initialization"
            # One deterministic version ID refuses a competing different key. No rotation/overwrite.
            response = sm.put_secret_value(
                SecretId=arn,
                ClientRequestToken=version_token(arn),
                SecretString=json.dumps(value),
                VersionStages=["AWSCURRENT"],
            )
            require(
                response.get("ARN") == arn and response.get("VersionId") == version_token(arn),
                "secret write response",
            )
        STAGE = "auth_secret_verification"
        require(metadata(sm, arn), "initialized secret absent")
        count = verify_auth(read_auth(sm, arn), cognito)
        return {
            "secret_version_id": version_token(arn),
            "auth_secret_verified": True,
            "newly_initialized": not exists,
            "cognito_checks": count,
            "encryption_verified": True,
        }


def application_proof(arn):
    global STAGE
    STAGE = "managed_runtime_settings"
    with client("secretsmanager") as sm:
        require(metadata(sm, arn), "secret not initialized")
        auth = read_auth(sm, arn)
    settings = load_settings()
    require(
        settings.auth_enabled
        and settings.auth_cookie_secure
        and not settings.staff_invitations_enabled
        and settings.auth_session_hours == 8,
        "runtime auth settings",
    )
    require(
        hmac.compare_digest(
            settings.cognito_client_secret.get_secret_value(),
            auth.cognito_client_secret.get_secret_value(),
        )
        and settings.auth_encryption_keys == auth.auth_encryption_keys,
        "runtime loaded values",
    )
    with client("cognito-idp") as cognito:
        count = verify_auth(auth, cognito)
    STAGE = "read_only_database"
    url = make_url(settings.database_url.get_secret_value())
    require(
        url.username == "fitfinity_app"
        and url.host == shared.HOST
        and url.query.get("sslmode") == "verify-full",
        "runtime database settings",
    )
    with shared.connect({"username": url.username, "password": url.password}) as connection:
        with connection.transaction(force_rollback=True):
            connection.execute("SET TRANSACTION READ ONLY")
            require(
                connection.execute("SHOW transaction_read_only").fetchone() == ("on",), "read only"
            )
            proof = shared.tls(connection, "fitfinity_app")
            shared.permissions(connection, "fitfinity_app")
            require(
                connection.execute("SELECT version_num FROM public.alembic_version").fetchall()
                == [("20260924_0006",)],
                "migration target",
            )
            marker = (
                "fitfinity-test-schema-v1:"
                + CONTRACT["migration_contract_sha256"]
                + ":"
                + CONTRACT["accepted_schema_sha256"]
            )
            require(
                connection.execute(
                    "SELECT obj_description('public.alembic_version'::regclass,'pg_class')"
                ).fetchone()
                == (marker,),
                "accepted schema marker",
            )
    return {
        **proof,
        "secret_version_id": version_token(arn),
        "auth_secret_verified": True,
        "managed_settings_verified": True,
        "cognito_checks": count,
        "encryption_verified": True,
        "database_read_only": True,
        "target_revision": "20260924_0006",
    }


async def run(request):
    global STAGE
    nonce = None
    identity = None
    ca_sha = None
    try:
        STAGE = "request_schema"
        raw = await request.body()
        require(len(raw) <= 256, "request size")
        event = json.loads(raw)
        nonce = event.get("nonce")
        mode = os.environ["FITFINITY_DB_ACCESS_MODE"]
        require(
            mode in {"auth-initialize", "auth-app-probe"}
            and event == {"action": event.get("action"), "nonce": nonce}
            and event["action"] in {mode, "preflight"}
            and isinstance(nonce, str)
            and re.fullmatch(r"[a-f0-9]{32}", nonce),
            "request",
        )
        STAGE = "exception_window"
        require(datetime.now(UTC) < datetime(2026, 9, 29, 15, 59, tzinfo=UTC), "exception expired")
        STAGE = "runtime_identity"
        identity = dict(
            zip(
                ("uid", "euid", "gid", "egid"),
                (os.getuid(), os.geteuid(), os.getgid(), os.getegid()),
                strict=True,
            )
        )
        require(
            tuple(identity.values()) in {(993, 993, 990, 990), (10001,) * 4}, "runtime identity"
        )
        STAGE = "tls_bundle"
        ca_sha = hashlib.sha256(shared.CA.read_bytes()).hexdigest()
        require(ca_sha == shared.CA_SHA256, "CA bundle")
        STAGE = "image_files"
        for path, expected in CONTRACT["files"].items():
            require(
                hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, "image file"
            )
        STAGE = "secret_reference"
        arn = os.environ["FITFINITY_AUTH_SECRET_ARN"]
        require(
            re.fullmatch(
                r"arn:aws:secretsmanager:ap-southeast-1:418638389566:secret:fitfinity/test/auth-[A-Za-z0-9]{6}",
                arn,
            ),
            "auth ARN",
        )
        if mode == "auth-app-probe":
            require(
                os.environ["FITFINITY_DATABASE_SECRET_ARN"] == CONTRACT["app_secret_arn"], "app ARN"
            )
        if event["action"] == "preflight":
            return {
                "ok": True,
                "nonce": nonce,
                "mode": mode,
                "preflight_only": True,
                "runtime_identity": identity,
                "ca_sha256": ca_sha,
                "image_files_sha256": digest(CONTRACT["files"]),
            }
        proof = initialize(arn) if mode == "auth-initialize" else application_proof(arn)
        return {"ok": True, "nonce": nonce, "mode": mode, "proof": proof}
    except Exception as error:
        code = getattr(error, "sqlstate", None)
        return {
            "ok": False,
            "nonce": nonce,
            "stage": STAGE,
            "error_type": type(error).__name__,
            "sqlstate": code
            if isinstance(code, str) and re.fullmatch(r"[A-Z0-9]{5}", code)
            else None,
            "runtime_identity": identity,
            "ca_sha256": ca_sha,
        }
