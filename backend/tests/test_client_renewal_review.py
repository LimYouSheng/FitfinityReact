"""Renewal reads preserve saved defaults and check both sides of the real calendar."""

from datetime import date, time, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.api.client_matching import DAYS, MatchRequest
from app.api.client_matching import preview as match_preview
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.people import Client, Trainer, TrainerAvailability
from app.models.training import (
    PackagePurchase,
    PurchasePreference,
    PurchaseScheduleSlot,
    TrainingSession,
)
from app.persistence import acknowledge, add_client, add_purchase, occupied_booking_clause
from tests.domain_fixtures import person, purchase_parts
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_client_deactivation_api import command, row_values, save
from tests.test_client_deactivation_api import review as deactivate_review
from tests.test_client_matching import declared_hours, request_body
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def read(api, graph):
    response = api.get(f"/api/clients/{graph['client_id']}/renewal-review")
    assert response.status_code == 200, response.text
    return response.json()


def body(graph, reviewed):
    start = date.fromisoformat(reviewed["minimumStartDate"])
    return {
        **request_body(graph),
        "startDate": str(start),
        "expected": reviewed["expected"],
        "clientPreferences": [{"days": [DAYS[start.weekday()]], "from": "10:00", "to": "11:00"}],
    }


def preview(api, graph, payload):
    return api.post(
        f"/api/clients/{graph['client_id']}/renewal-matches",
        json=payload,
        headers={"Idempotency-Key": str(uuid4())},
    )


def snapshot(domain_db):
    with domain_db.transaction() as session:
        return {
            model.__tablename__: [
                row_values(r) for r in session.scalars(select(model).order_by(model.id))
            ]
            for model in [
                Client,
                PackagePurchase,
                PurchaseScheduleSlot,
                PurchasePreference,
                TrainingSession,
            ]
        }


def another_trainer(session):
    trainer = Trainer(
        name="Other trainer",
        email="other@example.test",
        phone_country_code="+65",
        phone_number="91234567",
        gender="Other",
        trainer_type="Strength",
        peak_rate_cents=8000,
        off_peak_rate_cents=5500,
    )
    session.add(trainer)
    session.flush()
    return trainer


def test_review_and_matching_preserve_saved_defaults_and_all_records(api, domain_db, graph):
    with domain_db.transaction() as session:
        trainer = another_trainer(session)
        client = add_client(
            session,
            Client(kind="individual", name="Renewal Client", trainer_id=trainer.id),
            [person()],
        )
        graph = {**graph, "trainer_id": trainer.id, "client_id": client.id}
        purchase, slots, _, bookings = purchase_parts(graph, graph["start_date"], stage="current")
        preferences = [
            PurchasePreference(
                weekday=graph["start_date"].weekday(), starts_at=time(9), ends_at=time(12)
            )
        ]
        add_purchase(
            session, purchase, slots, preferences, bookings, expected_client_version=client.version
        )
        graph = {**graph, "purchase_id": purchase.id}
    viewed = read(api, graph)
    start = date.fromisoformat(viewed["minimumStartDate"])
    with domain_db.transaction() as session:
        session.add(
            TrainerAvailability(
                trainer_id=graph["trainer_id"],
                weekday=start.weekday(),
                starts_at=time(9),
                ends_at=time(18),
            )
        )
    before = snapshot(domain_db)
    assert viewed["package"]["id"] == str(graph["purchase_id"])
    assert viewed["package"]["sessionsPerWeek"] == 1
    assert viewed["trainerId"] == str(graph["trainer_id"])
    with domain_db.transaction() as session:
        today = session.scalar(
            text("SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Singapore')::date")
        )
    assert start == today + timedelta(days=1)
    assert viewed["clientPreferences"] == [
        {"days": [DAYS[graph["start_date"].weekday()]], "from": "09:00", "to": "12:00"}
    ]
    assert viewed["fixedWeeklySchedule"][0]["from"] == "10:00"
    result = preview(api, graph, body(graph, viewed))
    assert result.status_code == 200, result.text
    assert result.json()["matches"][0]["trainerId"] == str(graph["trainer_id"])
    assert read(api, graph) == viewed
    assert snapshot(domain_db) == before
    assert not any(
        word in result.text for word in ("clientId", "health", "email", "rate", "answers")
    )


def test_client_booking_blocks_a_different_trainer_but_touching_is_free(api, domain_db, graph):
    viewed = read(api, graph)
    start = date.fromisoformat(viewed["minimumStartDate"])
    with domain_db.transaction() as session:
        trainer = another_trainer(session)
        trainer_id = str(trainer.id)
        session.add(
            TrainerAvailability(
                trainer_id=trainer.id, weekday=start.weekday(), starts_at=time(9), ends_at=time(18)
            )
        )
        booking = session.get(TrainingSession, graph["session_id"])
        booking.training_date = start
        booking.schedule_slot_id = None
    payload = body(graph, viewed)
    assert preview(api, graph, payload).json() == {"matches": []}
    payload["clientPreferences"][0].update({"from": "11:00", "to": "12:00"})
    result = preview(api, graph, payload)
    assert result.status_code == 200, result.text
    assert [m["trainerId"] for m in result.json()["matches"]] == [trainer_id]


@pytest.mark.parametrize("target", ["client", "purchase", "schedule"])
def test_stale_review_rejects_changed_aggregate(api, domain_db, graph, target):
    viewed = read(api, graph)
    with domain_db.transaction() as session:
        if target == "schedule":
            record = session.scalar(
                select(PurchaseScheduleSlot).where(
                    PurchaseScheduleSlot.purchase_id == graph["purchase_id"]
                )
            )
        else:
            model, key = (
                (Client, "client_id") if target == "client" else (PackagePurchase, "purchase_id")
            )
            record = session.get(model, graph[key])
        record.version += 1
    assert preview(api, graph, body(graph, viewed)).status_code == 409


def test_new_queued_purchase_invalidates_review_without_delaying_minimum(api, domain_db, graph):
    viewed = read(api, graph)
    with domain_db.transaction() as session:
        client = session.get(Client, graph["client_id"])
        purchase, slots, preferences, bookings = purchase_parts(graph)
        add_purchase(
            session, purchase, slots, preferences, bookings, expected_client_version=client.version
        )
    assert preview(api, graph, body(graph, viewed)).status_code == 409
    assert read(api, graph)["minimumStartDate"] == viewed["minimumStartDate"]


@pytest.mark.parametrize(
    "patch,status",
    [
        ({"expected": "0" * 64}, 409),
        ({"expected": "invalid"}, 422),
        ({"startDate": "2000-01-01"}, 422),
        ({"clientId": str(uuid4())}, 422),
        ({"packageVersion": 2}, 409),
    ],
)
def test_invalid_or_stale_match_inputs_fail_closed(api, graph, patch, status):
    viewed = read(api, graph)
    assert preview(api, graph, {**body(graph, viewed), **patch}).status_code == status


def test_inactive_and_missing_client_rejected(api, graph):
    viewed = read(api, graph)
    assert save(api, graph, command(deactivate_review(api, graph))).status_code == 200
    assert api.get(f"/api/clients/{graph['client_id']}/renewal-review").status_code == 409
    assert preview(api, graph, body(graph, viewed)).status_code == 409
    assert api.get(f"/api/clients/{uuid4()}/renewal-review").status_code == 404


def test_trainer_cannot_read_or_match_renewals(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    viewed = read(api, graph)
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get(f"/api/clients/{graph['client_id']}/renewal-review").status_code == 403
    assert preview(api, graph, body(graph, viewed)).status_code == 403


def test_admin_can_review_and_match_but_csrf_is_required(
    api, graph, auth_service, auth_settings, fake_cognito, invitations
):
    created = create_admin(api).json()
    login_admin(api, auth_service, auth_settings, fake_cognito, created["id"])
    viewed = read(api, graph)
    assert preview(api, graph, body(graph, viewed)).status_code == 200
    api.headers.pop("X-CSRF-Token")
    assert preview(api, graph, body(graph, viewed)).status_code == 403


@pytest.mark.parametrize("completed", [False, True])
def test_calendar_occupancy_retains_completed_inactive_bookings_and_rejects_backdated_preview(
    api, domain_db, graph, completed
):
    declared_hours(domain_db, graph)
    with domain_db.transaction() as session:
        if completed:
            booking = session.get(TrainingSession, graph["session_id"])
            acknowledge(
                session, booking.id, booking.version, graph["owner_id"], method="late_no_show"
            )
    assert save(api, graph, command(deactivate_review(api, graph))).status_code == 200
    with domain_db.transaction() as session:
        occupied = session.scalars(
            select(TrainingSession.id)
            .join(PackagePurchase, TrainingSession.purchase_id == PackagePurchase.id)
            .join(Client, TrainingSession.client_id == Client.id)
            .where(TrainingSession.client_id == graph["client_id"], occupied_booking_clause())
        ).all()
        assert occupied == ([graph["session_id"]] if completed else [])
        principal = Principal(graph["owner_id"], "Owner Original", "owner", None)
        with pytest.raises(AuthError) as rejected:
            match_preview(
                session,
                principal,
                MatchRequest.model_validate(request_body(graph)),
                client_id=graph["client_id"],
            )
        assert rejected.value.status == 422


@pytest.mark.parametrize("scenario", ["preserve", "occupied", "outside_preferences"])
def test_saved_slots_are_preserved_exactly_or_unavailable(api, domain_db, graph, scenario):
    declared_hours(domain_db, graph)
    viewed = read(api, graph)
    payload = body(graph, viewed)
    payload.update(
        {
            "trainerId": str(graph["trainer_id"]),
            "fixedWeeklySchedule": [
                {k: v for k, v in slot.items() if k != "id"}
                for slot in viewed["fixedWeeklySchedule"]
            ],
            "clientPreferences": [
                {"days": [DAYS[graph["start_date"].weekday()]], "from": "09:00", "to": "12:00"}
            ],
        }
    )
    if scenario == "outside_preferences":
        payload["clientPreferences"][0]["from"] = "11:00"
    if scenario == "occupied":
        start = date.fromisoformat(payload["startDate"])
        with domain_db.transaction() as session:
            booking = session.get(TrainingSession, graph["session_id"])
            booking.training_date = start + timedelta(
                days=(graph["start_date"].weekday() - start.weekday()) % 7
            )
            booking.schedule_slot_id = None
    result = preview(api, graph, payload)
    assert result.status_code == 200, result.text
    if scenario == "preserve":
        assert result.json()["matches"][0]["schedule"] == payload["fixedWeeklySchedule"]
    else:
        assert result.json() == {"matches": []}


def test_retained_schedule_without_trainer_is_rejected(api, graph):
    viewed = read(api, graph)
    payload = body(graph, viewed)
    payload["fixedWeeklySchedule"] = [{"day": "Monday", "from": "10:00", "to": "11:00"}]
    assert preview(api, graph, payload).status_code == 422
