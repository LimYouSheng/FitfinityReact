"""Open sessions have no invented dates/numbers, cannot be completed and retain capacity."""

from concurrent.futures import ThreadPoolExecutor
from datetime import time

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.models.people import Trainer
from app.models.training import Acknowledgement, TrainingSession
from app.persistence import PersistenceConflict, acknowledge, add_purchase
from tests.domain_fixtures import purchase_parts
from tests.test_client_deactivation_api import row_values
from tests.test_client_reactivation_review import deactivate, preview, read
from tests.test_client_reactivation_save import body, save
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


def make_open(session, identity):
    row = session.get(TrainingSession, identity)
    row.schedule_state = "open"
    row.session_number = row.training_date = row.starts_at = row.ends_at = row.schedule_slot_id = (
        None
    )
    session.flush()
    return row


def test_open_records_round_trip_without_fake_scheduling_and_reactivate_unchanged(
    api, domain_db, graph
):
    with domain_db.transaction() as session:
        before = row_values(make_open(session, graph["session_id"]))
    summary = api.get(f"/api/sessions/{graph['session_id']}")
    assert summary.status_code == 200, summary.text
    assert summary.json()["schedule_state"] == "open"
    assert all(summary.json()[field] is None for field in ["training_date", "starts_at", "ends_at"])
    deactivate(api, graph)
    result = read(api, graph)
    row = next(r for r in result["rows"] if r["id"] == str(graph["session_id"]))
    assert row["scheduleState"] == "open" and row["error"] is None
    assert all(row[field] is None for field in ["date", "originalDate", "startsAt", "endsAt"])
    assert save(api, graph, body(api, graph)).status_code == 200
    with domain_db.transaction() as session:
        assert row_values(session.get(TrainingSession, graph["session_id"])) == before


def test_reactivation_cannot_date_an_open_session_or_revive_an_inactive_trainer(
    api, domain_db, graph
):
    with domain_db.transaction() as session:
        make_open(session, graph["session_id"])
    deactivate(api, graph)
    result = read(api, graph)
    dates = {str(graph["session_id"]): str(graph["start_date"])}
    checked = preview(api, graph, result["expected"], dates)
    assert checked.status_code == 200, checked.text
    row = next(r for r in checked.json()["rows"] if r["id"] == str(graph["session_id"]))
    assert "open session" in row["error"]
    assert row["date"] is None
    assert save(api, graph, {"expected": result["expected"], "dates": dates}).status_code == 409
    with domain_db.transaction() as session:
        session.get(Trainer, graph["trainer_id"]).status = "inactive"
    assert save(api, graph, body(api, graph)).status_code == 409
    assert all("assigned trainer" in r["error"] for r in read(api, graph)["rows"])


@pytest.mark.parametrize(
    "invalid", ["number", "date", "start", "end", "slot", "completed", "booked", "unknown"]
)
def test_partial_open_or_booked_shapes_are_rejected_at_storage(domain_db, graph, invalid):
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        row = make_open(session, graph["session_id"])
        if invalid == "number":
            row.session_number = 1
        if invalid == "date":
            row.training_date = graph["start_date"]
        if invalid == "start":
            row.starts_at = time(10)
        if invalid == "end":
            row.ends_at = time(11)
        if invalid == "slot":
            row.schedule_slot_id = session.get(
                TrainingSession, graph["second_session_id"]
            ).schedule_slot_id
        if invalid == "completed":
            row.status = "completed"
        if invalid == "booked":
            row.schedule_state = "booked"
        if invalid == "unknown":
            row.schedule_state = "unknown"


@pytest.mark.parametrize("layer", ["repository", "database"])
def test_open_session_cannot_gain_acknowledgement_or_credits(domain_db, graph, layer):
    with domain_db.transaction() as session:
        make_open(session, graph["session_id"])
    with (
        pytest.raises(PersistenceConflict if layer == "repository" else DBAPIError),
        domain_db.transaction() as session,
    ):
        if layer == "repository":
            booking = session.get(TrainingSession, graph["session_id"])
            acknowledge(
                session, booking.id, booking.version, graph["owner_id"], method="late_no_show"
            )
        else:
            session.add(
                Acknowledgement(
                    session_id=graph["session_id"],
                    sequence=1,
                    method="late_no_show",
                    actor_id=graph["owner_id"],
                    actor_name="Owner",
                )
            )


def test_completed_booking_cannot_be_rewritten_as_open(domain_db, graph):
    with domain_db.transaction() as session:
        row = session.get(TrainingSession, graph["session_id"])
        acknowledge(session, row.id, row.version, graph["owner_id"], method="late_no_show")
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        make_open(session, graph["session_id"])


def test_concurrent_open_inserts_cannot_exceed_purchased_capacity(domain_db, graph):
    with domain_db.transaction() as session:
        purchase, slots, preferences, bookings = purchase_parts(graph)
        add_purchase(
            session,
            purchase,
            slots,
            preferences,
            bookings,
            expected_client_version=graph["client_version"],
        )
        purchase_id = purchase.id
        booking_ids = [b.id for b in bookings]
    with domain_db.transaction() as session:
        for identity in booking_ids:
            session.delete(session.get(TrainingSession, identity))

    def insert():
        try:
            with domain_db.transaction() as session:
                session.add(
                    TrainingSession(
                        client_id=graph["client_id"],
                        purchase_id=purchase_id,
                        trainer_id=graph["trainer_id"],
                        schedule_state="open",
                        session_number=None,
                        training_date=None,
                        starts_at=None,
                        ends_at=None,
                    )
                )
            return "created"
        except DBAPIError:
            return "capacity"

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: insert(), range(3)))
    assert sorted(results) == ["capacity", "created", "created"]
    with domain_db.transaction() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(TrainingSession)
                .where(TrainingSession.purchase_id == purchase_id)
            )
            == 2
        )


def test_open_records_block_downgrade_before_losing_unscheduled_evidence(domain_db, graph, migrate):
    with domain_db.transaction() as session:
        make_open(session, graph["session_id"])
    with pytest.raises(DBAPIError, match="Open-session downgrade refused"):
        migrate("downgrade", "20261013_0021")
    with domain_db.transaction() as session:
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "20261023_0036"
        assert session.get(TrainingSession, graph["session_id"]).schedule_state == "open"


def test_booked_history_survives_forward_and_backward_schema_changes(domain_db, graph, migrate):
    query = text(
        "SELECT id, training_date, starts_at, ends_at, session_number, version "
        "FROM training_sessions ORDER BY id"
    )
    with domain_db.transaction() as session:
        before = session.execute(query).all()
    migrate("downgrade", "20261013_0021")
    migrate()
    with domain_db.transaction() as session:
        assert session.execute(query).all() == before
        assert all(r.schedule_state == "booked" for r in session.scalars(select(TrainingSession)))


def test_booked_number_cannot_change_without_an_open_transition(domain_db, graph):
    with (
        pytest.raises(DBAPIError, match="immutable field: training_sessions.session_number"),
        domain_db.transaction() as session,
    ):
        session.get(TrainingSession, graph["session_id"]).session_number = 2


def test_open_session_can_be_booked_again_with_the_same_purchase_identity(domain_db, graph):
    with domain_db.transaction() as session:
        original = row_values(session.get(TrainingSession, graph["session_id"]))
        make_open(session, graph["session_id"])
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        booking.schedule_state = "booked"
        for name in ["session_number", "training_date", "starts_at", "ends_at", "schedule_slot_id"]:
            setattr(booking, name, original[name])
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        assert (
            booking.client_id == original["client_id"]
            and booking.purchase_id == original["purchase_id"]
        )
        assert booking.trainer_id == original["trainer_id"] and booking.status == original["status"]
        assert (
            booking.training_date == original["training_date"]
            and booking.session_number == original["session_number"]
        )
