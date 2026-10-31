"""Shared durable staff provisioning; provider calls never hold database transactions."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.api.dependencies import authorized_transaction
from app.auth.errors import AuthError
from app.models.people import StaffIdentity
from app.models.staff import StaffInvitation


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


def provision(
    request,
    key,
    digest,
    lease,
    user_id,
    name,
    email,
    *,
    authorize,
    active_target,
    project,
    transaction=authorized_transaction,
):
    provider = request.app.state.invitations
    try:
        remote = provider.ensure(user_id, name, email)
        with transaction(request) as (session, principal):
            authorize(principal)
            invitation = locked(session, key, principal.user_id, digest)
            lease_check(invitation, lease)
            user = active_target(session, invitation)
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
                return project(session, user, invitation)
            if remote["status"] != "FORCE_CHANGE_PASSWORD":
                raise AuthError(
                    "STAFF_IDENTITY_CONFLICT",
                    "Account identity needs review. Contact support.",
                    409,
                )
            invitation.status = "sending"
        sent = provider.send(user_id, email)
        with transaction(request) as (session, principal):
            authorize(principal)
            invitation = locked(session, key, principal.user_id, digest)
            lease_check(invitation, lease)
            user = active_target(session, invitation)
            invitation.status = "sent" if sent else "unknown"
            invitation.sent_at = datetime.now(UTC) if sent else None
            invitation.lease_id = invitation.lease_until = None
            return project(session, user, invitation)
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
