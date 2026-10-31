"""Approve publication of a frozen library save; upload and verification stay separate."""

from sqlalchemy import select, text

from app.api import exercise_library as library
from app.api.admin_supervision import proposal_outcome, supervised
from app.api.library_schemas import OriginalLibraryAction
from app.authorization import conflict
from app.models.admin_requests import AdminOperationRequest
from app.models.media import LibrarySaveIntent, MediaAsset


def receipt(session, principal, key):
    return session.scalar(
        select(LibrarySaveIntent).where(
            LibrarySaveIntent.actor_id == principal.user_id,
            LibrarySaveIntent.request_key == key,
            LibrarySaveIntent.state == "completed",
        )
    )


@supervised("exerciseLibrary", "library.publish", OriginalLibraryAction, receipt=receipt)
def publish(session, principal, key, body):
    """Publish only the originally verified bytes after current catalogue checks."""
    session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": library.LIBRARY_LOCK})
    original, expected = library.preparation(session, principal, key)
    if original.state == "completed":
        return original.result
    if expected != session.info.get("verified_library_publication"):
        raise conflict()
    return library.commit(session, principal, key, expected)


def recovery(session, principal, key):
    proposal = proposal_outcome(session, principal, key, "library.publish")
    return (
        proposal
        if proposal is not None
        else library.view(library.original(session, principal, key))
    )


def held_for_review():
    """Pending Owner review retains uploaded bytes without extending upload URL leases."""
    return (
        select(AdminOperationRequest.id)
        .where(
            AdminOperationRequest.operation == "library.publish",
            AdminOperationRequest.status == "pending",
            AdminOperationRequest.actor_id == LibrarySaveIntent.actor_id,
            AdminOperationRequest.request_key == LibrarySaveIntent.request_key,
        )
        .exists()
    )


def snapshot(session, principal, key):
    intent = library.original(session, principal, key)
    current = library.target(session, intent.exercise_id, intent.expected_version)
    asset = session.get(MediaAsset, intent.upload_id) if intent.upload_id else None
    return {
        "subject": intent.name,
        "before": library.project(session, current).model_dump(mode="json") if current else None,
        "proposed": {
            "name": intent.name,
            "category": intent.category,
            "description": intent.description,
            "status": intent.exercise_status,
            "removeMedia": intent.remove_media,
            "attachment": {
                "id": str(asset.id),
                "name": asset.original_filename,
                "type": asset.content_type,
                "size": asset.size_bytes,
            }
            if asset
            else None,
        },
    }


def review_attachment(session, principal, identity):
    """Only the Owner/originating Admin can preview a pending proposal's immutable upload."""
    from app.api.admin_requests import private_query
    from app.authorization import unavailable

    proposal = session.scalar(private_query(principal).where(AdminOperationRequest.id == identity))
    if proposal is None or proposal.operation != "library.publish" or proposal.status != "pending":
        raise unavailable()
    intent = session.scalar(
        select(LibrarySaveIntent).where(
            LibrarySaveIntent.actor_id == proposal.actor_id,
            LibrarySaveIntent.request_key == proposal.request_key,
        )
    )
    asset = session.get(MediaAsset, intent.upload_id) if intent and intent.upload_id else None
    if asset is None or asset.status != "pending":
        raise unavailable()
    return library.evidence(asset), proposal.version
