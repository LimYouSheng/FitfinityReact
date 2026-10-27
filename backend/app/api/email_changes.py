"""Manager-requested email changes confirmed using the account holder's own token."""

import re
from datetime import timedelta
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from pydantic import Field, SecretStr, StrictInt, StrictStr, field_validator
from sqlalchemy import select, text

from app.api.dependencies import authorized_transaction
from app.api.request_types import RequestKey
from app.api.schemas import ERROR_RESPONSES, Contract
from app.auth.errors import AuthError, busy
from app.auth.routes import _handle
from app.authorization import conflict, unavailable
from app.models.email_changes import StaffEmailChange
from app.models.people import StaffIdentity, StaffUser, Trainer

router = APIRouter(tags=["staff email verification"], responses=ERROR_RESPONSES)


class EmailRequest(Contract):
    supersedes: UUID | None = None
    expectedVersion: StrictInt = Field(ge=1)
    email: StrictStr = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def email_address(cls, value):
        if any(ord(char) < 32 for char in value):
            raise ValueError("Invalid email address")
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Invalid email address")
        return value


class EmailState(Contract):
    id: UUID
    email: str
    state: Literal["requested", "sending", "pending", "verifying", "completed", "superseded"]
    signedOut: bool = False


class PendingEmail(Contract):
    change: EmailState | None


class EmailCode(Contract):
    code: SecretStr = Field(min_length=6, max_length=6)


def result(change, *, signed_out=False):
    return EmailState(
        id=change.id, email=change.new_email, state=change.state, signedOut=signed_out
    )


@router.post(
    "/api/trainers/{trainer_id}/email-change",
    response_model=EmailState,
    operation_id="requestTrainerEmailChange",
)
def request_change(trainer_id: UUID, body: EmailRequest, request: Request, key: RequestKey):
    """Reserve an address without changing login/recovery or sending mail to another user."""
    with authorized_transaction(request) as (session, principal):
        principal.operations()
        if (
            body.supersedes is not None
            and not request.app.state.auth_settings.staff_email_corrections_enabled
        ):
            raise AuthError(
                "EMAIL_CORRECTION_UNAVAILABLE", "Pending email correction is not enabled.", 409
            )
        target_id = session.scalar(select(Trainer.user_id).where(Trainer.id == trainer_id))
        user = session.scalar(select(StaffUser).where(StaffUser.id == target_id).with_for_update())
        trainer = session.scalar(select(Trainer).where(Trainer.id == trainer_id).with_for_update())
        if not user or not trainer or user.status != "active" or trainer.status != "active":
            raise unavailable()
        session.execute(text("SELECT pg_advisory_xact_lock(714602036)"))
        prior = session.scalar(
            select(StaffEmailChange).where(
                StaffEmailChange.actor_id == principal.user_id, StaffEmailChange.request_key == key
            )
        )
        if prior:
            if (prior.user_id, prior.new_email, prior.trainer_version, prior.supersedes_id) != (
                user.id,
                body.email,
                body.expectedVersion,
                body.supersedes,
            ):
                raise conflict()
            return result(prior)
        if trainer.version != body.expectedVersion or trainer.email != user.email:
            raise conflict()
        identity = session.scalar(
            select(StaffIdentity).where(
                StaffIdentity.user_id == user.id,
                StaffIdentity.issuer == request.app.state.auth_settings.cognito_issuer,
                StaffIdentity.status == "active",
            )
        )
        if not identity or not identity.provider_username:
            raise conflict()
        if body.email == user.email:
            raise AuthError("EMAIL_UNCHANGED", "Enter a different email address.", 422)
        pending = session.scalar(
            select(StaffEmailChange)
            .where(
                StaffEmailChange.user_id == user.id,
                StaffEmailChange.state.not_in(["completed", "superseded"]),
            )
            .with_for_update()
        )
        if pending:
            if body.supersedes != pending.id:
                raise AuthError(
                    "EMAIL_CHANGE_PENDING",
                    "Review the pending verification before correcting it.",
                    409,
                )
            if pending.state not in {"requested", "pending"} or pending.lease_id is not None:
                raise AuthError(
                    "EMAIL_CHANGE_UNCERTAIN",
                    "The trainer must reconcile the current provider action before correction.",
                    409,
                )
            if pending.new_email == body.email:
                raise AuthError("EMAIL_UNCHANGED", "Enter a different pending email address.", 422)
            pending.state, pending.superseded_at = "superseded", request.app.state.auth.clock()
            session.flush()
        elif body.supersedes is not None:
            raise conflict()
        change = StaffEmailChange(
            request_key=key,
            supersedes_id=body.supersedes,
            sends=pending.sends if pending else 0,
            attempts=pending.attempts if pending else 0,
            last_sent_at=pending.last_sent_at if pending else None,
            trainer_version=body.expectedVersion,
            user_id=user.id,
            identity_id=identity.id,
            old_email=user.email,
            new_email=body.email,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
        session.add(change)
        session.flush()
        return result(change)


@router.get(
    "/auth/email-change", response_model=PendingEmail, operation_id="pendingStaffEmailChange"
)
def pending(request: Request):
    """Read only this account holder's pending change. General directories omit it."""
    with authorized_transaction(request) as (session, principal):
        change = session.scalar(
            select(StaffEmailChange).where(
                StaffEmailChange.user_id == principal.user_id,
                StaffEmailChange.state.not_in(["completed", "superseded"]),
            )
        )
        return PendingEmail(change=result(change) if change else None)


@router.get(
    "/api/trainer-email-requests/{key}",
    response_model=EmailState,
    operation_id="reconcileTrainerEmailRequest",
)
def request_receipt(key: UUID, request: Request):
    """Read a serialized actor-scoped request receipt without sending a verification code."""
    with authorized_transaction(request) as (session, principal):
        principal.operations()
        session.execute(text("SELECT pg_advisory_xact_lock(714602036)"))
        change = session.scalar(
            select(StaffEmailChange).where(
                StaffEmailChange.actor_id == principal.user_id, StaffEmailChange.request_key == key
            )
        )
        if change is None:
            raise unavailable()
        return result(change)


@router.get(
    "/api/trainers/{trainer_id}/email-change",
    response_model=PendingEmail,
    operation_id="pendingTrainerEmailChange",
)
def trainer_pending(trainer_id: UUID, request: Request):
    """Managers can inspect a trainer's pending verification after reload."""
    with authorized_transaction(request) as (session, principal):
        principal.operations()
        trainer = session.get(Trainer, trainer_id)
        if not trainer:
            raise unavailable()
        change = session.scalar(
            select(StaffEmailChange).where(
                StaffEmailChange.user_id == trainer.user_id,
                StaffEmailChange.state.not_in(["completed", "superseded"]),
            )
        )
        return PendingEmail(change=result(change) if change else None)


def own_change(session, principal, identity_id, change_id):
    change = session.scalar(
        select(StaffEmailChange)
        .where(StaffEmailChange.id == change_id, StaffEmailChange.user_id == principal.user_id)
        .with_for_update()
    )
    if not change:
        raise unavailable()
    if change.state == "superseded":
        raise AuthError(
            "EMAIL_CHANGE_SUPERSEDED",
            "This request was corrected. Reload the current verification.",
            409,
        )
    if change.identity_id != identity_id:
        raise conflict()
    return change


def credentials(request, change_id):
    auth = request.app.state.auth
    _, record = auth.principal(_handle(request, csrf=True))
    with authorized_transaction(request) as (session, principal):
        own_change(session, principal, record.identity_id, change_id)
    access = auth.vault.open(record.access_cipher, f"{record.handle_hash}:access")
    return auth, record, access


def verified_address(auth, record, access):
    claims = auth.verifier.verify(access)
    remote = auth.provider.user(access)
    values = {item["Name"]: item["Value"] for item in remote.get("UserAttributes", [])}
    if (
        values.get("sub") != claims["sub"]
        or remote.get("Username") != claims["username"]
        or values.get("email_verified") != "true"
        or "SOFTWARE_TOKEN_MFA" not in (remote.get("UserMFASettingList") or [])
    ):
        raise AuthError()
    return values.get("email", "").strip().lower()


def finish(request, auth, record, change_id, address, lease=None):
    completed = False
    with authorized_transaction(request, exclusive_user=True) as (session, principal):
        change = own_change(session, principal, record.identity_id, change_id)
        if change.state == "completed":
            return result(change)
        if lease is not None and change.lease_id != lease:
            raise busy()
        if lease is None and change.lease_until and change.lease_until > auth.clock():
            raise busy()
        user = session.get(StaffUser, principal.user_id)
        trainer = session.scalar(select(Trainer).where(Trainer.user_id == user.id))
        if user.email != change.old_email or not trainer or trainer.email != change.old_email:
            raise conflict()
        if address == change.new_email and change.state in {"sending", "pending", "verifying"}:
            # Existing staff-email trigger revokes every session atomically with the
            # local address switch. Completed evidence survives a lost HTTP response.
            user.email = trainer.email = address
            change.state, change.completed_at = "completed", auth.clock()
            change.reservation_released_at = change.completed_at
            change.lease_id = change.lease_until = None
            completed = True
            session.flush()
        elif address != change.old_email:
            raise AuthError(
                "EMAIL_IDENTITY_CONFLICT", "Account email needs review. Contact support.", 409
            )
        response = result(change, signed_out=completed)
    if completed:
        auth.drain_revocations(user_id=record.user_id)
    return response


@router.post(
    "/auth/email-change/{change_id}/reconcile",
    response_model=EmailState,
    operation_id="reconcileStaffEmailChange",
)
def reconcile(change_id: UUID, request: Request):
    """Read back provider verification before reconciling an interrupted address switch."""
    auth, record, access = credentials(request, change_id)
    with authorized_transaction(request) as (session, principal):
        own_change(session, principal, record.identity_id, change_id)
    return finish(request, auth, record, change_id, verified_address(auth, record, access))


@router.post(
    "/auth/email-change/{change_id}/send",
    response_model=EmailState,
    operation_id="sendStaffEmailCode",
)
def send_code(change_id: UUID, request: Request):
    """Explicitly send a code using the target's token; uncertain sends are never replayed."""
    auth, record, access = credentials(request, change_id)
    reconciled = finish(request, auth, record, change_id, verified_address(auth, record, access))
    if reconciled.state == "completed":
        return reconciled
    lease = uuid4()
    with authorized_transaction(request, exclusive_user=True) as (session, principal):
        change = own_change(session, principal, record.identity_id, change_id)
        now = auth.clock()
        if change.lease_until and change.lease_until > now:
            raise busy()
        if change.last_sent_at and change.last_sent_at > now - timedelta(seconds=60):
            raise AuthError("AUTH_RATE_LIMITED", "Wait before requesting another code.", 429)
        if change.last_sent_at and change.last_sent_at <= now - timedelta(hours=1):
            change.sends = 0
        if change.sends >= 6:
            raise AuthError("AUTH_RATE_LIMITED", "Too many codes. Try again later.", 429)
        change.state, change.lease_id, change.lease_until = (
            "sending",
            lease,
            now + timedelta(seconds=30),
        )
        change.sends += 1
        change.last_sent_at = now
        email = change.new_email
    # Persist intent before the only mail-producing call; a timeout leaves 'sending'.
    auth.provider.request_email_change(access, email)
    with authorized_transaction(request, exclusive_user=True) as (session, principal):
        change = own_change(session, principal, record.identity_id, change_id)
        if change.lease_id != lease:
            raise busy()
        change.state, change.attempts = "pending", 0
        change.lease_id = change.lease_until = None
        return result(change)


@router.post(
    "/auth/email-change/{change_id}/verify",
    response_model=EmailState,
    operation_id="verifyStaffEmailChange",
)
def verify_code(change_id: UUID, body: EmailCode, request: Request):
    """Only the account holder can confirm; verified provider readback precedes local commit."""
    code = body.code.get_secret_value()
    if not re.fullmatch(r"[0-9]{6}", code):
        raise AuthError("INVALID_CODE", "Enter the six-digit verification code.", 422)
    auth, record, access = credentials(request, change_id)
    reconciled = finish(request, auth, record, change_id, verified_address(auth, record, access))
    if reconciled.state == "completed":
        return reconciled
    lease = uuid4()
    with authorized_transaction(request, exclusive_user=True) as (session, principal):
        change = own_change(session, principal, record.identity_id, change_id)
        if change.state == "requested" or not change.sends:
            raise conflict()
        if change.lease_until and change.lease_until > auth.clock():
            raise busy()
        if change.attempts >= 6:
            raise AuthError("AUTH_RATE_LIMITED", "Request a new code before trying again.", 429)
        change.state, change.lease_id = "verifying", lease
        change.lease_until = auth.clock() + timedelta(seconds=30)
        change.attempts += 1
    try:
        auth.provider.verify_email_change(access, code)
    except AuthError as error:
        if error.status in {400, 422, 429}:
            with authorized_transaction(request, exclusive_user=True) as (session, principal):
                change = own_change(session, principal, record.identity_id, change_id)
                if change.lease_id == lease:
                    change.state = "pending"
                    change.lease_id = change.lease_until = None
        raise
    return finish(
        request, auth, record, change_id, verified_address(auth, record, access), lease=lease
    )
