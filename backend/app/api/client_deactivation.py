"""Reviewed client deactivation freezes active purchases and retains all training history."""

import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictInt, model_validator
from sqlalchemy import select, text

from app.api.directory import bounded
from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import ClientDeactivationReceipt
from app.models.communications import Message, MessageReceipt
from app.models.people import Client, LifecycleEvent, StaffUser, Trainer
from app.models.training import PackagePurchase


class PurchaseReview(Contract):
    id: UUID
    version: StrictInt = Field(ge=1)
    status: Literal["active", "inactive"]


class PurchaseLabel(PurchaseReview):
    name: str


class DeactivationReview(Contract):
    id: UUID
    version: StrictInt = Field(ge=1)
    name: str
    trainerId: UUID
    purchases: list[PurchaseLabel] = Field(max_length=2000)


class DeactivateClient(Contract):
    expectedVersion: StrictInt = Field(ge=1)
    expectedTrainerId: UUID
    purchases: list[PurchaseReview] = Field(max_length=2000)

    @model_validator(mode="after")
    def distinct_purchases(self):
        if len({p.id for p in self.purchases}) != len(self.purchases):
            raise ValueError("Review each purchase once")
        return self


class DeactivationState(Contract):
    id: UUID
    version: StrictInt = Field(ge=1)
    status: Literal["inactive"] = "inactive"


def allowed(principal):
    principal.operations()


def target(session, identity, *, write=False):
    client = session.scalar(
        select(Client).where(Client.id == identity).with_for_update(read=not write)
    )
    if client is None:
        raise unavailable()
    purchases = bounded(
        session,
        select(PackagePurchase)
        .where(PackagePurchase.client_id == identity)
        .order_by(PackagePurchase.id)
        .with_for_update(read=not write),
    )
    return client, purchases


def review(session, principal, identity):
    allowed(principal)
    client, purchases = target(session, identity)
    if client.status != "active":
        raise conflict()
    return DeactivationReview(
        id=client.id,
        version=client.version,
        name=client.name,
        trainerId=client.trainer_id,
        purchases=[
            PurchaseLabel(id=p.id, version=p.version, status=p.status, name=p.name)
            for p in purchases
        ],
    )


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(714602043)"))
    return session.scalar(
        select(ClientDeactivationReceipt).where(
            ClientDeactivationReceipt.actor_id == principal.user_id,
            ClientDeactivationReceipt.request_key == key,
        )
    )


def reconcile(session, principal, key):
    allowed(principal)
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return DeactivationState.model_validate(saved.result)


def save(session, principal, identity, key, body):
    allowed(principal)
    saved = receipt(session, principal, key)
    canonical = body.model_dump(mode="json")
    canonical["purchases"] = sorted(canonical["purchases"], key=lambda p: p["id"])
    digest = hashlib.sha256(
        json.dumps(
            {"id": str(identity), **canonical}, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Review this request before retrying.", 409)
        return DeactivationState.model_validate(saved.result)
    client, purchases = target(session, identity, write=True)
    expected = {p.id: (p.version, p.status) for p in body.purchases}
    current = {p.id: (p.version, p.status) for p in purchases}
    if (
        client.status != "active"
        or client.version != body.expectedVersion
        or client.trainer_id != body.expectedTrainerId
        or expected != current
    ):
        raise conflict()
    previous = {
        "client": {
            "id": str(client.id),
            "version": client.version,
            "status": client.status,
            "lifecycleEventId": str(client.lifecycle_event_id)
            if client.lifecycle_event_id
            else None,
        },
        "purchases": [
            {
                "id": str(p.id),
                "version": p.version,
                "status": p.status,
                "lifecycleEventId": str(p.lifecycle_event_id) if p.lifecycle_event_id else None,
            }
            for p in purchases
        ],
    }
    cause = LifecycleEvent(
        client_id=identity,
        status="inactive",
        reason="owner",
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(cause)
    session.flush()
    client.status, client.lifecycle_event_id = "inactive", cause.id
    client.version += 1
    for purchase in purchases:
        if purchase.status == "inactive":
            continue
        effect = LifecycleEvent(
            purchase_id=purchase.id,
            status="inactive",
            reason="client",
            cause_id=cause.id,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
        session.add(effect)
        session.flush()
        purchase.status, purchase.lifecycle_event_id = "inactive", effect.id
        purchase.version += 1
    session.flush()
    result = DeactivationState(id=client.id, version=client.version)
    session.add(
        ClientDeactivationReceipt(
            request_key=key,
            request_sha256=digest,
            client_id=identity,
            previous=previous,
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    notify(session, principal, client)
    return result


def notify(session, principal, client):
    owners = session.scalars(
        select(StaffUser.id).where(StaffUser.role == "owner", StaffUser.status == "active")
    ).all()
    trainer_user = session.scalar(select(Trainer.user_id).where(Trainer.id == client.trainer_id))
    trainer_user = session.scalar(
        select(StaffUser.id).where(StaffUser.id == trainer_user, StaffUser.status == "active")
    )
    for body, recipients in [
        (
            f"{client.name} has been deactivated by {principal.name} "
            "and remains available for viewing.",
            [trainer_user] if trainer_user else [],
        ),
        (
            "The client and their packages are inactive. "
            "Retained sessions, credits and history are unchanged.",
            owners,
        ),
    ]:
        notice = Message(
            kind="client_status",
            title=f"{client.name} deactivated",
            body=body,
            client_id=client.id,
            trainer_id=client.trainer_id,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
        session.add(notice)
        session.flush()
        for user_id in recipients:
            session.add(MessageReceipt(message_id=notice.id, user_id=user_id))
