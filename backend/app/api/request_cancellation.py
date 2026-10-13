"""An active requesting Trainer may withdraw a pending proposal without applying it."""

import hashlib
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictInt
from sqlalchemy import select, text

from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import RequestCancellationReceipt
from app.models.communications import ChangeRequest, Message, MessageReceipt, RequestEvent
from app.models.people import StaffUser


class CancelRequest(Contract):
    expectedVersion: StrictInt = Field(ge=1)


class RequestActor(Contract):
    id: UUID
    name: str


class CancellationState(Contract):
    id: UUID
    version: StrictInt = Field(ge=1)
    status: Literal["cancelled"] = "cancelled"
    at: datetime
    by: RequestActor


def allowed(principal):
    if principal.role != "trainer" or principal.trainer_id is None:
        raise AuthError("forbidden", "Only the requesting Trainer can cancel this request.", 403)


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(714602045)"))
    return session.scalar(
        select(RequestCancellationReceipt).where(
            RequestCancellationReceipt.actor_id == principal.user_id,
            RequestCancellationReceipt.request_key == key,
        )
    )


def reconcile(session, principal, key):
    allowed(principal)
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return CancellationState.model_validate(saved.result)


def save(session, principal, identity, key, body):
    allowed(principal)
    saved = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps({"id": str(identity), **body.model_dump()}, sort_keys=True).encode()
    ).hexdigest()
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError(
                "idempotency_conflict", "Review the original request before retrying.", 409
            )
        return CancellationState.model_validate(saved.result)
    request = session.scalar(
        select(ChangeRequest)
        .where(ChangeRequest.id == identity, ChangeRequest.trainer_id == principal.trainer_id)
        .with_for_update()
    )
    if request is None:
        raise unavailable()
    if (
        request.status == "cancelled"
        and request.resolved_by == principal.user_id
        and body.expectedVersion in {request.version, request.version - 1}
    ):
        pass
    elif request.status == "pending" and request.version == body.expectedVersion:
        request.status = "cancelled"
        request.resolved_by = principal.user_id
        request.resolved_at = session.scalar(text("SELECT clock_timestamp()"))
        request.resolution_note = (
            "The requesting Trainer cancelled this request. The proposed change was not applied."
        )
        request.version += 1
        session.add(
            RequestEvent(
                request_id=request.id,
                sequence=2,
                status="cancelled",
                note=request.resolution_note,
                actor_id=principal.user_id,
                actor_name=principal.name,
            )
        )
        notify(session, principal, request)
        session.flush()
    else:
        raise conflict()
    event = session.scalar(
        select(RequestEvent).where(
            RequestEvent.request_id == request.id, RequestEvent.sequence == 2
        )
    )
    if event is None or event.status != "cancelled" or event.actor_id != principal.user_id:
        raise conflict()
    result = CancellationState(
        id=request.id,
        version=request.version,
        at=request.resolved_at,
        by=RequestActor(id=event.actor_id, name=event.actor_name),
    )
    session.add(
        RequestCancellationReceipt(
            request_key=key,
            request_sha256=digest,
            change_request_id=request.id,
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    return result


def notify(session, principal, request):
    owners = session.scalars(
        select(StaffUser.id).where(StaffUser.role == "owner", StaffUser.status == "active")
    ).all()
    for recipients in [owners, [principal.user_id]]:
        notice = Message(
            kind="request_decision",
            title="Request cancelled",
            body=f"{principal.name} cancelled this request. The proposed change was not applied.",
            request_id=request.id,
            client_id=request.client_id,
            session_id=request.session_id,
            trainer_id=request.trainer_id,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
        session.add(notice)
        session.flush()
        for identity in recipients:
            session.add(MessageReceipt(message_id=notice.id, user_id=identity))
