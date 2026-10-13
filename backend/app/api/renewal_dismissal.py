"""Remove a renewal follow-up without deleting the notice or changing a purchase."""

import hashlib
import json

from sqlalchemy import exists, select, text

from app.api.message_schemas import RenewalState
from app.api.messages import dismissal_evidence, visible_message
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import RenewalDismissal, RenewalDismissalReceipt
from app.models.people import Client
from app.models.training import PackagePurchase


def target(session, principal, identity):
    message = visible_message(session, principal, identity)
    if message.kind != "renewal" or not message.client_id or not message.purchase_id:
        raise unavailable()
    client = session.scalar(select(Client).where(Client.id == message.client_id).with_for_update())
    if client is None or (
        not principal.manages_operations and client.trainer_id != principal.trainer_id
    ):
        raise unavailable()
    return message, client


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(714602042)"))
    return session.scalar(
        select(RenewalDismissalReceipt).where(
            RenewalDismissalReceipt.actor_id == principal.user_id,
            RenewalDismissalReceipt.request_key == key,
        )
    )


def reconcile(session, principal, key):
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    target(session, principal, saved.message_id)
    return RenewalState.model_validate(saved.result)


def save(session, principal, identity, key, body):
    saved = receipt(session, principal, key)
    message, client = target(session, principal, identity)
    digest = hashlib.sha256(
        json.dumps(
            {"id": str(identity), **body.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Review this request before retrying.", 409)
        return RenewalState.model_validate(saved.result)
    if client.version != body.expectedClientVersion:
        raise conflict()
    purchase = session.scalar(
        select(PackagePurchase)
        .where(PackagePurchase.id == message.purchase_id, PackagePurchase.client_id == client.id)
        .with_for_update()
    )
    if purchase is None:
        raise unavailable()
    dismissal = session.scalar(
        select(RenewalDismissal).where(RenewalDismissal.message_id == identity)
    )
    renewed = session.scalar(
        select(
            exists().where(
                PackagePurchase.client_id == client.id,
                PackagePurchase.id != purchase.id,
                PackagePurchase.status == "active",
                PackagePurchase.start_date > purchase.end_date,
            )
        )
    )
    if dismissal is None and not renewed:
        dismissal = RenewalDismissal(
            message_id=identity, actor_id=principal.user_id, actor_name=principal.name
        )
        session.add(dismissal)
        session.flush()
        session.refresh(dismissal)
    result = RenewalState(
        id=identity,
        renewalStatus="removed" if dismissal else "renewed",
        renewalDismissal=dismissal_evidence(dismissal) if dismissal else None,
    )
    session.add(
        RenewalDismissalReceipt(
            request_key=key,
            request_sha256=digest,
            message_id=identity,
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    return result
