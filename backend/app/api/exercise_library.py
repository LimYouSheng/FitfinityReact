"""Private original save intents; external object IO occurs between authorized transactions."""

import hashlib
import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from app.api.directory import bounded
from app.api.library_schemas import Catalogue, LibraryExercise, LibraryIntentView, LibraryMedia
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.media_storage import ObjectEvidence
from app.models.communications import Message, MessageReceipt
from app.models.media import LibrarySaveIntent, MediaAsset, MediaDeletion
from app.models.people import StaffUser
from app.models.training import Exercise

# Serialize catalogue name/intent decisions before actor locks; no object IO under this lock.
LIBRARY_LOCK = 4670024101


def evidence(asset):
    return ObjectEvidence(
        asset.bucket, asset.object_key, asset.content_type, asset.size_bytes, asset.content_sha256
    )


def project(session, exercise):
    media = session.get(MediaAsset, exercise.media_id) if exercise.media_id else None
    return LibraryExercise(
        id=exercise.id,
        name=exercise.name,
        category=exercise.category,
        description=exercise.description,
        status=exercise.status,
        version=exercise.version,
        createdAt=exercise.created_at,
        updatedAt=exercise.updated_at,
        media=LibraryMedia(
            id=media.id,
            name=media.original_filename,
            type=media.content_type,
            size=media.size_bytes,
        )
        if media
        else None,
    )


def catalogue(session, principal):
    query = select(Exercise).order_by(Exercise.created_at.desc(), Exercise.id)
    if not principal.manages_operations:
        query = query.where(Exercise.status == "active")
    return Catalogue(items=[project(session, row) for row in bounded(session, query)])


def original(session, principal, key):
    principal.operations()
    row = session.scalar(
        select(LibrarySaveIntent)
        .where(
            LibrarySaveIntent.actor_id == principal.user_id,
            LibrarySaveIntent.request_key == key,
        )
        .with_for_update()
    )
    if row is None:
        raise unavailable()
    return row


def view(row):
    return LibraryIntentView(
        key=row.request_key, state=row.state, uploadUntil=row.upload_until, result=row.result
    )


def target(session, identity, expected):
    row = session.scalar(select(Exercise).where(Exercise.id == identity).with_for_update())
    if expected is None:
        if row is not None:
            raise conflict()
    elif row is None or row.version != expected:
        raise conflict()
    return row


def unique_name(session, identity, name):
    # Collapse whitespace just as the approved UI does, including older stored names.
    normalized = " ".join(name.split()).lower()
    for row in bounded(session, select(Exercise)):
        if row.id != identity and " ".join(row.name.split()).lower() == normalized:
            raise AuthError("exercise_name_conflict", "This exercise name is already in use.", 409)


def reserve(session, principal, key, body, bucket):
    """Allocate an invisible draft and immutable object key without publishing missing bytes."""
    principal.operations()
    digest = hashlib.sha256(
        json.dumps(body.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()
    found = session.scalar(
        select(LibrarySaveIntent)
        .where(
            LibrarySaveIntent.actor_id == principal.user_id,
            LibrarySaveIntent.request_key == key,
        )
        .with_for_update()
    )
    if found:
        if found.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "This key belongs to another save.", 409)
        return view(found)
    identity = body.id or uuid4()
    target(session, identity, body.expectedVersion)
    unique_name(session, identity, body.name)
    now = session.scalar(select(func.clock_timestamp()))
    upload_id = None
    if body.upload:
        if not bucket:
            raise AuthError("media_unavailable", "Protected media is not configured.", 503)
        upload_id = uuid4()
        session.add(
            MediaAsset(
                id=upload_id,
                purpose="exercise_media",
                status="pending",
                bucket=bucket,
                object_key=f"library/{upload_id}",
                original_filename=body.upload.name,
                content_type=body.upload.type,
                size_bytes=body.upload.size,
                content_sha256=body.upload.sha256,
                uploaded_by=principal.user_id,
            )
        )
        session.flush()
    row = LibrarySaveIntent(
        request_key=key,
        request_sha256=digest,
        exercise_id=identity,
        expected_version=body.expectedVersion,
        name=body.name,
        category=body.category,
        description=body.description,
        exercise_status=body.status,
        remove_media=body.removeMedia,
        upload_id=upload_id,
        upload_until=now + timedelta(minutes=5),
        state="pending",
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(row)
    session.flush()
    return view(row)


def preparation(session, principal, key):
    """Return only frozen storage evidence; the caller releases DB locks before network IO."""
    row = original(session, principal, key)
    if row.state == "completed":
        return view(row), None
    if row.state != "pending":
        raise conflict()
    target(session, row.exercise_id, row.expected_version)
    asset = session.get(MediaAsset, row.upload_id) if row.upload_id else None
    if asset and asset.status != "pending":
        raise conflict()
    return view(row), evidence(asset) if asset else None


def commit(session, principal, key, verified):
    """Recheck authority/version after storage; publish metadata, notice and receipt atomically."""
    row = original(session, principal, key)
    if row.state == "completed":
        return LibraryExercise.model_validate(row.result)
    if row.state != "pending":
        raise conflict()
    current = target(session, row.exercise_id, row.expected_version)
    unique_name(session, row.exercise_id, row.name)
    previous_id = current.media_id if current else None
    asset = (
        session.scalar(select(MediaAsset).where(MediaAsset.id == row.upload_id).with_for_update())
        if row.upload_id
        else None
    )
    if asset:
        if asset.status != "pending" or evidence(asset) != verified:
            raise conflict()
        asset.status = "ready"
    elif verified is not None:
        raise conflict()
    if current is None:
        current = Exercise(id=row.exercise_id)
        session.add(current)
    current.name, current.category = row.name, row.category
    current.description, current.status = row.description, row.exercise_status
    current.media_id = row.upload_id if asset else None if row.remove_media else previous_id
    if previous_id and previous_id != current.media_id:
        previous = session.get(MediaAsset, previous_id, with_for_update=True)
        previous.status = "delete_pending"
        upload_until = session.scalar(
            select(LibrarySaveIntent.upload_until).where(LibrarySaveIntent.upload_id == previous_id)
        )
        now = session.scalar(select(func.clock_timestamp()))
        session.add(
            MediaDeletion(
                media_id=previous_id,
                reason="replaced" if asset else "removed",
                next_attempt_at=max(now, upload_until or now),
            )
        )
    # Mappers intentionally have no ORM relationships; establish the referenced row first.
    session.flush()
    notice = Message(
        id=uuid4(),
        kind="exercise_library_update",
        title=f"Exercise saved: {row.name}",
        body=f"{row.category}. Existing saved session plans are preserved.",
        exercise_id=current.id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    for user_id in session.scalars(
        select(StaffUser.id).where(
            StaffUser.status == "active",
            (StaffUser.role == "owner") | (StaffUser.id == principal.user_id),
        )
    ):
        session.add(MessageReceipt(message_id=notice.id, user_id=user_id))
    saved = project(session, current)
    row.state, row.result = "completed", saved.model_dump(mode="json")
    session.flush()
    return saved


def readable(session, principal, media_id):
    """Current attachment and role both govern every read and post-fetch recheck."""
    query = select(Exercise).where(Exercise.media_id == media_id)
    if not principal.manages_operations:
        query = query.where(Exercise.status == "active")
    row = session.scalar(query.with_for_update(read=True))
    asset = session.get(MediaAsset, media_id) if row else None
    if asset is None or asset.status != "ready" or asset.purpose != "exercise_media":
        raise unavailable()
    return evidence(asset), row.version
