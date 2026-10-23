"""Booking order changes preserve IDs and reject invalid positions in PostgreSQL."""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.models.people import Client
from app.models.training import Acknowledgement, CreditDebit, PackagePurchase, TrainingSession
from app.persistence import acknowledge, add_purchase
from app.session_numbering import renumber_purchase
from tests.domain_fixtures import purchase_parts
from tests.test_client_deactivation_api import row_values
from tests.test_open_sessions import make_open

pytestmark = pytest.mark.database


def positions(db, graph):
    with db.transaction() as session:
        return {
            row.id: (row.session_number, row.training_date, row.version)
            for row in session.scalars(
                select(TrainingSession).where(TrainingSession.purchase_id == graph["purchase_id"])
            )
        }


def test_move_swaps_positions_without_replacing_records(domain_db, graph):
    before = positions(domain_db, graph)
    with domain_db.transaction() as session:
        moved = session.get(TrainingSession, graph["second_session_id"])
        moved.training_date = before[graph["session_id"]][1] - timedelta(days=1)
        assert set(renumber_purchase(session, graph["purchase_id"])) == set(before)
    after = positions(domain_db, graph)
    assert set(after) == set(before)
    assert after[graph["session_id"]][:2] == (2, before[graph["session_id"]][1])
    assert after[graph["second_session_id"]][0] == 1
    with domain_db.transaction() as session:
        assert renumber_purchase(session, graph["purchase_id"]) == []
    assert positions(domain_db, graph) == after


def test_open_record_has_no_position_and_does_not_reserve_one(domain_db, graph):
    with domain_db.transaction() as session:
        make_open(session, graph["session_id"])
        assert renumber_purchase(session, graph["purchase_id"]) == [graph["second_session_id"]]
    saved = positions(domain_db, graph)
    assert saved[graph["session_id"]][:2] == (None, None)
    assert saved[graph["second_session_id"]][0] == 1


def test_failed_transaction_restores_booking_and_all_positions(domain_db, graph):
    before = positions(domain_db, graph)
    with pytest.raises(RuntimeError, match="interrupt"), domain_db.transaction() as session:
        moved = session.get(TrainingSession, graph["second_session_id"])
        moved.training_date = before[graph["session_id"]][1] - timedelta(days=1)
        renumber_purchase(session, graph["purchase_id"])
        raise RuntimeError("interrupt before commit")
    assert positions(domain_db, graph) == before


def test_arbitrary_number_is_still_rejected_by_database(domain_db, graph):
    before = positions(domain_db, graph)
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.get(TrainingSession, graph["session_id"]).session_number = 2
    assert positions(domain_db, graph) == before


def test_completed_evidence_and_credit_survive_position_change(domain_db, graph):
    with domain_db.transaction() as session:
        acknowledge(session, graph["session_id"], 1, graph["owner_id"], method="late_no_show")

    def evidence():
        with domain_db.transaction() as session:
            return {
                model.__tablename__: [row_values(row) for row in session.scalars(select(model))]
                for model in (Acknowledgement, CreditDebit, PackagePurchase)
            }

    before = evidence()
    with domain_db.transaction() as session:
        completed = session.get(TrainingSession, graph["session_id"])
        original = row_values(completed)
        moved = session.get(TrainingSession, graph["second_session_id"])
        moved.training_date = completed.training_date - timedelta(days=1)
        renumber_purchase(session, graph["purchase_id"])
        assert completed.status == "completed" and completed.session_number == 2
        for key, value in original.items():
            if key not in {"session_number", "version", "updated_at"}:
                assert getattr(completed, key) == value
    assert evidence() == before


def test_other_purchase_positions_are_unchanged(domain_db, graph):
    with domain_db.transaction() as session:
        purchase, slots, preferences, bookings = purchase_parts(graph)
        add_purchase(
            session,
            purchase,
            slots,
            preferences,
            bookings,
            expected_client_version=session.get(Client, graph["client_id"]).version,
        )
        foreign_id = purchase.id
    other = {**graph, "purchase_id": foreign_id}
    before = positions(domain_db, other)
    with domain_db.transaction() as session:
        make_open(session, graph["session_id"])
        renumber_purchase(session, graph["purchase_id"])
    assert positions(domain_db, other) == before


def test_deferred_uniqueness_still_rejects_duplicate_positions_at_commit(domain_db, graph):
    before = positions(domain_db, graph)
    with pytest.raises(DBAPIError, match="uq_training_sessions_purchase_id_session_number"):
        with domain_db.transaction() as session:
            purchase, slots, preferences, bookings = purchase_parts(graph)
            bookings[1].session_number = 1
            add_purchase(
                session,
                purchase,
                slots,
                preferences,
                bookings,
                expected_client_version=session.get(Client, graph["client_id"]).version,
            )
            session.flush()
    assert positions(domain_db, graph) == before
    with domain_db.transaction() as session:
        assert len(session.scalars(select(PackagePurchase)).all()) == 1


def test_renumbered_history_survives_downgrade_and_upgrade(domain_db, graph, migrate):
    with domain_db.transaction() as session:
        moved = session.get(TrainingSession, graph["second_session_id"])
        moved.training_date -= timedelta(days=8)
        renumber_purchase(session, graph["purchase_id"])
    before = positions(domain_db, graph)
    migrate("downgrade", "20261013_0030")
    assert positions(domain_db, graph) == before
    migrate()
    assert positions(domain_db, graph) == before
