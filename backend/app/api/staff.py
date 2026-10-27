"""Owner-authorized Admin provisioning; durable retries and bounded external calls."""

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from sqlalchemy import func, select, text

from app.api import trainer_creation
from app.api.dependencies import authorized_transaction
from app.api.request_types import RequestKey
from app.api.schemas import ERROR_RESPONSES
from app.api.staff_provisioning import locked, provision
from app.api.staff_schemas import AdminCreated, NewAdmin
from app.auth.errors import AuthError
from app.models.people import StaffUser, Trainer
from app.models.staff import AdminProfile, StaffInvitation

router = APIRouter(prefix="/api/staff", tags=["staff access"], responses=ERROR_RESPONSES)


def result(user, invitation):
    return AdminCreated(
        id=user.id, name=user.name, email=user.email, role="admin", invitation=invitation.status
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
    return provision(
        request,
        key,
        digest,
        lease,
        user_id,
        body.name,
        body.email,
        authorize=lambda principal: principal.owner(),
        active_target=active_admin,
        project=lambda session, user, invitation: result(user, invitation),
    )


@router.post(
    "/trainers", response_model=trainer_creation.TrainerCreated, operation_id="createTrainer"
)
def create_trainer(body: trainer_creation.NewTrainer, request: Request, key: RequestKey):
    return trainer_creation.create(body, request, key)


@router.get(
    "/trainer-creations/{request_key}",
    response_model=trainer_creation.TrainerCreated,
    operation_id="reconcileTrainerCreation",
)
def reconcile_trainer_creation(request_key: UUID, request: Request):
    return trainer_creation.reconcile(request, request_key)
