"""Versioned approval controls with actor-scoped durable reconciliation evidence."""

import hashlib
import json
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt
from sqlalchemy import or_, select, text

from app.api.admin_supervision import supervised, supervised_recovery
from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import TrainerApprovalReceipt
from app.models.communications import Message, MessageReceipt
from app.models.people import StaffUser, Trainer

FIELDS = {
    "availability": "approve_availability",
    "sessionTime": "approve_session_time",
    "trainerReassignment": "approve_session_trainer",
    "fixedWeeklySchedule": "approve_weekly_schedule",
}


class ApprovalControls(Contract):
    availability: StrictBool
    sessionTime: StrictBool
    trainerReassignment: StrictBool
    fixedWeeklySchedule: StrictBool


class SaveApprovals(Contract):
    expectedVersion: StrictInt = Field(ge=1)
    approvalNeeded: ApprovalControls


class ApprovalState(Contract):
    id: UUID
    version: StrictInt = Field(ge=1)
    approvalNeeded: ApprovalControls


def receipt(session, principal, key):
    principal.operations()
    # Receipt lookup must serialize with commit even before a new receipt exists.
    session.execute(text("SELECT pg_advisory_xact_lock(714602032)"))
    return session.scalar(
        select(TrainerApprovalReceipt).where(
            TrainerApprovalReceipt.actor_id == principal.user_id,
            TrainerApprovalReceipt.request_key == key,
        )
    )


@supervised_recovery("trainer.approvals")
def reconcile(session, principal, key):
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return ApprovalState.model_validate(saved.result)


@supervised(
    "trainerAssignment", "trainer.approvals", SaveApprovals, receipt=receipt, target="trainer_id"
)
def save(session, principal, trainer_id, key, body):
    previous = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps(
            {"id": str(trainer_id), **body.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    if previous:
        if previous.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Review this request before retrying.", 409)
        return ApprovalState.model_validate(previous.result)
    trainer = session.scalar(select(Trainer).where(Trainer.id == trainer_id).with_for_update())
    if trainer is None:
        raise unavailable()
    if trainer.version != body.expectedVersion:
        raise conflict()
    before = {field: getattr(trainer, column) for field, column in FIELDS.items()}
    for field, column in FIELDS.items():
        setattr(trainer, column, getattr(body.approvalNeeded, field))
    trainer.version += 1
    session.flush()
    result = ApprovalState(
        id=trainer.id, version=trainer.version, approvalNeeded=body.approvalNeeded
    )
    session.add(
        TrainerApprovalReceipt(
            request_key=key,
            request_sha256=digest,
            trainer_id=trainer.id,
            previous=before,
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    notice = Message(
        kind="saved_edit",
        title=f"Autonomy and approvals saved: {trainer.name}",
        body="The trainer approval settings were updated.",
        trainer_id=trainer.id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    for user_id in session.scalars(
        select(StaffUser.id).where(
            StaffUser.status == "active",
            or_(StaffUser.role == "owner", StaffUser.id == trainer.user_id),
        )
    ):
        session.add(MessageReceipt(message_id=notice.id, user_id=user_id))
    return result
