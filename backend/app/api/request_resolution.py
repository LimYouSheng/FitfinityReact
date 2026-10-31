"""Resolve a reviewed proposal and its domain effects in one durable transaction."""

import hashlib
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictInt, ValidationError
from sqlalchemy import select, text

from app.api import request_application
from app.api.admin_supervision import supervised, supervised_recovery
from app.api.request_cancellation import DECISION_LOCK, RequestActor
from app.api.schemas import Contract
from app.api.session_mutation_journal import journal
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import RequestResolutionReceipt
from app.models.communications import ChangeRequest, Message, MessageReceipt, RequestEvent
from app.models.people import StaffUser, Trainer


class ResolveRequest(Contract):
    expectedVersion: StrictInt = Field(ge=1)
    decision: Literal["approved", "rejected"]


class ResolutionState(Contract):
    id: UUID
    version: StrictInt = Field(ge=1)
    status: Literal["approved", "rejected"]
    at: datetime
    by: RequestActor


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": DECISION_LOCK})
    return session.scalar(
        select(RequestResolutionReceipt).where(
            RequestResolutionReceipt.actor_id == principal.user_id,
            RequestResolutionReceipt.request_key == key,
        )
    )


@supervised_recovery("request.resolve")
def reconcile(session, principal, key):
    """Return the original actor's receipt without applying a proposal again."""
    principal.operations()
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return ResolutionState.model_validate(saved.result)


def notify(session, principal, request):
    """Deliver one durable decision notice to active affected staff, with private read states."""
    trainer = session.get(Trainer, request.trainer_id)
    replacement = (
        session.get(Trainer, request.replacement_trainer_id)
        if request.replacement_trainer_id
        else None
    )
    affected_users = {principal.user_id, trainer.user_id}
    if replacement is not None and request.status == "approved":
        affected_users.add(replacement.user_id)
    affected_users.discard(None)
    recipients = set(
        session.scalars(
            select(StaffUser.id).where(
                StaffUser.status == "active",
                (StaffUser.role == "owner") | StaffUser.id.in_(affected_users),
            )
        )
    )
    message = Message(
        kind="request_decision",
        title=f"Request {request.status}",
        body=request.resolution_note,
        request_id=request.id,
        client_id=request.client_id,
        purchase_id=request.purchase_id,
        session_id=request.session_id,
        trainer_id=request.trainer_id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(message)
    session.flush()
    for identity in recipients:
        session.add(MessageReceipt(message_id=message.id, user_id=identity))


@supervised(
    "sessionScheduling", "request.resolve", ResolveRequest, receipt=receipt, target="identity"
)
@journal("request.resolve")
def save(session, principal, identity, key, body):
    """Bind current authority, immutable proposal, decision version and exact retry intent."""
    principal.operations()
    saved = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps({"id": str(identity), **body.model_dump()}, sort_keys=True).encode()
    ).hexdigest()
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Check the original request decision.", 409)
        return ResolutionState.model_validate(saved.result)
    peek = session.get(ChangeRequest, identity)
    if peek is None:
        raise unavailable()
    if peek.status != "pending" or peek.version != body.expectedVersion:
        raise conflict()
    # A rejection needs no eligible target and must remain possible after a stale proposal.
    viewed = (
        request_application.context(session, principal, peek)
        if body.decision == "approved"
        else None
    )
    request = session.scalar(
        select(ChangeRequest)
        .where(ChangeRequest.id == identity)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if request.status != "pending" or request.version != body.expectedVersion:
        raise conflict()
    if body.decision == "approved":
        try:
            request_application.apply(session, principal, request, viewed)
        except ValidationError as error:
            raise conflict() from error
    request.status = body.decision
    request.version += 1
    request.resolved_by = principal.user_id
    request.resolved_at = session.scalar(text("SELECT clock_timestamp()"))
    request.resolution_note = f"{principal.name} {body.decision} this request. " + (
        "The reviewed change was applied."
        if body.decision == "approved"
        else "The proposed change was not applied."
    )
    session.add(
        RequestEvent(
            request_id=request.id,
            sequence=2,
            status=request.status,
            note=request.resolution_note,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    notify(session, principal, request)
    result = ResolutionState(
        id=request.id,
        version=request.version,
        status=request.status,
        at=request.resolved_at,
        by=RequestActor(id=principal.user_id, name=principal.name),
    )
    session.add(
        RequestResolutionReceipt(
            request_key=key,
            request_sha256=digest,
            change_request_id=request.id,
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    return result
