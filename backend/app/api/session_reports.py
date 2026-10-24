"""Persist report launch audit without claiming delivery or repeating the browser action."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select, text

from app.api.request_cancellation import DECISION_LOCK
from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import client_record, unavailable
from app.models.communications import Message, MessageReceipt
from app.models.evidence import ReportAudit
from app.models.people import StaffUser, Trainer
from app.models.training import PackagePurchase
from app.persistence import PersistenceConflict, report_action


class ReportAction(Contract):
    purchaseId: UUID
    kind: Literal["pdf_export", "pdf_share_opened", "whatsapp_opened"]


class ReportActor(Contract):
    id: UUID
    name: str


class ReportEvent(Contract):
    id: UUID
    clientId: UUID
    packageId: UUID | None
    kind: Literal["pdf_export", "pdf_share_opened", "whatsapp_opened", "csv_export"]
    at: datetime
    by: ReportActor


def project(row):
    return ReportEvent(
        id=row.id,
        clientId=row.client_id,
        packageId=row.purchase_id,
        kind=row.kind,
        at=row.created_at,
        by=ReportActor(id=row.actor_id, name=row.actor_name),
    )


def receipt(session, principal, key):
    session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": DECISION_LOCK})
    return session.scalar(
        select(ReportAudit).where(ReportAudit.id == key, ReportAudit.actor_id == principal.user_id)
    )


def reconcile(session, principal, key):
    found = receipt(session, principal, key)
    if found is None:
        raise unavailable()
    return project(found)


def record(session, principal, identity, key, body):
    """Reuse an immutable operation identity; scope and purchase membership remain server-owned."""
    previous = receipt(session, principal, key)
    if previous:
        if (
            previous.client_id != identity
            or previous.purchase_id != body.purchaseId
            or previous.kind != body.kind
        ):
            raise AuthError(
                "idempotency_conflict", "This key belongs to another report action.", 409
            )
        return project(previous)
    client = client_record(session, principal, identity)
    if (
        session.scalar(
            select(PackagePurchase.id).where(
                PackagePurchase.id == body.purchaseId, PackagePurchase.client_id == identity
            )
        )
        is None
    ):
        raise unavailable()
    try:
        saved = report_action(session, key, principal.user_id, identity, body.purchaseId, body.kind)
    except PersistenceConflict as error:
        raise AuthError(
            "idempotency_conflict", "This key belongs to another report action.", 409
        ) from error
    label = {
        "pdf_export": "PDF export started",
        "pdf_share_opened": "PDF share opened",
        "whatsapp_opened": "WhatsApp opened",
    }[body.kind]
    notice = Message(
        kind="saved_edit",
        title=f"Progress report: {client.name}",
        body=f"{label} · {principal.name}",
        client_id=identity,
        trainer_id=client.trainer_id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    trainer_user = session.scalar(select(Trainer.user_id).where(Trainer.id == client.trainer_id))
    users = session.scalars(
        select(StaffUser.id).where(
            StaffUser.status == "active",
            (StaffUser.role == "owner") | (StaffUser.id == trainer_user),
        )
    )
    for user_id in users:
        session.add(MessageReceipt(message_id=notice.id, user_id=user_id))
    return project(saved)


def history(session, principal, identity, purchase_id=None):
    """Operations-only retained audit, including historical CSV evidence without new CSV writes."""
    principal.operations()
    client_record(session, principal, identity)
    query = select(ReportAudit).where(ReportAudit.client_id == identity)
    if purchase_id is not None:
        if (
            session.scalar(
                select(PackagePurchase.id).where(
                    PackagePurchase.id == purchase_id, PackagePurchase.client_id == identity
                )
            )
            is None
        ):
            raise unavailable()
        query = query.where(ReportAudit.purchase_id == purchase_id)
    rows = list(
        session.scalars(
            query.order_by(ReportAudit.created_at.desc(), ReportAudit.id.desc()).limit(2001)
        )
    )
    if len(rows) > 2000:
        raise AuthError("report_capacity", "Report history could not be loaded completely.", 503)
    return [project(row) for row in rows]
