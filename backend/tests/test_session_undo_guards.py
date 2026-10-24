"""Direct PostgreSQL mutation attempts cannot rewrite compensation evidence."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.models.session_mutations import MutationSession, SessionMutation, SessionMutationUndo
from tests.test_session_undo_api import change_summary, undo, undo_review
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


@pytest.mark.parametrize("model", [SessionMutation, MutationSession, SessionMutationUndo])
@pytest.mark.parametrize("action", ["update", "delete"])
def test_original_and_compensation_evidence_is_immutable(api, graph, domain_db, model, action):
    _, mutation, _ = change_summary(api, graph, domain_db)
    assert undo(api, mutation, undo_review(api, mutation)).status_code == 200
    with pytest.raises(DBAPIError, match="immutable"), domain_db.transaction() as session:
        row = session.scalars(select(model)).first()
        if action == "delete":
            session.delete(row)
        elif model is MutationSession:
            row.client_summary = "forged evidence"
        else:
            row.actor_name = "forged actor"


def test_snapshot_cannot_be_appended_after_original_transaction(api, graph, domain_db):
    _, mutation, _ = change_summary(api, graph, domain_db)
    with pytest.raises(DBAPIError, match="original command"), domain_db.transaction() as session:
        row = session.scalars(select(MutationSession)).first()
        values = {
            column.name: getattr(row, column.name) for column in MutationSession.__table__.columns
        }
        session.add(MutationSession(**{**values, "entity_id": uuid4()}))


def test_populated_undo_migration_refuses_downgrade_without_losing_history(
    api, graph, domain_db, migrate
):
    _, mutation, _ = change_summary(api, graph, domain_db)
    assert undo(api, mutation, undo_review(api, mutation)).status_code == 200
    with pytest.raises(DBAPIError, match="downgrade refused"):
        migrate("downgrade", "20261024_0044")
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(SessionMutation)) == 1
        assert session.scalar(select(func.count()).select_from(SessionMutationUndo)) == 1
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "20261024_0045"
