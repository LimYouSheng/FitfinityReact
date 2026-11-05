"""Atomic, explicitly targeted populated upgrades; no bootstrap, grants or downgrade.

The caller owns target identity, maintenance, backup and source/artifact authorization.
This primitive is not exposed by the application API and does not load AWS credentials.
"""

from alembic import command
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.migrations import migration_config

LOCK_KEY = 4603487381042


class UpgradeRefused(RuntimeError):
    """Safe refusal without connection strings, SQL parameters or customer records."""


def upgrade_existing(engine, *, expected_database, expected_user, from_revision, to_revision):
    """Upgrade one known nonempty schema in one transaction under an advisory lock.

    Repeating after a lost response returns already_at_target. This establishes only
    the schema revision, not that this invocation committed it or rollout is accepted.
    Any migration error rolls back the entire chain; caller must inspect before retry.
    """
    config = migration_config()
    scripts = ScriptDirectory.from_config(config)
    revisions = [row.revision for row in reversed(list(scripts.walk_revisions()))]
    if (
        scripts.get_heads() != [to_revision]
        or from_revision not in revisions
        or to_revision not in revisions
        or revisions.index(from_revision) >= revisions.index(to_revision)
        or not expected_database
        or not expected_user
    ):
        raise UpgradeRefused("Review an exact forward migration range and database identity")
    if engine.dialect.name != "postgresql":
        raise UpgradeRefused("Only PostgreSQL is supported")
    with engine.begin() as connection:
        identity = connection.execute(text("SELECT current_database(), current_user")).one()
        if tuple(identity) != (expected_database, expected_user):
            raise UpgradeRefused("Database or migration identity differs")
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(text("SET LOCAL statement_timeout = '60s'"))
        if not connection.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": LOCK_KEY}):
            raise UpgradeRefused("Another migration is in progress")
        current = MigrationContext.configure(connection).get_current_heads()
        if current == (to_revision,):
            return {"outcome": "already_at_target", "schema": to_revision}
        if current != (from_revision,):
            raise UpgradeRefused("Observed schema differs; no bootstrap or guessed resume")
        config.attributes["connection"] = connection
        command.upgrade(config, to_revision)
        if MigrationContext.configure(connection).get_current_heads() != (to_revision,):
            raise UpgradeRefused("Migration target was not reached")
    return {"outcome": "upgraded", "schema": to_revision}
