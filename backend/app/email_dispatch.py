"""Dedicated signed scheduler endpoint; never accept mail content from callers."""

import hashlib
import hmac
import json
import re
import time
from uuid import UUID

import boto3
from botocore.config import Config
from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from app.email_delivery import dispatch_one
from app.email_provider import SesEmail

router = APIRouter()


def signing_key(settings):
    """Read the dedicated worker secret, not staff passwords or auth encryption material."""
    client = boto3.client(
        "secretsmanager",
        region_name=settings.aws_region,
        config=Config(connect_timeout=2, read_timeout=3, retries={"total_max_attempts": 1}),
    )
    try:
        value = json.loads(
            client.get_secret_value(
                SecretId=settings.email_dispatch_secret_arn, VersionStage="AWSCURRENT"
            )["SecretString"]
        )
        key = value.get("dispatch_key", "")
        if not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ValueError("Invalid email dispatch key")
        return bytes.fromhex(key)
    finally:
        client.close()


def verify_request(body, signature, key, *, now=None):
    """Bind a short-lived request to one exact byte sequence and dispatch purpose."""
    if len(body) > 256 or not re.fullmatch(r"[a-f0-9]{64}", signature):
        return False
    expected = hmac.new(key, b"fitfinity.email.dispatch.v1\n" + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False
    try:
        value = json.loads(body)
        return (
            set(value) == {"at", "id"}
            and type(value["at"]) is int
            and abs((time.time() if now is None else now) - value["at"]) <= 60
            and str(UUID(value["id"])) == value["id"]
        )
    except (ValueError, TypeError, KeyError):
        return False


@router.post("/internal/email-dispatch", include_in_schema=False)
async def dispatch(request: Request):
    settings = request.app.state.auth_settings
    if not settings.transactional_email_enabled:
        raise HTTPException(404)
    signatures = request.headers.getlist("x-fitfinity-email-signature")
    if len(signatures) != 1 or not re.fullmatch(r"[a-f0-9]{64}", signatures[0]):
        raise HTTPException(403)
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > 256:
            raise HTTPException(413)
    # Fetching/signing uses a dedicated secret shared only with the scheduler role.
    if not verify_request(body, signatures[0], await run_in_threadpool(signing_key, settings)):
        raise HTTPException(403)
    provider = SesEmail(
        settings.aws_region, settings.email_sender, settings.email_configuration_set
    )
    try:
        result = await run_in_threadpool(dispatch_one, request.app.state.database, provider)
        return {"delivery": result}
    finally:
        provider.close()
