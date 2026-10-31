"""Compensating writes follow the same Admin approval area as the original change."""

from pydantic import Field, StrictStr
from sqlalchemy import select

from app.api import package_action_undo, session_undo_review, session_undo_save
from app.api.admin_supervision import supervised, supervised_recovery
from app.api.package_action_schemas import UndoPackageDeletion
from app.api.schemas import Contract
from app.authorization import conflict, unavailable
from app.models.package_actions import PackageDeletionUndo
from app.models.session_mutations import SessionMutation

AREAS = {
    **dict.fromkeys(
        [
            "session.details",
            "session.change",
            "session.time",
            "session.trainer",
            "session.postpone",
            "client.weekly",
            "request.resolve",
        ],
        "sessionScheduling",
    ),
    **dict.fromkeys(
        ["session.plan", "session.copy_plan", "session.outcome", "session.summary"],
        "sessionContent",
    ),
    "client.assignment": "trainerAssignment",
    "client.deactivate": "clientLifecycle",
    "client.reactivate": "clientLifecycle",
    "trainer.deactivate": "trainerLifecycle",
    "trainer.reactivate": "trainerLifecycle",
}
# Uploads remain approval-free; Undo of legacy launch metadata does not launch a share.
EXEMPT = {"session.recording", "session.handoff"}


class UndoChange(Contract):
    expected: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


def command_for(area):
    """Register a fixed area, never a caller-selected permission or executable path."""

    @supervised(area, f"undo.{area}", UndoChange, receipt=session_undo_save.original, target=True)
    def apply(session, principal, identity, key, body):
        mutation = session.get(SessionMutation, identity)
        if mutation is None or AREAS.get(mutation.operation) != area:
            raise unavailable()
        return session_undo_save.commit(
            session,
            principal,
            identity,
            key,
            body,
            session.info.get("verified_undo_originals", []),
        )

    return apply


COMMANDS = {area: command_for(area) for area in sorted(set(AREAS.values()))}


def commit(session, principal, identity, key, body, checked):
    """Replay the original receipt or supervise this exact compensating intent."""
    if session_undo_save.original(session, principal, key):
        return session_undo_save.commit(session, principal, identity, key, body, checked)
    mutation = session.get(SessionMutation, identity)
    if mutation is None:
        raise unavailable()
    area = AREAS.get(mutation.operation)
    if principal.role != "admin" or mutation.operation in EXEMPT:
        return session_undo_save.commit(session, principal, identity, key, body, checked)
    if area is None:
        raise conflict()
    session.info["verified_undo_originals"] = checked
    return COMMANDS[area](session, principal, identity, key, body)


@supervised_recovery(*(f"undo.{area}" for area in COMMANDS))
def reconcile(session, principal, key):
    return session_undo_save.reconcile(session, principal, key)


def snapshot(session, principal, identity):
    """Expose the frozen before/after business fields only in the private approval review."""
    viewed, mutation, changes, _ = session_undo_review.inspect(session, principal, identity)
    return {
        "subject": f"Undo {mutation.operation}",
        "before": {"expiresAt": viewed["expiresAt"], "originalActor": mutation.actor_name},
        "proposed": [
            {"record": model.__tablename__, "id": entity_id, "current": after, "restore": before}
            for model, entity_id, before, after, _ in changes
        ],
    }


def package_receipt(session, principal, key):
    return session.scalar(
        select(PackageDeletionUndo).where(
            PackageDeletionUndo.actor_id == principal.user_id,
            PackageDeletionUndo.request_key == key,
        )
    )


@supervised(
    "clientPackages",
    "undo.clientPackages",
    UndoPackageDeletion,
    receipt=package_receipt,
    target=True,
)
def restore_package(session, principal, identity, key, body):
    """Restore reviewed deleted sessions without reactivating their purchase."""
    return package_action_undo.commit(
        session, principal, identity, key, body, session.info.get("verified_undo_originals", [])
    )


@supervised_recovery("undo.clientPackages")
def reconcile_package(session, principal, key):
    return package_action_undo.reconcile(session, principal, key)
