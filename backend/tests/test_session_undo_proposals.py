"""Undo of supervised proposals cancels only pending requests, retaining their events."""

import pytest
from sqlalchemy import select

from app.models.communications import ChangeRequest, RequestEvent
from app.models.people import Trainer
from app.models.training import TrainingSession
from tests import test_client_weekly_schedule as weekly
from tests import test_session_changes_api as changes
from tests import test_session_postponement_api as postpone
from tests.test_session_changes_api import candidate as candidate
from tests.test_session_changes_api import replacement as replacement
from tests.test_session_postponement_api import future as future
from tests.test_session_undo_api import latest, undo, undo_review
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


@pytest.mark.parametrize("kind", ["time", "trainer", "postpone", "weekly"])
def test_proposal_undo_appends_cancellation_without_touching_session(
    api, graph, domain_db, future, replacement, auth_settings, auth_service, fake_cognito, kind
):
    with domain_db.transaction() as session:
        trainer = session.get(Trainer, graph["trainer_id"])
        trainer.approve_session_time = trainer.approve_session_trainer = (
            trainer.approve_weekly_schedule
        ) = True
        before = {
            row.id: (row.training_date, row.starts_at, row.ends_at, row.trainer_id, row.version)
            for row in session.scalars(select(TrainingSession))
        }
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    if kind in {"time", "trainer"}:
        response = changes.save(
            api, graph, kind, changes.body_for(changes.review(api, graph, kind), replacement)
        )
    elif kind == "postpone":
        response = postpone.save(api, graph, postpone.review(api, graph))
    else:
        response = weekly.save(api, graph, weekly.payload(api, graph))
    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "requested"
    mutation = latest(domain_db)
    restored = undo(api, mutation, undo_review(api, mutation))
    assert restored.status_code == 200, restored.text
    with domain_db.transaction() as session:
        request = session.scalar(select(ChangeRequest))
        assert request.status == "cancelled" and request.resolved_by == graph["user_id"]
        events = session.scalars(
            select(RequestEvent)
            .where(RequestEvent.request_id == request.id)
            .order_by(RequestEvent.sequence)
        ).all()
        assert [event.status for event in events] == ["pending", "cancelled"]
        assert {
            row.id: (row.training_date, row.starts_at, row.ends_at, row.trainer_id, row.version)
            for row in session.scalars(select(TrainingSession))
        } == before
