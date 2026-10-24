"""Review and compensate permitted changes; external media IO stays outside DB locks."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import Field, StrictStr

from app.api import session_undo_review, session_undo_save
from app.api.dependencies import authorized_transaction
from app.api.library_routes import storage
from app.api.request_cancellation import DECISION_LOCK
from app.api.routes import RequestKey
from app.api.schemas import ERROR_RESPONSES, Contract

router = APIRouter(tags=["permitted session Undo"], responses=ERROR_RESPONSES)


class UndoReview(Contract):
    id: UUID
    messageId: UUID
    expected: str
    expiresAt: datetime
    count: int


class UndoChange(Contract):
    expected: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class UndoSaved(Contract):
    id: UUID
    actionId: UUID
    status: Literal["undone"]
    undoneAt: datetime


@router.get("/api/session-changes/{identity}/undo-review", response_model=UndoReview)
def review(identity: UUID, request: Request):
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        return session_undo_review.inspect(session, principal, identity)[0]


@router.post("/api/session-changes/{identity}/undo", response_model=UndoSaved)
def undo(identity: UUID, body: UndoChange, request: Request, key: RequestKey):
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        if session_undo_save.original(session, principal, key):
            return session_undo_save.commit(session, principal, identity, key, body, [])
        checked = session_undo_review.inspect(session, principal, identity)[3]
    for item in checked:
        storage(request).verified_bytes(item)
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        return session_undo_save.commit(session, principal, identity, key, body, checked)


@router.get("/api/session-undos/{key}", response_model=UndoSaved)
def reconcile(key: UUID, request: Request):
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        return session_undo_save.reconcile(session, principal, key)
