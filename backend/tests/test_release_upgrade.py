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
    from psycopg import sql

    engine, kwargs = outgoing
    if target == HEAD:
        upgrade_existing(engine, **kwargs)
    before = owner(engine)
    script = (Path(__file__).parents[1] / "infrastructure/read-schema.sql").read_text()
    dsn = engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
    revoke_connect = sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(
        sql.Identifier(kwargs["expected_database"])
    )
    with psycopg.connect(dsn, autocommit=True) as connection, connection.cursor() as cursor:
        for change, expected in (
            (None, (True, True, True)),
            ("ALTER ROLE fitfinity_app NOLOGIN", (False, True, True)),
            (revoke_connect, (True, False, True)),
            ("REVOKE USAGE ON SCHEMA public FROM PUBLIC", (True, True, False)),
        ):
            # Stage the fixed probe role privately. The packaged query rolls back the role and ACLs.
            cursor.execute("BEGIN ISOLATION LEVEL REPEATABLE READ")
            cursor.execute("CREATE ROLE fitfinity_app LOGIN")
            if change is not None:
                cursor.execute(change)
            results = []
            cursor.execute(script)
            while True:
                if cursor.description:
                    results.append(cursor.fetchone()[0])
                if not cursor.nextset():
                    break
            assert connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
            assert len(results) == 1
            receipt = results[0]
            runtime = next(row for row in receipt["roles"] if row["name"] == "fitfinity_app")
            access = (runtime["login"], runtime["database_connect"], runtime["schema_usage"])
            assert access == expected
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


@pytest.mark.parametrize("target", [BASE, HEAD])
def test_private_catalog_probe_preserves_real_database_and_redacts_rows(outgoing, target):
    import hashlib

    from app.schema_probe import SQL, observe

    engine, kwargs = outgoing
    if target == HEAD:
        upgrade_existing(engine, **kwargs)
    before = owner(engine)
    receipt = observe(
        engine.url.render_as_string(hide_password=False),
        expected_database=kwargs["expected_database"],
        expected_user=kwargs["expected_user"],
        sql_sha256=hashlib.sha256(SQL.read_bytes()).hexdigest(),
    )
    assert receipt["alembic_revisions"] == [target]
    assert receipt["transaction_read_only"] == "on"
    assert "Synthetic Owner" not in str(receipt)
    assert "owner@example.test" not in str(receipt)
    assert owner(engine) == before
    assert revision(engine) == target


def test_probe_refuses_wrong_identity_and_changed_sql_without_mutation(outgoing):
    import hashlib

    from app.schema_probe import SQL, ObservationRefused, observe

    engine, kwargs = outgoing
    arguments = dict(
        expected_database=kwargs["expected_database"],
        expected_user=kwargs["expected_user"],
        sql_sha256=hashlib.sha256(SQL.read_bytes()).hexdigest(),
    )
    before = owner(engine)
    for key, value in [
        ("expected_database", "foreign"),
        ("expected_user", "foreign"),
        ("sql_sha256", "0" * 64),
    ]:
        with pytest.raises(ObservationRefused):
            observe(engine.url.render_as_string(hide_password=False), **{**arguments, key: value})
        assert owner(engine) == before
        assert revision(engine) == BASE


def test_probe_read_only_session_rejects_even_digest_bound_write(outgoing, monkeypatch, tmp_path):
    import hashlib

    from app import schema_probe

    engine, kwargs = outgoing
    before = owner(engine)
    # Use an unconstrained synthetic table: staff deletion is independently blocked
    # by domain triggers and cannot prove this session's read-only protection.
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE probe_write_guard (id integer PRIMARY KEY)"))
        connection.execute(text("INSERT INTO probe_write_guard VALUES (1)"))
        assert connection.execute(text("DELETE FROM probe_write_guard")).rowcount == 1
        connection.execute(text("INSERT INTO probe_write_guard VALUES (1)"))
    script = tmp_path / "bad.sql"
    script.write_text("DELETE FROM probe_write_guard;")
    monkeypatch.setattr(schema_probe, "SQL", script)
    with pytest.raises(schema_probe.ObservationRefused):
        schema_probe.observe(
            engine.url.render_as_string(hide_password=False),
            expected_database=kwargs["expected_database"],
            expected_user=kwargs["expected_user"],
            sql_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),
        )
    assert owner(engine) == before
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM probe_write_guard")) == 1


def test_probe_missing_schema_fails_without_bootstrap(database_url):
    import hashlib

    from app.schema_probe import SQL, ObservationRefused, observe

    url = make_url(database_url)
    with pytest.raises(ObservationRefused, match="Catalog observation failed"):
        observe(
            database_url,
            expected_database=url.database,
            expected_user=url.username,
            sql_sha256=hashlib.sha256(SQL.read_bytes()).hexdigest(),
        )
    engine = create_engine(database_url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT to_regclass('public.alembic_version')")) is None
    finally:
        engine.dispose()


def test_private_http_upgrade_preserves_populated_rows_and_recovers_lost_receipt(outgoing):
    from fastapi.testclient import TestClient

    from app.release_upgrade_service import create_upgrade

    engine, kwargs = outgoing
    before = owner(engine)
    app = create_upgrade(
        lambda: upgrade_existing(engine, **kwargs),
        operation_id="a" * 32,
        source_sha="b" * 40,
        from_revision=BASE,
        to_revision=HEAD,
    )
    intent = b'{"operation":"upgrade-existing","operation_id":"' + b"a" * 32 + b'"}'
    with TestClient(app) as client:
        first = client.post("/events", content=intent)
        assert first.status_code == 200
        assert first.json()["outcome"] == "upgraded"
        assert revision(engine) == HEAD
        assert owner(engine) == before
        recovered = client.post("/events", content=intent)
        assert recovered.status_code == 200
        assert recovered.json()["outcome"] == "already_at_target"
        assert owner(engine) == before


def test_private_http_failure_after_ddl_rolls_back_and_does_not_leak(outgoing, monkeypatch):
    from fastapi.testclient import TestClient

    from app.release_upgrade_service import create_upgrade

    engine, kwargs = outgoing
    before = owner(engine)
    original = command.upgrade

    def fail(config, target):
        original(config, target)
        raise RuntimeError("sensitive SQL and credentials")

    monkeypatch.setattr(command, "upgrade", fail)
    app = create_upgrade(
        lambda: upgrade_existing(engine, **kwargs),
        operation_id="a" * 32,
        source_sha="b" * 40,
        from_revision=BASE,
        to_revision=HEAD,
    )
    with TestClient(app) as client:
        response = client.post(
            "/events",
            content=b'{"operation":"upgrade-existing","operation_id":"' + b"a" * 32 + b'"}',
        )
        assert response.status_code == 503
        assert response.json() == {"error": "migration_failed_or_uncertain"}
    assert revision(engine) == BASE
    assert owner(engine) == before


def test_upgrade_expired_during_database_preflight_cannot_start_ddl(outgoing, monkeypatch):
    from app import release_upgrade

    engine, kwargs = outgoing
    before = owner(engine)
    ticks = iter([100, 201])
    monkeypatch.setattr(release_upgrade, "utc_timestamp", lambda: next(ticks))
    with pytest.raises(UpgradeRefused, match="expired during database preflight"):
        upgrade_existing(engine, **kwargs, deadline=200)
    assert revision(engine) == BASE
    assert owner(engine) == before


def test_inflight_application_transaction_prevents_any_schema_write(outgoing):
    from psycopg.errors import LockNotAvailable

    engine, kwargs = outgoing
    before = owner(engine)
    with engine.begin() as application:
        application.execute(text("SELECT id FROM staff_users"))
        with pytest.raises(LockNotAvailable):
            upgrade_existing(engine, **kwargs)
        assert revision(engine) == BASE
        assert owner(engine) == before
    assert upgrade_existing(engine, **kwargs)["outcome"] == "upgraded"
    assert owner(engine) == before


def test_catalog_table_identifiers_cannot_escape_the_migration_lock(outgoing):
    from psycopg import sql

    engine, kwargs = outgoing
    name = 'audit"; DROP TABLE staff_users; --'
    with engine.begin() as connection:
        with connection.connection.driver_connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE TABLE {} (id integer)").format(sql.Identifier(name)))
    before = owner(engine)
    assert upgrade_existing(engine, **kwargs)["outcome"] == "upgraded"
    assert owner(engine) == before
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename=:name"
                ),
                {"name": name},
            )
            == 1
        )


@pytest.fixture
def runtime(outgoing):
    """Create one restricted login owned by this isolated test database."""
    from psycopg import sql

    engine, kwargs = outgoing
    role = "fitfinity_test_runtime_" + uuid4().hex
    with engine.begin() as connection:
        with connection.connection.driver_connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE ROLE {} LOGIN NOINHERIT").format(sql.Identifier(role)))
            cursor.execute(
                sql.SQL("REVOKE TEMP ON DATABASE {} FROM PUBLIC").format(
                    sql.Identifier(kwargs["expected_database"])
                )
            )
            cursor.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role))
            )
    try:
        yield engine, {**kwargs, "runtime_role": role}
    finally:
        with engine.begin() as connection:
            with connection.connection.driver_connection.cursor() as cursor:
                cursor.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
                cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_upgrade_grants_new_tables_and_preserves_immutable_and_ddl_denials(runtime):
    from psycopg import sql
    from sqlalchemy.exc import ProgrammingError

    engine, kwargs = runtime
    before = owner(engine)
    assert upgrade_existing(engine, **kwargs)["outcome"] == "upgraded"
    assert owner(engine) == before
    assert upgrade_existing(engine, **kwargs)["outcome"] == "already_at_target"
    with engine.connect() as connection:
        with connection.connection.driver_connection.cursor() as cursor:
            cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(kwargs["runtime_role"])))
        assert connection.scalar(text("SELECT name FROM staff_users")) == "Synthetic Owner"
        assert connection.scalar(text("SELECT count(*) FROM admin_operation_requests")) == 0
        assert (
            connection.execute(text("UPDATE admin_operation_requests SET status=status")).rowcount
            == 0
        )
        connection.rollback()
    for statement in (
        "DELETE FROM session_events",
        "UPDATE api_receipts SET id=id",
        "TRUNCATE staff_users",
        "CREATE TABLE unauthorized (id integer)",
        "CREATE TEMP TABLE unauthorized (id integer)",
    ):
        with engine.connect() as connection:
            with connection.connection.driver_connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(kwargs["runtime_role"]))
                )
            with pytest.raises(ProgrammingError, match="permission denied"):
                connection.execute(text(statement))
    assert owner(engine) == before


@pytest.mark.parametrize(
    "drift", ["excess", "unknown_table", "public_grant", "membership", "future_grant"]
)
def test_grant_drift_rolls_back_schema_and_missing_permissions(runtime, drift):
    from psycopg import sql

    from app.runtime_grants import RuntimeGrantsRefused

    engine, kwargs = runtime
    role = kwargs["runtime_role"]
    with engine.begin() as connection:
        with connection.connection.driver_connection.cursor() as cursor:
            if drift == "excess":
                cursor.execute(
                    sql.SQL("GRANT TRUNCATE ON staff_users TO {}").format(sql.Identifier(role))
                )
            elif drift == "unknown_table":
                cursor.execute("CREATE TABLE unexpected (id integer)")
            elif drift == "public_grant":
                cursor.execute("GRANT SELECT ON staff_users TO PUBLIC")
            elif drift == "future_grant":
                cursor.execute(
                    sql.SQL("ALTER DEFAULT PRIVILEGES GRANT SELECT ON TABLES TO {}").format(
                        sql.Identifier(role)
                    )
                )
            else:
                cursor.execute(sql.SQL("GRANT pg_read_all_data TO {}").format(sql.Identifier(role)))
    before = owner(engine)
    with pytest.raises(RuntimeGrantsRefused):
        upgrade_existing(engine, **kwargs)
    assert revision(engine) == BASE
    assert owner(engine) == before
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT to_regclass('public.admin_operation_requests')")) is None
        )
        assert not connection.scalar(
            text("SELECT has_table_privilege(:role,'staff_users','INSERT')"), {"role": role}
        )


def test_target_revision_with_missing_grants_is_refused_without_repair(runtime):
    from app.runtime_grants import RuntimeGrantsRefused

    engine, kwargs = runtime
    upgrade_existing(
        engine, **{key: value for key, value in kwargs.items() if key != "runtime_role"}
    )
    with pytest.raises(RuntimeGrantsRefused, match="incomplete"):
        upgrade_existing(engine, **kwargs)
    with engine.connect() as connection:
        assert not connection.scalar(
            text("SELECT has_table_privilege(:role,'staff_users','SELECT')"),
            {"role": kwargs["runtime_role"]},
        )
