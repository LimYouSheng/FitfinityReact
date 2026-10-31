"""Restore one reviewed purchase without changing other purchase or client lifecycle state."""

import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictInt
from sqlalchemy import select, text

from app.api.admin_supervision import supervised, supervised_recovery
from app.api.client_reactivation import ReactivationDates, review
from app.api.client_reactivation_save import apply_dates
from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import PackageReactivationReceipt
from app.models.communications import Message, MessageReceipt
from app.models.people import Client, LifecycleEvent, StaffUser, Trainer
from app.models.training import PackagePurchase


class PackageReactivationState(Contract):
    id: UUID
    version: StrictInt = Field(ge=1)
    packageId: UUID
    status: Literal["active"] = "active"


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(714602048)"))
    return session.scalar(
        select(PackageReactivationReceipt).where(
            PackageReactivationReceipt.actor_id == principal.user_id,
            PackageReactivationReceipt.request_key == key,
        )
    )


@supervised_recovery("purchase.reactivate")
def reconcile(session, principal, key):
    principal.operations()
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return PackageReactivationState.model_validate(saved.result)


@supervised(
    "clientPackages",
    "purchase.reactivate",
    ReactivationDates,
    receipt=receipt,
    target=("identity", "purchase_id"),
)
def save(session, principal, identity, purchase_id, key, body):
    principal.operations()
    saved = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps(
            {"id": str(identity), "packageId": str(purchase_id), **body.model_dump(mode="json")},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Review this request before retrying.", 409)
        return PackageReactivationState.model_validate(saved.result)
    viewed = review(session, principal, identity, body, write=True, package_id=purchase_id)
    if viewed.packageError or any(row.error for row in viewed.rows):
        raise conflict()
    client = session.get(Client, identity)
    purchase = session.get(PackagePurchase, purchase_id)
    effect = LifecycleEvent(
        purchase_id=purchase_id,
        status="active",
        reason="owner",
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(effect)
    session.flush()
    purchase.status, purchase.lifecycle_event_id = "active", effect.id
    purchase.version += 1
    client.version += 1
    apply_dates(session, principal, viewed.rows, "package_reactivation_date")
    session.flush()
    result = PackageReactivationState(id=identity, version=client.version, packageId=purchase_id)
    session.add(
        PackageReactivationReceipt(
            request_key=key,
            request_sha256=digest,
            client_id=identity,
            purchase_id=purchase_id,
            previous=viewed.model_dump(mode="json"),
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    notify(session, principal, client, purchase)
    return result


def notify(session, principal, client, purchase):
    trainer = session.get(Trainer, purchase.trainer_id)
    owners = session.scalars(
        select(StaffUser.id).where(StaffUser.role == "owner", StaffUser.status == "active")
    ).all()
    notice = Message(
        kind="saved_edit",
        title=f"Package reactivated: {client.name}",
        body=f"{purchase.name} · {principal.name} · Used credits and expiry date retained. "
        "Deleted sessions are not recreated.",
        client_id=client.id,
        trainer_id=purchase.trainer_id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    for user_id in set(owners + ([trainer.user_id] if trainer.user_id else [])):
        session.add(MessageReceipt(message_id=notice.id, user_id=user_id))
