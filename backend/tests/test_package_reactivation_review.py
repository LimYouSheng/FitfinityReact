"""Single-purchase restoration reviews never expand into other purchases or mutate records."""

from datetime import timedelta
from uuid import uuid4

import pytest

from app.models.people import Client, LifecycleEvent, Trainer
from app.models.training import PackagePurchase, TrainingSession
from app.persistence import acknowledge, add_purchase
from tests.domain_fixtures import purchase_parts
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_client_reactivation_review import deactivate, snapshot
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def freeze(session, graph, purchase):
    event = LifecycleEvent(
        purchase_id=purchase.id,
        status="inactive",
        reason="owner",
        actor_id=graph["owner_id"],
        actor_name="Owner",
    )
    session.add(event)
    session.flush()
    purchase.status, purchase.lifecycle_event_id = "inactive", event.id
    session.flush()


@pytest.fixture
def frozen(domain_db, graph):
    with domain_db.transaction() as session:
        freeze(session, graph, session.get(PackagePurchase, graph["purchase_id"]))


def path(graph, purchase_id=None):
    purchase = purchase_id or graph["purchase_id"]
    return f"/api/clients/{graph['client_id']}/packages/{purchase}/reactivation-review"


def read(api, graph, purchase_id=None):
    response = api.get(path(graph, purchase_id))
    assert response.status_code == 200, response.text
    return response.json()


def preview(api, graph, expected, dates=None, purchase_id=None):
    return api.post(
        path(graph, purchase_id),
        json={"expected": expected, "dates": dates or {}},
        headers={"Idempotency-Key": str(uuid4())},
    )


def next_purchase(session, graph):
    purchase, slots, preferences, bookings = purchase_parts(graph)
    client = session.get(Client, graph["client_id"])
    add_purchase(
        session, purchase, slots, preferences, bookings, expected_client_version=client.version
    )
    return purchase, bookings


def test_review_and_free_date_preview_preserve_every_record(api, domain_db, graph, frozen):
    before = snapshot(domain_db)
    result = read(api, graph)
    assert result["packageId"] == str(graph["purchase_id"])
    assert result["purchaseIds"] == [str(graph["purchase_id"])]
    assert {r["id"] for r in result["rows"]} == {
        str(graph["session_id"]),
        str(graph["second_session_id"]),
    }
    assert result["packageError"] is None and all(r["error"] is None for r in result["rows"])
    day = str(graph["end_date"] + timedelta(days=200))
    changed = preview(api, graph, result["expected"], {str(graph["session_id"]): day})
    assert changed.status_code == 200, changed.text
    row = next(r for r in changed.json()["rows"] if r["id"] == str(graph["session_id"]))
    assert row["date"] == day and row["originalDate"] == str(graph["start_date"])
    assert row["startsAt"] == "10:00" and row["endsAt"] == "11:00"
    assert snapshot(domain_db) == before


def test_other_active_purchase_is_occupancy_not_an_editable_row(api, domain_db, graph, frozen):
    with domain_db.transaction() as session:
        purchase, bookings = next_purchase(session, graph)
        other_id, other_session, day = purchase.id, bookings[0].id, bookings[0].training_date
    result = read(api, graph)
    assert all(r["purchaseId"] == str(graph["purchase_id"]) for r in result["rows"])
    blocked = preview(api, graph, result["expected"], {str(graph["session_id"]): str(day)})
    assert blocked.status_code == 200, blocked.text
    assert (
        "Conflicts"
        in next(r for r in blocked.json()["rows"] if r["id"] == str(graph["session_id"]))["error"]
    )
    assert (
        preview(api, graph, result["expected"], {str(other_session): str(day)}).status_code == 422
    )
    assert api.get(path(graph, other_id)).status_code == 409


def test_same_review_cannot_be_reused_for_another_inactive_purchase(api, domain_db, graph, frozen):
    with domain_db.transaction() as session:
        purchase, _ = next_purchase(session, graph)
        freeze(session, graph, purchase)
        other_id = purchase.id
    first, other = read(api, graph), read(api, graph, other_id)
    assert first["expected"] != other["expected"]
    assert preview(api, graph, first["expected"], purchase_id=other_id).status_code == 409


@pytest.mark.parametrize(
    "model,key",
    [
        (Client, "client_id"),
        (PackagePurchase, "purchase_id"),
        (TrainingSession, "session_id"),
        (Trainer, "trainer_id"),
    ],
)
def test_changed_reviewed_evidence_rejects(api, domain_db, graph, frozen, model, key):
    result = read(api, graph)
    with domain_db.transaction() as session:
        session.get(model, graph[key]).version += 1
    assert preview(api, graph, result["expected"]).status_code == 409


def test_overlapping_active_purchase_blocks_restoration(api, domain_db, graph, frozen):
    with domain_db.transaction() as session:
        purchase, slots, prefs, bookings = purchase_parts(graph, graph["start_date"])
        client = session.get(Client, graph["client_id"])
        add_purchase(
            session, purchase, slots, prefs, bookings, expected_client_version=client.version
        )
    result = read(api, graph)
    assert "overlap" in result["packageError"]


def test_completed_and_open_sessions_preserve_their_restoration_rules(api, domain_db, graph):
    with domain_db.transaction() as session:
        b = session.get(TrainingSession, graph["session_id"])
        acknowledge(session, b.id, b.version, graph["owner_id"], method="late_no_show")
        other = session.get(TrainingSession, graph["second_session_id"])
        other.schedule_state = "open"
        other.training_date = other.starts_at = other.ends_at = None
        other.session_number = other.schedule_slot_id = None
        freeze(session, graph, session.get(PackagePurchase, graph["purchase_id"]))
    result = read(api, graph)
    assert len(result["rows"]) == 1 and result["rows"][0]["scheduleState"] == "open"
    assert result["rows"][0]["date"] is None
    moved = preview(
        api, graph, result["expected"], {str(graph["second_session_id"]): str(graph["start_date"])}
    )
    assert "open session" in moved.json()["rows"][0]["error"]
    assert (
        preview(
            api, graph, result["expected"], {str(graph["session_id"]): str(graph["start_date"])}
        ).status_code
        == 422
    )


def test_active_missing_and_inactive_client_reviews_reject(api, graph):
    assert api.get(path(graph)).status_code == 409
    assert api.get(path(graph, uuid4())).status_code == 404
    assert api.get(path({**graph, "client_id": uuid4()})).status_code == 404
    deactivate(api, graph)
    assert api.get(path(graph)).status_code == 409


def test_trainer_cannot_read_or_preview_package_restoration(
    api, domain_db, graph, frozen, auth_settings, auth_service, fake_cognito
):
    result = read(api, graph)
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get(path(graph)).status_code == 403
    assert preview(api, graph, result["expected"]).status_code == 403


def test_admin_can_review_but_preview_requires_csrf(
    api, domain_db, graph, frozen, invitations, auth_settings, auth_service, fake_cognito
):
    created = create_admin(api)
    login_admin(api, auth_service, auth_settings, fake_cognito, created.json()["id"])
    result = read(api, graph)
    assert preview(api, graph, result["expected"]).status_code == 200
    api.headers.pop("X-CSRF-Token")
    assert preview(api, graph, result["expected"]).status_code == 403
