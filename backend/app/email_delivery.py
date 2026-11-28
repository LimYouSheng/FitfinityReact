"""Commit mail intent with business writes; lease each SES attempt before external IO."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.email_provider import DeliveryFailure
from app.email_templates import EmailContent, render
from app.models.email_delivery import EmailDelivery


def enqueue(session, event_key, kind, recipient, values):
    """Freeze one recipient's content atomically; repeated business receipts cannot resend."""
    if not session.info.get("transactional_email_enabled", False):
        return None
    recipient = recipient.strip().lower()
    if not recipient or "@" not in recipient or any(c in recipient for c in "\r\n"):
        raise ValueError("A valid email recipient is required")
    content = render(kind, values)
    identity = uuid4()
    inserted = session.scalar(
        insert(EmailDelivery)
        .values(
            id=identity,
            event_key=event_key,
            kind=kind,
            recipient=recipient,
            subject=content.subject,
            body=content.text,
        )
        .on_conflict_do_nothing(index_elements=["event_key", "recipient"])
        .returning(EmailDelivery.id)
    )
    if inserted:
        return inserted
    existing = session.scalar(
        select(EmailDelivery).where(
            EmailDelivery.event_key == event_key,
            EmailDelivery.recipient == recipient,
        )
    )
    if (existing.kind, existing.subject, existing.body) != (kind, content.subject, content.text):
        raise ValueError("Email event conflicts with its original content")
    return existing.id


def dispatch_one(database, provider, *, now=None):
    """Do not retry expired leases or uncertain SES outcomes: SES has no send idempotency key."""
    now = now or datetime.now(UTC)
    with database.transaction() as session:
        session.execute(
            update(EmailDelivery)
            .where(
                EmailDelivery.state == "sending",
                EmailDelivery.lease_until <= now,
            )
            .values(state="unknown", error_code="attempt_interrupted")
        )
        delivery = session.scalar(
            select(EmailDelivery)
            .where(
                EmailDelivery.state == "pending",
                EmailDelivery.available_at <= now,
                EmailDelivery.attempts < 5,
            )
            .order_by(EmailDelivery.created_at, EmailDelivery.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if delivery is None:
            return None
        identity, lease = delivery.id, uuid4()
        delivery.state, delivery.lease_id = "sending", lease
        delivery.lease_until = now + timedelta(seconds=120)
        delivery.attempts += 1
        recipient, content = delivery.recipient, EmailContent(delivery.subject, delivery.body)
    try:
        provider_id = provider.send(recipient, content, identity)
        state, code = "accepted", None
    except DeliveryFailure as error:
        provider_id, state, code = None, error.state, error.code
    with database.transaction() as session:
        delivery = session.scalar(
            select(EmailDelivery)
            .where(
                EmailDelivery.id == identity,
            )
            .with_for_update()
        )
        if delivery.state != "sending" or delivery.lease_id != lease:
            return {"id": str(identity), "state": "unknown"}
        if state == "retry":
            state = "pending" if delivery.attempts < 5 else "failed"
            delivery.available_at = now + timedelta(seconds=60 * 2**delivery.attempts)
        delivery.state, delivery.error_code, delivery.provider_id = state, code, provider_id
        delivery.lease_id = delivery.lease_until = None
    return {"id": str(identity), "state": state}
