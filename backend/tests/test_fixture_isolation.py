"""Schema reuse must never reuse scenario data or bypass fresh migration coverage."""

import psycopg
from sqlalchemy.engine import make_url

from tests.conftest import isolated_database


def connect(url):
    return psycopg.connect(
        make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
    )


def test_domain_template_clones_have_real_schema_and_isolated_writes(migrated_template):
    with isolated_database(template=migrated_template) as first:
        with connect(first) as connection:
            assert (
                connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
                == "20261025_0046"
            )
            assert connection.execute("SELECT count(*) FROM staff_users").fetchone()[0] == 0
            connection.execute("CREATE TABLE scenario_isolation_probe (value integer)")
            connection.execute("INSERT INTO scenario_isolation_probe VALUES (42)")
        with isolated_database(template=migrated_template) as second:
            assert first != second
            with connect(second) as connection:
                assert (
                    connection.execute("SELECT to_regclass('scenario_isolation_probe')").fetchone()[
                        0
                    ]
                    is None
                )
                assert connection.execute("SELECT count(*) FROM staff_users").fetchone()[0] == 0
                assert (
                    connection.execute(
                        "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal"
                    ).fetchone()[0]
                    == 242
                )
        with connect(first) as connection:
            assert (
                connection.execute("SELECT value FROM scenario_isolation_probe").fetchone()[0] == 42
            )


def test_direct_migration_fixture_still_starts_without_schema(database_url, migrate):
    with connect(database_url) as connection:
        assert connection.execute("SELECT to_regclass('alembic_version')").fetchone()[0] is None
    migrate()
    with connect(database_url) as connection:
        assert (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == "20261025_0046"
        )
