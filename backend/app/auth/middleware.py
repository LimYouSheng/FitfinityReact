"""Bound request size before JSON parsing; reject cross-origin credential mutations."""

from app.observability import error_response


class AuthRequestMiddleware:
    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "").removeprefix(self.settings.root_path)
        if scope["type"] != "http" or not (
            path.startswith("/auth/") or path == "/me" or path.startswith("/api/")
        ):
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        failure = None
        sensitive = {
            b"origin",
            b"cookie",
            b"authorization",
            b"content-type",
            b"x-csrf-token",
            b"idempotency-key",
            b"content-length",
        }
        names = [key.lower() for key, _ in scope.get("headers", [])]
        if any(names.count(key) > 1 for key in sensitive):
            failure = ("REQUEST_REJECTED", "Request headers are ambiguous.", 400)
        if not failure and b"authorization" in headers:
            failure = ("AUTH_FAILED", "Use the staff session sign-in flow.", 401)
        elif not failure and scope["method"] == "POST":
            if headers.get(b"origin", b"").decode("latin1") not in self.settings.auth_origins:
                failure = ("ORIGIN_REJECTED", "Request origin is not allowed.", 403)
            elif (
                headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower()
                != b"application/json"
            ):
                failure = ("JSON_REQUIRED", "Send a JSON request.", 415)
        if failure:
            await error_response(*failure, scope["state"]["request_id"])(scope, receive, send)
            return
        limit = 131072 if path.startswith("/api/") else 16384
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > limit:
                await error_response(
                    "REQUEST_TOO_LARGE",
                    "Request is too large.",
                    413,
                    scope["state"]["request_id"],
                )(scope, receive, send)
                return
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        consumed = False

        async def bounded_receive():
            nonlocal consumed
            if consumed:
                return await receive()
            consumed = True
            return {"type": "http.request", "body": b"".join(chunks), "more_body": False}

        await self.app(scope, bounded_receive, send)
