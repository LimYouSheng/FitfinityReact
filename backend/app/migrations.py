"""Shared Alembic configuration for operators, readiness and isolated DB tests."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def migration_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return config


def expected_revisions() -> set[str]:
    return set(ScriptDirectory.from_config(migration_config()).get_heads())
