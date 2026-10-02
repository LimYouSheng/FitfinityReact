"""Generate one schema from actual routes, including cookie/CSRF transport and safe errors."""


def configure_openapi(app, settings):
    generate = app.openapi

    def schema():
        if app.openapi_schema:
            return app.openapi_schema
        result = generate()
        if settings.auth_enabled:
            result.setdefault("components", {})["securitySchemes"] = {
                "StaffSession": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": settings.session_cookie,
                    "description": "Opaque HttpOnly staff session after MFA.",
                },
                "StaffFlow": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": settings.flow_cookie,
                    "description": "Short-lived sign-in/recovery flow; not a staff session.",
                },
                "SessionCSRF": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-CSRF-Token",
                    "description": "Session-bound CSRF token; required on mutations.",
                },
            }
        public = {
            "/health/live",
            "/health/ready",
            "/auth/policy",
            "/auth/sign-in",
            "/auth/forgot-password",
        }
        flow = {"/auth/challenge", "/auth/reset-password"}
        for path, methods in result["paths"].items():
            for method, operation in methods.items():
                if method not in {"get", "post"}:
                    continue
                operation.setdefault("description", operation.get("summary", "Staff API contract"))
                if path not in public:
                    security = {"StaffFlow" if path in flow else "StaffSession": []}
                    if method == "post" and path not in flow:
                        security["SessionCSRF"] = []
                    operation["security"] = [security]
                if method == "post":
                    operation.setdefault("parameters", []).append(
                        {
                            "in": "header",
                            "name": "Origin",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Exact configured staff frontend origin required.",
                            "example": "https://staff.example.test",
                        }
                    )
                for status, response in operation["responses"].items():
                    response.setdefault("headers", {}).update(
                        {
                            "X-Request-ID": {
                                "schema": {"type": "string"},
                                "description": "Server-generated support ID",
                            },
                            "Cache-Control": {"schema": {"type": "string", "const": "no-store"}},
                        }
                    )
                    if int(status) >= 400:
                        response["content"]["application/json"]["example"] = {
                            "error": {
                                "code": "validation_error"
                                if status == "422"
                                else "request_rejected",
                                "message": "Request rejected.",
                                "requestId": "example-support-id",
                            }
                        }
        app.openapi_schema = result
        return result

    app.openapi = schema
