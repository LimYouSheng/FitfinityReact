"""Append compensation evidence without erasing original commands or financial history."""

from uuid import uuid4

from sqlalchemy import func, insert, select

from app.api import session_media, session_outcomes, session_undo_review
from app.api.package_action_review import digest
from app.api.session_mutation_journal import FIELDS
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models import communications, media, people, training
from app.models.session_mutations import MutationScope, SessionMutationUndo
from app.persistence import occupied_booking_clause
from app.session_numbering import renumber_purchase


def original(session, principal, key):
    return session.scalar(
        select(SessionMutationUndo).where(
            SessionMutationUndo.actor_id == principal.user_id,
            SessionMutationUndo.request_key == key,
        )
    )


def reconcile(session, principal, key):
    saved = original(session, principal, key)
    if saved is None:
        raise unavailable()
    return saved.result


def append_lifecycle(session, principal, row, status):
    """Append a causal lifecycle correction without replacing original event identities."""
    field = {
        people.Client: "client_id",
        people.Trainer: "trainer_id",
        training.PackagePurchase: "purchase_id",
    }[type(row)]
    reason, cause = "owner", None
    if isinstance(row, training.PackagePurchase):
        client = session.get(people.Client, row.client_id)
        if client.status == status and client.lifecycle_event_id:
            reason = "client" if status == "inactive" else "client_reactivated"
            cause = client.lifecycle_event_id
    event = people.LifecycleEvent(
        **{field: row.id},
        status=status,
        reason=reason,
        cause_id=cause,
        note="Permitted Undo; original lifecycle history is retained.",
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(event)
    session.flush()
    if hasattr(row, "lifecycle_event_id"):
        row.lifecycle_event_id = event.id


def restore_fields(session, model, entity_id, before, after, *, principal, now):
    """Restore only changed domain columns; current version and creation evidence never rewind."""
    row = session.get(model, entity_id)
    if model is communications.ChangeRequest:
        if before is None and row.status == "pending":
            row.status, row.resolved_at = "cancelled", now
            row.resolved_by = principal.user_id
            row.resolution_note = "Original proposal cancelled by permitted Undo."
            row.version += 1
            session.add(
                communications.RequestEvent(
                    request_id=row.id,
                    sequence=2,
                    status="cancelled",
                    note="Original proposal cancelled by permitted Undo.",
                    actor_id=principal.user_id,
                    actor_name=principal.name,
                )
            )
        # Applied/rejected decisions stay terminal; the Undo projection carries reversal.
        return
    if model is media.MediaAsset:
        if before is not None and before["status"] == "ready" and before["session_id"] is not None:
            row.session_id = before["session_id"]
            work = session.scalar(
                select(media.MediaDeletion).where(media.MediaDeletion.media_id == row.id)
            )
            if work:
                work.next_attempt_at = row.expires_at
        elif row.session_id is not None:
            session_media.retire(session, row, now, "removed")
        return
    if model is training.ExerciseResult:
        session_outcomes.preserve(session, principal, row)
    if before is None:
        if model is training.ExercisePlanItem:
            row.retired_at, row.position = now, None
        elif model is training.ExerciseResult:
            row.retired_at = now
        elif model is training.ExercisePlanDetail:
            session.delete(row)
            return
        else:
            raise conflict()
    elif after is None:
        if model is not training.ExercisePlanDetail:
            raise conflict()
        # ORM insertion initializes Versioned rows to one. This guarded restoration
        # must retain the original creation time and advance its archived version.
        session.execute(
            insert(model.__table__).values(
                id=entity_id,
                **{name: value for name, value in before.items() if name != "version"},
                version=before["version"] + 1,
            )
        )
        return
    else:
        for name in FIELDS[model]:
            if (
                name in {"version", "created_at", "lifecycle_event_id", "session_number"}
                or before[name] == after[name]
            ):
                continue
            if name == "status" and model in {
                people.Client,
                people.Trainer,
                training.PackagePurchase,
            }:
                append_lifecycle(session, principal, row, before[name])
            setattr(row, name, before[name])
        if (
            model is training.TrainingSession
            and before["schedule_state"] != after["schedule_state"]
        ):
            row.session_number = before["session_number"]
    row.version += 1
    session.flush()


def validate_occupancy(session, ids):
    """Check restored occupancy against active calendars and retained completed bookings."""
    for row in session.scalars(
        select(training.TrainingSession).where(training.TrainingSession.id.in_(ids))
    ):
        client, purchase = (
            session.get(people.Client, row.client_id),
            session.get(training.PackagePurchase, row.purchase_id),
        )
        if row.status == "cancelled":
            continue
        if row.status != "completed" and (client.status != "active" or purchase.status != "active"):
            continue
        if (
            row.status != "completed"
            and session.get(people.Trainer, row.trainer_id).status != "active"
        ):
            raise conflict()
        if row.schedule_state != "booked" or row.status == "cancelled":
            continue
        occupied = session.scalar(
            select(training.TrainingSession.id)
            .join(
                training.PackagePurchase,
                training.TrainingSession.purchase_id == training.PackagePurchase.id,
            )
            .join(people.Client, training.TrainingSession.client_id == people.Client.id)
            .where(
                occupied_booking_clause(),
                training.TrainingSession.id != row.id,
                training.TrainingSession.training_date == row.training_date,
                training.TrainingSession.starts_at < row.ends_at,
                training.TrainingSession.ends_at > row.starts_at,
                (training.TrainingSession.trainer_id == row.trainer_id)
                | (training.TrainingSession.client_id == row.client_id),
            )
            .limit(1)
        )
        if occupied:
            raise AuthError(
                "booking_conflict", "The restored time conflicts with another booking.", 409
            )


def append_assignment_history(session, principal, changes):
    """Compensating assignments append new evidence rather than rewind earlier events."""
    for model, identity, before, after, current in changes:
        if model is not people.Client or before["trainer_id"] == after["trainer_id"]:
            continue
        old_id, new_id = current["trainer_id"], before["trainer_id"]
        event = training.AssignmentEvent(
            client_id=identity,
            client_version=current["version"],
            old_trainer_id=old_id,
            new_trainer_id=new_id,
            old_trainer_name=session.get(people.Trainer, old_id).name,
            new_trainer_name=session.get(people.Trainer, new_id).name,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
        session.add(event)
        session.flush()
        for target, target_id, earlier, later, live in changes:
            if target not in {training.PackagePurchase, training.TrainingSession}:
                continue
            if earlier["client_id"] != identity or earlier["trainer_id"] == later["trainer_id"]:
                continue
            field = "purchase_id" if target is training.PackagePurchase else "session_id"
            session.add(
                training.AssignmentChange(
                    event_id=event.id,
                    **{field: target_id},
                    old_trainer_id=live["trainer_id"],
                    new_trainer_id=earlier["trainer_id"],
                    old_version=live["version"],
                )
            )


def commit(session, principal, identity, key, body, checked):
    """Recheck after external IO and atomically compensate with one private receipt."""
    fingerprint = digest({"id": identity, **body.model_dump()})
    saved = original(session, principal, key)
    if saved:
        if saved.request_sha256 != fingerprint:
            raise conflict()
        return saved.result
    viewed, mutation, changes, originals = session_undo_review.inspect(session, principal, identity)
    if viewed["expected"] != body.expected or originals != checked:
        raise conflict()
    now = session.scalar(select(func.clock_timestamp()))
    notice = communications.Message(
        kind="session_undo",
        title="Session change undone",
        body="The original history remains. This correction does not recall any shared message.",
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    result = {
        "id": str(uuid4()),
        "actionId": str(identity),
        "status": "undone",
        "undoneAt": now.isoformat(),
    }
    session.add(
        SessionMutationUndo(
            id=result["id"],
            mutation_id=identity,
            request_key=key,
            request_sha256=fingerprint,
            message_id=notice.id,
            result=result,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    session.flush()
    append_assignment_history(session, principal, changes)
    # Restore existing plan parents before details; retire newly created parents last.
    ordered = sorted(
        changes,
        key=lambda e: (
            2
            if e[0] is training.ExercisePlanItem and e[2] is None
            else 0
            if e[0] is training.ExercisePlanItem
            else 1
        ),
    )
    bookings, purchases = set(), set()
    for model, entity_id, before, after, _ in ordered:
        restore_fields(session, model, entity_id, before, after, principal=principal, now=now)
        if model is training.TrainingSession:
            bookings.add(entity_id)
            purchases.add((before or after)["purchase_id"])
            session.add(
                communications.SessionEvent(
                    session_id=entity_id,
                    session_version=session.get(training.TrainingSession, entity_id).version,
                    kind="session_undo",
                    note=f"Compensation for {mutation.operation}; original evidence retained.",
                    actor_id=principal.user_id,
                    actor_name=principal.name,
                )
            )
    session.flush()
    for purchase in purchases:
        renumber_purchase(session, purchase)
    for scope in session.scalars(
        select(MutationScope).where(MutationScope.mutation_id == identity)
    ):
        condition = (
            training.TrainingSession.id == scope.session_id
            if scope.session_id
            else training.TrainingSession.client_id == scope.client_id
            if scope.client_id
            else training.TrainingSession.trainer_id == scope.trainer_id
        )
        bookings.update(session.scalars(select(training.TrainingSession.id).where(condition)))
    validate_occupancy(session, bookings)
    recipients = set(
        session.scalars(
            select(communications.MessageReceipt.user_id).where(
                communications.MessageReceipt.message_id == mutation.message_id
            )
        )
    ) | {principal.user_id}
    for user in recipients:
        session.add(communications.MessageReceipt(message_id=notice.id, user_id=user))
    return result
