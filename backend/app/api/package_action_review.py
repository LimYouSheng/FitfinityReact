"""Bind a package action to its complete current records and exact eligible bookings."""

import hashlib
import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from app.api.directory import bounded
from app.api.package_action_schemas import PackageActionReview
from app.api.session_booking_review import position
from app.authorization import conflict, unavailable
from app.models.communications import ChangeRequest
from app.models.people import Client
from app.models.training import Acknowledgement, CreditDebit, PackagePurchase, TrainingSession


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def clock():
    return datetime.now(UTC)


def contents(session, identity):
    return session.scalar(text("SELECT ff_session_contents(:id)"), {"id": identity})


def target(session, client_id, purchase_id):
    """Lock client, purchase and bookings in the shared domain order."""
    client = session.scalar(select(Client).where(Client.id == client_id).with_for_update())
    purchase = session.scalar(
        select(PackagePurchase)
        .where(PackagePurchase.id == purchase_id, PackagePurchase.client_id == client_id)
        .with_for_update()
    )
    if client is None or purchase is None:
        raise unavailable()
    rows = bounded(
        session,
        select(TrainingSession)
        .where(TrainingSession.purchase_id == purchase_id)
        .order_by(TrainingSession.id)
        .with_for_update(),
    )
    return client, purchase, rows


def review(session, principal, client_id, purchase_id, operation):
    """Eligibility is recomputed at save; a booking starting during review changes the hash."""
    principal.operations()
    client, purchase, rows = target(session, client_id, purchase_id)
    if operation == "deactivate" and client.status != "active":
        raise conflict()
    if operation == "delete_sessions" and purchase.status != "inactive":
        raise conflict()
    ids = [row.id for row in rows]
    protected = set(
        session.scalars(
            select(Acknowledgement.session_id).where(Acknowledgement.session_id.in_(ids))
        )
    ) | set(session.scalars(select(CreditDebit.session_id).where(CreditDebit.session_id.in_(ids))))
    now = clock().astimezone(ZoneInfo("Asia/Singapore")).replace(tzinfo=None)
    eligible = [
        row
        for row in rows
        if row.status not in {"completed", "cancelled"}
        and row.id not in protected
        and (
            row.schedule_state == "open" or datetime.combine(row.training_date, row.starts_at) > now
        )
    ]
    requests = bounded(
        session,
        select(ChangeRequest)
        .where(ChangeRequest.session_id.in_(ids), ChangeRequest.status == "pending")
        .order_by(ChangeRequest.id)
        .with_for_update(),
    )
    expected = digest(
        {
            "operation": operation,
            "client": [client.id, client.version, client.status, client.trainer_id],
            "purchase": [
                purchase.id,
                purchase.version,
                purchase.status,
                purchase.lifecycle_event_id,
            ],
            "sessions": [
                [position(row).model_dump(mode="json"), row.status, contents(session, row.id)]
                for row in rows
            ],
            "protected": sorted(str(identity) for identity in protected),
            "eligible": [row.id for row in eligible],
            "requests": [[row.id, row.version, row.status] for row in requests],
        }
    )
    viewed = PackageActionReview(
        clientId=client.id,
        clientVersion=client.version,
        purchaseId=purchase.id,
        purchaseVersion=purchase.version,
        name=purchase.name,
        status=purchase.status,
        operation=operation,
        expected=expected,
        eligible=[position(row) for row in eligible],
    )
    return viewed, client, purchase, eligible, requests
