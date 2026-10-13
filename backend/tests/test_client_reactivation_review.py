"""Reactivation reviews are scoped, complete and never mutate the retained calendar."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.people import Client, LifecycleEvent
from app.models.training import PackagePurchase, TrainingSession
from app.persistence import acknowledge, add_client, add_purchase
from tests.domain_fixtures import person, purchase_parts
from tests.test_client_deactivation_api import command, review, row_values, save
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def deactivate(api, graph):
    assert save(api, graph, command(review(api, graph))).status_code == 200


def read(api, graph):
    response = api.get(f"/api/clients/{graph['client_id']}/reactivation-review")
    assert response.status_code == 200, response.text
    return response.json()


def preview(api, graph, expected, dates):
    return api.post(
        f"/api/clients/{graph['client_id']}/reactivation-review",
        json={"expected": expected, "dates": dates},
        headers={"Idempotency-Key": str(uuid4())},
    )


def snapshot(domain_db):
    with domain_db.transaction() as session:
        return {
            model.__tablename__: [
                row_values(r) for r in session.scalars(select(model).order_by(model.id))
            ]
            for model in [Client, PackagePurchase, TrainingSession, LifecycleEvent]
        }


def test_complete_review_and_date_preview_never_change_retained_records(api, domain_db, graph):
    deactivate(api, graph)
    before = snapshot(domain_db)
    result = read(api, graph)
    assert result["purchaseIds"] == [str(graph["purchase_id"])]
    assert len(result["rows"]) == 2
    assert all(row["error"] is None for row in result["rows"])
    assert result["packageError"] is None
    day = str(graph["end_date"] + timedelta(days=100))
    changed = preview(api, graph, result["expected"], {str(graph["session_id"]): day})
    assert changed.status_code == 200, changed.text
    moved = next(r for r in changed.json()["rows"] if r["id"] == str(graph["session_id"]))
    assert moved["date"] == day and moved["originalDate"] == str(graph["start_date"])
    assert moved["startsAt"] == "10:00" and moved["endsAt"] == "11:00"
    assert moved["trainerId"] == str(graph["trainer_id"]) and moved["error"] is None
    assert snapshot(domain_db) == before


def test_preview_rechecks_competing_bookings_and_mutual_proposed_dates(api, domain_db, graph):
    deactivate(api, graph)
    viewed = read(api, graph)
    with domain_db.transaction() as session:
        other = add_client(
            session,
            Client(kind="individual", name="Other", trainer_id=graph["trainer_id"]),
            [person("Other")],
        )
        purchase, slots, preferences, bookings = purchase_parts(
            graph, graph["start_date"], client_id=other.id, stage="current"
        )
        add_purchase(
            session, purchase, slots, preferences, bookings, expected_client_version=other.version
        )
    blocked = preview(api, graph, viewed["expected"], {})
    assert blocked.status_code == 200, blocked.text
    assert all(r["error"] for r in blocked.json()["rows"])
    free = str(graph["start_date"] + timedelta(days=1))
    collision = preview(
        api,
        graph,
        viewed["expected"],
        {str(graph["session_id"]): free, str(graph["second_session_id"]): free},
    )
    assert all(r["error"] for r in collision.json()["rows"])
    resolved = preview(
        api,
        graph,
        viewed["expected"],
        {
            str(graph["session_id"]): free,
            str(graph["second_session_id"]): str(graph["start_date"] + timedelta(days=2)),
        },
    )
    assert all(r["error"] is None for r in resolved.json()["rows"])


def test_completed_sessions_and_separately_inactive_purchases_are_not_reactivation_rows(
    api, domain_db, graph
):
    with domain_db.transaction() as session:
        b = session.get(TrainingSession, graph["session_id"])
        acknowledge(session, b.id, b.version, graph["owner_id"], method="late_no_show")
        purchase, slots, preferences, bookings = purchase_parts(graph)
        add_purchase(
            session,
            purchase,
            slots,
            preferences,
            bookings,
            expected_client_version=graph["client_version"],
        )
        session.flush()
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
    deactivate(api, graph)
    result = read(api, graph)
    assert result["purchaseIds"] == [str(graph["purchase_id"])]
    assert [r["id"] for r in result["rows"]] == [str(graph["second_session_id"])]
    assert (
        preview(
            api, graph, result["expected"], {str(graph["session_id"]): str(graph["start_date"])}
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "model,key",
    [(Client, "client_id"), (PackagePurchase, "purchase_id"), (TrainingSession, "session_id")],
)
def test_review_rejects_stale_retained_evidence(api, domain_db, graph, model, key):
    deactivate(api, graph)
    result = read(api, graph)
    with domain_db.transaction() as session:
        session.get(model, graph[key]).version += 1
    assert preview(api, graph, result["expected"], {}).status_code == 409


@pytest.mark.parametrize("day", ["2026-02-30", "2026-01-01T00:00:00Z", 123])
def test_invalid_replacement_dates_are_rejected(api, graph, day):
    deactivate(api, graph)
    result = read(api, graph)
    assert (
        preview(api, graph, result["expected"], {str(graph["session_id"]): day}).status_code == 422
    )


def test_active_missing_and_unknown_session_reviews_fail_closed(api, graph):
    assert api.get(f"/api/clients/{graph['client_id']}/reactivation-review").status_code == 409
    assert api.get(f"/api/clients/{uuid4()}/reactivation-review").status_code == 404
    deactivate(api, graph)
    result = read(api, graph)
    assert (
        preview(
            api, graph, result["expected"], {str(uuid4()): str(graph["start_date"])}
        ).status_code
        == 422
    )


def test_assigned_trainer_cannot_read_or_preview_reactivation(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    deactivate(api, graph)
    result = read(api, graph)
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get(f"/api/clients/{graph['client_id']}/reactivation-review").status_code == 403
    assert preview(api, graph, result["expected"], {}).status_code == 403


def test_inactive_trainer_is_reported_and_invalidates_the_old_review(api, domain_db, graph):
    from app.models.people import Trainer

    deactivate(api, graph)
    old = read(api, graph)
    with domain_db.transaction() as session:
        session.get(Trainer, graph["trainer_id"]).status = "inactive"
    assert preview(api, graph, old["expected"], {}).status_code == 409
    assert all("assigned trainer" in r["error"] for r in read(api, graph)["rows"])


@pytest.mark.parametrize("completed", [False, True])
def test_touching_intervals_are_free_but_inactive_completed_booking_still_occupies(
    api, domain_db, graph, completed
):
    from datetime import time

    deactivate(api, graph)
    with domain_db.transaction() as session:
        other = add_client(
            session,
            Client(kind="individual", name="Other", trainer_id=graph["trainer_id"]),
            [person("Other")],
        )
        purchase, slots, preferences, bookings = purchase_parts(
            graph, graph["start_date"], client_id=other.id, stage="current"
        )
        if not completed:
            slots[0].starts_at = slots[0].purchased_starts_at = time(11)
            slots[0].ends_at = slots[0].purchased_ends_at = time(12)
            for booking in bookings:
                booking.starts_at, booking.ends_at = time(11), time(12)
        add_purchase(
            session, purchase, slots, preferences, bookings, expected_client_version=other.version
        )
        session.flush()
        if completed:
            acknowledge(
                session,
                bookings[0].id,
                bookings[0].version,
                graph["owner_id"],
                method="late_no_show",
            )
        other_id = other.id
    if completed:
        deactivate(api, {**graph, "client_id": other_id})
    result = read(api, graph)
    errors = {r["id"]: r["error"] for r in result["rows"]}
    assert bool(errors[str(graph["session_id"])]) is completed
    assert errors[str(graph["second_session_id"])] is None
