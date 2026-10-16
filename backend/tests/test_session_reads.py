"""Calendar scope is actual session assignment; cover context never becomes a profile."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.api import session_reads
from app.models.people import ClientPerson
from app.models.training import ExercisePlanItem, ExerciseResult, TrainingSession
from app.persistence import acknowledge
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_client_reactivation_review import snapshot
from tests.test_directory_api import covered_session
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def read(api, graph):
    response = api.get(f"/api/sessions/{graph['session_id']}/details")
    assert response.status_code == 200, response.text
    return response.json()


def test_owner_calendar_is_persisted_scoped_labels_and_read_only(api, domain_db, graph):
    before = snapshot(domain_db)
    response = api.get("/api/session-calendar")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["viewerId"] == str(graph["owner_id"])
    assert {s["id"] for s in data["sessions"]} == {
        str(graph[k]) for k in ["session_id", "second_session_id"]
    }
    assert data["clients"] == [
        {
            "id": str(graph["client_id"]),
            "name": "Client One",
            "kind": "individual",
            "status": "active",
        }
    ]
    assert data["purchases"][0]["used"] == 0
    assert data["purchases"][0]["total"] == 2
    assert response.headers["cache-control"] == "no-store"
    assert snapshot(domain_db) == before


def test_cover_calendar_uses_minimal_context_and_never_grants_profile_access(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    covered_client, booking, other_trainer = covered_session(domain_db, graph)
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    data = api.get("/api/session-calendar").json()
    assert len(data["sessions"]) == 3
    assert {t["id"] for t in data["trainers"]} == {str(graph["trainer_id"])}
    context = next(c for c in data["clients"] if c["id"] == str(covered_client))
    assert set(context) == {"id", "name", "kind", "status"}
    assert context["name"] == "Covered Couple"
    assert api.get(f"/api/sessions/{booking}/details").status_code == 200
    assert str(covered_client) not in [c["id"] for c in api.get("/api/directory").json()["clients"]]
    assert api.get(f"/api/clients/{covered_client}/notes").status_code == 404
    with domain_db.transaction() as session:
        excluded = session.scalar(
            select(TrainingSession.id).where(
                TrainingSession.client_id == covered_client,
                TrainingSession.trainer_id == other_trainer,
            )
        )
    assert api.get(f"/api/sessions/{excluded}/details").status_code == 404


def test_permanent_relationship_keeps_cover_history_separate_from_assignment(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    _, _, other_trainer = covered_session(domain_db, graph)
    with domain_db.transaction() as session:
        session.get(TrainingSession, graph["second_session_id"]).trainer_id = other_trainer
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    data = api.get("/api/session-calendar").json()
    historical = next(s for s in data["sessions"] if s["id"] == str(graph["second_session_id"]))
    assert historical["readAccess"] == "historical"
    assert (
        api.get(f"/api/sessions/{graph['second_session_id']}/details").json()["session"][
            "readAccess"
        ]
        == "historical"
    )


def test_admin_calendar_and_details_never_include_financial_or_profile_fields(
    api, domain_db, graph, invitations, auth_service, auth_settings, fake_cognito
):
    admin = create_admin(api).json()["id"]
    login_admin(api, auth_service, auth_settings, fake_cognito, admin)
    with domain_db.transaction() as session:
        person = session.scalar(
            select(ClientPerson).where(ClientPerson.client_id == graph["client_id"])
        )
        person.health_notes = "PRIVATE HEALTH SENTINEL"
    for path in ["/api/session-calendar", f"/api/sessions/{graph['session_id']}/details"]:
        response = api.get(path)
        assert response.status_code == 200, response.text
        for private in [
            "PRIVATE HEALTH SENTINEL",
            "peak_rate",
            "off_peak",
            "phone",
            "email",
            "assessments",
            "health_notes",
            "object_key",
            "bucket",
        ]:
            assert private not in response.text


def test_open_session_remains_undated_unnumbered_and_visible(api, domain_db, graph):
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        booking.schedule_state = "open"
        booking.training_date = booking.starts_at = booking.ends_at = booking.session_number = (
            booking.schedule_slot_id
        ) = None
    data = read(api, graph)["session"]
    assert data["scheduleState"] == "open"
    assert all(data[k] is None for k in ["date", "startsAt", "endsAt", "sessionNumber"])
    assert str(graph["session_id"]) in {
        s["id"] for s in api.get("/api/session-calendar").json()["sessions"]
    }


def test_cancelled_session_retains_its_real_status_and_dates(api, domain_db, graph):
    with domain_db.transaction() as session:
        session.get(TrainingSession, graph["session_id"]).status = "cancelled"
    data = read(api, graph)["session"]
    assert data["status"] == "cancelled" and data["date"] is not None


def test_plan_results_notes_and_truthful_handoff_are_read_from_storage(api, domain_db, graph):
    with domain_db.transaction() as session:
        plan = ExercisePlanItem(
            session_id=graph["session_id"],
            position=1,
            name="Stored Squat",
            weight="12 kg",
            reps="8",
            rounds="3",
            rest="60s",
            notes="Stored instruction",
        )
        session.add(plan)
        session.flush()
        session.add(
            ExerciseResult(
                session_id=graph["session_id"],
                plan_item_id=plan.id,
                name=plan.name,
                load_kg=12.5,
                reps=8,
                sets=3,
            )
        )
        booking = session.get(TrainingSession, graph["session_id"])
        booking.trainer_comments, booking.client_summary = "Stored outcome", "Stored summary"
        plan_id = plan.id
    data = read(api, graph)
    assert data["exercisePlan"][0]["id"] == str(plan_id)
    assert data["exercisePlan"][0]["notes"] == "Stored instruction"
    assert data["exercisePlan"][0]["videoAttached"] is False
    assert data["exerciseResults"][0]["planItemId"] == str(plan_id)
    assert data["exerciseResults"][0]["loadKg"] == 12.5
    assert data["trainerComments"] == "Stored outcome" and data["clientSummary"] == "Stored summary"
    assert data["whatsappOpenedAt"] is None and data["whatsappOpenCount"] == 0


def test_acknowledgement_correction_retains_both_actors_signature_and_single_credit(
    api, domain_db, graph
):
    strokes = [[{"x": 10, "y": 10}, {"x": 30, "y": 30}, {"x": 60, "y": 10}]]
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        acknowledge(
            session,
            booking.id,
            booking.version,
            graph["owner_id"],
            method="late_no_show",
            note="Initial note",
        )
        acknowledge(
            session,
            booking.id,
            booking.version,
            graph["owner_id"],
            method="signature",
            signer_name="Client One",
            strokes=strokes,
            note="Corrected",
        )
    data = read(api, graph)
    assert data["session"]["status"] == "completed"
    assert [r["method"] for r in data["acknowledgementHistory"]] == ["late_no_show", "signature"]
    assert data["acknowledgementHistory"][1]["signature"] == strokes
    assert data["acknowledgementHistory"][0]["recordedBy"]["id"] == str(graph["owner_id"])
    assert data["purchase"]["used"] == 1
    assert api.get("/api/session-calendar").json()["purchases"][0]["used"] == 1
    assert "signature" not in api.get("/api/session-calendar").text


def test_calendar_capacity_fails_closed_instead_of_truncating(api, monkeypatch):
    monkeypatch.setattr(session_reads, "MAX_SESSIONS", 1)
    response = api.get("/api/session-calendar")
    assert response.status_code == 503 and response.json()["error"]["code"] == "calendar_capacity"


def test_missing_detail_has_no_context(api):
    response = api.get(f"/api/sessions/{uuid4()}/details")
    assert response.status_code == 404
    assert "client" not in response.text


@pytest.mark.parametrize(
    "path", ["/api/session-calendar", "/api/sessions/10000000-0000-4000-8000-000000000001"]
)
def test_signed_out_session_reads_are_rejected(api, path):
    api.cookies.clear()
    assert api.get(path).status_code == 401


def test_completed_cover_keeps_session_evidence_but_not_temporary_profile(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    client_id, booking_id, _ = covered_session(domain_db, graph)
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, booking_id)
        acknowledge(session, booking.id, booking.version, graph["user_id"], method="late_no_show")
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    data = api.get(f"/api/sessions/{booking_id}/details").json()
    assert data["session"]["status"] == "completed"
    assert data["acknowledgementHistory"][0]["recordedBy"]["id"] == str(graph["user_id"])
    assert set(data["client"]) == {"id", "name", "kind", "status"}
    assert api.get(f"/api/sessions/{booking_id}/client").status_code == 404
    assert api.get(f"/api/clients/{client_id}/notes").status_code == 404


@pytest.mark.parametrize("expired", [False, True])
def test_video_presence_respects_expiry_without_exposing_storage_or_mutating_media(
    api, domain_db, graph, expired, monkeypatch
):
    from datetime import UTC, datetime, timedelta

    from app.models.media import MediaAsset

    now = datetime.now(UTC)
    with domain_db.transaction() as session:
        plan = ExercisePlanItem(session_id=graph["session_id"], position=1, name="Recorded Squat")
        session.add(plan)
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
            session_id=graph["session_id"],
            original_session_id=graph["session_id"],
            original_plan_item_id=plan.id,
            expires_at=now + timedelta(days=1),
        )
        session.add(media)
        session.flush()
        media_id = media.id
    if expired:

        class FutureClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return now + timedelta(days=3)

        monkeypatch.setattr(session_reads, "datetime", FutureClock)
    response = api.get(f"/api/sessions/{graph['session_id']}/details")
    assert response.status_code == 200, response.text
    assert response.json()["exercisePlan"][0]["videoAttached"] is (not expired)
    assert "private-fixture" not in response.text and "private-object" not in response.text
    with domain_db.transaction() as session:
        assert session.get(MediaAsset, media_id).status == "ready"
