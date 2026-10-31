"""Server-owned command registry; proposals never grant callers additional authority."""

import hashlib
import json
from dataclasses import dataclass
from functools import wraps
from inspect import signature
from typing import Literal
from uuid import UUID

from fastapi.responses import JSONResponse
from sqlalchemy import select, text

from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.models.admin_management import AdminApprovalRequirement
from app.models.admin_requests import AdminOperationRequest
from app.models.communications import Message, MessageReceipt
from app.models.people import StaffUser

# Acquire before actor locks for Admin writes and Owner approval/policy decisions.
SUPERVISION_LOCK = 714602081
COMMANDS = {}


class ApprovalPending(Contract):
    approvalPending: Literal[True] = True
    requestId: UUID
    message: Literal["Submitted for Owner approval. No changes have been applied."] = (
        "Submitted for Owner approval. No changes have been applied."
    )


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def pending_response(proposal):
    return JSONResponse(
        status_code=202, content=ApprovalPending(requestId=proposal.id).model_dump(mode="json")
    )


def original_proposal(session, principal, key):
    return session.scalar(
        select(AdminOperationRequest).where(
            AdminOperationRequest.actor_id == principal.user_id,
            AdminOperationRequest.request_key == key,
        )
    )


def proposal_outcome(session, principal, key, operation):
    """Recover a confirmed proposal only through its own domain receipt route."""
    proposal = original_proposal(session, principal, key)
    if proposal is None or proposal.operation != operation:
        return None
    if proposal.status == "pending":
        return pending_response(proposal)
    if proposal.status != "approved":
        raise AuthError(
            "approval_closed", "This request was not approved. Review a new change.", 409
        )
    return None


def notify_proposal(session, principal, proposal):
    """Notify only the originating Admin and active Owners; omit the private payload."""
    pending = proposal.status == "pending"
    notice = Message(
        actor_id=principal.user_id,
        actor_name=principal.name,
        kind="admin_operation_request" if pending else "admin_operation_decision",
        title="Admin change awaiting review" if pending else f"Admin change {proposal.status}",
        body=f"Request {proposal.id}. Open Admin Requests in Messages to review the exact change.",
    )
    session.add(notice)
    session.flush()
    recipients = set(
        session.scalars(
            select(StaffUser.id).where(StaffUser.role == "owner", StaffUser.status == "active")
        )
    )
    recipients.add(proposal.actor_id)
    for identity in recipients:
        session.add(MessageReceipt(message_id=notice.id, user_id=identity))


@dataclass(frozen=True)
class Command:
    area: str
    function: object
    schema: object
    target: tuple[str, ...]

    def execute(self, session, principal, proposal):
        values = {"body": self.schema.model_validate(proposal.body["body"])}
        for name in self.target:
            values[name] = UUID(proposal.body[name])
        # Nested domain helpers remain authorized as the original Admin, but must not
        # enqueue a second proposal inside an already-approved atomic operation.
        previous = session.info.get("admin_approval_execution")
        session.info["admin_approval_execution"] = True
        try:
            return self.function(session, principal, key=proposal.request_key, **values)
        finally:
            if previous is None:
                session.info.pop("admin_approval_execution", None)
            else:
                session.info["admin_approval_execution"] = previous


def supervised(area, operation, schema, *, receipt, target=False):
    """Wrap only domain entry commands; normal domain guards still run on approval/replay."""

    targets = (
        ("identity",)
        if target is True
        else (target,)
        if isinstance(target, str)
        else tuple(target or ())
    )

    def decorate(function):
        parameters = signature(function)
        if operation in COMMANDS:
            raise RuntimeError(f"Duplicate supervised command: {operation}")
        # Store the original function, not its proposal wrapper. Only Owner decision code
        # can execute this registry; no client-provided function/module/path is accepted.
        COMMANDS[operation] = Command(area, function, schema, targets)

        @wraps(function)
        def invoke(session, principal, *args, **kwargs):
            if principal.role != "admin" or session.info.get("admin_approval_execution"):
                return function(session, principal, *args, **kwargs)
            values = parameters.bind(session, principal, *args, **kwargs).arguments
            key = values["key"]
            # Freeze the public request spelling so nested aliases (notably schedule
            # "from") can be validated again when the Owner approves the proposal.
            payload = {
                "body": values["body"].model_dump(mode="json", by_alias=True, exclude_unset=True)
            }
            for name in targets:
                payload[name] = str(values[name])
            fingerprint = digest({"operation": operation, **payload})
            session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": SUPERVISION_LOCK})
            proposal = original_proposal(session, principal, key)
            if proposal:
                if proposal.request_sha256 != fingerprint:
                    raise AuthError(
                        "idempotency_conflict", "Check the original approval request.", 409
                    )
                if proposal.status == "pending":
                    return pending_response(proposal)
                if proposal.status != "approved":
                    raise AuthError(
                        "approval_closed",
                        "This request was not approved. Review a new change.",
                        409,
                    )
                if receipt(session, principal, key) is None:
                    raise AuthError(
                        "approval_incomplete", "The original approved change needs recovery.", 503
                    )
                return function(session, principal, *args, **kwargs)
            # An old successful command remains a receipt replay after policy changes.
            if receipt(session, principal, key) is not None:
                return function(session, principal, *args, **kwargs)
            policy = session.get(AdminApprovalRequirement, (principal.user_id, area))
            if policy is None or not policy.required:
                return function(session, principal, *args, **kwargs)
            if operation not in {"content.save", "package.save"}:
                from app.api.admin_review import review_snapshot

                payload["review"] = review_snapshot(session, principal, operation, values)
            proposal = AdminOperationRequest(
                actor_id=principal.user_id,
                actor_name=principal.name,
                request_key=key,
                request_sha256=fingerprint,
                operation=operation,
                area=area,
                body=payload,
                status="pending",
            )
            session.add(proposal)
            session.flush()
            notify_proposal(session, principal, proposal)
            return pending_response(proposal)

        return invoke

    return decorate


def supervised_recovery(*operations):
    """Retain the domain's original authorization and receipt checks before proposal recovery."""

    def decorate(function):
        @wraps(function)
        def reconcile(session, principal, key):
            try:
                return function(session, principal, key)
            except AuthError as error:
                if error.code != "not_found":
                    raise
                for operation in operations:
                    outcome = proposal_outcome(session, principal, key, operation)
                    if outcome is not None:
                        return outcome
                raise

        return reconcile

    return decorate
