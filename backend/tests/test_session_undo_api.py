"""Real PostgreSQL compensation retains original effects and independently checks restoration."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.api import session_undo_save
from app.auth.errors import AuthError
from app.models.api import SessionSummaryReceipt
from app.models.session_mutations import SessionMutation, SessionMutationUndo
from app.models.training import CreditDebit, ExercisePlanDetail, ExercisePlanItem, TrainingSession
from tests.test_session_media_api import recording as recording
from tests.test_session_summaries_api import review, save
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


def change_summary(api, graph, domain_db):
    identity = graph["session_id"]
    response = save(api, identity, review(api, identity), "A new reviewed summary")
    assert response.status_code == 200, response.text
    with domain_db.transaction() as session:
        mutation = session.scalar(select(SessionMutation))
        assert mutation.operation == "session.summary"
        return identity, mutation.id, response.json()["version"]


def undo_review(api, mutation):
    response = api.get(f"/api/session-changes/{mutation}/undo-review")
    assert response.status_code == 200, response.text
    return response.json()


def undo(api, mutation, viewed, key=None):
    return api.post(
        f"/api/session-changes/{mutation}/undo",
        json={"expected": viewed["expected"]},
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_summary_undo_preserves_history_and_increases_version(api, graph, domain_db):
    identity, mutation, version = change_summary(api, graph, domain_db)
    viewed, key = undo_review(api, mutation), uuid4()
    result = undo(api, mutation, viewed, key)
    assert result.status_code == 200, result.text
    assert result.json()["actionId"] == str(mutation)
    assert undo(api, mutation, viewed, key).json() == result.json()
    assert api.get(f"/api/session-undos/{key}").json() == result.json()
    with domain_db.transaction() as session:
        row = session.get(TrainingSession, identity)
        assert row.client_summary == "" and row.version > version
        assert (
            session.scalar(select(SessionSummaryReceipt)).result["summary"]
            == "A new reviewed summary"
        )
        assert session.scalar(select(func.count()).select_from(SessionMutationUndo)) == 1
        assert session.scalar(select(func.count()).select_from(CreditDebit)) == 0
        assert session.get(TrainingSession, graph["second_session_id"]).version == 1


def test_later_change_and_foreign_identity_cannot_be_reversed(api, graph, domain_db):
    identity, mutation, _ = change_summary(api, graph, domain_db)
    viewed = undo_review(api, mutation)
    assert save(api, identity, review(api, identity), "Later correction").status_code == 200
    assert undo(api, mutation, viewed).status_code == 409
    assert api.get(f"/api/session-changes/{uuid4()}/undo-review").status_code == 404
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, identity).client_summary == "Later correction"
        assert session.scalar(select(func.count()).select_from(SessionMutationUndo)) == 0


def test_interrupted_compensation_rolls_back_undo_receipt_and_domain(
    api, graph, domain_db, monkeypatch
):
    identity, mutation, version = change_summary(api, graph, domain_db)
    viewed, key = undo_review(api, mutation), uuid4()

    def fail(*args):
        raise AuthError("injected_failure", "Interrupted compensation", 503)

    with monkeypatch.context() as patch:
        patch.setattr(session_undo_save, "validate_occupancy", fail)
        assert undo(api, mutation, viewed, key).status_code == 503
    with domain_db.transaction() as session:
        row = session.get(TrainingSession, identity)
        assert row.client_summary == "A new reviewed summary" and row.version == version
        assert session.scalar(select(func.count()).select_from(SessionMutationUndo)) == 0
    assert undo(api, mutation, viewed, key).status_code == 200


def latest(domain_db):
    with domain_db.transaction() as session:
        return session.scalar(
            select(SessionMutation.id)
            .order_by(SessionMutation.created_at.desc(), SessionMutation.id)
            .limit(1)
        )


def plan_save(api, identity, name, details):
    viewed = api.get(f"/api/sessions/{identity}/plan-review").json()
    response = api.post(
        f"/api/sessions/{identity}/plan",
        json={
            "expected": viewed["expected"],
            "items": [
                {
                    "id": "draft-test",
                    "name": name,
                    "weight": "5 kg",
                    "reps": "8",
                    "rounds": "3",
                    "rest": "60s",
                    "customDetails": details,
                }
            ],
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_plan_undo_restores_retired_identity_and_retains_new_plan_history(api, graph, domain_db):
    identity = graph["session_id"]
    first = plan_save(api, identity, "Original squat", [{"id": "tempo", "value": "Slow descent"}])
    second = plan_save(api, identity, "Replacement press", [])
    mutation = latest(domain_db)
    result = undo(api, mutation, undo_review(api, mutation))
    assert result.status_code == 200, result.text
    restored = api.get(f"/api/sessions/{identity}/details").json()["exercisePlan"]
    assert [r["id"] for r in restored] == [first["items"][0]["id"]]
    assert restored[0]["name"] == "Original squat"
    assert restored[0]["customDetails"] == [{"id": "tempo", "value": "Slow descent"}]
    with domain_db.transaction() as session:
        assert session.get(ExercisePlanItem, second["items"][0]["id"]).retired_at is not None
        assert session.scalar(select(func.count()).select_from(SessionMutation)) == 2


def test_plan_detail_deletion_undo_restores_original_id_with_higher_version(api, graph, domain_db):
    identity = graph["session_id"]
    first = plan_save(api, identity, "Squat", [{"id": "tempo", "value": "Slow descent"}])
    with domain_db.transaction() as session:
        detail = session.scalar(select(ExercisePlanDetail))
        detail_id, version = detail.id, detail.version
    viewed = api.get(f"/api/sessions/{identity}/plan-review").json()
    item = {k: first["items"][0][k] for k in ["id", "name", "weight", "reps", "rounds", "rest"]}
    response = api.post(
        f"/api/sessions/{identity}/plan",
        json={"expected": viewed["expected"], "items": [{**item, "customDetails": []}]},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    mutation = latest(domain_db)
    result = undo(api, mutation, undo_review(api, mutation))
    assert result.status_code == 200, result.text
    with domain_db.transaction() as session:
        detail = session.get(ExercisePlanDetail, detail_id)
        assert detail.value == "Slow descent" and detail.version > version


def test_recording_removal_undo_checks_and_restores_actual_original_bytes(
    api, graph, domain_db, recording
):
    from tests.test_session_media_api import commit, path, publish, reserve

    _, item, _ = recording
    _, saved = publish(api, graph, item)
    key, _, response = reserve(api, graph, item, remove=True)
    assert response.status_code == 200
    assert commit(api, key).status_code == 200
    assert api.get(path(graph, item)).json() is None
    mutation = latest(domain_db)
    result = undo(api, mutation, undo_review(api, mutation))
    assert result.status_code == 200, result.text
    restored = api.get(path(graph, item) + "/review").json()["media"]
    assert restored["id"] == saved["media"]["id"]
    assert restored["expiresAt"] == saved["media"]["expiresAt"]
    assert api.get(path(graph, item)).status_code == 200
