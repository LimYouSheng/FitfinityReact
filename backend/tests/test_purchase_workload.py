"""Maximum supported purchase size must use bounded database round trips."""

from datetime import timedelta

import pytest
from sqlalchemy import event, func, select

from app.models.training import PackageTemplateRevision, TrainingSession
from app.persistence import add_purchase
from tests.domain_fixtures import purchase_parts

pytestmark = pytest.mark.database


def test_365_session_purchase_uses_one_batched_conflict_check(domain_db, graph):
    with domain_db.transaction() as session:
        session.add(
            PackageTemplateRevision(
                template_id=graph["template_id"],
                revision=2,
                name="365 sessions",
                total_sessions=365,
                validity_days=2790,
                actor_id=graph["owner_id"],
                actor_name="Owner",
            )
        )
    purchase, slots, preferences, _ = purchase_parts(graph)
    purchase.name = "365 sessions"
    purchase.template_revision = 2
    purchase.total_sessions = 365
    purchase.validity_days = 2790
    purchase.end_date = purchase.start_date + timedelta(days=2789)
    bookings = [
        TrainingSession(
            client_id=graph["client_id"],
            trainer_id=graph["trainer_id"],
            session_number=index + 1,
            schedule_slot_id=slots[0].id,
            training_date=purchase.start_date + timedelta(days=index * 7),
            starts_at=slots[0].starts_at,
            ends_at=slots[0].ends_at,
        )
        for index in range(365)
    ]
    selects = []

    def record(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(domain_db.engine, "before_cursor_execute", record)
    try:
        with domain_db.transaction() as session:
            add_purchase(
                session,
                purchase,
                slots,
                preferences,
                bookings,
                expected_client_version=graph["client_version"],
            )
    finally:
        event.remove(domain_db.engine, "before_cursor_execute", record)
    assert len(selects) <= 12, "Purchase reads must remain bounded as session count grows"
    with domain_db.transaction() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(TrainingSession)
                .where(TrainingSession.purchase_id == purchase.id)
            )
            == 365
        )
