"""Authenticated package actions use the shared decision lock before actor locks."""

from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api import (
    package_action_review,
    package_action_save,
    package_action_undo,
    session_undo_approval,
)
from app.api.admin_supervision import ApprovalPending
from app.api.dependencies import authorized_transaction
from app.api.exercise_library import evidence
from app.api.library_routes import storage
from app.api.package_action_schemas import (
    Operation,
    PackageActionReview,
    PackageActionState,
    PackageUndoReview,
    PackageUndoState,
    SavePackageAction,
    UndoPackageDeletion,
)
from app.api.request_cancellation import DECISION_LOCK
from app.api.routes import RequestKey
from app.api.schemas import ERROR_RESPONSES
from app.models.package_actions import PackageDeletionUndo

router = APIRouter(tags=["package session lifecycle"], responses=ERROR_RESPONSES)


@router.get(
    "/api/clients/{client_id}/purchases/{purchase_id}/action-review",
    response_model=PackageActionReview,
    operation_id="reviewPackageAction",
)
def review(client_id: UUID, purchase_id: UUID, operation: Operation, request: Request):
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        return package_action_review.review(session, principal, client_id, purchase_id, operation)[
            0
        ]


@router.post(
    "/api/clients/{client_id}/purchases/{purchase_id}/actions",
    response_model=PackageActionState,
    operation_id="savePackageAction",
    responses={202: {"model": ApprovalPending}},
)
def save(
    client_id: UUID, purchase_id: UUID, body: SavePackageAction, request: Request, key: RequestKey
):
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        return package_action_save.save(session, principal, client_id, purchase_id, key, body)


@router.get(
    "/api/package-actions/{key}",
    response_model=PackageActionState,
    operation_id="reconcilePackageAction",
    responses={202: {"model": ApprovalPending}},
)
def reconcile(key: UUID, request: Request):
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        return package_action_save.reconcile(session, principal, key)


@router.get("/api/package-actions/{identity}/undo-review", response_model=PackageUndoReview)
def undo_review(identity: UUID, request: Request):
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        return package_action_undo.inspect(session, principal, identity)[0]


@router.post(
    "/api/package-actions/{identity}/undo",
    response_model=PackageUndoState,
    responses={202: {"model": ApprovalPending}},
)
def undo(identity: UUID, body: UndoPackageDeletion, request: Request, key: RequestKey):
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        principal.operations()
        saved = session.scalar(
            select(PackageDeletionUndo.id).where(
                PackageDeletionUndo.actor_id == principal.user_id,
                PackageDeletionUndo.request_key == key,
            )
        )
        if saved:
            return package_action_undo.commit(session, principal, identity, key, body, [])
        inspected = package_action_undo.inspect(session, principal, identity)
        checked = [evidence(row) for row in inspected[4]]
    for original in checked:
        storage(request).verified_bytes(original)
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        session.info["verified_undo_originals"] = checked
        return session_undo_approval.restore_package(session, principal, identity, key, body)


@router.get(
    "/api/package-undos/{key}",
    response_model=PackageUndoState,
    responses={202: {"model": ApprovalPending}},
)
def undo_reconcile(key: UUID, request: Request):
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        return session_undo_approval.reconcile_package(session, principal, key)
