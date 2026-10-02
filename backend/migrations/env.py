"""Explicit online migrations. A supplied test connection never consults deployment credentials."""

from alembic import context
from sqlalchemy import create_engine, pool

from app import models  # noqa: F401 — register every canonical domain table
from app.config import load_settings
from app.database import Base


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Use a reviewed online migration against the explicitly configured database")
elif context.config.attributes.get("connection") is not None:
    migrate(context.config.attributes["connection"])
else:
    settings = load_settings(purpose="migration")
    engine = create_engine(
        settings.database_url.get_secret_value(),
        poolclass=pool.NullPool,
        hide_parameters=True,
        connect_args={"connect_timeout": settings.db_connect_timeout_seconds},
    )
    try:
        with engine.connect() as connection:
            migrate(connection)
    finally:
        engine.dispose()
