"""JSON-only cookie authentication; exact origins and session-bound CSRF for mutations."""

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, TypeAdapter
from starlette.responses import JSONResponse

from app.api.schemas import (
    ERROR_RESPONSES,
    AuthChallenge,
    AuthPolicy,
    PasswordChanged,
    PasswordReset,
    RecoveryStarted,
    Refreshed,
    SessionBootstrap,
    SessionInfo,
    SignedIn,
    SignedOut,
)
from app.auth.errors import AuthError
from app.auth.security import require_csrf

router = APIRouter(tags=["staff authentication"], responses=ERROR_RESPONSES)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class SignIn(Input):
    email: str = Field(min_length=3, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=256)


class Challenge(Input):
    code: SecretStr | None = Field(default=None, max_length=6)
    newPassword: SecretStr | None = Field(default=None, max_length=128)


class SignOut(Input):
    allSessions: bool = Field(default=False, strict=True)


class ChangePassword(Input):
    currentPassword: SecretStr = Field(min_length=1, max_length=256)
    newPassword: SecretStr = Field(min_length=15, max_length=128)


class ForgotPassword(Input):
    email: str = Field(min_length=3, max_length=320)


class ResetPassword(Input):
    code: SecretStr = Field(min_length=1, max_length=64)
    newPassword: SecretStr = Field(min_length=15, max_length=128)


def _handle(request, *, flow=False, csrf=False):
    settings = request.app.state.auth_settings
    name = settings.flow_cookie if flow else settings.session_cookie
    # Reject duplicate cookie names rather than depend on cookie-parser ordering.
    values = [
        part.strip().split("=", 1)
        for part in request.headers.get("cookie", "").split(";")
        if "=" in part
    ]
    if sum(key == name for key, _ in values) != 1:
        raise AuthError("SESSION_EXPIRED", "Your session has ended. Sign in again.")
    handle = request.cookies.get(name)
    if csrf:
        require_csrf(handle, request.headers.get("x-csrf-token"))
    return handle


def _response(request, result, model):
    adapter = TypeAdapter(model)
    body = adapter.validate_python(result.body)
    response = JSONResponse(adapter.dump_python(body, mode="json", exclude_unset=True))
    settings = request.app.state.auth_settings
    options = {
        "path": "/",
        "secure": settings.auth_cookie_secure,
        "httponly": True,
        "samesite": "lax",
    }
    # Revocation/flow consumption is authoritative in the service. Shared cookie deletion
    # cannot compare the browser's current handle and could erase a newer login or flow.
    for name, handle in [
        (settings.session_cookie, result.session_handle),
        (settings.flow_cookie, result.flow_handle),
    ]:
        if handle:
            remaining = max(0, int((result.expires_at - datetime.now(UTC)).total_seconds()))
            response.set_cookie(name, handle, max_age=remaining, **options)
    return response


@router.get("/auth/policy", response_model=AuthPolicy, operation_id="staffAuthPolicy")
def policy():
    return {
        "password": {
            "minimumLength": 15,
            "maximumLength": 128,
            "spacesAllowed": False,
            "requiresCharacterMix": False,
            "scheduledRotation": False,
        },
        "mfa": {"required": True, "method": "totp"},
        "recovery": "verified_email",
    }


@router.post("/auth/sign-in", response_model=AuthChallenge, operation_id="staffSignIn")
def sign_in(body: SignIn, request: Request):
    return _response(
        request,
        request.app.state.auth.sign_in(body.email, body.password.get_secret_value()),
        AuthChallenge,
    )


@router.post(
    "/auth/challenge", response_model=AuthChallenge | SignedIn, operation_id="staffChallenge"
)
def challenge(body: Challenge, request: Request):
    return _response(
        request,
        request.app.state.auth.challenge(
            _handle(request, flow=True),
            code=body.code.get_secret_value() if body.code else None,
            new_password=body.newPassword.get_secret_value() if body.newPassword else None,
        ),
        AuthChallenge | SignedIn,
    )


@router.get("/me", response_model=SessionInfo, operation_id="staffMe")
def me(request: Request):
    return _response(request, request.app.state.auth.me(_handle(request)), SessionInfo)


@router.get("/auth/session", response_model=SessionBootstrap, operation_id="staffSessionBootstrap")
def session_bootstrap(request: Request):
    return _response(request, request.app.state.auth.bootstrap(_handle(request)), SessionBootstrap)


@router.post("/auth/refresh", response_model=Refreshed, operation_id="staffRefresh")
def refresh(body: Input, request: Request):
    return _response(
        request, request.app.state.auth.refresh(_handle(request, csrf=True)), Refreshed
    )


@router.post("/auth/sign-out", response_model=SignedOut, operation_id="staffSignOut")
def sign_out(body: SignOut, request: Request):
    return _response(
        request,
        request.app.state.auth.sign_out(_handle(request, csrf=True), body.allSessions),
        SignedOut,
    )


@router.post(
    "/auth/change-password", response_model=PasswordChanged, operation_id="staffChangePassword"
)
def change_password(body: ChangePassword, request: Request):
    return _response(
        request,
        request.app.state.auth.change_password(
            _handle(request, csrf=True),
            body.currentPassword.get_secret_value(),
            body.newPassword.get_secret_value(),
        ),
        PasswordChanged,
    )


@router.post(
    "/auth/forgot-password", response_model=RecoveryStarted, operation_id="staffForgotPassword"
)
def forgot_password(body: ForgotPassword, request: Request):
    return _response(request, request.app.state.auth.forgot_password(body.email), RecoveryStarted)


@router.post(
    "/auth/reset-password", response_model=PasswordReset, operation_id="staffResetPassword"
)
def reset_password(body: ResetPassword, request: Request):
    return _response(
        request,
        request.app.state.auth.reset_password(
            _handle(request, flow=True),
            body.code.get_secret_value(),
            body.newPassword.get_secret_value(),
        ),
        PasswordReset,
    )
