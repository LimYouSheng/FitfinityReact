"""Private catalog observer; separate entry point, never registered in the staff API.

Deploy only through a reviewed private Lambda without a Function URL/API integration.
The immutable image and SQL digest, IAM invocation and database identity are boundaries.
"""

import hashlib
import json
import os
import re
import time
from pathlib import Path

import psycopg
from sqlalchemy.engine import make_url
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.managed_secrets import managed_values

SQL = Path(__file__).resolve().parents[1] / "infrastructure" / "read-schema.sql"


class ObservationRefused(RuntimeError):
    """Safe failure text; never propagate database/provider exceptions."""


def observe(database_url, *, expected_database, expected_user, sql_sha256):
    """Fixed catalog query, read-only session, identity checks and closed connection."""
    try:
        script = SQL.read_bytes()
        if hashlib.sha256(script).hexdigest() != sql_sha256:
            raise ObservationRefused("Catalog query digest differs")
        url = make_url(database_url)
        with psycopg.connect(
            url.set(drivername="postgresql").render_as_string(hide_password=False),
            autocommit=True,
            connect_timeout=5,
            options=(
                "-c default_transaction_read_only=on "
                "-c statement_timeout=15000 -c lock_timeout=3000"
            ),
        ) as connection:
            identity = connection.execute("SELECT current_database(), current_user").fetchone()
            if identity != (expected_database, expected_user):
                raise ObservationRefused("Database identity differs")
            results = []
            with connection.cursor() as cursor:
                cursor.execute(script.decode())
                while True:
                    if cursor.description:
                        results.append(cursor.fetchone()[0])
                    if not cursor.nextset():
                        break
            if (
                len(results) != 1
                or connection.info.transaction_status != psycopg.pq.TransactionStatus.IDLE
            ):
                raise ObservationRefused("Unexpected catalog result")
        result = results[0]
        if (
            result.get("transaction_read_only") != "on"
            or result.get("database") != expected_database
            or result.get("database_user") != expected_user
            or len(json.dumps(result).encode()) > 1024 * 1024
        ):
            raise ObservationRefused("Unexpected catalog receipt")
        return result
    except ObservationRefused:
        raise
    except Exception:
        raise ObservationRefused("Catalog observation failed") from None


def create_probe(observer, *, source_sha, sql_sha256):
    """Only fixed invocation intent is accepted; request data cannot supply SQL/code."""
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha) or not re.fullmatch(
        r"[0-9a-f]{64}", sql_sha256
    ):
        raise ObservationRefused("Reviewed source and SQL bindings required")

    async def live(_request):
        return JSONResponse({"status": "live"})

    async def collect(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 64:
                return JSONResponse({"error": "invalid_probe_request"}, status_code=400)
        if bytes(body) != b'{"operation":"observe-schema"}':
            return JSONResponse({"error": "invalid_probe_request"}, status_code=400)
        try:
            receipt = await run_in_threadpool(observer)
            return JSONResponse(
                {"source_sha": source_sha, "sql_sha256": sql_sha256, "catalog": receipt},
                headers={"Cache-Control": "no-store"},
            )
        except Exception:
            return JSONResponse({"error": "catalog_observation_failed"}, status_code=503)

    return Starlette(
        routes=[Route("/health/live", live), Route("/events", collect, methods=["POST"])]
    )


def create_app():
    """Lambda factory: fail closed unless explicitly configured for managed secrets."""
    if os.environ.get("FITFINITY_CONFIG_SOURCE") != "aws-secrets-manager":
        raise ObservationRefused("Probe requires managed database credentials")
    source = os.environ.get("FITFINITY_PROBE_SOURCE_SHA", "")
    sql_hash = os.environ.get("FITFINITY_PROBE_SQL_SHA256", "")
    try:
        expires = int(os.environ["FITFINITY_PROBE_EXPIRES_AT"])
    except (KeyError, ValueError):
        raise ObservationRefused("Probe expiry required") from None

    def collect():
        if time.time() >= expires:
            raise ObservationRefused("Probe expired")
        # Existing loader verifies target account/region, CA digest/TLS and restricted
        # migration username. It retrieves no Cognito or authentication secret.
        values = managed_values("migration")
        return observe(
            values["database_url"].get_secret_value(),
            expected_database=os.environ.get("FITFINITY_DB_NAME", ""),
            expected_user="fitfinity_migrator",
            sql_sha256=sql_hash,
        )

    return create_probe(collect, source_sha=source, sql_sha256=sql_hash)
