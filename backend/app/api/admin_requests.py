"""Owner decisions execute only registered, frozen Admin proposals atomically."""

from contextlib import contextmanager
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import Field, StrictInt
from sqlalchemy import select, text

from app.api.admin_supervision import COMMANDS, SUPERVISION_LOCK, digest, notify_proposal
from app.api.dependencies import authorized_transaction
from app.api.directory import bounded
from app.api.library_schemas import MediaReadCheck, ReadLease
from app.api.routes import RequestKey
from app.api.schemas import ERROR_RESPONSES, Contract
from app.auth.errors import AuthError
from app.authorization import Principal, conflict, unavailable
from app.models.admin_requests import AdminOperationDecision, AdminOperationRequest
from app.models.people import StaffUser

router = APIRouter(
    prefix="/api/admin-requests", tags=["Admin approvals"], responses=ERROR_RESPONSES
)


class AdminRequestView(Contract):
    id: UUID
    version: int
    actorId: UUID
    actorName: str
    operation: str
    area: str
    body: dict
    status: Literal["pending", "approved", "rejected", "cancelled"]
    createdAt: datetime
    resolvedAt: datetime | None
    resolvedBy: UUID | None


class AdminDecision(Contract):
    expectedVersion: StrictInt = Field(ge=1)
    decision: Literal["approved", "rejected", "cancelled"]


def project(row):
    return AdminRequestView(
        id=row.id,
        version=row.version,
        actorId=row.actor_id,
        actorName=row.actor_name,
        operation=row.operation,
        area=row.area,
        body=row.body,
        status=row.status,
        createdAt=row.created_at,
        resolvedAt=row.resolved_at,
        resolvedBy=row.resolved_by,
    )


def private_query(principal):
    principal.operations()
    query = select(AdminOperationRequest)
    return (
        query
        if principal.role == "owner"
        else query.where(AdminOperationRequest.actor_id == principal.user_id)
    )


def decide(session, principal, identity, key, body):
    """The domain write, terminal proposal and original decision receipt commit together."""
    principal.operations()
    if body.decision != "cancelled":
        principal.owner()
    session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": SUPERVISION_LOCK})
    fingerprint = digest({"id": str(identity), **body.model_dump(mode="json")})
    receipt = session.scalar(
        select(AdminOperationDecision).where(
            AdminOperationDecision.actor_id == principal.user_id,
            AdminOperationDecision.request_key == key,
        )
    )
    if receipt:
        if receipt.request_sha256 != fingerprint:
            raise AuthError("idempotency_conflict", "Check the original approval decision.", 409)
        return AdminRequestView.model_validate(receipt.result)
    proposal = session.scalar(
        private_query(principal).where(AdminOperationRequest.id == identity).with_for_update()
    )
    if proposal is None:
        raise unavailable()
    if body.decision == "cancelled" and proposal.actor_id != principal.user_id:
        raise AuthError("forbidden", "Only the requesting Admin can cancel this proposal.", 403)
    if proposal.status != "pending" or proposal.version != body.expectedVersion:
        raise conflict()
    if body.decision == "approved":
        actor = session.scalar(
            select(StaffUser).where(StaffUser.id == proposal.actor_id).with_for_update(read=True)
        )
        if actor is None or actor.status != "active" or actor.role != "admin":
            raise conflict()
        command = COMMANDS.get(proposal.operation)
        if command is None or command.area != proposal.area:
            raise AuthError(
                "approval_unavailable", "This request cannot be applied by this version.", 503
            )
        command.execute(session, Principal(actor.id, actor.name, actor.role, None), proposal)
    proposal.status = body.decision
    proposal.resolved_by = principal.user_id
    proposal.resolved_at = session.scalar(text("SELECT clock_timestamp()"))
    proposal.version += 1
    session.flush()
    notify_proposal(session, principal, proposal)
    result = project(proposal)
    session.add(
        AdminOperationDecision(
            proposal_id=proposal.id,
            actor_id=principal.user_id,
            actor_name=principal.name,
            request_key=key,
            request_sha256=fingerprint,
            result=result.model_dump(mode="json"),
        )
    )
    return result


@router.get("", response_model=list[AdminRequestView])
def list_requests(request: Request):
    """List all requests for the Owner, or only the originating Admin’s requests."""
    with authorized_transaction(request) as (session, principal):
        rows = bounded(
            session,
            private_query(principal).order_by(
                AdminOperationRequest.created_at.desc(), AdminOperationRequest.id
            ),
        )
        return [project(row) for row in rows]


@router.get("/decisions/{key}", response_model=AdminRequestView)
def recover_decision(key: UUID, request: Request):
    """Read the current actor’s original immutable approval-decision receipt."""
    with authorized_transaction(request, advisory_lock=SUPERVISION_LOCK) as (session, principal):
        principal.operations()
        receipt = session.scalar(
            select(AdminOperationDecision).where(
                AdminOperationDecision.actor_id == principal.user_id,
                AdminOperationDecision.request_key == key,
            )
        )
        if receipt is None:
            raise unavailable()
        return AdminRequestView.model_validate(receipt.result)


def decision_evidence(request, identity, decision):
    """Verify publication/Undo bytes outside locks, then recheck the frozen intent."""
    from app.api import exercise_library as library
    from app.api.library_routes import storage

    evidence, lock, undo_originals = None, None, []
    with authorized_transaction(request) as (session, principal):
        if decision != "cancelled":
            principal.owner()
        proposal = session.scalar(
            private_query(principal).where(AdminOperationRequest.id == identity)
        )
        if proposal is None:
            raise unavailable()
        if proposal.operation == "library.publish":
            lock = library.LIBRARY_LOCK
            if decision == "approved" and proposal.status == "pending":
                principal.owner()
                actor = session.get(StaffUser, proposal.actor_id)
                if actor is None or actor.role != "admin" or actor.status != "active":
                    raise conflict()
                _, evidence = library.preparation(
                    session, Principal(actor.id, actor.name, actor.role, None), proposal.request_key
                )
        elif proposal.operation.startswith("undo."):
            from app.api.request_cancellation import DECISION_LOCK
            from app.api.session_undo_review import inspect

            lock = DECISION_LOCK
            if decision == "approved" and proposal.status == "pending":
                actor = session.get(StaffUser, proposal.actor_id)
                if actor is None or actor.role != "admin" or actor.status != "active":
                    raise conflict()
                original_actor = Principal(actor.id, actor.name, actor.role, None)
                target_id = UUID(proposal.body["identity"])
                if proposal.operation == "undo.clientPackages":
                    from app.api.package_action_undo import inspect as inspect_package

                    undo_originals = [
                        library.evidence(row)
                        for row in inspect_package(session, original_actor, target_id)[4]
                    ]
                else:
                    undo_originals = inspect(session, original_actor, target_id)[3]

    if evidence is not None:
        storage(request).verified_bytes(evidence)
    for original in undo_originals:
        storage(request).verified_bytes(original)
    return evidence, lock, undo_originals


@router.post("/{identity}/decision", response_model=AdminRequestView)
def decide_request(identity: UUID, body: AdminDecision, request: Request, key: RequestKey):
    """Approve or reject as Owner, or cancel as the originating Admin; recheck current state."""
    from app.api.email_changes import bind_request_context

    evidence, lock, undo_originals = decision_evidence(request, identity, body.decision)
    with authorized_transaction(request, advisory_lock=lock) as (session, principal):
        bind_request_context(session, request)
        session.info["verified_library_publication"] = evidence
        session.info["verified_undo_originals"] = undo_originals
        result = decide(session, principal, identity, key, body)
    if result.status == "approved" and result.operation == "trainer.create":
        from app.api.trainer_creation import NewTrainer, complete

        @contextmanager
        def approved_actor(current_request):
            # Authenticate the deciding Owner on every provider transition, then recheck
            # the frozen grant and originating Admin. This is never a client principal override.
            with authorized_transaction(current_request) as (session, owner):
                owner.owner()
                proposal = session.scalar(
                    select(AdminOperationRequest)
                    .where(AdminOperationRequest.id == identity)
                    .with_for_update(read=True)
                )
                actor = session.scalar(
                    select(StaffUser)
                    .where(StaffUser.id == proposal.actor_id)
                    .with_for_update(read=True)
                )
                if (
                    proposal.status != "approved"
                    or proposal.operation != "trainer.create"
                    or actor is None
                    or actor.role != "admin"
                    or actor.status != "active"
                ):
                    raise conflict()
                yield session, Principal(actor.id, actor.name, actor.role, None)

        with approved_actor(request) as (session, actor):
            proposal = session.get(AdminOperationRequest, identity)
            original_key = proposal.request_key
            original_body = NewTrainer.model_validate(proposal.body["body"])
        complete(request, original_key, original_body, transaction=approved_actor)
    return result


@router.get("/{identity}/attachment", response_model=ReadLease)
def attachment(identity: UUID, request: Request):
    """Lease pending-proposal bytes privately and recheck before returning the URL."""
    from app.api.library_approval import review_attachment
    from app.api.library_routes import storage

    with authorized_transaction(request) as (session, principal):
        evidence, version = review_attachment(session, principal, identity)
    url = storage(request).download(evidence, 60)
    with authorized_transaction(request) as (session, principal):
        if review_attachment(session, principal, identity) != (evidence, version):
            raise conflict()
    return ReadLease(
        url=url,
        sha256=evidence.sha256,
        size=evidence.size,
        type=evidence.content_type,
        version=version,
    )


@router.get("/{identity}/attachment/check", response_model=MediaReadCheck)
def check_attachment(identity: UUID, version: int, request: Request):
    """Recheck proposal visibility after the browser verifies downloaded bytes."""
    from app.api.library_approval import review_attachment

    with authorized_transaction(request) as (session, principal):
        _, current = review_attachment(session, principal, identity)
        if version != current:
            raise conflict()
    return MediaReadCheck(valid=True)
