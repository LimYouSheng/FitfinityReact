"""Release DB locks around storage IO and re-enter current authority before publication."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request
from sqlalchemy import func, select

from app.api import exercise_library as library
from app.api.dependencies import authorized_transaction
from app.api.library_schemas import (
    Catalogue,
    LibraryExercise,
    LibraryIntentView,
    MediaReadCheck,
    OriginalLibraryAction,
    ReadLease,
    SaveLibrary,
    UploadLease,
)
from app.auth.errors import AuthError
from app.authorization import conflict
from app.media_storage import unavailable

router = APIRouter(prefix="/api", tags=["exercise library"])
RequestKey = Annotated[UUID, Header(alias="Idempotency-Key")]


def storage(request):
    value = getattr(request.app.state, "media", None)
    if value is None:
        raise unavailable()
    return value


@router.get("/exercise-library", response_model=Catalogue)
def catalogue(request: Request):
    with authorized_transaction(request, advisory_lock=library.LIBRARY_LOCK) as (session, actor):
        return library.catalogue(session, actor)


@router.post("/exercise-library/save-intents", response_model=LibraryIntentView)
def reserve(body: SaveLibrary, request: Request, key: RequestKey):
    if body.upload:
        storage(request)
    with authorized_transaction(request, advisory_lock=library.LIBRARY_LOCK) as (session, actor):
        return library.reserve(
            session, actor, key, body, request.app.state.auth_settings.media_bucket
        )


@router.get("/exercise-library/save-intents/{key}", response_model=LibraryIntentView)
def recover(key: UUID, request: Request):
    with authorized_transaction(request, advisory_lock=library.LIBRARY_LOCK) as (session, actor):
        return library.view(library.original(session, actor, key))


@router.post("/exercise-library/save-intents/{key}/upload", response_model=UploadLease)
def upload(key: UUID, body: OriginalLibraryAction, request: Request, request_key: RequestKey):
    if request_key != key:
        raise conflict()
    store = storage(request)
    with authorized_transaction(request, advisory_lock=library.LIBRARY_LOCK) as (session, actor):
        original, evidence = library.preparation(session, actor, key)
        now = session.scalar(select(func.clock_timestamp()))
        lifetime = int((original.uploadUntil - now).total_seconds())
        if original.state != "pending" or evidence is None or lifetime < 1:
            raise conflict()
    # Every issued URL ends no later than the original fixed deadline.
    return store.upload(evidence, min(300, lifetime), deadline=original.uploadUntil)


@router.post("/exercise-library/save-intents/{key}/commit", response_model=LibraryExercise)
def commit(key: UUID, body: OriginalLibraryAction, request: Request, request_key: RequestKey):
    if request_key != key:
        raise conflict()
    with authorized_transaction(request, advisory_lock=library.LIBRARY_LOCK) as (session, actor):
        original, evidence = library.preparation(session, actor, key)
        if original.state == "completed":
            return original.result
    if evidence:
        storage(request).verified_bytes(evidence)
    with authorized_transaction(request, advisory_lock=library.LIBRARY_LOCK) as (session, actor):
        return library.commit(session, actor, key, evidence)


@router.get("/exercise-library/media/{identity}", response_model=ReadLease)
def read(identity: UUID, request: Request):
    store = storage(request)
    with authorized_transaction(request, advisory_lock=library.LIBRARY_LOCK) as (session, actor):
        evidence, version = library.readable(session, actor, identity)
    url = store.download(evidence, 60)
    with authorized_transaction(request, advisory_lock=library.LIBRARY_LOCK) as (session, actor):
        current, current_version = library.readable(session, actor, identity)
        if current != evidence or current_version != version:
            raise conflict()
    return ReadLease(
        url=url,
        sha256=evidence.sha256,
        size=evidence.size,
        type=evidence.content_type,
        version=version,
    )


@router.get("/exercise-library/media/{identity}/check", response_model=MediaReadCheck)
def recheck(identity: UUID, version: int, request: Request):
    with authorized_transaction(request, advisory_lock=library.LIBRARY_LOCK) as (session, actor):
        _, current = library.readable(session, actor, identity)
        if version != current:
            raise AuthError("media_changed", "This attachment changed. Refresh the exercise.", 409)
    return {"valid": True}
