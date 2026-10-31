"""Add a reviewed future purchase without replacing the client's current settings."""

import hashlib
import json
from uuid import UUID

from pydantic import Field, StrictInt, model_validator
from sqlalchemy import select, text

from app.api.admin_supervision import supervised, supervised_recovery
from app.api.client_matching import MatchedSlot, MatchRequest
from app.api.client_renewal import RenewalMatchRequest, review
from app.api.purchase_creation import persist_purchase, prepare_purchase
from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.api import ClientRenewalReceipt
from app.models.communications import Message, MessageReceipt
from app.models.people import Client, StaffUser, Trainer
from app.persistence import PersistenceConflict


class RenewPackage(MatchRequest):
    expected: str = Field(pattern=r"^[0-9a-f]{64}$")
    trainerId: UUID
    trainerVersion: StrictInt = Field(ge=1)
    fixedWeeklySchedule: list[MatchedSlot] = Field(min_length=1, max_length=7)

    @model_validator(mode="after")
    def complete_schedule(self):
        RenewalMatchRequest.model_validate(
            self.model_dump(mode="json", by_alias=True, exclude={"trainerVersion"})
        )
        if len(self.fixedWeeklySchedule) != self.sessionsPerWeek:
            raise ValueError("Review the complete weekly cadence")
        return self


class ClientRenewalState(Contract):
    id: UUID
    version: StrictInt = Field(ge=1)
    purchaseId: UUID


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(714602047)"))
    return session.scalar(
        select(ClientRenewalReceipt).where(
            ClientRenewalReceipt.actor_id == principal.user_id,
            ClientRenewalReceipt.request_key == key,
        )
    )


@supervised_recovery("client.purchase")
def reconcile(session, principal, key):
    principal.operations()
    saved = receipt(session, principal, key)
    if saved is None:
        raise unavailable()
    return ClientRenewalState.model_validate(saved.result)


@supervised("clientPackages", "client.purchase", RenewPackage, receipt=receipt, target="identity")
def save(session, principal, identity, key, body):
    principal.operations()
    saved = receipt(session, principal, key)
    digest = hashlib.sha256(
        json.dumps(
            {"id": str(identity), **body.model_dump(mode="json", by_alias=True)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    if saved:
        if saved.request_sha256 != digest:
            raise AuthError("idempotency_conflict", "Review this request before retrying.", 409)
        return ClientRenewalState.model_validate(saved.result)
    viewed = review(session, principal, identity, write=True)
    if viewed.expected != body.expected:
        raise conflict()
    if body.startDate < viewed.minimumStartDate:
        raise AuthError("invalid_request", "Choose a future start date.", 422)
    client = session.get(Client, identity)
    prepared = prepare_purchase(session, body, allow_subwindows=True)
    try:
        purchase = persist_purchase(session, client, body, prepared, stage="queued")
    except PersistenceConflict:
        raise conflict() from None
    notify(session, principal, client, purchase)
    result = ClientRenewalState(id=client.id, version=client.version, purchaseId=purchase.id)
    session.add(
        ClientRenewalReceipt(
            request_key=key,
            request_sha256=digest,
            client_id=client.id,
            purchase_id=purchase.id,
            result=result.model_dump(mode="json"),
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    return result


def notify(session, principal, client, purchase):
    trainer = session.get(Trainer, client.trainer_id)
    owners = session.scalars(
        select(StaffUser.id).where(
            StaffUser.role == "owner",
            StaffUser.status == "active",
        )
    ).all()
    notice = Message(
        kind="saved_edit",
        title=f"Package added: {client.name}",
        body=f"{purchase.name} · {purchase.total_sessions} sessions · "
        f"{purchase.start_date}–{purchase.end_date}",
        client_id=client.id,
        trainer_id=client.trainer_id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    for user_id in set(owners + ([trainer.user_id] if trainer.user_id else [])):
        session.add(MessageReceipt(message_id=notice.id, user_id=user_id))
