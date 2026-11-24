"""Expose fixed, expiring upgrades only through a separately deployed private Lambda."""

import json
import os
import re
import time

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.managed_secrets import managed_values
from app.release_upgrade import UpgradeRefused, upgrade_existing


def create_upgrade(upgrader, *, operation_id, source_sha, from_revision, to_revision):
    """Accept one exact intent and return metadata without exposing provider/database errors."""
    for value, pattern in (
        (operation_id, r"[0-9a-f]{32}"),
        (source_sha, r"[0-9a-f]{40}"),
        (from_revision, r"[0-9]{8}_[0-9]{4}"),
        (to_revision, r"[0-9]{8}_[0-9]{4}"),
    ):
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            raise UpgradeRefused("Exact migration identity and revisions required")
    if from_revision == to_revision:
        raise UpgradeRefused("A reviewed forward migration range is required")
    intent = json.dumps(
        {"operation": "upgrade-existing", "operation_id": operation_id}, separators=(",", ":")
    ).encode()
    headers = {"Cache-Control": "no-store"}

    async def live(_request):
        return JSONResponse({"status": "live"}, headers=headers)

    async def execute(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > len(intent):
                return JSONResponse(
                    {"error": "invalid_upgrade_request"}, status_code=400, headers=headers
                )
        if bytes(body) != intent:
            return JSONResponse(
                {"error": "invalid_upgrade_request"}, status_code=400, headers=headers
            )
        try:
            result = await run_in_threadpool(upgrader)
            if result not in (
                {"outcome": "upgraded", "schema": to_revision},
                {"outcome": "already_at_target", "schema": to_revision},
            ):
                raise RuntimeError("Unexpected upgrade receipt")
            return JSONResponse(
                {
                    "operation_id": operation_id,
                    "source_sha": source_sha,
                    "from_revision": from_revision,
                    **result,
                },
                headers=headers,
            )
        except UpgradeRefused:
            return JSONResponse({"error": "migration_refused"}, status_code=409, headers=headers)
        except Exception:
            return JSONResponse(
                {"error": "migration_failed_or_uncertain"}, status_code=503, headers=headers
            )

    return Starlette(
        routes=[Route("/health/live", live), Route("/events", execute, methods=["POST"])]
    )


def create_app():
    """Load migration-only managed credentials and recheck expiry after secret retrieval."""
    if os.environ.get("FITFINITY_CONFIG_SOURCE") != "aws-secrets-manager":
        raise UpgradeRefused("Upgrade requires managed migration credentials")
    try:
        expires = int(os.environ["FITFINITY_UPGRADE_EXPIRES_AT"])
    except (KeyError, ValueError):
        raise UpgradeRefused("Upgrade expiry required") from None
    database = os.environ.get("FITFINITY_DB_NAME", "")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,62}", database):
        raise UpgradeRefused("Exact database required")
    start = os.environ.get("FITFINITY_UPGRADE_FROM", "")
    end = os.environ.get("FITFINITY_UPGRADE_TO", "")

    def execute():
        if not 0 < expires - time.time() <= 3600:
            raise UpgradeRefused("Upgrade expired")
        values = managed_values("migration")
        if not 0 < expires - time.time() <= 3600:
            raise UpgradeRefused("Upgrade expired during credential retrieval")
        engine = create_engine(
            values["database_url"].get_secret_value(),
            poolclass=NullPool,
            hide_parameters=True,
            connect_args={"connect_timeout": 5},
        )
        try:
            return upgrade_existing(
                engine,
                expected_database=database,
                expected_user="fitfinity_migrator",
                from_revision=start,
                to_revision=end,
                deadline=expires,
                runtime_role="fitfinity_app",
            )
        finally:
            engine.dispose()

    return create_upgrade(
        execute,
        operation_id=os.environ.get("FITFINITY_UPGRADE_OPERATION_ID", ""),
        source_sha=os.environ.get("FITFINITY_UPGRADE_SOURCE_SHA", ""),
        from_revision=start,
        to_revision=end,
    )
