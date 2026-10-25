"""Real PostgreSQL attribution keeps session identity separate from entry actors."""

from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import MetaData, create_engine, select, text
from sqlalchemy.exc import DBAPIError

from app.auth.errors import AuthError
from app.authorization import Principal, client_record, session_record
from app.migrations import migration_config
from app.models.communications import SessionEvent
from app.models.session_attribution import (
    SessionTrainerAssignmentHistory,
    SessionTrainerAttribution,
)
from app.models.training import TrainingSession
from app.persistence import acknowledge
from tests.conftest import isolated_database
from tests.test_client_assignment_review import replacement as replacement
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


def test_attribution_http_has_only_scoped_identity_evidence(api, graph):
    result = api.get(f"/api/sessions/{graph['session_id']}/attribution")
    assert result.status_code == 200, result.text
    assert result.json() == {
        "sessionId": str(graph["session_id"]),
        "originalState": "captured",
        "original": {"id": str(graph["trainer_id"]), "name": "Trainer One"},
        "assigned": {"id": str(graph["trainer_id"]), "name": "Trainer One"},
        "performedBy": None,
        "history": [],
    }
    assert api.get(f"/api/sessions/{uuid4()}/attribution").status_code == 404


def test_original_and_performer_are_not_the_acknowledgement_actor(domain_db, graph):
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        assert booking.assigned_trainer_id == graph["trainer_id"]
        row = session.get(SessionTrainerAttribution, booking.id)
        assert row.original_trainer_id == graph["trainer_id"]
        assert row.original_state == "captured"
        assert row.performed_by_trainer_id is None
        acknowledge(session, booking.id, booking.version, graph["owner_id"], method="late_no_show")
    with domain_db.transaction() as session:
        row = session.get(SessionTrainerAttribution, graph["session_id"])
        assert row.performed_by_trainer_id == graph["trainer_id"]
        assert row.performed_by_trainer_id != graph["owner_id"]


@pytest.mark.parametrize("change", ["original", "performer", "delete"])
def test_attribution_cannot_be_rewritten(domain_db, graph, change):
    with pytest.raises(DBAPIError, match="immutable Trainer attribution"):
        with domain_db.transaction() as session:
            if change == "delete":
                statement = "DELETE FROM session_trainer_attributions WHERE session_id=:id"
            elif change == "original":
                statement = (
                    "UPDATE session_trainer_attributions SET original_trainer_id=NULL "
                    "WHERE session_id=:id"
                )
            else:
                statement = (
                    "UPDATE session_trainer_attributions "
                    "SET performed_by_trainer_id=original_trainer_id WHERE session_id=:id"
                )
            session.execute(text(statement), {"id": graph["session_id"]})


def test_assignment_history_retains_actor_and_original_read_scope(domain_db, graph, replacement):
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        session.add(
            SessionEvent(
                session_id=booking.id,
                session_version=booking.version,
                kind="session_trainer",
                old_trainer_id=booking.trainer_id,
                new_trainer_id=replacement,
                note="Reviewed cover",
                actor_id=graph["owner_id"],
                actor_name="Owner Original",
            )
        )
        booking.trainer_id = replacement
    with domain_db.transaction() as session:
        row = session.get(SessionTrainerAttribution, graph["session_id"])
        assert row.original_trainer_id == graph["trainer_id"]
        edge = session.scalar(select(SessionTrainerAssignmentHistory))
        assert (edge.old_trainer_id, edge.new_trainer_id) == (graph["trainer_id"], replacement)
        evidence = session.get(SessionEvent, edge.event_id)
        assert evidence.actor_id == graph["owner_id"] and evidence.note == "Reviewed cover"
        original = Principal(graph["user_id"], "Trainer One", "trainer", graph["trainer_id"])
        assert session_record(session, original, graph["session_id"]).trainer_id == replacement
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        session.add(
            SessionEvent(
                session_id=booking.id,
                session_version=booking.version,
                kind="session_trainer",
                old_trainer_id=replacement,
                new_trainer_id=graph["trainer_id"],
                actor_id=graph["owner_id"],
                actor_name="Owner Original",
                note="Cover ended",
            )
        )
        booking.trainer_id = graph["trainer_id"]
    # This Trainer is neither original, current nor permanent: only the immutable
    # assignment edge grants history, and it grants no other scope or writes.
    historical = Principal(uuid4(), "Former cover", "trainer", replacement)
    with domain_db.transaction() as session:
        assert (
            session_record(session, historical, graph["session_id"]).trainer_id
            == graph["trainer_id"]
        )
        for operation in (
            lambda: session_record(session, historical, graph["session_id"], write=True),
            lambda: session_record(session, historical, graph["second_session_id"]),
            lambda: client_record(session, historical, graph["client_id"]),
        ):
            with pytest.raises(AuthError) as denied:
                operation()
            assert denied.value.status == 404
    with pytest.raises(DBAPIError, match="immutable"):
        with domain_db.transaction() as session:
            session.execute(text("DELETE FROM session_trainer_assignment_history"))


def test_populated_upgrade_flags_unknown_originals_and_preserves_completed_performer(
    domain_db, graph
):
    """Copy synthetic records into the actual outgoing schema, then run the forward migration."""
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        acknowledge(session, booking.id, booking.version, graph["owner_id"], method="late_no_show")
    with isolated_database() as url:
        engine = create_engine(url)
        try:
            with engine.connect() as connection:
                config = migration_config()
                config.attributes["connection"] = connection
                command.upgrade(config, "20261024_0045")
            legacy = MetaData()
            legacy.reflect(bind=engine)
            with domain_db.engine.connect() as source, engine.begin() as target:
                target.execute(text("SET CONSTRAINTS ALL DEFERRED"))
                for name in (
                    "staff_users",
                    "trainers",
                    "clients",
                    "client_people",
                    "package_templates",
                    "package_template_revisions",
                    "package_purchases",
                    "purchase_schedule_slots",
                    "session_identities",
                    "training_sessions",
                    "acknowledgements",
                    "credit_debits",
                ):
                    table = legacy.tables[name]
                    # Omit transaction provenance so the outgoing schema's normal
                    # creation guards bind these copied synthetic rows to this transaction.
                    fields = [c for c in table.columns if c.name != "created_xid"]
                    records = source.execute(select(*fields)).mappings().all()
                    if records:
                        target.execute(
                            table.insert(),
                            [
                                {**dict(row), **({"version": 1} if "version" in row else {})}
                                for row in records
                            ],
                        )
            with engine.connect() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
                rows = (
                    connection.execute(
                        text(
                            "SELECT session_id, original_state, original_trainer_id, "
                            "performed_by_trainer_id "
                            "FROM session_trainer_attributions ORDER BY session_id"
                        )
                    )
                    .mappings()
                    .all()
                )
                assert len(rows) == 2
                assert all(row["original_state"] == "legacy_unresolved" for row in rows)
                assert all(row["original_trainer_id"] is None for row in rows)
                completed = next(row for row in rows if row["session_id"] == graph["session_id"])
                assert completed["performed_by_trainer_id"] == graph["trainer_id"]
                assert connection.scalar(text("SELECT count(*) FROM credit_debits")) == 1
        finally:
            engine.dispose()


def test_history_cannot_forge_another_sessions_authority(domain_db, graph, replacement):
    with domain_db.transaction() as session:
        event = SessionEvent(
            session_id=graph["session_id"],
            session_version=1,
            kind="session_details",
            actor_id=graph["owner_id"],
            actor_name="Owner Original",
        )
        session.add(event)
        session.flush()
        identity = event.id
    with pytest.raises(DBAPIError, match="invalid assignment history source"):
        with domain_db.transaction() as session:
            session.add(
                SessionTrainerAssignmentHistory(
                    event_id=identity,
                    session_id=graph["second_session_id"],
                    old_trainer_id=graph["trainer_id"],
                    new_trainer_id=replacement,
                )
            )
