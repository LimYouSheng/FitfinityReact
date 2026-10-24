"""A postponed-session proposal retains its booking until a separate approved command."""

from datetime import time

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models.communications import ChangeRequest
from app.models.training import TrainingSession
from tests.test_message_api import seed_request

pytestmark = pytest.mark.database


@pytest.mark.parametrize(
    "field,value",
    [("old_date", None), ("old_start", None), ("old_end", time(9)), ("new_start", time(12))],
)
def test_postponement_proposal_requires_a_complete_original_booking_and_open_target(
    domain_db, graph, field, value
):
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        seed_request(session, graph, "session_postpone", **{field: value})
    with domain_db.transaction() as session:
        assert session.scalar(select(ChangeRequest)) is None


def test_retained_postponement_prevents_lossy_downgrade_and_never_unschedules_booking(
    domain_db, graph, migrate
):
    with domain_db.transaction() as session:
        identity, _ = seed_request(session, graph, "session_postpone")
    with pytest.raises(DBAPIError, match="Postponement-request downgrade refused"):
        migrate("downgrade", "20261013_0023")
    with domain_db.transaction() as session:
        assert session.get(ChangeRequest, identity).status == "pending"
        booking = session.get(TrainingSession, graph["session_id"])
        assert booking.schedule_state == "booked" and booking.training_date == graph["start_date"]
        assert booking.starts_at == time(10)
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "20261024_0038"


def test_open_session_time_proposal_cancels_without_booking_or_losing_its_original_open_state(
    domain_db, graph, migrate
):
    from uuid import uuid4

    from app.api.request_cancellation import CancelRequest, save
    from tests.test_open_sessions import make_open
    from tests.test_request_cancellation import actor

    with domain_db.transaction() as session:
        make_open(session, graph["session_id"])
        identity, _ = seed_request(
            session, graph, "session_time", old_date=None, old_start=None, old_end=None
        )
    with pytest.raises(DBAPIError, match="Postponement-request downgrade refused"):
        migrate("downgrade", "20261013_0023")
    with domain_db.transaction() as session:
        saved = save(session, actor(graph), identity, uuid4(), CancelRequest(expectedVersion=1))
        assert saved.status == "cancelled"
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, graph["session_id"]).schedule_state == "open"
        assert session.get(ChangeRequest, identity).old_date is None


@pytest.mark.parametrize("patch", [{"old_date": None}, {"old_start": None}, {"new_date": None}])
def test_session_time_proposal_rejects_partial_old_or_new_bookings(domain_db, graph, patch):
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        seed_request(session, graph, "session_time", **patch)
