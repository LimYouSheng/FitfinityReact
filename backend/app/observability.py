"""Allowlisted JSON events: never log request bodies, credentials, raw URLs or SQL errors."""

import json
import logging
import sys
import time
from datetime import UTC, datetime
from uuid import uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

EVENT_FIELDS = ("request_id", "method", "route", "status", "duration_ms", "error_type")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for field in EVENT_FIELDS:
            if hasattr(record, field):
                event[field] = getattr(record, field)
        return json.dumps(event, separators=(",", ":"))


def configure_logging(level: str) -> logging.Logger:
    logger = logging.getLogger("fitfinity")
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    return logger


def error_response(code: str, message: str, status: int, request_id: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message, "requestId": request_id}},
        status_code=status,
    )


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, logger: logging.Logger):
        self.app = app
        self.logger = logger

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # Generate our own ID rather than trusting caller-controlled log content.
        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        status = 500
        response_started = False

        async def send_response(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status = message["status"]
                response_started = True
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() not in {b"x-request-id", b"cache-control"}
                ]
                headers.extend(
                    [(b"x-request-id", request_id.encode()), (b"cache-control", b"no-store")]
                )
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_response)
        except Exception as exc:
            self.logger.error(
                "request_failed",
                extra={"request_id": request_id, "error_type": type(exc).__name__},
            )
            if response_started:
                raise
            await error_response(
                "internal_error", "The request could not be completed.", 500, request_id
            )(scope, receive, send_response)
        finally:
            route = getattr(scope.get("route"), "path", "unmatched")
            self.logger.info(
                "request_completed",
                extra={
                    "request_id": request_id,
                    "method": scope["method"]
                    if scope["method"]
                    in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
                    else "OTHER",
                    "route": route,
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
