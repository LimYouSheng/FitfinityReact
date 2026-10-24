"""Private recording leases never hold database locks during external object IO."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from fastapi import APIRouter, Request

from app.api import session_media as recordings
from app.api.dependencies import authorized_transaction
from app.api.library_routes import storage
from app.api.library_schemas import MediaReadCheck, OriginalLibraryAction, ReadLease, UploadLease
from app.api.request_cancellation import DECISION_LOCK
from app.api.routes import RequestKey
from app.api.schemas import ERROR_RESPONSES
from app.api.session_media_schemas import (
    RecordingIntent,
    RecordingReview,
    RecordingSaved,
    SaveRecording,
)
from app.authorization import conflict

router = APIRouter(tags=["session recordings"], responses=ERROR_RESPONSES)


@router.get(
    "/api/sessions/{identity}/exercises/{item_id}/video/review", response_model=RecordingReview
)
def review(identity: UUID, item_id: UUID, request: Request):
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        return recordings.inspect(session, principal, identity, item_id)[0]


@router.post("/api/session-media/intents", response_model=RecordingIntent)
def reserve(body: SaveRecording, request: Request, key: RequestKey):
    if body.upload:
        storage(request)
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        return recordings.reserve(
            session, principal, key, body, request.app.state.auth_settings.media_bucket
        )


@router.get("/api/session-media/intents/{key}", response_model=RecordingIntent)
def recover(key: UUID, request: Request):
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        return recordings.view(recordings.original(session, principal, key))


@router.post("/api/session-media/intents/{key}/upload", response_model=UploadLease)
def upload(key: UUID, body: OriginalLibraryAction, request: Request, request_key: RequestKey):
    if key != request_key:
        raise conflict()
    store = storage(request)
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        original, checked = recordings.preparation(session, principal, key)
        lifetime = int((original.upload_until - recordings.clock(session)).total_seconds())
        if original.state != "pending" or checked is None or lifetime < 1:
            raise conflict()
        deadline = original.upload_until
    return store.upload(checked, min(300, lifetime), deadline=deadline)


@router.post("/api/session-media/intents/{key}/commit", response_model=RecordingSaved)
def commit(key: UUID, body: OriginalLibraryAction, request: Request, request_key: RequestKey):
    if key != request_key:
        raise conflict()
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        original, checked = recordings.preparation(session, principal, key)
        if original.state == "completed":
            return original.result
    if checked:
        storage(request).verified_bytes(checked)
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        return recordings.commit(session, principal, key, checked)


@router.get("/api/sessions/{identity}/exercises/{item_id}/video", response_model=ReadLease | None)
def read(identity: UUID, item_id: UUID, request: Request):
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        original = recordings.readable(session, principal, identity, item_id)
        if original is None:
            return None
        checked, version, deadline = original
        lifetime = min(60, int((deadline - recordings.clock(session)).total_seconds()))
    if lifetime < 1:
        return None
    url = storage(request).download(checked, lifetime)
    query = parse_qs(urlsplit(url).query)
    signed = datetime.strptime(query["X-Amz-Date"][0], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    if signed + timedelta(seconds=int(query["X-Amz-Expires"][0])) > deadline:
        raise conflict()
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        if recordings.readable(session, principal, identity, item_id) != original:
            raise conflict()
    return ReadLease(
        url=url,
        sha256=checked.sha256,
        size=checked.size,
        type=checked.content_type,
        version=version,
    )


@router.get(
    "/api/sessions/{identity}/exercises/{item_id}/video/check", response_model=MediaReadCheck
)
def recheck(identity: UUID, item_id: UUID, version: int, request: Request):
    with authorized_transaction(request, advisory_lock=DECISION_LOCK) as (session, principal):
        current = recordings.readable(session, principal, identity, item_id)
        if current is None or current[1] != version:
            raise conflict()
        return {"valid": True}
