"""Reviewed weekly edits apply atomically or create a durable supervised proposal."""

import hashlib
import json
from datetime import time
from typing import Literal
from uuid import UUID

from sqlalchemy import select, text

from app.api.client_weekly_schedule import changes, inspect
from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import unavailable
from app.models.api import ClientWeeklyScheduleReceipt
from app.models.communications import (
    ChangeRequest,
    Message,
    MessageReceipt,
    RequestEvent,
    RequestSlot,
    SessionEvent,
)
from app.models.people import StaffUser


class WeeklySavedClient(Contract):
    id: UUID
    version: int


class ClientWeeklyState(Contract):
    outcome: Literal["applied", "requested"]
    client: WeeklySavedClient
    requestId: UUID | None
    updatedSessions: int


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(714602051)"))
    return session.scalar(
        select(ClientWeeklyScheduleReceipt).where(
            ClientWeeklyScheduleReceipt.actor_id == principal.user_id,
            ClientWeeklyScheduleReceipt.request_key == key,
        )
    )


def reconcile(session, principal, key):
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return ClientWeeklyState.model_validate(saved.result)


def slot_values(rows, side=None):
    return sorted(
        [
            [str(s.slot_identity), s.weekday, str(s.starts_at), str(s.ends_at)]
            for s in rows
            if side is None or s.side == side
        ]
    )


def proposal(session, principal, client, purchase, trainer, slots, body):
    before = sorted([[str(s.id), s.weekday, str(s.starts_at), str(s.ends_at)] for s in slots])
    after = sorted(
        [
            [
                str(s.id),
                s.weekday,
                str(time.fromisoformat(s.startsAt)),
                str(time.fromisoformat(s.endsAt)),
            ]
            for s in body.slots
        ]
    )
    for pending in session.scalars(
        select(ChangeRequest)
        .where(
            ChangeRequest.kind == "fixed_weekly_schedule",
            ChangeRequest.status == "pending",
            ChangeRequest.client_id == client.id,
            ChangeRequest.purchase_id == purchase.id,
            ChangeRequest.trainer_id == trainer.id,
            ChangeRequest.expected_version == purchase.version,
        )
        .order_by(ChangeRequest.id)
        .with_for_update()
    ):
        prior = session.scalars(
            select(RequestSlot).where(RequestSlot.request_id == pending.id)
        ).all()
        if slot_values(prior, "old") == before and slot_values(prior, "new") == after:
            return pending.id
    request = ChangeRequest(
        kind="fixed_weekly_schedule",
        client_id=client.id,
        purchase_id=purchase.id,
        trainer_id=trainer.id,
        expected_version=purchase.version,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(request)
    session.flush()
    session.add(
        RequestEvent(
            request_id=request.id,
            sequence=1,
            status="pending",
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    for side, values in [("old", before), ("new", after)]:
        for identity, weekday, start, end in values:
            session.add(
                RequestSlot(
                    request_id=request.id,
                    side=side,
                    slot_identity=UUID(identity),
                    weekday=weekday,
                    starts_at=time.fromisoformat(start),
                    ends_at=time.fromisoformat(end),
                )
            )
    notify(session, principal, client, trainer, request.id, 0)
    return request.id


def save(session, principal, identity, key, body):
    saved = receipt(session, principal, key)
    canonical = body.model_dump(mode="json")
    canonical["slots"].sort(key=lambda row: row["id"])
    digest = hashlib.sha256(
        json.dumps({"id": str(identity), **canonical}, sort_keys=True).encode()
    ).hexdigest()
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError(
                "idempotency_conflict", "Review the original weekly schedule change.", 409
            )
        return ClientWeeklyState.model_validate(saved.result)
    viewed, client, purchase, trainer, slots, bookings, now = inspect(
        session, principal, identity, write=True
    )
    planned = changes(session, viewed, slots, bookings, now, body)
    request_id = None
    if viewed.outcome == "requested":
        request_id = proposal(session, principal, client, purchase, trainer, slots, body)
    else:
        after = {s.id: s for s in body.slots}
        for slot in slots:
            start, end = (
                time.fromisoformat(after[slot.id].startsAt),
                time.fromisoformat(after[slot.id].endsAt),
            )
            if (slot.starts_at, slot.ends_at) != (start, end):
                slot.starts_at, slot.ends_at, slot.version = start, end, slot.version + 1
        for booking, start, end in planned:
            session.add(
                SessionEvent(
                    session_id=booking.id,
                    session_version=booking.version,
                    kind="fixed_weekly_schedule",
                    note="Current purchase weekly times changed.",
                    old_date=booking.training_date,
                    new_date=booking.training_date,
                    old_start=booking.starts_at,
                    old_end=booking.ends_at,
                    new_start=start,
                    new_end=end,
                    actor_id=principal.user_id,
                    actor_name=principal.name,
                )
            )
            booking.starts_at, booking.ends_at = start, end
            booking.version += 1
        purchase.version += 1
        client.version += 1
        notify(session, principal, client, trainer, None, len(planned))
    session.flush()
    result = ClientWeeklyState(
        outcome=viewed.outcome,
        client=WeeklySavedClient(id=client.id, version=client.version),
        requestId=request_id,
        updatedSessions=0 if request_id else len(planned),
    )
    session.add(
        ClientWeeklyScheduleReceipt(
            request_key=key,
            request_sha256=digest,
            client_id=client.id,
            purchase_id=purchase.id,
            previous=viewed.model_dump(mode="json"),
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    return result


def notify(session, principal, client, trainer, request_id, count):
    owners = set(
        session.scalars(
            select(StaffUser.id).where(StaffUser.role == "owner", StaffUser.status == "active")
        )
    )
    assigned = set(
        session.scalars(
            select(StaffUser.id).where(
                StaffUser.id == trainer.user_id, StaffUser.status == "active"
            )
        )
    )
    recipients = [owners, assigned] if request_id else [owners | assigned]
    for ids in recipients:
        notice = Message(
            kind="schedule_request" if request_id else "schedule_update",
            title=f"Fixed weekly schedule {'change' if request_id else 'saved'}: {client.name}",
            body="Review the current and proposed weekly times. Approved times remain unchanged."
            if request_id
            else f"Weekly times saved; {count} eligible upcoming sessions updated.",
            request_id=request_id,
            client_id=client.id,
            trainer_id=trainer.id,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
        session.add(notice)
        session.flush()
        for user_id in ids:
            session.add(MessageReceipt(message_id=notice.id, user_id=user_id))
