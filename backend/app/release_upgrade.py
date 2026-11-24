"""Atomic, explicitly targeted populated upgrades and reviewed runtime grants.

The caller owns target identity, maintenance, backup and source/artifact authorization.
This primitive is not exposed by the application API and does not load AWS credentials.
"""

from time import time as utc_timestamp

from alembic import command
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from psycopg import sql
from sqlalchemy import text

from app.migrations import migration_config
from app.runtime_grants import reconcile

LOCK_KEY = 4603487381042


class UpgradeRefused(RuntimeError):
    """Safe refusal without connection strings, SQL parameters or customer records."""


def upgrade_existing(
    engine,
    *,
    expected_database,
    expected_user,
    from_revision,
    to_revision,
    deadline=None,
    runtime_role=None,
):
    """Upgrade one known nonempty schema in one transaction under an advisory lock.

    Repeating after a lost response returns already_at_target. This establishes only
    the schema revision, not that this invocation committed it or rollout is accepted.
    Any migration or grant error rolls back the chain; inspect before retry.
    When a runtime role is supplied, verify its access even at the target revision.
    """
    if deadline is not None and (
        type(deadline) is not int or not 0 < deadline - utc_timestamp() <= 3600
    ):
        raise UpgradeRefused("Migration requires an unexpired one-hour deadline")
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
            if runtime_role is not None:
                reconcile(
                    connection,
                    expected_migrator=expected_user,
                    target_revision=to_revision,
                    runtime_role=runtime_role,
                )
            return {"outcome": "already_at_target", "schema": to_revision}
        if current != (from_revision,):
            raise UpgradeRefused("Observed schema differs; no bootstrap or guessed resume")
        tables = connection.scalars(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND c.relkind IN ('r','p') ORDER BY c.relname"
            )
        ).all()
        # Fence in-flight transactions after the operator disables new staff invocation.
        with connection.connection.driver_connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE NOWAIT").format(
                    sql.SQL(", ").join(sql.Identifier("public", name) for name in tables)
                )
            )
        config.attributes["connection"] = connection
        if deadline is not None and not 0 < deadline - utc_timestamp() <= 3600:
            raise UpgradeRefused("Migration expired during database preflight")
        command.upgrade(config, to_revision)
        if MigrationContext.configure(connection).get_current_heads() != (to_revision,):
            raise UpgradeRefused("Migration target was not reached")
        if runtime_role is not None:
            reconcile(
                connection,
                expected_migrator=expected_user,
                target_revision=to_revision,
                runtime_role=runtime_role,
                apply=True,
            )
    return {"outcome": "upgraded", "schema": to_revision}
