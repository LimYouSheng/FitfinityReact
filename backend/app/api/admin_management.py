"""Owner-only Admin account review, lifecycle and supervision controls."""

import hashlib
import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import Field, StrictBool, StrictInt, model_validator
from sqlalchemy import select, text

from app.api.dependencies import authorized_transaction
from app.api.directory import bounded
from app.api.routes import RequestKey
from app.api.schemas import ERROR_RESPONSES, Contract
from app.api.staff_schemas import NewAdmin
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.admin_management import (
    APPROVAL_AREAS,
    AdminApprovalRequirement,
    AdminManagementReceipt,
)
from app.models.people import StaffUser
from app.models.staff import AdminProfile

router = APIRouter(prefix="/api/staff/admins", tags=["Admin management"], responses=ERROR_RESPONSES)


class AdminDetails(Contract):
    id: UUID
    version: int
    role: Literal["admin"] = "admin"
    status: Literal["active", "inactive"]
    details: NewAdmin
    approvalNeeded: dict[str, StrictBool]


class AdminUpdate(Contract):
    expectedVersion: StrictInt = Field(ge=1)
    operation: Literal["details", "approvals", "deactivate", "reactivate"]
    details: NewAdmin | None = None
    approvalNeeded: dict[str, StrictBool] | None = None

    @model_validator(mode="after")
    def exact_action(self):
        if (self.operation == "details") != (self.details is not None):
            raise ValueError("Review one Admin details change")
        if (self.operation == "approvals") != (self.approvalNeeded is not None):
            raise ValueError("Review one approval-policy change")
        if self.approvalNeeded is not None and set(self.approvalNeeded) != set(APPROVAL_AREAS):
            raise ValueError("Review the complete supported approval policy")
        return self


def target(session, identity, *, write=False):
    user = session.scalar(
        select(StaffUser)
        .where(
            StaffUser.id == identity,
            StaffUser.role == "admin",
        )
        .with_for_update(read=not write)
    )
    profile = session.scalar(
        select(AdminProfile)
        .where(
            AdminProfile.user_id == identity,
        )
        .with_for_update(read=not write)
    )
    if user is None or profile is None:
        raise unavailable()
    return user, profile


def project(session, user, profile):
    requirements = dict(
        session.execute(
            select(
                AdminApprovalRequirement.area,
                AdminApprovalRequirement.required,
            ).where(AdminApprovalRequirement.user_id == user.id)
        ).all()
    )
    # Older Admins retain their previously granted direct operational workflow.
    return AdminDetails(
        id=user.id,
        version=user.version,
        status=user.status,
        details=NewAdmin(
            name=user.name,
            email=user.email,
            phone_country_code=profile.phone_country_code,
            phone_number=profile.phone_number,
            birthday=str(profile.birthday),
            gender=profile.gender,
        ),
        approvalNeeded={area: requirements.get(area, False) for area in APPROVAL_AREAS},
    )


def save(session, principal, identity, key, body):
    """One immutable owner command; status triggers invalidate all old app sessions."""
    principal.owner()
    session.execute(text("SELECT pg_advisory_xact_lock(714602080)"))
    digest = hashlib.sha256(
        json.dumps(
            {"id": str(identity), **body.model_dump(mode="json")},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    previous = session.scalar(
        select(AdminManagementReceipt).where(
            AdminManagementReceipt.actor_id == principal.user_id,
            AdminManagementReceipt.request_key == key,
        )
    )
    if previous:
        if previous.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Check the original Admin change.", 409)
        return AdminDetails.model_validate(previous.result)
    user, profile = target(session, identity, write=True)
    if user.version != body.expectedVersion:
        raise conflict()
    before = project(session, user, profile)
    if body.operation in {"details", "approvals"} and user.status != "active":
        raise conflict()
    if body.operation == "details":
        if body.details.email != user.email:
            raise AuthError(
                "verification_required", "Login email changes require verification.", 422
            )
        user.name = body.details.name
        for field in ("phone_country_code", "phone_number", "birthday", "gender"):
            setattr(profile, field, getattr(body.details, field))
    elif body.operation == "approvals":
        for area, required in body.approvalNeeded.items():
            requirement = session.get(AdminApprovalRequirement, (user.id, area))
            if requirement is None:
                session.add(AdminApprovalRequirement(user_id=user.id, area=area, required=required))
            else:
                requirement.required = required
    else:
        expected = "active" if body.operation == "deactivate" else "inactive"
        if user.status != expected:
            raise conflict()
        user.status = "inactive" if body.operation == "deactivate" else "active"
    user.version += 1
    session.flush()
    result = project(session, user, profile)
    session.add(
        AdminManagementReceipt(
            actor_id=principal.user_id,
            actor_name=principal.name,
            admin_id=user.id,
            request_key=key,
            request_sha256=digest,
            operation=body.operation,
            previous=before.model_dump(mode="json"),
            result=result.model_dump(mode="json"),
        )
    )
    return result


@router.get("", response_model=list[AdminDetails])
def list_admins(request: Request):
    """Owner-only bounded Admin directory with fixed roles and current policy."""
    with authorized_transaction(request) as (session, principal):
        principal.owner()
        rows = bounded(
            session,
            select(StaffUser)
            .where(StaffUser.role == "admin")
            .order_by(StaffUser.name, StaffUser.id),
        )
        return [project(session, *target(session, user.id)) for user in rows]


@router.get("/{identity}", response_model=AdminDetails)
def get_admin(identity: UUID, request: Request):
    """Review one retained Admin account and its current version."""
    with authorized_transaction(request) as (session, principal):
        principal.owner()
        return project(session, *target(session, identity))


@router.post("/{identity}", response_model=AdminDetails)
def update_admin(identity: UUID, body: AdminUpdate, request: Request, key: RequestKey):
    """Commit one Owner-reviewed account, policy or lifecycle change atomically."""
    with authorized_transaction(request) as (session, principal):
        return save(session, principal, identity, key, body)


@router.get("/changes/{key}", response_model=AdminDetails)
def recover_admin(key: UUID, request: Request):
    """Read only the original Owner’s immutable account-change receipt."""
    with authorized_transaction(request) as (session, principal):
        principal.owner()
        session.execute(text("SELECT pg_advisory_xact_lock(714602080)"))
        receipt = session.scalar(
            select(AdminManagementReceipt).where(
                AdminManagementReceipt.actor_id == principal.user_id,
                AdminManagementReceipt.request_key == key,
            )
        )
        if receipt is None:
            raise unavailable()
        return AdminDetails.model_validate(receipt.result)
