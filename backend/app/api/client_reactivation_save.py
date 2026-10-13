"""Commit the exact reviewed retained calendar and lifecycle, with immutable recovery."""

import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictInt
from sqlalchemy import select, text

from app.api.client_reactivation import review
from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import ClientReactivationReceipt
from app.models.communications import Message, MessageReceipt, SessionEvent
from app.models.people import Client, LifecycleEvent, StaffUser, Trainer
from app.models.training import PackagePurchase, TrainingSession


class ClientReactivationState(Contract):
    id: UUID
    version: StrictInt = Field(ge=1)
    status: Literal["active"] = "active"


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(714602044)"))
    return session.scalar(
        select(ClientReactivationReceipt).where(
            ClientReactivationReceipt.actor_id == principal.user_id,
            ClientReactivationReceipt.request_key == key,
        )
    )


def reconcile(session, principal, key):
    principal.operations()
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return ClientReactivationState.model_validate(saved.result)


def save(session, principal, identity, key, body):
    principal.operations()
    saved = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps({"id": str(identity), **body.model_dump(mode="json")}, sort_keys=True).encode()
    ).hexdigest()
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Review this request before retrying.", 409)
        return ClientReactivationState.model_validate(saved.result)
    # Lock order matches purchase creation: client, retained aggregate, sorted trainers.
    # Competing creators wait on the trainer barrier, then recheck committed occupancy.
    viewed = review(session, principal, identity, body, write=True)
    if viewed.packageError or any(row.error for row in viewed.rows):
        raise conflict()
    client = session.get(Client, identity)
    cause = LifecycleEvent(
        client_id=identity,
        status="active",
        reason="owner",
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(cause)
    session.flush()
    client.status, client.lifecycle_event_id = "active", cause.id
    client.version += 1
    for purchase_id in viewed.purchaseIds:
        purchase = session.get(PackagePurchase, purchase_id)
        effect = LifecycleEvent(
            purchase_id=purchase_id,
            status="active",
            reason="client_reactivated",
            cause_id=cause.id,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
        session.add(effect)
        session.flush()
        purchase.status, purchase.lifecycle_event_id = "active", effect.id
        purchase.version += 1
    for row in viewed.rows:
        if row.date == row.originalDate:
            continue
        booking = session.get(TrainingSession, row.id)
        session.add(
            SessionEvent(
                session_id=booking.id,
                session_version=booking.version,
                kind="client_reactivation_date",
                old_date=booking.training_date,
                new_date=row.date,
                actor_id=principal.user_id,
                actor_name=principal.name,
            )
        )
        booking.training_date = row.date
        booking.version += 1
    session.flush()
    result = ClientReactivationState(id=client.id, version=client.version)
    session.add(
        ClientReactivationReceipt(
            request_key=key,
            request_sha256=digest,
            client_id=identity,
            previous=viewed.model_dump(mode="json"),
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    notify(session, principal, client)
    return result


def notify(session, principal, client):
    trainer_user = session.scalar(select(Trainer.user_id).where(Trainer.id == client.trainer_id))
    user_id = session.scalar(
        select(StaffUser.id).where(StaffUser.id == trainer_user, StaffUser.status == "active")
    )
    notice = Message(
        kind="client_status",
        title=f"{client.name} reactivated",
        body=f"{client.name} is active again and has returned to your assigned client list.",
        client_id=client.id,
        trainer_id=client.trainer_id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    if user_id:
        session.add(MessageReceipt(message_id=notice.id, user_id=user_id))
