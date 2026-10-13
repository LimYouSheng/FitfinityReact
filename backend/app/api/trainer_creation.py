"""Complete Trainer records and durable staff access setup; never expose Admin pay values."""

import hashlib
from datetime import UTC, datetime, time, timedelta
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Request
from pydantic import Field, StrictStr, field_validator, model_validator
from sqlalchemy import func, select, text

from app.api.dependencies import authorized_transaction
from app.api.schemas import Contract
from app.api.staff_provisioning import locked, provision
from app.api.staff_schemas import NewAdmin
from app.api.trainer_approvals import FIELDS, ApprovalControls
from app.api.trainer_availability import AvailabilityWindow, SaveAvailability
from app.api.trainer_rates import RateValues
from app.auth.errors import AuthError
from app.authorization import unavailable
from app.models.communications import Message, MessageReceipt
from app.models.people import StaffUser, Trainer, TrainerAvailability
from app.models.staff import StaffInvitation

DEFAULT_RATES = {"peak": 8000, "offPeak": 5500}


class NewTrainer(NewAdmin):
    trainerType: StrictStr = Field(min_length=1, max_length=120)
    qualifications: StrictStr = Field(max_length=10000)
    publicProfile: Literal["Visible", "Hidden"]
    rates: RateValues | None = None
    slots: list[AvailabilityWindow] = Field(min_length=1, max_length=10080)
    approvalNeeded: ApprovalControls

    @field_validator("trainerType")
    @classmethod
    def nonblank_type(cls, value):
        if not value.strip():
            raise ValueError("Trainer type is required")
        return value.strip()

    @model_validator(mode="after")
    def approved_availability(self):
        SaveAvailability(expectedVersion=1, slots=self.slots)
        return self


class TrainerCreated(Contract):
    id: UUID
    invitation: Literal["pending", "sending", "sent", "unknown"]


def allowed(principal, body=None):
    principal.operations()
    if body is not None:
        if principal.role == "admin" and "rates" in body.model_fields_set:
            raise AuthError("forbidden", "Trainer pay rates are restricted.", 403)
        if principal.role == "owner" and body.rates is None:
            raise AuthError("invalid_request", "Review the trainer pay rates.", 422)


def active_target(session, invitation):
    user = session.scalar(
        select(StaffUser).where(StaffUser.id == invitation.user_id).with_for_update(read=True)
    )
    trainer = session.scalar(
        select(Trainer).where(Trainer.user_id == invitation.user_id).with_for_update(read=True)
    )
    if (
        user is None
        or user.role != "trainer"
        or user.status != "active"
        or trainer is None
        or trainer.status != "active"
    ):
        raise AuthError("STAFF_INACTIVE", "This account is unavailable for invitation.", 409)
    return user


def result(session, user, invitation):
    trainer_id = session.scalar(select(Trainer.id).where(Trainer.user_id == user.id))
    if trainer_id is None or user.role != "trainer":
        raise unavailable()
    return TrainerCreated(id=trainer_id, invitation=invitation.status)


def reconcile(request, key):
    with authorized_transaction(request) as (session, principal):
        allowed(principal)
        invitation = session.scalar(
            select(StaffInvitation).where(
                StaffInvitation.request_key == key,
                StaffInvitation.actor_id == principal.user_id,
            )
        )
        if invitation is None:
            raise unavailable()
        user = session.get(StaffUser, invitation.user_id)
        # Reading an existing result must not retry setup or resend an invitation.
        return result(session, user, invitation)


def create(body: NewTrainer, request: Request, key: UUID):
    with authorized_transaction(request) as (session, principal):
        allowed(principal, body)
        if not request.app.state.auth_settings.staff_invitations_enabled:
            raise AuthError(
                "INVITATIONS_UNAVAILABLE", "Staff invitations are not ready. Contact support.", 503
            )
    provider = request.app.state.invitations
    provider.check_configuration()
    digest = hashlib.sha256(("trainer.create/" + body.model_dump_json()).encode()).hexdigest()
    now, lease = datetime.now(UTC), uuid4()
    with authorized_transaction(request) as (session, principal):
        allowed(principal, body)
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
            user = StaffUser(name=body.name, email=body.email, role="trainer")
            session.add(user)
            session.flush()
            rates = body.rates.model_dump() if principal.role == "owner" else DEFAULT_RATES
            trainer = Trainer(
                user_id=user.id,
                name=body.name,
                email=body.email,
                phone_country_code=body.phone_country_code,
                phone_number=body.phone_number,
                birthday=body.birthday,
                gender=body.gender,
                trainer_type=body.trainerType,
                qualifications=body.qualifications.strip(),
                public_profile=body.publicProfile == "Visible",
                peak_rate_cents=rates["peak"],
                off_peak_rate_cents=rates["offPeak"],
                **{column: getattr(body.approvalNeeded, field) for field, column in FIELDS.items()},
            )
            session.add(trainer)
            session.flush()
            for slot in body.slots:
                session.add(
                    TrainerAvailability(
                        trainer_id=trainer.id,
                        weekday=slot.weekday,
                        starts_at=time.fromisoformat(slot.startsAt),
                        ends_at=time.fromisoformat(slot.endsAt),
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
            notify(session, principal, trainer)
        else:
            user = active_target(session, invitation)
            if invitation.status == "sending" and invitation.lease_until <= now:
                invitation.status = "unknown"
                invitation.lease_id = invitation.lease_until = None
            if invitation.status in {"sent", "unknown", "sending"}:
                return result(session, user, invitation)
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
        authorize=allowed,
        active_target=active_target,
        project=result,
    )


def notify(session, principal, trainer):
    owners = session.scalars(
        select(StaffUser.id).where(StaffUser.role == "owner", StaffUser.status == "active")
    ).all()
    for title, body, recipients in [
        (
            f"New trainer created: {trainer.name}",
            "Trainer profile, session rates, approved availability "
            "and approval controls were saved.",
            owners,
        ),
        (
            f"Trainer profile created: {trainer.name}",
            "Your profile and approved availability are ready for client assignment.",
            [trainer.user_id],
        ),
    ]:
        notice = Message(
            kind="trainer_created",
            title=title,
            body=body,
            trainer_id=trainer.id,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
        session.add(notice)
        session.flush()
        for user_id in recipients:
            session.add(MessageReceipt(message_id=notice.id, user_id=user_id))
