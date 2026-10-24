"""Confirmed copies use real PostgreSQL versions, identities and original receipts."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.api import session_plans
from app.models.api import SessionPlanReceipt
from app.models.training import ExercisePlanItem, TrainingSession
from tests.test_directory_api import covered_session
from tests.test_session_plans_api import item, review, save
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def preview(api, identity):
    response = api.get(f"/api/sessions/{identity}/previous-plan")
    assert response.status_code == 200, response.text
    return response.json()


def confirm(api, identity, viewed, key=None):
    return api.post(
        f"/api/sessions/{identity}/copy-plan",
        json={
            "expected": viewed["target"]["expected"],
            "sourceId": viewed["source"]["sessionId"],
            "sourceExpected": viewed["source"]["expected"],
        },
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def prepare(api, graph):
    source, target = graph["session_id"], graph["second_session_id"]
    result = save(api, source, {"expected": review(api, source)["expected"], "items": [item()]})
    assert result.status_code == 200, result.text
    return source, target, result.json()


def test_preview_confirm_persists_new_ids_preserves_source_and_private_receipt(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    source, target, original = prepare(api, graph)
    assert preview(api, source)["source"] is None
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    viewed = preview(api, target)
    assert viewed["source"]["sessionId"] == str(source)
    assert viewed["source"]["items"] == original["items"]
    assert review(api, target)["items"] == []
    key = uuid4()
    result = confirm(api, target, viewed, key)
    assert result.status_code == 200, result.text
    copied = result.json()
    assert copied["copiedFromSessionId"] == str(source)
    assert copied["items"][0]["id"] != original["items"][0]["id"]
    assert copied["items"][0]["customDetails"] == original["items"][0]["customDetails"]
    assert copied["items"][0]["videoAttached"] is False
    assert review(api, source)["items"] == original["items"]
    assert review(api, target)["items"] == copied["items"]
    assert confirm(api, target, viewed, key).json() == copied
    assert api.get(f"/api/session-plans/{key}").json() == copied
    assert (
        save(
            api, target, {"expected": viewed["target"]["expected"], "items": [item()]}, key
        ).status_code
        == 409
    )
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, target).copied_from_session_id == source
        receipt = session.scalar(
            select(SessionPlanReceipt).where(SessionPlanReceipt.request_key == key)
        )
        assert receipt.previous["source"]["sessionId"] == str(source)
        assert session.scalar(select(func.count()).select_from(ExercisePlanItem)) == 2


@pytest.mark.parametrize("change", ["source", "target"])
def test_changed_review_rejects_copy_without_partial_write(api, domain_db, graph, change):
    source, target, _ = prepare(api, graph)
    viewed = preview(api, target)
    changed = source if change == "source" else target
    saved = save(
        api,
        changed,
        {"expected": review(api, changed)["expected"], "items": [item(name="Changed")]},
    )
    assert saved.status_code == 200, saved.text
    before = review(api, target)
    assert confirm(api, target, viewed).status_code == 409
    assert review(api, target) == before
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, target).copied_from_session_id is None
        assert session.scalar(select(func.count()).select_from(SessionPlanReceipt)) == 2


def test_foreign_client_plan_never_selected_or_exposed(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    client, foreign, _ = covered_session(domain_db, graph)
    result = save(
        api,
        foreign,
        {"expected": review(api, foreign)["expected"], "items": [item(name="Private")]},
    )
    assert result.status_code == 200
    assert preview(api, graph["second_session_id"])["source"] is None
    with domain_db.transaction() as session:
        row = session.get(TrainingSession, foreign)
        row.trainer_id = session.get(TrainingSession, graph["session_id"]).trainer_id
        # covered_session grants access only to this single session, not its client history.
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    with domain_db.transaction() as session:
        other = session.scalar(
            select(TrainingSession.id).where(
                TrainingSession.client_id == client, TrainingSession.id != foreign
            )
        )
    assert api.get(f"/api/sessions/{other}/previous-plan").status_code == 404


def test_copy_failure_rolls_back_replacement_and_receipt(api, domain_db, graph, monkeypatch):
    source, target, _ = prepare(api, graph)
    viewed = preview(api, target)
    original = session_plans.apply_plan

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("simulated disconnect before commit")

    monkeypatch.setattr(session_plans, "apply_plan", fail)
    assert confirm(api, target, viewed).status_code == 500
    assert review(api, target)["items"] == []
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, target).copied_from_session_id is None
        assert session.scalar(select(func.count()).select_from(SessionPlanReceipt)) == 1


@pytest.mark.parametrize("excluded", ["same_day", "open_source", "open_target"])
def test_previous_selection_excludes_same_day_and_open_sessions(api, domain_db, graph, excluded):
    source, target, _ = prepare(api, graph)
    with domain_db.transaction() as session:
        row = session.get(TrainingSession, source if excluded == "open_source" else target)
        if excluded == "same_day":
            from datetime import time

            row.training_date = session.get(TrainingSession, source).training_date
            row.starts_at, row.ends_at = time(12), time(13)
        else:
            row.schedule_state = "open"
            row.training_date = row.starts_at = row.ends_at = row.session_number = (
                row.schedule_slot_id
            ) = None
    assert preview(api, target)["source"] is None


def test_completed_source_is_readable_but_completed_target_cannot_be_replaced(
    api, domain_db, graph
):
    from app.persistence import acknowledge

    source, target, original = prepare(api, graph)
    with domain_db.transaction() as session:
        row = session.get(TrainingSession, source)
        acknowledge(session, source, row.version, graph["owner_id"], method="late_no_show")
    viewed = preview(api, target)
    assert viewed["source"]["items"] == original["items"]
    with domain_db.transaction() as session:
        row = session.get(TrainingSession, target)
        acknowledge(session, target, row.version, graph["owner_id"], method="late_no_show")
    assert preview(api, target)["source"]["sessionId"] == str(source)
    assert confirm(api, target, viewed).status_code == 409


def test_new_latest_plan_invalidates_original_selection(api, domain_db, graph):
    from app.models.people import Client
    from app.persistence import add_purchase
    from tests.domain_fixtures import purchase_parts

    source, newer, _ = prepare(api, graph)
    with domain_db.transaction() as session:
        purchase, slots, preferences, bookings = purchase_parts(graph)
        client = session.get(Client, graph["client_id"])
        add_purchase(
            session, purchase, slots, preferences, bookings, expected_client_version=client.version
        )
        target = bookings[0].id
    viewed = preview(api, target)
    assert viewed["source"]["sessionId"] == str(source)
    saved = save(
        api, newer, {"expected": review(api, newer)["expected"], "items": [item(name="Latest")]}
    )
    assert saved.status_code == 200, saved.text
    assert confirm(api, target, viewed).status_code == 409
    assert preview(api, target)["source"]["sessionId"] == str(newer)
    assert review(api, target)["items"] == []


def test_duplicate_copy_on_independent_connections_has_one_effect(
    api, domain_db, database_settings, graph
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import text

    from app.authorization import Principal
    from app.database import Database
    from app.models.people import StaffUser

    source, target, _ = prepare(api, graph)
    viewed, key = preview(api, target), uuid4()
    body = session_plans.CopyPlan(
        expected=viewed["target"]["expected"],
        sourceId=source,
        sourceExpected=viewed["source"]["expected"],
    )
    with domain_db.transaction() as session:
        user = session.get(StaffUser, graph["owner_id"])
        principal = Principal(user.id, user.name, user.role, None)
    replicas, ready = [Database(database_settings), Database(database_settings)], Barrier(2)

    def apply(db):
        with db.transaction() as session:
            pid = session.scalar(text("SELECT pg_backend_pid()"))
            ready.wait(timeout=5)
            return pid, session_plans.copy_previous(
                session, principal, target, key, body
            ).model_dump(mode="json")

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(apply, replicas))
    finally:
        for db in replicas:
            db.close()
    assert results[0][0] != results[1][0]
    assert results[0][1] == results[1][1]
    assert confirm(api, target, viewed).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(SessionPlanReceipt)) == 2
        assert session.scalar(select(func.count()).select_from(ExercisePlanItem)) == 2


def test_copy_retires_target_evidence_without_moving_either_sessions_media(api, domain_db, graph):
    from datetime import UTC, datetime, timedelta
    from uuid import UUID

    from app.models.media import MediaAsset
    from app.models.training import ExerciseResult

    source, target, source_plan = prepare(api, graph)
    saved = save(
        api,
        target,
        {"expected": review(api, target)["expected"], "items": [item(name="Old target")]},
    )
    assert saved.status_code == 200
    target_id = UUID(saved.json()["items"][0]["id"])
    source_id = UUID(source_plan["items"][0]["id"])
    with domain_db.transaction() as session:
        for identity, plan_id in [(source, source_id), (target, target_id)]:
            session.add(
                MediaAsset(
                    purpose="session_video",
                    status="ready",
                    bucket="private-fixture",
                    object_key=str(identity),
                    original_filename="clip.mp4",
                    content_type="video/mp4",
                    size_bytes=1024,
                    content_sha256="a" * 64,
                    uploaded_by=graph["user_id"],
                    client_id=graph["client_id"],
                    purchase_id=graph["purchase_id"],
                    session_id=identity,
                    original_session_id=identity,
                    original_plan_item_id=plan_id,
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                )
            )
        session.add(
            ExerciseResult(
                session_id=target,
                plan_item_id=target_id,
                name="Old target",
                load_kg=12,
                reps=8,
                sets=3,
            )
        )
    viewed = preview(api, target)
    assert viewed["source"]["items"][0]["videoAttached"] is True
    response = confirm(api, target, viewed)
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["videoAttached"] is False
    detail = api.get(f"/api/sessions/{target}/details").json()
    assert detail["retiredPlanItemIds"] == [str(target_id)]
    assert detail["exerciseResults"][0]["planItemId"] == str(target_id)
    with domain_db.transaction() as session:
        assert session.get(ExercisePlanItem, target_id).retired_at is not None
        assert session.get(ExercisePlanItem, source_id).retired_at is None
        assets = list(session.scalars(select(MediaAsset)))
        assert {(a.session_id, a.original_plan_item_id, a.object_key) for a in assets} == {
            (source, source_id, str(source)),
            (target, target_id, str(target)),
        }


def test_changed_assignment_denies_new_copy_but_keeps_original_actor_receipt(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    _, _, other_trainer = covered_session(domain_db, graph)
    source, target, _ = prepare(api, graph)
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    viewed, key = preview(api, target), uuid4()
    saved = confirm(api, target, viewed, key)
    assert saved.status_code == 200, saved.text
    with domain_db.transaction() as session:
        session.get(TrainingSession, target).trainer_id = other_trainer
    assert confirm(api, target, viewed).status_code == 404
    assert api.get(f"/api/sessions/{target}/previous-plan").status_code == 404
    assert confirm(api, target, viewed, key).json() == saved.json()
    assert api.get(f"/api/session-plans/{key}").json() == saved.json()
