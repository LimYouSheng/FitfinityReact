"""Current authority and typed dependency checks precede any compensating write."""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.api import messages
from app.api.exercise_library import evidence
from app.api.package_action_review import digest
from app.api.remuneration import cycle_for
from app.api.session_mutation_journal import FIELDS, SOURCES, scope_digest, semantic, values
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models import communications, media, people, training
from app.models.evidence import RemunerationApproval
from app.models.session_mutations import MutationScope, SessionMutation, SessionMutationUndo


def clock(session):
    return session.scalar(select(func.clock_timestamp()))


def pairs(session, identity):
    """Lock affected records in lifecycle order before reading persisted comparison values."""
    result = []
    priority = {people.Client: 0, training.PackagePurchase: 1, training.TrainingSession: 2}
    for model in sorted(SOURCES, key=lambda item: priority.get(item, 3)):
        snapshot = SOURCES[model]
        records = session.scalars(select(snapshot).where(snapshot.mutation_id == identity)).all()
        grouped = {}
        for row in records:
            grouped.setdefault(row.entity_id, {})[row.side] = {
                name: getattr(row, name) for name in FIELDS[model]
            }
        if not grouped:
            continue
        session.execute(
            select(model.id).where(model.id.in_(grouped)).order_by(model.id).with_for_update()
        ).all()
        current = values(session, model, grouped)
        for entity_id, sides in grouped.items():
            result.append(
                (model, entity_id, sides.get("before"), sides.get("after"), current.get(entity_id))
            )
    return result


def authority(session, principal, mutation):
    if principal.manages_operations:
        return
    if (
        principal.role != "trainer"
        or mutation.actor_role != "trainer"
        or principal.user_id != mutation.actor_id
    ):
        raise unavailable()
    trainer = session.get(people.Trainer, principal.trainer_id)
    if trainer is None or trainer.status != "active":
        raise unavailable()


def inspect(session, principal, identity):
    """Bind one current review, including original media leases for the subsequent IO phase."""
    mutation = session.get(SessionMutation, identity)
    if mutation is None:
        raise unavailable()
    messages.visible_message(session, principal, mutation.message_id)
    authority(session, principal, mutation)
    now = clock(session)
    if mutation.expires_at <= now or session.scalar(
        select(SessionMutationUndo.id).where(SessionMutationUndo.mutation_id == identity)
    ):
        raise conflict()
    changes = pairs(session, identity)
    if not changes:
        raise conflict()
    for _, _, _, after, current in changes:
        if semantic(current) != semantic(after):
            raise AuthError(
                "undo_stale", "A related record changed. Review the later change before Undo.", 409
            )
    scopes = session.scalars(
        select(MutationScope).where(MutationScope.mutation_id == identity)
    ).all()
    for scope in scopes:
        if (
            scope_digest(
                session,
                client_id=scope.client_id,
                trainer_id=scope.trainer_id,
                session_id=scope.session_id,
            )
            != scope.sha256
        ):
            raise conflict()
    bookings = [entry for entry in changes if entry[0] is training.TrainingSession]
    requests = {
        entity_id for model, entity_id, _, _, _ in changes if model is communications.ChangeRequest
    }
    client_ids = {entry[4]["client_id"] for entry in bookings}
    session_ids = {entry[1] for entry in bookings}
    if session.scalar(
        select(communications.ChangeRequest.id)
        .where(
            communications.ChangeRequest.status == "pending",
            communications.ChangeRequest.id.not_in(requests),
            communications.ChangeRequest.session_id.in_(session_ids)
            | (
                (communications.ChangeRequest.kind == "fixed_weekly_schedule")
                & communications.ChangeRequest.client_id.in_(client_ids)
            ),
        )
        .limit(1)
    ):
        raise conflict()
    local = now.astimezone(ZoneInfo("Asia/Singapore")).replace(tzinfo=None)
    for _, _, before, after, current in bookings:
        if before is None or after is None:
            raise conflict()  # Package creation/deletion retains its separate lifecycle owner.
        substantive = any(
            before[name] != after[name]
            for name in FIELDS[training.TrainingSession]
            if name not in {"version", "session_number"}
        )
        if (
            not principal.manages_operations
            and substantive
            and current["trainer_id"] != principal.trainer_id
        ):
            raise unavailable()
        client = session.get(people.Client, current["client_id"])
        purchase = session.get(training.PackagePurchase, current["purchase_id"])
        lifecycle = (
            mutation.operation.startswith("client.") or mutation.operation == "trainer.deactivate"
        )
        if not lifecycle and (client.status != "active" or purchase.status != "active"):
            raise conflict()
        pay_fields = {"training_date", "starts_at", "ends_at", "trainer_id", "status"}
        if any(before[name] != after[name] for name in pay_fields):
            for row in (before, after):
                if row["training_date"] and session.scalar(
                    select(RemunerationApproval.id)
                    .where(
                        RemunerationApproval.trainer_id == row["trainer_id"],
                        RemunerationApproval.cycle_key == cycle_for(row["training_date"]),
                    )
                    .limit(1)
                ):
                    raise AuthError(
                        "undo_pay_approved",
                        "This change affects approved remuneration. "
                        "An owner payment adjustment is required.",
                        409,
                    )
        schedule_fields = {"training_date", "starts_at", "ends_at", "trainer_id", "schedule_state"}
        changed_schedule = any(before[name] != after[name] for name in schedule_fields)
        if changed_schedule:
            if any(
                row["schedule_state"] == "booked"
                and datetime.combine(row["training_date"], row["starts_at"]) <= local
                for row in (before, after)
            ):
                raise AuthError(
                    "undo_started",
                    "A session has already started. Its schedule cannot be restored.",
                    409,
                )
            for table in (training.Acknowledgement, training.CreditDebit):
                if session.scalar(
                    select(table.id).where(table.session_id.in_(session_ids)).limit(1)
                ):
                    raise conflict()
            if not principal.manages_operations and mutation.operation != "client.weekly":
                trainer = session.get(people.Trainer, principal.trainer_id)
                policy = (
                    trainer.approve_session_trainer
                    if before["trainer_id"] != after["trainer_id"]
                    else trainer.approve_session_time
                )
                if policy:
                    raise AuthError(
                        "undo_approval",
                        "Owner/Admin approval is now required to reverse this change.",
                        409,
                    )
        if mutation.operation == "client.weekly" and not principal.manages_operations:
            if session.get(people.Trainer, principal.trainer_id).approve_weekly_schedule:
                raise conflict()
    originals = []
    for model, entity_id, before, _after, _current in changes:
        if (
            model is not media.MediaAsset
            or before is None
            or before["status"] != "ready"
            or before["session_id"] is None
        ):
            continue
        asset = session.get(media.MediaAsset, entity_id)
        if asset.status != "ready" or asset.expires_at <= now:
            raise AuthError("undo_media_expired", "Original media is unavailable or expired.", 409)
        cleanup = session.scalar(
            select(media.MediaDeletion)
            .where(media.MediaDeletion.media_id == entity_id)
            .with_for_update()
        )
        if cleanup and (cleanup.status != "pending" or cleanup.lease_until is not None):
            raise conflict()
        originals.append(evidence(asset))
    expected = digest(
        {
            "mutation": identity,
            "rows": [
                [model.__tablename__, entity_id, current]
                for model, entity_id, _, _, current in changes
            ],
            "media": [item.__dict__ for item in originals],
        }
    )
    view = {
        "id": identity,
        "messageId": mutation.message_id,
        "expected": expected,
        "expiresAt": mutation.expires_at,
        "count": len(bookings),
    }
    return view, mutation, changes, originals
