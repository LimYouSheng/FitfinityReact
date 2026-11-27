"""Allow the active Owner to review and save their own contact profile."""

import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import Field, StrictInt
from sqlalchemy import select

from app.api.dependencies import authorized_transaction
from app.api.routes import RequestKey
from app.api.schemas import ERROR_RESPONSES, Contract
from app.api.staff_schemas import NewAdmin
from app.authorization import conflict, unavailable
from app.models.owner_profile import OwnerProfile, OwnerProfileReceipt
from app.models.people import StaffUser

router = APIRouter(prefix="/api/owner-profile", tags=["Owner profile"], responses=ERROR_RESPONSES)


class ProfileView(Contract):
    id: UUID
    version: int
    name: str
    email: str
    phone_country_code: str
    phone_number: str
    birthday: str
    gender: str


class ProfileSave(Contract):
    expectedVersion: StrictInt = Field(ge=1)
    details: NewAdmin


def project(user, profile):
    return ProfileView(
        id=user.id,
        version=user.version,
        name=user.name,
        email=user.email,
        phone_country_code=profile.phone_country_code if profile else "+65",
        phone_number=profile.phone_number if profile else "",
        birthday=str(profile.birthday) if profile else "",
        gender=profile.gender if profile else "",
    )


@router.get("", response_model=ProfileView, operation_id="ownerProfile")
def read(request: Request):
    with authorized_transaction(request) as (session, principal):
        principal.owner()
        return project(
            session.get(StaffUser, principal.user_id), session.get(OwnerProfile, principal.user_id)
        )


@router.get("/saves/{key}", response_model=ProfileView, operation_id="ownerProfileReceipt")
def receipt(key: UUID, request: Request):
    with authorized_transaction(request) as (session, principal):
        principal.owner()
        saved = session.scalar(
            select(OwnerProfileReceipt).where(
                OwnerProfileReceipt.actor_id == principal.user_id,
                OwnerProfileReceipt.request_key == key,
            )
        )
        if saved is None:
            raise unavailable()
        return ProfileView.model_validate(saved.result)


@router.post("", response_model=ProfileView, operation_id="saveOwnerProfile")
def save(body: ProfileSave, request: Request, key: RequestKey):
    with authorized_transaction(request, exclusive_user=True) as (session, principal):
        principal.owner()
        user = session.get(StaffUser, principal.user_id)
        digest = hashlib.sha256(
            json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        prior = session.scalar(
            select(OwnerProfileReceipt).where(
                OwnerProfileReceipt.actor_id == user.id, OwnerProfileReceipt.request_key == key
            )
        )
        if prior:
            if prior.request_sha256 != digest:
                raise conflict()
            return ProfileView.model_validate(prior.result)
        if user.version != body.expectedVersion or body.details.email != user.email:
            raise conflict()
        profile = session.get(OwnerProfile, user.id)
        if profile is None:
            profile = OwnerProfile(user_id=user.id)
            session.add(profile)
        for field in ("phone_country_code", "phone_number", "birthday", "gender"):
            setattr(profile, field, getattr(body.details, field))
        user.name = body.details.name
        user.version += 1
        session.flush()
        result = project(user, profile)
        session.add(
            OwnerProfileReceipt(
                actor_id=user.id,
                actor_name=principal.name,
                request_key=key,
                request_sha256=digest,
                result=result.model_dump(mode="json"),
            )
        )
        return result
