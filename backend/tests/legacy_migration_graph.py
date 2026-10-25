"""Preserve historical migration round trips in an actual outgoing-schema database."""

from contextlib import contextmanager

from alembic import command
from sqlalchemy import MetaData, select, text

from app.config import Settings
from app.database import Database
from app.migrations import migration_config
from tests.conftest import isolated_database


@contextmanager
def outgoing_graph(source):
    """Copy only synthetic fixture records; never remove current attribution protection."""
    with isolated_database() as url:
        db = Database(Settings(environment="test", database_url=url))

        def migrate(direction="upgrade", target="20261024_0045"):
            with db.engine.connect() as connection:
                config = migration_config()
                config.attributes["connection"] = connection
                getattr(command, direction)(config, target)

        try:
            migrate()
            metadata = MetaData()
            metadata.reflect(bind=db.engine)
            with source.engine.connect() as original, db.engine.begin() as copied:
                copied.execute(text("SET CONSTRAINTS ALL DEFERRED"))
                for name in (
                    "staff_users",
                    "staff_identities",
                    "trainers",
                    "clients",
                    "client_people",
                    "package_templates",
                    "package_template_revisions",
                    "package_purchases",
                    "purchase_schedule_slots",
                    "session_identities",
                    "training_sessions",
                ):
                    table = metadata.tables[name]
                    fields = [column for column in table.columns if column.name != "created_xid"]
                    rows = original.execute(select(*fields)).mappings().all()
                    if rows:
                        copied.execute(
                            table.insert(),
                            [
                                {**dict(row), **({"version": 1} if "version" in row else {})}
                                for row in rows
                            ],
                        )
            yield db, migrate
        finally:
            db.close()
