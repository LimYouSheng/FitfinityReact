"""Apply already-purchased settings when their Singapore business date becomes due."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import exists, select

from app.api.directory import bounded
from app.auth.errors import AuthError
from app.models.people import Client
from app.models.training import PackagePurchase


def activation_time():
    return datetime.now(UTC)


def activate_due(session):
    now = activation_time()
    today = now.astimezone(ZoneInfo("Asia/Singapore")).date()
    due = exists(
        select(PackagePurchase.id).where(
            PackagePurchase.client_id == Client.id,
            PackagePurchase.stage == "queued",
            PackagePurchase.status == "active",
            PackagePurchase.start_date <= today,
        )
    )
    clients = bounded(
        session,
        select(Client).where(Client.status == "active", due).order_by(Client.id).with_for_update(),
    )
    for client in clients:
        purchases = bounded(
            session,
            select(PackagePurchase)
            .where(PackagePurchase.client_id == client.id)
            .order_by(PackagePurchase.start_date, PackagePurchase.id)
            .with_for_update(),
        )
        current = next((p for p in purchases if p.stage == "current"), None)
        if current is None:
            raise AuthError("directory_incomplete", "Current package details are unavailable.", 503)
        for purchased in purchases:
            if (
                purchased.stage != "queued"
                or purchased.status != "active"
                or purchased.start_date > today
            ):
                continue
            if current.status == "active" and current.end_date >= today:
                # Concurrent purchases retain their own Trainer/settings. The current
                # row is the profile default, not exclusive ownership of usable credits.
                if purchased.activated_at is None:
                    purchased.activated_at = now
                continue
            current.stage = "archived"
            session.flush()  # Release the immediate one-current-purchase constraint first.
            purchased.stage = "current"
            purchased.activated_at = now
            client.trainer_id = purchased.trainer_id
            client.gender_preference = purchased.gender_preference
            client.version += 1
            session.flush()
            current = purchased
