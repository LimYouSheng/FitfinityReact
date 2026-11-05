"""Actual PostgreSQL populated-upgrade, rollback and concurrency evidence."""

from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from app.migrations import migration_config
from app.release_upgrade import LOCK_KEY, UpgradeRefused, upgrade_existing

pytestmark = pytest.mark.database
BASE = "20260924_0006"
HEAD = "20261101_0052"


@pytest.fixture
def outgoing(database_url):
    engine = create_engine(database_url, poolclass=NullPool, hide_parameters=True)
    config = migration_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, BASE)
        connection.execute(
            text("INSERT INTO staff_users (id,name,email,role) VALUES (:id,:name,:email,'owner')"),
            {"id": uuid4(), "name": "Synthetic Owner", "email": "owner@example.test"},
        )
    url = make_url(database_url)
    kwargs = dict(
        expected_database=url.database,
        expected_user=url.username,
        from_revision=BASE,
        to_revision=HEAD,
    )
    try:
        yield engine, kwargs
    finally:
        engine.dispose()


def owner(engine):
    with engine.connect() as connection:
        return connection.execute(text("SELECT id,name,email,role FROM staff_users")).all()


def revision(engine):
    with engine.connect() as connection:
        return connection.scalar(text("SELECT version_num FROM alembic_version"))


def test_populated_initial_release_upgrade_preserves_owner_and_can_recover_lost_receipt(outgoing):
    engine, kwargs = outgoing
    before = owner(engine)
    assert upgrade_existing(engine, **kwargs) == {"outcome": "upgraded", "schema": HEAD}
    assert owner(engine) == before
    assert revision(engine) == HEAD
    assert upgrade_existing(engine, **kwargs) == {"outcome": "already_at_target", "schema": HEAD}
    assert owner(engine) == before


def test_wrong_database_or_identity_cannot_change_schema(outgoing):
    engine, kwargs = outgoing
    for key in ("expected_database", "expected_user"):
        with pytest.raises(UpgradeRefused, match="identity differs"):
            upgrade_existing(engine, **{**kwargs, key: "wrong"})
        assert revision(engine) == BASE


def test_stale_start_revision_refuses_before_changes(outgoing):
    engine, kwargs = outgoing
    with pytest.raises(UpgradeRefused, match="Observed schema differs"):
        upgrade_existing(engine, **{**kwargs, "from_revision": "20261024_0045"})
    assert revision(engine) == BASE


def test_upgrade_lock_rejects_competing_connection(outgoing):
    engine, kwargs = outgoing
    with engine.begin() as held:
        held.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
        with pytest.raises(UpgradeRefused, match="in progress"):
            upgrade_existing(engine, **kwargs)
        assert revision(engine) == BASE
    assert upgrade_existing(engine, **kwargs)["outcome"] == "upgraded"


def test_failure_after_real_ddl_rolls_back_schema_and_preserves_owner(outgoing, monkeypatch):
    engine, kwargs = outgoing
    before = owner(engine)
    original = command.upgrade

    def interrupted(config, target):
        original(config, target)
        raise RuntimeError("synthetic interrupted response before commit")

    monkeypatch.setattr(command, "upgrade", interrupted)
    with pytest.raises(RuntimeError, match="synthetic interrupted"):
        upgrade_existing(engine, **kwargs)
    assert revision(engine) == BASE
    assert owner(engine) == before
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT to_regclass('public.session_trainer_attributions')"))
            is None
        )
    monkeypatch.setattr(command, "upgrade", original)
    assert upgrade_existing(engine, **kwargs)["outcome"] == "upgraded"


def test_no_downgrade_floating_head_or_bootstrap(outgoing):
    engine, kwargs = outgoing
    for changes in (
        {"to_revision": "head"},
        {"from_revision": "base"},
        {"from_revision": HEAD, "to_revision": BASE},
    ):
        with pytest.raises(UpgradeRefused, match="exact forward"):
            upgrade_existing(engine, **{**kwargs, **changes})
    assert revision(engine) == BASE


def test_populated_later_release_preserves_client_package_and_session_graph(domain_db, graph):
    from tests.legacy_migration_graph import outgoing_graph

    with outgoing_graph(domain_db) as (db, _):
        with db.engine.connect() as connection:
            database, user = connection.execute(
                text("SELECT current_database(), current_user")
            ).one()
            before = {
                table: connection.execute(text(f"SELECT * FROM {table} ORDER BY id"))
                .mappings()
                .all()
                for table in ("clients", "package_purchases", "training_sessions")
            }
        assert (
            upgrade_existing(
                db.engine,
                expected_database=database,
                expected_user=user,
                from_revision="20261024_0045",
                to_revision=HEAD,
            )["outcome"]
            == "upgraded"
        )
        with db.engine.connect() as connection:
            for table, rows in before.items():
                after = (
                    connection.execute(text(f"SELECT * FROM {table} ORDER BY id")).mappings().all()
                )
                assert len(after) == len(rows)
                assert [{key: row[key] for key in rows[0]} for row in after] == rows
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM session_trainer_attributions "
                        "WHERE original_state='legacy_unresolved'"
                    )
                )
                == 2
            )
            assert connection.scalar(text("SELECT count(*) FROM credit_debits")) == 0


@pytest.mark.parametrize("target", [BASE, HEAD])
def test_read_only_schema_receipt_reports_actual_revision_without_business_rows(outgoing, target):
    import json
    from pathlib import Path

    import psycopg

    engine, kwargs = outgoing
    if target == HEAD:
        upgrade_existing(engine, **kwargs)
    before = owner(engine)
    script = (Path(__file__).parents[1] / "infrastructure/read-schema.sql").read_text()
    dsn = engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
    results = []
    with psycopg.connect(dsn, autocommit=True) as connection, connection.cursor() as cursor:
        cursor.execute(script)
        while True:
            if cursor.description:
                results.append(cursor.fetchone()[0])
            if not cursor.nextset():
                break
        assert connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
    assert len(results) == 1
    receipt = results[0]
    assert receipt["alembic_revisions"] == [target]
    assert receipt["transaction_read_only"] == "on"
    assert receipt["database"] == kwargs["expected_database"]
    tables = {item["name"]: item for item in receipt["tables"]}
    assert "staff_users" in tables
    assert ("session_trainer_attributions" in tables) == (target == HEAD)
    assert {column["name"] for column in tables["staff_users"]["columns"]} >= {"id", "email"}
    assert receipt["constraints"] and receipt["triggers"] and receipt["indexes"]
    assert "owner@example.test" not in json.dumps(receipt)
    assert "Synthetic Owner" not in json.dumps(receipt)
    assert owner(engine) == before
    assert revision(engine) == target
