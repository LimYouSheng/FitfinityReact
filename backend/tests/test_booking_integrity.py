"""Strict persistence schedules and full-interval completed-booking occupancy."""

from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy import func, select

from app.models.people import Client, LifecycleEvent
from app.models.training import PackagePurchase, TrainingSession
from app.persistence import (
    PersistenceConflict,
    acknowledge,
    add_client,
    add_purchase,
    require_valid_session_schedule,
)
from tests.domain_fixtures import person, purchase_parts


@pytest.mark.parametrize(
    "day,start,end",
    [
        ("2026-02-31", time(10), time(11)),
        ("2026-09-10", time(10), time(11)),
        (datetime(2026, 9, 10), time(10), time(11)),
        (None, time(10), time(11)),
        (date(2026, 9, 10), "25:00", "26:00"),
        (date(2026, 9, 10), time(11), time(10)),
        (date(2026, 9, 10), time(10), time(10)),
        (date(2026, 9, 10), time(10, tzinfo=UTC), time(11, tzinfo=UTC)),
        (date(2026, 9, 10), time(10, 0, 1), time(11)),
        (date(2026, 9, 10), time(10), time(11, 0, 0, 1)),
    ],
)
def test_persistence_rejects_invalid_schedule(day, start, end):
    with pytest.raises(ValueError, match="valid date"):
        require_valid_session_schedule(day, start, end)


def test_persistence_accepts_leap_day_and_variable_duration():
    require_valid_session_schedule(date(2028, 2, 29), time(10, 5), time(11, 40))


@pytest.mark.database
@pytest.mark.parametrize("inactive", [False, True])
def test_completed_no_show_keeps_its_full_interval_even_when_inactive(domain_db, graph, inactive):
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        acknowledge(session, booking.id, booking.version, graph["user_id"], method="late_no_show")
        if inactive:
            cause = LifecycleEvent(
                client_id=graph["client_id"],
                status="inactive",
                reason="owner",
                actor_id=graph["owner_id"],
                actor_name="Owner",
            )
            session.add(cause)
            session.flush()
            effect = LifecycleEvent(
                purchase_id=graph["purchase_id"],
                status="inactive",
                reason="client",
                cause_id=cause.id,
                actor_id=graph["owner_id"],
                actor_name="Owner",
            )
            session.add(effect)
            session.flush()
            client = session.get(Client, graph["client_id"])
            purchase = session.get(PackagePurchase, graph["purchase_id"])
            client.status, client.lifecycle_event_id = "inactive", cause.id
            purchase.status, purchase.lifecycle_event_id = "inactive", effect.id
        other = add_client(
            session,
            Client(kind="individual", name="Other Client", trainer_id=graph["trainer_id"]),
            [person("Other Client")],
        )
        other_id, other_version = other.id, other.version
    if inactive:
        with domain_db.transaction() as session:
            client = session.get(Client, graph["client_id"])
            purchase = session.get(PackagePurchase, graph["purchase_id"])
            assert client.status == purchase.status == "inactive"
            assert (
                session.get(LifecycleEvent, purchase.lifecycle_event_id).cause_id
                == client.lifecycle_event_id
            )
    purchase, slots, preferences, bookings = purchase_parts(
        graph, graph["start_date"], client_id=other_id, stage="current"
    )
    bookings[0].starts_at, bookings[0].ends_at = time(10, 45), time(11, 45)
    # The other scheduled booking must not mask a missed completed-session conflict.
    bookings[1].starts_at, bookings[1].ends_at = time(11), time(12)
    with pytest.raises(PersistenceConflict, match="existing booking"):
        with domain_db.transaction() as session:
            add_purchase(
                session,
                purchase,
                slots,
                preferences,
                bookings,
                expected_client_version=other_version,
            )
    with domain_db.transaction() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(PackagePurchase)
                .where(PackagePurchase.client_id == other_id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(TrainingSession)
                .where(TrainingSession.client_id == other_id)
            )
            == 0
        )


@pytest.mark.database
def test_new_purchase_allows_touching_intervals_beside_completed_sessions(domain_db, graph):
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        acknowledge(session, booking.id, booking.version, graph["user_id"], method="late_no_show")
        other = add_client(
            session,
            Client(kind="individual", name="Adjacent Client", trainer_id=graph["trainer_id"]),
            [person("Adjacent Client")],
        )
        purchase, slots, preferences, bookings = purchase_parts(
            graph, graph["start_date"], client_id=other.id, stage="current"
        )
        for booking in bookings:
            booking.starts_at, booking.ends_at = time(11), time(12)
        add_purchase(
            session,
            purchase,
            slots,
            preferences,
            bookings,
            expected_client_version=other.version,
        )
    with domain_db.transaction() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(TrainingSession)
                .where(TrainingSession.purchase_id == purchase.id)
            )
            == 2
        )
