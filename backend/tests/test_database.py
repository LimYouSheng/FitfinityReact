import pytest
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, TimeoutError

from app.database import Database
from app.main import create_app
from app.migrations import expected_revisions

pytestmark = pytest.mark.database


def test_forward_backward_forward_migrations_preserve_other_data(database_settings, migrate):
    db = Database(database_settings)
    try:
        with db.transaction() as session:
            session.execute(text("CREATE TABLE preservation_probe (value integer NOT NULL)"))
            session.execute(text("INSERT INTO preservation_probe VALUES (17)"))
        migrate()
        migrate()  # A repeated upgrade must be harmless.
        with db.engine.connect() as connection:
            assert (
                set(MigrationContext.configure(connection).get_current_heads())
                == expected_revisions()
            )
        migrate("downgrade", "base")
        with db.engine.connect() as connection:
            assert MigrationContext.configure(connection).get_current_heads() == ()
            assert connection.scalar(text("SELECT value FROM preservation_probe")) == 17
        migrate()
        with db.engine.connect() as connection:
            assert (
                set(MigrationContext.configure(connection).get_current_heads())
                == expected_revisions()
            )
    finally:
        db.close()


def test_readiness_requires_current_migrations(database_settings, migrate):
    with TestClient(create_app(database_settings)) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        migrate()
        assert client.get("/health/ready").status_code == 200
        migrate("downgrade", "base")
        assert client.get("/health/ready").status_code == 503


def test_transaction_failure_rolls_back_every_write(database_settings):
    db = Database(database_settings)
    try:
        with db.transaction() as session:
            session.execute(text("CREATE TABLE atomic_probe (id integer PRIMARY KEY)"))
        with pytest.raises(IntegrityError), db.transaction() as session:
            session.execute(text("INSERT INTO atomic_probe VALUES (1)"))
            session.execute(text("INSERT INTO atomic_probe VALUES (1)"))
        with db.transaction() as session:
            assert session.scalar(text("SELECT count(*) FROM atomic_probe")) == 0
            session.execute(text("INSERT INTO atomic_probe VALUES (2)"))
        with db.transaction() as session:
            assert session.scalar(text("SELECT id FROM atomic_probe")) == 2
    finally:
        db.close()


def test_pool_has_no_overflow_and_recovers_after_exhaustion(database_settings):
    db = Database(database_settings)
    try:
        with db.engine.connect() as first:
            assert first.scalar(text("SELECT 1")) == 1
            with pytest.raises(TimeoutError), db.engine.connect():
                pytest.fail("A bounded pool must not open an overflow connection")
        with db.engine.connect() as recovered:
            assert recovered.scalar(text("SELECT 1")) == 1
    finally:
        db.close()


def test_connections_have_server_time_and_transaction_limits(database_settings):
    db = Database(database_settings)
    try:
        with db.engine.connect() as connection:
            assert connection.scalar(text("SHOW timezone")) == "UTC"
            assert connection.scalar(text("SHOW statement_timeout")) == "5s"
            assert connection.scalar(text("SHOW idle_in_transaction_session_timeout")) == "5s"
            assert connection.scalar(text("SHOW lock_timeout")) == "1s"
    finally:
        db.close()


def test_each_database_starts_without_another_tests_tables(database_settings):
    db = Database(database_settings)
    try:
        with db.engine.connect() as connection:
            tables = (
                connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                )
                .scalars()
                .all()
            )
            assert tables == []
    finally:
        db.close()
