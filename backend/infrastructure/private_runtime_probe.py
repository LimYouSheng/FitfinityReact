"""Hash-pinned private current-image proof; no users, secrets or business data are changed."""

import asyncio
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

CONTRACT = json.loads(globals()["FITFINITY_CURRENT_CONTRACT"])  # provided by the hash-pinned bundle
ROOT = Path("/app")
auth_proof = None


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def runtime_preflight():
    checked = datetime.now(UTC)
    require(
        datetime.fromisoformat(CONTRACT["authorized_at"])
        <= checked
        < datetime.fromisoformat(CONTRACT["expires_at"]),
        "exception window",
    )
    identity = [os.getuid(), os.geteuid(), os.getgid(), os.getegid()]
    require(identity in [[993, 993, 990, 990], [10001] * 4], "non-root runtime identity")
    require(
        os.environ.get("AWS_LAMBDA_FUNCTION_NAME") in CONTRACT["function_names"],
        "function identity",
    )
    for name, expected in CONTRACT["files"].items():
        path = ROOT / name
        require(
            not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
            "image source: " + name,
        )
    for name, expected in CONTRACT["dependencies"].items():
        require(version(name) == expected, "locked dependency: " + name)
    return {
        "runtime_identity": identity,
        "source_files_verified": len(CONTRACT["files"]),
        "dependencies_verified": len(CONTRACT["dependencies"]),
        "image_digest": CONTRACT["image_digest"],
        "revision": CONTRACT["revision"],
    }


async def asgi_get(app, path, host="runtime.invalid"):
    """Send one bounded empty GET using only the runtime's standard library."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", host.encode("ascii"))],
        "client": ("127.0.0.1", 12345),
        "server": ("runtime.invalid", 443),
    }
    requested = False
    finished = asyncio.Event()
    status = None
    body = bytearray()

    async def receive():
        nonlocal requested
        if not requested:
            requested = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await finished.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        nonlocal status
        if message["type"] == "http.response.start":
            require(status is None and not finished.is_set(), "duplicate response start")
            status = message["status"]
        else:
            require(
                message["type"] == "http.response.body"
                and status is not None
                and not finished.is_set(),
                "unexpected response frame",
            )
            body.extend(message.get("body", b""))
            require(len(body) <= 4096, "health response size")
            if not message.get("more_body", False):
                finished.set()

    await app(scope, receive, send)
    require(status is not None and finished.is_set(), "incomplete health response")
    return status, bytes(body)


async def application_startup():
    from app.config import load_settings
    from app.main import create_app

    settings = load_settings()
    require(
        settings.allowed_hosts == ["runtime.invalid"]
        and settings.auth_origins == ["https://runtime.invalid"],
        "private origin settings",
    )
    require(
        settings.auth_enabled
        and settings.auth_cookie_secure
        and not settings.staff_invitations_enabled,
        "authentication settings",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        live, body = await asgi_get(app, "/health/live")
        require(live == 200 and json.loads(body) == {"status": "alive"}, "application liveness")
        ready, body = await asgi_get(app, "/health/ready")
        require(
            ready == 200 and json.loads(body) == {"status": "ready"},
            "application database readiness",
        )
        invalid, _ = await asgi_get(app, "/health/live", "untrusted.invalid")
        require(invalid == 400, "untrusted host")
    return {
        "liveness_status": 200,
        "readiness_status": 200,
        "untrusted_host_status": 400,
        "application_startup_verified": True,
        "application_shutdown_verified": True,
        "transport": "actual FastAPI lifespan and ASGI requests inside private image Lambda",
    }


async def run(request):
    global auth_proof
    nonce = None
    stage = "request"
    try:
        data = await request.body()
        require(len(data) <= 256, "request size")
        event = json.loads(data)
        nonce = event.get("nonce")
        action = event.get("action")
        require(
            event == {"action": action, "nonce": nonce}
            and action in {"preflight", "current-runtime"}
            and isinstance(nonce, str)
            and re.fullmatch(r"[a-f0-9]{32}", nonce),
            "request schema",
        )
        stage = "current_image_preflight"
        result = {"ok": True, "nonce": nonce, "action": action, **runtime_preflight()}
        if action == "current-runtime":
            stage = "managed_database_cognito_proof"
            # Unchanged read-only helper from the accepted authentication owner.
            # Its historical run()/initializer are never invoked and keep their original expiry.
            auth_proof = globals()["load_auth_proof"]()
            proof = auth_proof.application_proof(CONTRACT["auth_secret_arn"])
            require(
                proof.get("database_read_only") is True and proof.get("cognito_checks") == 18,
                "managed proof",
            )
            stage = "public_cognito_jwks_from_private_subnet"
            from app.auth.jwt import AccessVerifier, download_keys
            from app.config import load_settings

            settings = load_settings()
            keys = download_keys(settings.cognito_issuer + "/.well-known/jwks.json")
            require(
                isinstance(keys.get("keys"), list) and 1 <= len(keys["keys"]) <= 8, "JWKS inventory"
            )
            verifier = AccessVerifier(settings, fetch=lambda url: keys)
            verifier._key(keys["keys"][0]["kid"])
            stage = "actual_application_startup_and_health"
            app_proof = await application_startup()
            result.update(
                proof=proof, jwks_reachable=True, jwks_key_count=len(keys["keys"]), **app_proof
            )
        result["stage"] = "complete"
    except Exception as error:
        sqlstate = getattr(error, "sqlstate", None)
        missing = getattr(error, "name", None) if isinstance(error, ModuleNotFoundError) else None
        provider = getattr(error, "response", {}).get("Error", {}).get("Code")
        result = {
            "ok": False,
            "nonce": nonce,
            "stage": stage,
            "error_type": type(error).__name__,
            "managed_proof_stage": getattr(auth_proof, "STAGE", None)
            if stage == "managed_database_cognito_proof"
            else None,
            "sqlstate": sqlstate
            if isinstance(sqlstate, str) and re.fullmatch("[A-Z0-9]{5}", sqlstate)
            else None,
            "missing_module": missing
            if isinstance(missing, str) and re.fullmatch("[A-Za-z_][A-Za-z0-9_.]{0,127}", missing)
            else None,
            "provider_code": provider
            if isinstance(provider, str) and re.fullmatch("[A-Za-z0-9]+", provider)
            else None,
        }
    # Safe, nonce-bound recovery evidence if the synchronous Invoke response is lost.
    print("FITFINITY_RUNTIME_PROOF " + json.dumps(result, sort_keys=True), flush=True)
    return result
