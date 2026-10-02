"""Real PostgreSQL tests get a fresh database; never fall back to a deployment URL."""

import os
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

pytest_plugins = ["tests.domain_fixtures", "tests.auth_fixtures"]


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


@pytest.fixture
def database_url():
    control = test_control_url(os.getenv("FITFINITY_TEST_DATABASE_URL"))
    database_name = "fitfinity_test_" + uuid4().hex
    admin_dsn = control.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(admin_dsn, autocommit=True, connect_timeout=5) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {} ").format(sql.Identifier(database_name)))
    try:
        yield control.set(database=database_name).render_as_string(hide_password=False)
    finally:
        with psycopg.connect(admin_dsn, autocommit=True, connect_timeout=5) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database_name))
            )


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
