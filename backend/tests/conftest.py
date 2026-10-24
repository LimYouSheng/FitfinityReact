"""Real PostgreSQL tests get a fresh database; never fall back to a deployment URL."""

import os
from contextlib import contextmanager
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from app.config import Settings
from app.migrations import migration_config

pytest_plugins = ["tests.domain_fixtures", "tests.auth_fixtures", "tests.media_fixtures"]


def test_control_url(value: str | None):
    if not value:
        raise ValueError("FITFINITY_TEST_DATABASE_URL is required; no database tests are skipped")
    url = make_url(value)
    if url.drivername != "postgresql+psycopg" or url.database != "fitfinity_test":
        raise ValueError("Tests require the dedicated fitfinity_test control database")
    return url


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+psycopg://unit:unit@127.0.0.1:1/unit_test",
        db_connect_timeout_seconds=1,
    )


@contextmanager
def isolated_database(*, template=None):
    """Own one disposable database; a template never contains scenario records."""
    control = test_control_url(os.getenv("FITFINITY_TEST_DATABASE_URL"))
    database_name = "fitfinity_test_" + uuid4().hex
    admin_dsn = control.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(admin_dsn, autocommit=True, connect_timeout=5) as connection:
        statement = sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
        if template is not None:
            if not template.startswith("fitfinity_test_"):
                raise ValueError("Only this test invocation's isolated template is permitted")
            statement += sql.SQL(" TEMPLATE {}").format(sql.Identifier(template))
        connection.execute(statement)
    try:
        yield control.set(database=database_name).render_as_string(hide_password=False)
    finally:
        with psycopg.connect(admin_dsn, autocommit=True, connect_timeout=5) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database_name))
            )


@pytest.fixture(scope="session")
def migrated_template():
    """Apply real Alembic migrations once; clone only the empty schema for domain tests."""
    with isolated_database() as url:
        engine = create_engine(url, poolclass=NullPool)
        try:
            with engine.connect() as connection:
                config = migration_config()
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
        finally:
            engine.dispose()
        yield make_url(url).database


@pytest.fixture
def database_url(request):
    # Direct migration/database tests retain an empty database. Domain scenarios
    # still own separate databases, connections, transactions and teardown.
    template = (
        request.getfixturevalue("migrated_template")
        if "domain_db" in request.fixturenames
        else None
    )
    with isolated_database(template=template) as url:
        yield url


@pytest.fixture
def database_settings(database_url):
    return Settings(environment="test", database_url=database_url, db_pool_timeout_seconds=1)


@pytest.fixture
def migrate(database_settings):
    engine = create_engine(database_settings.database_url.get_secret_value(), poolclass=NullPool)

    def run(direction="upgrade", target="head"):
        with engine.connect() as connection:
            config = migration_config()
            config.attributes["connection"] = connection
            getattr(command, direction)(config, target)

    yield run
    engine.dispose()
