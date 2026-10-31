"""Matching reads current PostgreSQL bookings and never reserves or discloses health."""

from datetime import time, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.api.client_matching import DAYS
from app.models.people import Trainer, TrainerAvailability
from app.models.training import TrainingSession
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = [pytest.mark.database, pytest.mark.parametrize("graph", ["future"], indirect=True)]


def request_body(graph):
    return {
        "packageId": str(graph["template_id"]),
        "packageVersion": 1,
        "startDate": graph["start_date"].isoformat(),
        "sessionsPerWeek": 1,
        "genderPreference": "No gender preference",
        "clientPreferences": [
            {"days": [DAYS[graph["start_date"].weekday()]], "from": "10:00", "to": "11:00"}
        ],
    }


def declared_hours(domain_db, graph):
    with domain_db.transaction() as session:
        session.add(
            TrainerAvailability(
                trainer_id=graph["trainer_id"],
                weekday=graph["start_date"].weekday(),
                starts_at=time(9),
                ends_at=time(18),
            )
        )


def preview(api, graph, **patch):
    return api.post(
        "/api/client-onboarding/matches",
        json={**request_body(graph), **patch},
        headers={"Idempotency-Key": str(uuid4())},
    )


def test_matches_real_occupied_dates_and_touching_intervals_without_writing(api, domain_db, graph):
    declared_hours(domain_db, graph)
    assert preview(api, graph).json() == {"matches": []}
    body = request_body(graph)
    body["clientPreferences"].append(
        {"days": body["clientPreferences"][0]["days"], "from": "11:00", "to": "12:00"}
    )
    response = api.post(
        "/api/client-onboarding/matches", json=body, headers={"Idempotency-Key": str(uuid4())}
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "matches": [
            {
                "trainerId": str(graph["trainer_id"]),
                "trainerVersion": 1,
                "matches": 2,
                "total": 2,
                "schedule": [
                    {"day": body["clientPreferences"][0]["days"][0], "from": "11:00", "to": "12:00"}
                ],
            }
        ]
    }
    assert not any(
        word in response.text for word in ("clientId", "name", "rate", "email", "answers", "health")
    )
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(TrainingSession)) == 2


def test_missing_hours_and_gender_mismatch_never_match(api, domain_db, graph):
    assert preview(api, graph).json() == {"matches": []}
    declared_hours(domain_db, graph)
    with domain_db.transaction() as session:
        trainer = session.get(Trainer, graph["trainer_id"])
        trainer.gender = "Female"
    assert preview(api, graph, genderPreference="Male trainer preferred").json() == {"matches": []}


@pytest.mark.parametrize(
    "patch,status",
    [
        ({"packageVersion": 2}, 409),
        ({"packageId": str(uuid4())}, 404),
        ({"sessionsPerWeek": True}, 422),
        ({"startDate": "2026-02-31"}, 422),
        ({"startDate": 0}, 422),
        ({"startDate": "9999-12-31"}, 422),
        (
            {"clientPreferences": [{"days": ["Monday", "Monday"], "from": "10:00", "to": "11:00"}]},
            422,
        ),
        ({"clientPreferences": [{"days": ["Monday"], "from": "10:00:00", "to": "11:00"}]}, 422),
        ({"actor": "owner"}, 422),
    ],
)
def test_invalid_or_stale_requests_are_rejected(api, graph, patch, status):
    assert preview(api, graph, **patch).status_code == status


def test_assigned_trainer_cannot_use_operations_preview(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert preview(api, graph).status_code == 403


def test_authenticated_admin_can_preview_and_csrf_remains_required(
    api, domain_db, graph, auth_service, auth_settings, fake_cognito, invitations
):
    created = create_admin(api).json()
    login_admin(api, auth_service, auth_settings, fake_cognito, created["id"])
    assert preview(api, graph).status_code == 200
    api.headers.pop("X-CSRF-Token")
    assert preview(api, graph).status_code == 403


@pytest.mark.parametrize("days_before_future_start", [1, 2])
def test_onboarding_rejects_today_and_past_start_without_writes(
    api, domain_db, graph, days_before_future_start
):
    declared_hours(domain_db, graph)
    start = graph["start_date"] - timedelta(days=days_before_future_start)
    response = preview(api, graph, startDate=start.isoformat())
    assert response.status_code == 422, response.text
    assert response.json()["error"]["message"] == "Choose a future start date."
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(TrainingSession)) == 2
