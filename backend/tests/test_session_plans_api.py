"""Exercise-plan acceptance runs real routes, transactions and isolated PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.api import session_plans as command
from app.auth.errors import AuthError
from app.authorization import Principal
from app.database import Database
from app.models.api import SessionPlanReceipt
from app.models.communications import SessionEvent
from app.models.people import StaffUser
from app.models.training import (
    ExercisePlanDetail,
    ExercisePlanItem,
    ExerciseResult,
    PackagePurchase,
    TrainingSession,
)
from app.persistence import acknowledge
from tests.test_client_reactivation_review import deactivate
from tests.test_directory_api import covered_session
from tests.test_package_reactivation_review import freeze
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def review(api, identity):
    result = api.get(f"/api/sessions/{identity}/plan-review")
    assert result.status_code == 200, result.text
    return result.json()


def item(identity="draft-one", name="Squat"):
    return dict(
        id=identity,
        name=name,
        weight="12 kg",
        reps="8",
        rounds="3",
        rest="60s",
        customDetails=[
            dict(id="detail-a", value="Keep heels down"),
            dict(id="detail-b", value="Slow descent"),
        ],
    )


def save(api, identity, body, key=None):
    return api.post(
        f"/api/sessions/{identity}/plan",
        json=body,
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_create_edit_reorder_retire_preserves_results_and_receipt(api, domain_db, graph):
    identity = graph["session_id"]
    first = save(
        api,
        identity,
        dict(
            expected=review(api, identity)["expected"], items=[item(), item("draft-two", "Lunge")]
        ),
    )
    assert first.status_code == 200, first.text
    a, b = first.json()["items"]
    with domain_db.transaction() as session:
        session.add(
            ExerciseResult(
                session_id=identity,
                plan_item_id=UUID(a["id"]),
                name="Squat",
                load_kg=12,
                reps=8,
                sets=3,
            )
        )
    viewed = review(api, identity)
    next_item = item(b["id"], "Updated lunge")
    next_item["customDetails"].reverse()
    next_item["customDetails"][1] = dict(id="detail-new", value="New ordered instruction")
    key = uuid4()
    body = dict(expected=viewed["expected"], items=[next_item, item("draft-three", "Press")])
    second = save(api, identity, body, key)
    assert second.status_code == 200, second.text
    assert second.json()["items"][0]["id"] == b["id"]
    assert second.json()["items"][0]["customDetails"] == next_item["customDetails"]
    assert save(api, identity, body, key).json() == second.json()
    assert api.get(f"/api/session-plans/{key}").json() == second.json()
    assert save(api, identity, {**body, "items": [item()]}, key).status_code == 409
    detail = api.get(f"/api/sessions/{identity}/details").json()
    assert detail["exercisePlan"] == second.json()["items"]
    assert detail["retiredPlanItemIds"] == [a["id"]]
    assert detail["exerciseResults"][0]["planItemId"] == a["id"]
    assert detail["session"]["status"] == "planned" and detail["purchase"]["used"] == 0
    with domain_db.transaction() as session:
        retired = session.get(ExercisePlanItem, UUID(a["id"]))
        assert retired.retired_at and retired.position is None
        assert session.scalar(select(func.count()).select_from(SessionEvent)) == 2
        assert session.scalar(select(func.count()).select_from(SessionPlanReceipt)) == 2
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.get(ExercisePlanItem, UUID(a["id"])).name = "Tampered"
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        detail = session.scalar(
            select(ExercisePlanDetail).where(ExercisePlanDetail.plan_item_id == UUID(a["id"]))
        )
        detail.value = "Tampered"
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.get(ExercisePlanItem, UUID(b["id"])))
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.scalar(select(SessionPlanReceipt)).result = {}


def test_legacy_notes_can_be_kept_or_deliberately_removed_without_resurrection(
    api, domain_db, graph
):
    identity = graph["session_id"]
    with domain_db.transaction() as session:
        plan = ExercisePlanItem(
            session_id=identity, name="Legacy", position=1, notes="Original note"
        )
        session.add(plan)
    viewed = review(api, identity)
    old = viewed["items"][0]
    assert old["customDetails"] == [dict(id=f"{old['id']}/notes", value="Original note")]
    updated = item(old["id"], "Legacy")
    updated["customDetails"] = []
    response = save(api, identity, dict(expected=viewed["expected"], items=[updated]))
    assert response.status_code == 200, response.text
    assert review(api, identity)["items"][0]["customDetails"] == []
    with domain_db.transaction() as session:
        receipt = session.scalar(select(SessionPlanReceipt))
        assert receipt.previous["items"][0]["notes"] == "Original note"


@pytest.mark.parametrize("change", ["version", "client", "purchase", "completed", "cancelled"])
def test_changed_or_final_records_reject_without_partial_effects(api, domain_db, graph, change):
    identity = graph["session_id"]
    viewed = review(api, identity)
    if change == "client":
        deactivate(api, graph)
    with domain_db.transaction() as session:
        if change == "client":
            pass
        elif change == "purchase":
            freeze(session, graph, session.get(PackagePurchase, graph["purchase_id"]))
        else:
            booking = session.get(TrainingSession, identity)
            if change == "version":
                booking.version += 1
            elif change == "completed":
                acknowledge(
                    session, identity, booking.version, graph["owner_id"], method="late_no_show"
                )
            else:
                booking.status = change
    assert save(api, identity, dict(expected=viewed["expected"], items=[item()])).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(ExercisePlanItem)) is None
        assert session.scalar(select(SessionPlanReceipt)) is None
        assert session.scalar(select(SessionEvent)) is None


def test_assigned_trainer_writes_open_plan_but_foreign_and_historical_scope_cannot(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    _, _, other_trainer = covered_session(domain_db, graph)
    identity = graph["session_id"]
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, identity)
        booking.schedule_state = "open"
        booking.training_date = booking.starts_at = booking.ends_at = booking.session_number = (
            booking.schedule_slot_id
        ) = None
        session.get(TrainingSession, graph["second_session_id"]).trainer_id = other_trainer
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    viewed, key = review(api, identity), uuid4()
    saved = save(api, identity, dict(expected=viewed["expected"], items=[item()]), key)
    assert saved.status_code == 200, saved.text
    for forbidden in [graph["second_session_id"], uuid4()]:
        assert api.get(f"/api/sessions/{forbidden}/plan-review").status_code == 404
        assert (
            save(api, forbidden, dict(expected=viewed["expected"], items=[item()])).status_code
            == 404
        )
    with domain_db.transaction() as session:
        session.get(TrainingSession, identity).trainer_id = other_trainer
    assert api.get(f"/api/sessions/{identity}/plan-review").status_code == 404
    assert api.get(f"/api/session-plans/{key}").json() == saved.json()
    assert api.get(f"/api/session-plans/{uuid4()}").status_code == 404


@pytest.mark.parametrize("bad", ["foreign", "duplicate", "empty", "actor", "media"])
def test_foreign_items_and_untrusted_payloads_never_write(api, domain_db, graph, bad):
    identity = graph["session_id"]
    body = dict(expected=review(api, identity)["expected"], items=[item()])
    expected = 422
    if bad == "foreign":
        with domain_db.transaction() as session:
            row = ExercisePlanItem(
                session_id=graph["second_session_id"], name="Foreign", position=1
            )
            session.add(row)
            session.flush()
            body["items"][0]["id"] = str(row.id)
        expected = 404
    elif bad == "duplicate":
        body["items"].append(item())
    elif bad == "empty":
        body["items"] = []
    elif bad == "actor":
        body["actorId"] = str(graph["owner_id"])
    else:
        body["items"][0]["videoAttached"] = True
    assert save(api, identity, body).status_code == expected
    with domain_db.transaction() as session:
        assert session.scalar(select(SessionPlanReceipt)) is None
        assert (
            session.scalar(select(ExercisePlanItem).where(ExercisePlanItem.session_id == identity))
            is None
        )


def test_failed_receipt_rolls_back_plan_and_event(api, domain_db, graph, monkeypatch):
    identity = graph["session_id"]
    body = dict(expected=review(api, identity)["expected"], items=[item()])

    def fail(**kwargs):
        raise AuthError("injected_failure", "Interrupted before commit", 503)

    monkeypatch.setattr(command, "SessionPlanReceipt", fail)
    # Receipt lookup needs the mapped class; inject after lookup instead.
    monkeypatch.setattr(command, "receipt", lambda *args: None)
    assert save(api, identity, body).status_code == 503
    with domain_db.transaction() as session:
        assert session.scalar(select(ExercisePlanItem)) is None
        assert session.scalar(select(SessionEvent)) is None
        assert session.get(TrainingSession, identity).status == "scheduled"


def test_independent_connections_duplicate_one_effect_and_stale_competitor_conflicts(
    api, domain_db, database_settings, graph
):
    identity, key = graph["session_id"], uuid4()
    body = command.SavePlan(expected=review(api, identity)["expected"], items=[item()])
    with domain_db.transaction() as session:
        user = session.get(StaffUser, graph["owner_id"])
        principal = Principal(user.id, user.name, user.role, None)
    replicas, ready = [Database(database_settings), Database(database_settings)], Barrier(2)

    def apply(db):
        with db.transaction() as session:
            pid = session.scalar(text("SELECT pg_backend_pid()"))
            ready.wait(timeout=5)
            return pid, command.save(session, principal, identity, key, body).model_dump(
                mode="json"
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(apply, replicas))
    finally:
        for db in replicas:
            db.close()
    assert results[0][0] != results[1][0] and results[0][1] == results[1][1]
    assert api.get(f"/api/session-plans/{key}").json() == results[0][1]
    assert save(api, identity, body.model_dump(mode="json")).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(SessionPlanReceipt)) == 1
        assert session.scalar(select(func.count()).select_from(SessionEvent)) == 1


def test_review_is_bound_to_the_exact_session_even_when_empty_versions_match(api, graph):
    viewed = review(api, graph["session_id"])
    response = save(
        api, graph["second_session_id"], dict(expected=viewed["expected"], items=[item()])
    )
    assert response.status_code == 409


def test_removing_video_item_preserves_original_media_identity_and_downgrade_refuses(
    api, domain_db, graph
):
    import runpy
    from datetime import UTC, datetime, timedelta

    from app.models.media import MediaAsset

    identity = graph["session_id"]
    with domain_db.transaction() as session:
        old = ExercisePlanItem(session_id=identity, position=1, name="Recorded Squat")
        session.add(old)
        session.flush()
        media = MediaAsset(
            purpose="session_video",
            status="ready",
            bucket="private-fixture",
            object_key="private-object",
            original_filename="clip.mp4",
            content_type="video/mp4",
            size_bytes=1024,
            content_sha256="a" * 64,
            uploaded_by=graph["user_id"],
            client_id=graph["client_id"],
            purchase_id=graph["purchase_id"],
            session_id=identity,
            original_session_id=identity,
            original_plan_item_id=old.id,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        session.add(media)
        session.flush()
        media_id, old_id = media.id, old.id
    viewed = review(api, identity)
    assert viewed["items"][0]["videoAttached"] is True
    response = save(api, identity, dict(expected=viewed["expected"], items=[item()]))
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["videoAttached"] is False
    assert api.get(f"/api/sessions/{identity}/details").json()["retiredPlanItemIds"] == []
    with domain_db.transaction() as session:
        media = session.get(MediaAsset, media_id)
        assert media.original_plan_item_id == old_id and media.session_id == identity
        assert media.object_key == "private-object" and media.status == "ready"
    sql = runpy.run_path("migrations/versions/20261023_0036_session_plans.py")["DOWNGRADE_SQL"]
    with pytest.raises(DBAPIError, match="downgrade refused"), domain_db.transaction() as session:
        session.execute(text(sql))
