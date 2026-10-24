"""Undo restores current projections while preserving original immutable evidence."""

import pytest
from sqlalchemy import func, select

from app.models.api import SessionHandoffReceipt, SessionPlanReceipt
from app.models.communications import ChangeRequest, RequestEvent
from app.models.training import ExercisePlanItem, ExerciseResultRevision, TrainingSession
from tests import test_previous_session_plan_api as copy_plan
from tests import test_request_resolution as resolution
from tests import test_session_handoffs_api as handoff
from tests import test_session_outcomes_api as outcome
from tests.test_session_postponement_api import future as future
from tests.test_session_undo_api import latest, undo, undo_review
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


def test_outcome_undo_keeps_measurement_identity_and_every_revision(api, graph, domain_db):
    identity, plan = outcome.setup_plan(api, graph)
    first = outcome.save(
        api, identity, outcome.review(api, identity), [outcome.measurement(plan, 20)]
    )
    assert first.status_code == 200, first.text
    second = outcome.save(
        api,
        identity,
        outcome.review(api, identity),
        [outcome.measurement(plan, 35)],
        comments="Later measurement",
    )
    assert second.status_code == 200, second.text
    mutation = latest(domain_db)
    response = undo(api, mutation, undo_review(api, mutation))
    assert response.status_code == 200, response.text
    restored = outcome.review(api, identity)
    assert restored["rows"][0]["resultId"] == first.json()["rows"][0]["resultId"]
    assert restored["rows"][0]["loadKg"] == 20
    with domain_db.transaction() as session:
        revisions = session.scalars(
            select(ExerciseResultRevision).order_by(ExerciseResultRevision.result_version)
        ).all()
        # Revisions archive outgoing states; the restored 20 remains the current row.
        assert [row.load_kg for row in revisions] == [20, 35]
        assert session.get(TrainingSession, identity).trainer_comments == "Measured today"


def test_copy_undo_restores_source_pointer_without_erasing_copied_plan_history(
    api, graph, domain_db
):
    source, target, original = copy_plan.prepare(api, graph)
    result = copy_plan.confirm(api, target, copy_plan.preview(api, target))
    assert result.status_code == 200, result.text
    mutation = latest(domain_db)
    response = undo(api, mutation, undo_review(api, mutation))
    assert response.status_code == 200, response.text
    assert copy_plan.review(api, source)["items"] == original["items"]
    assert copy_plan.review(api, target)["items"] == []
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, target).copied_from_session_id is None
        assert session.get(ExercisePlanItem, result.json()["items"][0]["id"]).retired_at is not None
        assert session.scalar(select(func.count()).select_from(SessionPlanReceipt)) == 2


def test_handoff_undo_preserves_opening_receipt_and_disclaims_external_recall(
    api, graph, domain_db
):
    identity = graph["session_id"]
    result = handoff.mark(api, identity, handoff.review(api, identity))
    assert result.status_code == 200, result.text
    mutation = latest(domain_db)
    notice = next(
        row
        for row in api.get("/api/messages").json()
        if row.get("undo", {}).get("id") == str(mutation)
    )
    assert "recall" in notice["undo"]["notice"].lower()
    response = undo(api, mutation, undo_review(api, mutation))
    assert response.status_code == 200, response.text
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, identity)
        assert booking.whatsapp_open_count == 0 and booking.whatsapp_opened_at is None
        assert session.scalar(select(func.count()).select_from(SessionHandoffReceipt)) == 1


def test_approved_request_undo_restores_schedule_but_keeps_original_decision(
    api, graph, domain_db, future
):
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        original = (booking.training_date, booking.starts_at, booking.ends_at)
    request = resolution.seed(domain_db, graph, "session_time")
    result = resolution.resolve(api, request)
    assert result.status_code == 200, result.text
    mutation = latest(domain_db)
    response = undo(api, mutation, undo_review(api, mutation))
    assert response.status_code == 200, response.text
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        assert (booking.training_date, booking.starts_at, booking.ends_at) == original
        assert session.get(ChangeRequest, request).status == "approved"
        decisions = session.scalars(
            select(RequestEvent)
            .where(RequestEvent.request_id == request)
            .order_by(RequestEvent.sequence)
        ).all()
        assert [row.status for row in decisions] == ["pending", "approved"]


def test_later_plan_must_be_reversed_before_earlier_summary_can_be_undone(api, graph, domain_db):
    from tests.test_session_undo_api import change_summary, plan_save

    identity, earlier, _ = change_summary(api, graph, domain_db)
    viewed = undo_review(api, earlier)
    plan_save(api, identity, "Later added exercise", [])
    assert undo(api, earlier, viewed).status_code == 409
    later = latest(domain_db)
    assert undo(api, later, undo_review(api, later)).status_code == 200
    assert undo(api, earlier, undo_review(api, earlier)).status_code == 200
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, identity).client_summary == ""
        assert session.scalar(select(func.count()).select_from(ExercisePlanItem)) == 1
