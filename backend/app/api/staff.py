"""Owner-authorized Admin provisioning; durable retries and bounded external calls."""

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Request
from sqlalchemy import func, select, text

from app.api.dependencies import authorized_transaction
from app.api.routes import RequestKey
from app.api.schemas import ERROR_RESPONSES
from app.api.staff_schemas import AdminCreated, NewAdmin
from app.auth.errors import AuthError
from app.models.people import StaffIdentity, StaffUser, Trainer
from app.models.staff import AdminProfile, StaffInvitation

router = APIRouter(prefix="/api/staff", tags=["staff access"], responses=ERROR_RESPONSES)


def result(user, invitation):
    return AdminCreated(
        id=user.id, name=user.name, email=user.email, role="admin", invitation=invitation.status
    )


def locked(session, key, actor_id, digest):
    invitation = session.scalar(
        select(StaffInvitation).where(StaffInvitation.request_key == key).with_for_update()
    )
    if invitation and (invitation.actor_id != actor_id or invitation.request_sha256 != digest):
        raise AuthError(
            "idempotency_conflict", "Use the original account details for this request.", 409
        )
    return invitation


def lease_check(invitation, lease):
    if invitation.lease_id != lease or invitation.lease_until <= datetime.now(UTC):
        raise AuthError(
            "INVITATION_BUSY", "Account setup is still being checked. Try again shortly.", 409
        )


def active_admin(session, invitation):
    user = session.get(StaffUser, invitation.user_id)
    if user is None or user.role != "admin" or user.status != "active":
        raise AuthError("STAFF_INACTIVE", "This account is unavailable for invitation.", 409)
    return user


@router.post("/admins", response_model=AdminCreated, operation_id="createAdmin")
def create_admin(body: NewAdmin, request: Request, key: RequestKey):
    """Create one Admin and request its access email. Reuse key and body after an interruption.

    Unknown email delivery is never resent automatically. No role selection, pay fields,
    provider identifiers or temporary password can be supplied or returned by this endpoint.
    """
    with authorized_transaction(request) as (session, principal):
        principal.owner()
        if not request.app.state.auth_settings.staff_invitations_enabled:
            raise AuthError(
                "INVITATIONS_UNAVAILABLE", "Staff invitations are not ready. Contact support.", 503
            )
    provider = request.app.state.invitations
    provider.check_configuration()
    digest = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    now, lease = datetime.now(UTC), uuid4()
    with authorized_transaction(request) as (session, principal):
        principal.owner()
        # Serialize account allocation/retries for this Owner; duplicate emails also have a
        # unique database constraint. Lock scope ends before any provider request begins.
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:actor, 0))"),
            {"actor": str(principal.user_id)},
        )
        invitation = locked(session, key, principal.user_id, digest)
        if invitation is None:
            if session.scalar(
                select(StaffUser.id).where(StaffUser.email == body.email)
            ) or session.scalar(select(Trainer.id).where(Trainer.email == body.email)):
                raise AuthError(
                    "STAFF_EMAIL_EXISTS",
                    "This email already belongs to a staff account or trainer.",
                    409,
                )
            recent = session.scalar(
                select(func.count())
                .select_from(StaffInvitation)
                .where(
                    StaffInvitation.actor_id == principal.user_id,
                    StaffInvitation.created_at > now - timedelta(hours=1),
                )
            )
            if recent >= 10:
                raise AuthError("INVITATION_LIMIT", "Too many new accounts. Try again later.", 429)
            user = StaffUser(name=body.name, email=body.email, role="admin")
            session.add(user)
            session.flush()
            session.add(
                AdminProfile(
                    user_id=user.id,
                    phone_country_code=body.phone_country_code,
                    phone_number=body.phone_number,
                    birthday=body.birthday,
                    gender=body.gender,
                )
            )
            invitation = StaffInvitation(
                user_id=user.id,
                request_key=key,
                request_sha256=digest,
                actor_id=principal.user_id,
                actor_name=principal.name,
                status="pending",
            )
            session.add(invitation)
        else:
            user = active_admin(session, invitation)
            if invitation.status == "sending" and invitation.lease_until <= now:
                invitation.status = "unknown"
                invitation.lease_id = invitation.lease_until = None
            if invitation.status in {"sent", "unknown", "sending"}:
                return result(user, invitation)
            if invitation.lease_until and invitation.lease_until > now:
                raise AuthError(
                    "INVITATION_BUSY", "Account setup is in progress. Try again shortly.", 409
                )
        invitation.lease_id, invitation.lease_until = lease, now + timedelta(seconds=60)
        user_id = user.id
    try:
        remote = provider.ensure(user_id, body.name, body.email)
        with authorized_transaction(request) as (session, principal):
            principal.owner()
            invitation = locked(session, key, principal.user_id, digest)
            lease_check(invitation, lease)
            user = active_admin(session, invitation)
            identity = session.scalar(
                select(StaffIdentity).where(
                    StaffIdentity.user_id == user.id,
                    StaffIdentity.issuer == request.app.state.auth_settings.cognito_issuer,
                )
            )
            if identity is None:
                session.add(
                    StaffIdentity(
                        user_id=user.id,
                        issuer=request.app.state.auth_settings.cognito_issuer,
                        subject=remote["subject"],
                        provider_username=remote["username"],
                    )
                )
            elif (
                identity.subject != remote["subject"]
                or identity.provider_username != remote["username"]
                or identity.status != "active"
            ):
                raise AuthError(
                    "STAFF_IDENTITY_CONFLICT",
                    "Account identity needs review. Contact support.",
                    409,
                )
            if remote["status"] == "CONFIRMED":
                invitation.status = "sent"
                invitation.lease_id = invitation.lease_until = None
                return result(user, invitation)
            if remote["status"] != "FORCE_CHANGE_PASSWORD":
                raise AuthError(
                    "STAFF_IDENTITY_CONFLICT",
                    "Account identity needs review. Contact support.",
                    409,
                )
            invitation.status = "sending"
        sent = provider.send(user_id, body.email)
        with authorized_transaction(request) as (session, principal):
            principal.owner()
            invitation = locked(session, key, principal.user_id, digest)
            lease_check(invitation, lease)
            user = active_admin(session, invitation)
            invitation.status = "sent" if sent else "unknown"
            invitation.sent_at = datetime.now(UTC) if sent else None
            invitation.lease_id = invitation.lease_until = None
            return result(user, invitation)
    except AuthError:
        # Preserve account/identity on failures. Reconciliation may retry a suppressed create,
        # but an uncertain email is never resent by replaying the creation request.
        with request.app.state.database.transaction() as session:
            invitation = session.scalar(
                select(StaffInvitation).where(StaffInvitation.request_key == key).with_for_update()
            )
            if invitation and invitation.lease_id == lease:
                if invitation.status == "sending":
                    invitation.status = "unknown"
                invitation.lease_id = invitation.lease_until = None
        raise
