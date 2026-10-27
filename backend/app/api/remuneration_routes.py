"""Remuneration HTTP registration; parent router retains shared API metadata."""

from uuid import UUID

from fastapi import APIRouter, Request

from app.api import remuneration, remuneration_schemas
from app.api.dependencies import authorized_transaction
from app.api.request_types import RequestKey

router = APIRouter()


@router.get("/remuneration", response_model=list[remuneration_schemas.PayView])
def list_remuneration(request: Request):
    """Owner all-trainer or Trainer self-only cycles; Admin financial access is forbidden."""
    with authorized_transaction(request, advisory_lock=remuneration.DECISION_LOCK) as (
        session,
        principal,
    ):
        return remuneration.listing(session, principal)


@router.get("/remuneration/{cycle_key}/{trainer_id}", response_model=remuneration_schemas.PayRecord)
def remuneration_detail(cycle_key: str, trainer_id: UUID, request: Request):
    """Current calculation alongside immutable approved amounts and later evidence differences."""
    with authorized_transaction(request, advisory_lock=remuneration.DECISION_LOCK) as (
        session,
        principal,
    ):
        return remuneration.detail(session, principal, cycle_key, trainer_id)


@router.post(
    "/remuneration/{cycle_key}/{trainer_id}/approval", response_model=remuneration_schemas.PaySaved
)
def approve_remuneration(
    cycle_key: str,
    trainer_id: UUID,
    body: remuneration_schemas.ApprovePay,
    request: Request,
    key: RequestKey,
):
    """Owner approval binds the reviewed source and atomically records immutable pay evidence."""
    with authorized_transaction(request, advisory_lock=remuneration.DECISION_LOCK) as (
        session,
        principal,
    ):
        return remuneration.approve(session, principal, cycle_key, trainer_id, key, body)


@router.get("/remuneration-approvals/{request_key}", response_model=remuneration_schemas.PaySaved)
def remuneration_approval_receipt(request_key: UUID, request: Request):
    """Original active Owner can recover an approval without repeating its financial effect."""
    with authorized_transaction(request, advisory_lock=remuneration.DECISION_LOCK) as (
        session,
        principal,
    ):
        return remuneration.reconcile(session, principal, request_key)
