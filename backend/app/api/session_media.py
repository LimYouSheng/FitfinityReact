"""Recording publication rechecks current domain authority after private object verification."""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from app.api import session_plans
from app.api.exercise_library import evidence
from app.api.package_action_review import digest
from app.api.session_media_schemas import (
    RecordingIntent,
    RecordingMedia,
    RecordingReview,
    RecordingSaved,
)
from app.api.session_mutation_journal import journal
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.communications import Message, MessageReceipt, SessionEvent
from app.models.media import MediaAsset, MediaDeletion
from app.models.people import StaffUser, Trainer
from app.models.session_media import SessionMediaIntent


def clock(session):
    return session.scalar(select(func.now()))


def project(session, asset):
    if asset is None:
        return None
    original = session.scalar(
        select(SessionMediaIntent).where(
            SessionMediaIntent.upload_id == asset.id, SessionMediaIntent.state == "completed"
        )
    )
    return RecordingMedia(
        id=asset.id,
        name=asset.original_filename,
        type=asset.content_type,
        size=asset.size_bytes,
        attachedAt=original.completed_at if original else asset.created_at,
        expiresAt=asset.expires_at,
    )


def inspect(session, principal, identity, item_id, *, write=False):
    """Current scope, active plan ownership and media expiry are part of every review."""
    plan, booking, rows, _ = session_plans.inspect(session, principal, identity, write=write)
    item = next((row for row in rows if row.id == item_id and row.retired_at is None), None)
    if item is None:
        raise unavailable()
    assets = session.scalars(
        select(MediaAsset)
        .where(
            MediaAsset.session_id == identity,
            MediaAsset.original_session_id == identity,
            MediaAsset.original_plan_item_id == item_id,
            MediaAsset.purpose == "session_video",
            MediaAsset.status == "ready",
        )
        .order_by(MediaAsset.id)
        .with_for_update()
    ).all()
    if len(assets) > 1:
        raise conflict()
    asset = assets[0] if assets else None
    live = asset if asset and asset.expires_at > clock(session) else None
    expected = digest(
        {
            "plan": plan.expected,
            "item": item_id,
            "asset": [asset.id, asset.version, asset.expires_at, live is not None]
            if asset
            else None,
        }
    )
    return (
        RecordingReview(
            sessionId=identity,
            exerciseId=item_id,
            version=booking.version,
            expected=expected,
            media=project(session, live),
        ),
        booking,
        item,
        asset,
    )


def original(session, principal, key):
    row = session.scalar(
        select(SessionMediaIntent)
        .where(
            SessionMediaIntent.actor_id == principal.user_id, SessionMediaIntent.request_key == key
        )
        .with_for_update()
    )
    if row is None:
        raise unavailable()
    return row


def view(row):
    return RecordingIntent(
        key=row.request_key, state=row.state, uploadUntil=row.upload_until, result=row.result
    )


def reserve(session, principal, key, body, bucket):
    """Reserve only a reviewed writable target; the private original command cannot drift."""
    fingerprint = digest(body.model_dump(mode="json"))
    found = session.scalar(
        select(SessionMediaIntent)
        .where(
            SessionMediaIntent.actor_id == principal.user_id, SessionMediaIntent.request_key == key
        )
        .with_for_update()
    )
    if found:
        if found.request_sha256 != fingerprint:
            raise AuthError("idempotency_conflict", "Check the original recording save.", 409)
        return view(found)
    reviewed, booking, _, previous = inspect(
        session, principal, body.sessionId, body.exerciseId, write=True
    )
    if reviewed.expected != body.expected:
        raise conflict()
    now = clock(session)
    asset_id = None
    if body.upload:
        if not bucket:
            raise AuthError("MEDIA_UNAVAILABLE", "Protected recording storage is unavailable.", 503)
        asset_id = uuid4()
        session.add(
            MediaAsset(
                id=asset_id,
                purpose="session_video",
                status="pending",
                bucket=bucket,
                object_key=f"recordings/{asset_id}",
                original_filename=body.upload.name,
                content_type=body.upload.type,
                size_bytes=body.upload.size,
                content_sha256=body.upload.sha256,
                uploaded_by=principal.user_id,
                client_id=booking.client_id,
                purchase_id=booking.purchase_id,
                session_id=booking.id,
                original_session_id=booking.id,
                original_plan_item_id=body.exerciseId,
                expires_at=now + timedelta(days=7),
            )
        )
        session.flush()
    row = SessionMediaIntent(
        request_key=key,
        request_sha256=fingerprint,
        expected_sha256=body.expected,
        session_id=body.sessionId,
        plan_item_id=body.exerciseId,
        remove_media=body.remove,
        upload_id=asset_id,
        previous_media_id=previous.id if previous else None,
        duration_seconds=body.duration,
        source=body.source,
        caption=body.caption,
        processing_status=body.processingStatus,
        audio_included=body.audioIncluded,
        upload_until=now + timedelta(minutes=5),
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(row)
    session.flush()
    return view(row)


def preparation(session, principal, key):
    row = original(session, principal, key)
    if row.state == "completed":
        return row, None
    if row.state != "pending" or row.upload_until <= clock(session):
        raise AuthError("SAVE_EXPIRED", "The original recording save expired.", 409)
    reviewed, _, _, _ = inspect(session, principal, row.session_id, row.plan_item_id, write=True)
    if reviewed.expected != row.expected_sha256:
        raise conflict()
    asset = session.get(MediaAsset, row.upload_id) if row.upload_id else None
    if asset and (asset.status != "pending" or asset.session_id != row.session_id):
        raise conflict()
    return row, evidence(asset) if asset else None


def retire(session, asset, now, reason):
    """Deny new reads immediately, retaining original bytes through the permitted Undo hold."""
    asset.session_id = None
    work = session.scalar(
        select(MediaDeletion).where(MediaDeletion.media_id == asset.id).with_for_update()
    )
    due = min(now + timedelta(hours=24), asset.expires_at)
    original = session.scalar(
        select(SessionMediaIntent).where(SessionMediaIntent.upload_id == asset.id)
    )
    if original:
        due = max(due, original.upload_until)
    if work is None:
        session.add(MediaDeletion(media_id=asset.id, reason=reason, next_attempt_at=due))
    elif work.status != "done":
        work.next_attempt_at = max(work.next_attempt_at, due)


@journal("session.recording")
def commit(session, principal, key, checked):
    """Publish verified bytes and one receipt atomically, after the second authority check."""
    row, current = preparation(session, principal, key)
    if row.state == "completed":
        return RecordingSaved.model_validate(row.result)
    if current != checked:
        raise conflict()
    reviewed, booking, item, previous = inspect(
        session, principal, row.session_id, row.plan_item_id, write=True
    )
    if (previous.id if previous else None) != row.previous_media_id:
        raise conflict()
    now = clock(session)
    if previous:
        retire(session, previous, now, "removed" if row.remove_media else "replaced")
    asset = session.get(MediaAsset, row.upload_id) if row.upload_id else None
    if asset:
        asset.status, asset.expires_at = "ready", now + timedelta(days=7)
    booking.version += 1
    item.version += 1
    session.add(
        SessionEvent(
            session_id=booking.id,
            session_version=reviewed.version,
            kind="session_video_removed" if row.remove_media else "session_video_saved",
            note="Recording removed."
            if row.remove_media
            else "Private recording saved; processing acceptance remains separate.",
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    notice = Message(
        kind="session_updated",
        title="Session recording removed" if row.remove_media else "Session recording saved",
        body="The exercise plan remains unchanged.",
        client_id=booking.client_id,
        purchase_id=booking.purchase_id,
        session_id=booking.id,
        trainer_id=booking.trainer_id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    trainer_user = session.scalar(select(Trainer.user_id).where(Trainer.id == booking.trainer_id))
    recipients = session.scalars(
        select(StaffUser.id).where(
            StaffUser.status == "active",
            (StaffUser.role == "owner") | StaffUser.id.in_([principal.user_id, trainer_user]),
        )
    ).all()
    for identity in set(recipients):
        session.add(MessageReceipt(message_id=notice.id, user_id=identity))
    media = (
        RecordingMedia(
            id=asset.id,
            name=asset.original_filename,
            type=asset.content_type,
            size=asset.size_bytes,
            attachedAt=now,
            expiresAt=asset.expires_at,
        )
        if asset
        else None
    )
    result = RecordingSaved(
        sessionId=booking.id, exerciseId=item.id, version=booking.version, savedAt=now, media=media
    )
    row.state, row.completed_at, row.result = "completed", now, result.model_dump(mode="json")
    session.flush()
    return result


def readable(session, principal, identity, item_id):
    _, _, _, asset = inspect(session, principal, identity, item_id)
    if asset is None or asset.expires_at <= clock(session):
        return None
    return evidence(asset), asset.version, asset.expires_at
