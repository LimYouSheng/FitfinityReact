"""Capture typed compensation evidence inside an explicitly selected domain transaction."""

from datetime import timedelta
from functools import wraps
from inspect import signature
from uuid import uuid4

from sqlalchemy import event, func, select

from app.api.package_action_review import digest
from app.models import communications, media, people, training
from app.models import session_mutations as history

SOURCES = {
    training.TrainingSession: history.MutationSession,
    people.Client: history.MutationClient,
    training.PackagePurchase: history.MutationPurchase,
    training.PurchaseScheduleSlot: history.MutationSlot,
    people.Trainer: history.MutationTrainer,
    people.StaffUser: history.MutationUser,
    training.ExercisePlanItem: history.MutationPlan,
    training.ExercisePlanDetail: history.MutationDetail,
    training.ExerciseResult: history.MutationResult,
    media.MediaAsset: history.MutationMedia,
    communications.ChangeRequest: history.MutationRequest,
}
FIELDS = {
    model: [
        c.name
        for c in snapshot.__table__.columns
        if c.name not in {"mutation_id", "entity_id", "side"}
    ]
    for model, snapshot in SOURCES.items()
}
LABELS = {
    "session.details": "Session booking changed",
    "session.change": "Session time or Trainer change",
    "session.time": "Session time change",
    "session.trainer": "Session Trainer change",
    "session.postpone": "Session postponement",
    "session.plan": "Exercise plan saved",
    "session.copy_plan": "Previous exercise plan copied",
    "session.outcome": "Session outcome saved",
    "session.summary": "Client summary saved",
    "session.handoff": "Session opening recorded",
    "session.recording": "Session recording changed",
    "client.weekly": "Fixed weekly schedule changed",
    "client.assignment": "Client Trainer assignment changed",
    "client.deactivate": "Client deactivated",
    "client.reactivate": "Client reactivated",
    "trainer.deactivate": "Trainer deactivated",
    "trainer.reactivate": "Trainer reactivated",
    "request.resolve": "Session request applied",
}
SESSION_REQUESTS = {"session_time", "session_trainer", "session_postpone", "fixed_weekly_schedule"}


def values(session, model, ids):
    """Read persisted rows in one batch, independent of dirty ORM attribute values."""
    table = model.__table__
    rows = (
        session.connection()
        .execute(
            select(table.c.id, *(table.c[name] for name in FIELDS[model])).where(
                table.c.id.in_(ids)
            )
        )
        .mappings()
    )
    return {row["id"]: {name: row[name] for name in FIELDS[model]} for row in rows}


def semantic(row):
    return None if row is None else {key: value for key, value in row.items() if key != "version"}


def scope_digest(session, *, client_id=None, trainer_id=None, session_id=None):
    """Bind lifecycle dependents by business state, allowing monotonic compensated versions."""
    condition = (
        training.TrainingSession.id == session_id
        if session_id
        else training.TrainingSession.client_id == client_id
        if client_id
        else training.TrainingSession.trainer_id == trainer_id
    )
    rows = session.scalars(
        select(training.TrainingSession).where(condition).order_by(training.TrainingSession.id)
    ).all()
    bookings = [
        [
            row.id,
            {
                name: getattr(row, name)
                for name in FIELDS[training.TrainingSession]
                if name != "version"
            },
        ]
        for row in rows
    ]
    # Scope includes child records, including newly added rows absent from typed patches.
    # Ignore retired additions so undoing a later change can restore this dependency state.
    children = []
    ids = [row.id for row in rows]
    plans = session.scalars(
        select(training.ExercisePlanItem)
        .where(
            training.ExercisePlanItem.session_id.in_(ids),
            training.ExercisePlanItem.retired_at.is_(None),
        )
        .order_by(training.ExercisePlanItem.id)
    ).all()
    for model, condition in (
        (training.ExercisePlanItem, training.ExercisePlanItem.id.in_([r.id for r in plans])),
        (
            training.ExercisePlanDetail,
            training.ExercisePlanDetail.plan_item_id.in_([r.id for r in plans]),
        ),
        (
            training.ExerciseResult,
            training.ExerciseResult.session_id.in_(ids)
            & training.ExerciseResult.retired_at.is_(None),
        ),
        (media.MediaAsset, media.MediaAsset.session_id.in_(ids)),
    ):
        child_ids = list(session.scalars(select(model.id).where(condition).order_by(model.id)))
        persisted = values(session, model, child_ids)
        for identity in child_ids:
            children.append([model.__tablename__, identity, semantic(persisted[identity])])
    for model in (training.Acknowledgement, training.CreditDebit):
        children.append(
            [
                model.__tablename__,
                list(
                    session.scalars(
                        select(model.id).where(model.session_id.in_(ids)).order_by(model.id)
                    )
                ),
            ]
        )
    purchases = []
    if client_id:
        for row in session.scalars(
            select(training.PackagePurchase)
            .where(training.PackagePurchase.client_id == client_id)
            .order_by(training.PackagePurchase.id)
        ):
            purchases.append(
                [
                    row.id,
                    row.status,
                    row.trainer_id,
                    row.start_date,
                    row.end_date,
                    row.total_sessions,
                ]
            )
    return digest({"sessions": bookings, "purchases": purchases, "children": children})


class Capture:
    """A listener belongs to one Session and is always removed before compensation storage."""

    def __init__(self):
        self.before = {}
        self.notices = set()

    def before_flush(self, session, _context, _instances):
        self.notices.update(row for row in session.new if isinstance(row, communications.Message))
        grouped = {}
        for row in set(session.new) | set(session.dirty) | set(session.deleted):
            if type(row) in SOURCES and row not in self.before:
                grouped.setdefault(type(row), []).append(row)
        for model, rows in grouped.items():
            persisted = values(session, model, [row.id for row in rows if row not in session.new])
            for row in rows:
                self.before[row] = persisted.get(row.id)

    def changes(self, session):
        result = []
        for model in SOURCES:
            rows = [row for row in self.before if type(row) is model]
            after = values(session, model, [row.id for row in rows])
            for row in rows:
                old, current = self.before[row], after.get(row.id)
                if old != current:
                    result.append((model, row.id, old, current))
        return result


def journal(operation):
    """Wrap only approved reversible owners; nested calls join the outer atomic journal."""
    if operation not in LABELS:
        raise ValueError("Unknown reversible operation")

    def decorate(function):
        @wraps(function)
        def wrapped(session, principal, *args, **kwargs):
            if session.info.get("session_mutation_capture"):
                return function(session, principal, *args, **kwargs)
            bound = signature(function).bind(session, principal, *args, **kwargs)
            key = bound.arguments["key"]
            capture = Capture()
            session.info["session_mutation_capture"] = capture
            event.listen(session, "before_flush", capture.before_flush)
            try:
                result = function(session, principal, *args, **kwargs)
                session.flush()
                changes = capture.changes(session)
            finally:
                event.remove(session, "before_flush", capture.before_flush)
                session.info.pop("session_mutation_capture", None)
            # Availability-only decisions and exact command replays are not session Undo.
            changes = [
                entry
                for entry in changes
                if entry[0] is not communications.ChangeRequest
                or (entry[3] or entry[2])["kind"] in SESSION_REQUESTS
            ]
            if any(
                semantic(before) != semantic(after)
                and (
                    model is not communications.ChangeRequest
                    or before is None
                    and after["status"] == "pending"
                )
                for model, _, before, after in changes
            ):
                persist(session, principal, operation, key, changes, capture.notices)
            return result

        return wrapped

    return decorate


def persist(session, principal, operation, key, changes, notices):
    """Store typed originals and one discoverable notice in the same business transaction."""
    identity, now = uuid4(), session.scalar(select(func.clock_timestamp()))
    bookings = [
        after or before for model, _, before, after in changes if model is training.TrainingSession
    ]
    first = bookings[0] if bookings else None
    from app.api.messages import scope

    notice = session.scalar(
        select(communications.Message)
        .where(communications.Message.id.in_([row.id for row in notices]), scope(principal))
        .order_by(communications.Message.id)
        .limit(1)
    )
    if notice is None:
        notice = communications.Message(
            kind="session_update",
            title=LABELS[operation],
            body=(
                "Undo is available for 24 hours while affected records remain eligible. "
                "Original history is retained."
            ),
            client_id=first["client_id"] if first else None,
            purchase_id=first["purchase_id"] if first else None,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
        session.add(notice)
        session.flush()
        trainer_ids = {row["trainer_id"] for row in bookings}
        trainer_users = select(people.Trainer.user_id).where(people.Trainer.id.in_(trainer_ids))
        recipients = set(
            session.scalars(
                select(people.StaffUser.id).where(
                    people.StaffUser.status == "active",
                    (people.StaffUser.role == "owner")
                    | (people.StaffUser.id == principal.user_id)
                    | people.StaffUser.id.in_(trainer_users),
                )
            )
        )
        for user in recipients:
            session.add(communications.MessageReceipt(message_id=notice.id, user_id=user))
    session.add(
        history.SessionMutation(
            id=identity,
            operation=operation,
            request_key=key,
            actor_role=principal.role,
            trainer_id=principal.trainer_id,
            actor_id=principal.user_id,
            actor_name=principal.name,
            message_id=notice.id,
            expires_at=now + timedelta(hours=24),
        )
    )
    session.flush()
    retired = {
        entity_id
        for model, entity_id, before, after in changes
        if model is training.ExercisePlanItem
        and before
        and after
        and before["retired_at"] is None
        and after["retired_at"] is not None
    }
    captured_media = {entity_id for model, entity_id, _, _ in changes if model is media.MediaAsset}
    for asset in session.scalars(
        select(media.MediaAsset).where(
            media.MediaAsset.original_plan_item_id.in_(retired),
            media.MediaAsset.session_id.is_not(None),
            media.MediaAsset.status == "ready",
            media.MediaAsset.expires_at > now,
        )
    ):
        if asset.id not in captured_media:
            data = {name: getattr(asset, name) for name in FIELDS[media.MediaAsset]}
            changes.append((media.MediaAsset, asset.id, data, data))
    clients, trainers = set(), set()
    for model, entity_id, before, after in changes:
        for side, data in (("before", before), ("after", after)):
            if data is not None:
                session.add(
                    SOURCES[model](mutation_id=identity, entity_id=entity_id, side=side, **data)
                )
        if model is people.Client and semantic(before) != semantic(after):
            clients.add(entity_id)
        if model is training.PurchaseScheduleSlot:
            clients.add(
                session.get(training.PackagePurchase, (after or before)["purchase_id"]).client_id
            )
        if model is people.Trainer and semantic(before) != semantic(after):
            trainers.add(entity_id)
    for client in clients:
        session.add(
            history.MutationScope(
                mutation_id=identity,
                client_id=client,
                sha256=scope_digest(session, client_id=client),
            )
        )
    for trainer in trainers:
        session.add(
            history.MutationScope(
                mutation_id=identity,
                trainer_id=trainer,
                sha256=scope_digest(session, trainer_id=trainer),
            )
        )

    for booking_id in {
        entity_id for model, entity_id, _, _ in changes if model is training.TrainingSession
    }:
        session.add(
            history.MutationScope(
                mutation_id=identity,
                session_id=booking_id,
                sha256=scope_digest(session, session_id=booking_id),
            )
        )
