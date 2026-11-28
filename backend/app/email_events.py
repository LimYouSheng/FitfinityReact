"""Project only client-facing event details into individual transactional emails."""

from sqlalchemy import select

from app.email_delivery import enqueue
from app.models.people import ClientPerson
from app.models.training import PackagePurchase


def package_values(purchase, used=0):
    """Project the purchased terms shared by welcome and later package notices."""
    return {
        "package": purchase.name,
        "used": used,
        "total": purchase.total_sessions,
        "start": purchase.start_date.isoformat(),
        "end": purchase.end_date.isoformat(),
    }


def client_welcome(session, client, trainer, purchase):
    if not session.info.get("transactional_email_enabled", False):
        return
    for person in session.scalars(select(ClientPerson).where(ClientPerson.client_id == client.id)):
        enqueue(
            session,
            f"client.welcome:{person.id}",
            "client_welcome",
            person.email,
            {"name": person.name, "trainer": trainer.name, **package_values(purchase)},
        )


def package_notice(session, purchase, event_key, *, kind="package_added", used=None):
    if not session.info.get("transactional_email_enabled", False):
        return
    for person in session.scalars(
        select(ClientPerson).where(ClientPerson.client_id == purchase.client_id)
    ):
        if not person.email:
            continue
        enqueue(
            session,
            f"{event_key}:{person.id}",
            kind,
            person.email,
            {
                "name": person.name,
                **package_values(purchase, 0 if used is None else used),
            },
        )


def session_completed(session, booking, key, used):
    if not session.info.get("transactional_email_enabled", False):
        return
    purchase = session.get(PackagePurchase, booking.purchase_id)
    package_notice(
        session, purchase, f"session.acknowledged:{key}", kind="session_complete", used=used
    )
