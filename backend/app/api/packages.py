"""Package catalogue commands; the authenticated outer transaction owns every write."""

import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictInt, StrictStr, field_validator, model_validator
from sqlalchemy import func, select, text

from app.api.schemas import Contract, DirectoryPackage
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import PackageSaveReceipt
from app.models.communications import Message, MessageReceipt
from app.models.people import StaffUser
from app.models.training import PackageTemplate, PackageTemplateRevision


class PackageDraft(Contract):
    name: StrictStr = Field(min_length=1, max_length=80)
    total: StrictInt = Field(ge=1, le=365)
    status: Literal["active", "inactive"]

    @field_validator("name")
    @classmethod
    def name_required(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Package name is required")
        return value


class SavePackage(Contract):
    id: UUID | None = None
    expectedVersion: StrictInt | None = Field(default=None, ge=1)
    draft: PackageDraft

    @model_validator(mode="after")
    def reviewed_update(self):
        if (self.id is None) != (self.expectedVersion is None):
            raise ValueError("An update requires its reviewed version")
        return self


# All catalogue commands and reconciliation reads take this transaction-scoped lock.
# It serializes name checks across actors, including creation when no row exists yet.
def catalogue_lock(session):
    session.execute(text("SELECT pg_advisory_xact_lock(714602031)"))


def receipt(session, principal, key):
    principal.operations()
    catalogue_lock(session)
    return session.scalar(
        select(PackageSaveReceipt).where(
            PackageSaveReceipt.actor_id == principal.user_id,
            PackageSaveReceipt.request_key == key,
        )
    )


def reconcile(session, principal, key):
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return DirectoryPackage.model_validate(saved.result)


def save(session, principal, key, body):
    previous = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if previous:
        if previous.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Review this request before retrying.", 409)
        return DirectoryPackage.model_validate(previous.result)
    template = None
    if body.id:
        template = session.scalar(
            select(PackageTemplate).where(PackageTemplate.id == body.id).with_for_update()
        )
        if template is None:
            raise unavailable()
        if template.version != body.expectedVersion:
            raise conflict()
    latest = (
        select(
            PackageTemplateRevision.template_id,
            func.max(PackageTemplateRevision.revision).label("revision"),
        )
        .group_by(PackageTemplateRevision.template_id)
        .subquery()
    )
    revisions = session.scalars(
        select(PackageTemplateRevision).join(
            latest,
            (PackageTemplateRevision.template_id == latest.c.template_id)
            & (PackageTemplateRevision.revision == latest.c.revision),
        )
    ).all()
    if any(
        r.template_id != body.id and r.name.lower() == body.draft.name.lower() for r in revisions
    ):
        raise AuthError("duplicate_name", "A package already uses this name.", 409)
    old_revision = next((r for r in revisions if r.template_id == body.id), None)
    if template and old_revision is None:
        raise AuthError("directory_incomplete", "Package details are unavailable.", 503)
    if template is None:
        template = PackageTemplate(status=body.draft.status)
        session.add(template)
    else:
        template.status = body.draft.status
        # Terms changes must advance the optimistic version even if status stays the same.
        template.version += 1
    session.flush()
    revision = PackageTemplateRevision(
        template_id=template.id,
        revision=old_revision.revision + 1 if old_revision else 1,
        name=body.draft.name,
        total_sessions=body.draft.total,
        validity_days=(body.draft.total * 90 + 11) // 12,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(revision)
    result = DirectoryPackage(
        id=template.id,
        version=template.version,
        revision=revision.revision,
        name=revision.name,
        total_sessions=revision.total_sessions,
        validity_days=revision.validity_days,
        status=template.status,
    )
    session.add(
        PackageSaveReceipt(
            request_key=key,
            request_sha256=digest,
            template_id=template.id,
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    notice = Message(
        kind="package_setup",
        title=f"Package {'updated' if body.id else 'created'}: {revision.name}",
        body=f"{revision.total_sessions} sessions · {revision.validity_days} days · "
        f"{template.status}. "
        "Existing client packages keep their purchased terms.",
        package_template_id=template.id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    for user_id in session.scalars(
        select(StaffUser.id).where(
            StaffUser.role.in_(["owner", "admin"]), StaffUser.status == "active"
        )
    ):
        session.add(MessageReceipt(message_id=notice.id, user_id=user_id))
    return result
