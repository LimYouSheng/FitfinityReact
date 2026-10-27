"""Content HTTP registration; parent router retains shared API metadata."""

from uuid import UUID

from fastapi import APIRouter, Request

from app.api import content
from app.api.dependencies import authorized_transaction
from app.api.request_types import RequestKey

router = APIRouter()


@router.get("/content", response_model=list[content.ContentState], operation_id="staffContent")
def staff_content(request: Request):
    """Read the complete bounded staff content catalogue; never public website content."""
    with authorized_transaction(request) as (session, principal):
        return content.records(session, principal)


@router.post("/content", response_model=content.ContentState, operation_id="saveContent")
def save_content(body: content.SaveContent, request: Request, key: RequestKey):
    """Save reviewed staff content and its immutable receipt/Owner notice atomically."""
    with authorized_transaction(request) as (session, principal):
        return content.save(session, principal, key, body)


@router.get(
    "/content-saves/{request_key}",
    response_model=content.ContentState,
    operation_id="reconcileContent",
)
def reconcile_content(request_key: UUID, request: Request):
    """Read only this actor's original saved content after an interrupted response."""
    with authorized_transaction(request) as (session, principal):
        return content.reconcile(session, principal, request_key)
