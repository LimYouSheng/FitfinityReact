"""Approved domain commands retain real PostgreSQL versions, receipts and business guards."""

from uuid import uuid4

import pytest

from tests.test_admin_api import invitations as invitations
from tests.test_admin_approvals import decision
from tests.test_admin_approvals import identities as identities
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


def enable(api, identities, area):
    admin_id, use = identities
    use("owner")
    path = f"/api/staff/admins/{admin_id}"
    current = api.get(path).json()
    result = api.post(
        path,
        json={
            "expectedVersion": current["version"],
            "operation": "approvals",
            "approvalNeeded": {**current["approvalNeeded"], area: True},
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert result.status_code == 200, result.text
    use("admin")
    return use


def scenario(api, graph, operation, domain_db=None):
    client, trainer, booking = (
        str(graph[key]) for key in ["client_id", "trainer_id", "session_id"]
    )
    if operation == "trainer.reactivate":
        from tests.test_trainer_reactivation import body, deactivate

        deactivate(domain_db, graph)
        return (
            "trainerLifecycle",
            f"/api/trainers/{trainer}/reactivation",
            body(graph),
            "/api/trainer-reactivations",
            "/api/directory",
        )
    if operation == "assessment.create":
        from tests.test_staff_api import body

        person = next(
            row for row in api.get("/api/directory").json()["clients"] if row["id"] == client
        )["people"][0]
        path = f"/api/people/{person['id']}/assessments"
        return "assessments", path, body(), "/api/assessment-saves", path
    if operation == "client.notes":
        read = f"/api/clients/{client}/notes"
        before = api.get(read).json()
        return (
            "clientDetails",
            read,
            {"expectedVersion": before["version"], "patch": {"remarks": "Reviewed coaching note"}},
            "/api/client-note-saves",
            read,
        )
    if operation == "client.details":
        from tests.test_client_details import payload

        return (
            "clientDetails",
            f"/api/clients/{client}/personal-details",
            payload(api, graph),
            "/api/client-detail-saves",
            "/api/directory",
        )
    if operation == "trainer.details":
        return (
            "trainerDetails",
            f"/api/trainers/{trainer}/personal-details",
            {"expectedVersion": 1, "patch": {"name": "Reviewed Trainer"}},
            "/api/trainer-detail-saves",
            "/api/directory",
        )
    if operation == "trainer.approvals":
        from tests.test_trainer_approvals import CONTROLS

        return (
            "trainerAssignment",
            f"/api/trainers/{trainer}/approvals",
            {"expectedVersion": 1, "approvalNeeded": CONTROLS},
            "/api/trainer-approval-saves",
            "/api/directory",
        )
    if operation == "client.deactivate":
        before = api.get(f"/api/clients/{client}/deactivation").json()
        body = {
            "expectedVersion": before["version"],
            "expectedTrainerId": before["trainerId"],
            "purchases": [
                {k: p[k] for k in ["id", "version", "status"]} for p in before["purchases"]
            ],
        }
        return (
            "clientLifecycle",
            f"/api/clients/{client}/deactivation",
            body,
            "/api/client-deactivations",
            "/api/directory",
        )
    if operation == "session.plan":
        from tests.test_session_plans_api import item

        read = f"/api/sessions/{booking}/plan-review"
        before = api.get(read).json()
        return (
            "sessionContent",
            f"/api/sessions/{booking}/plan",
            {"expected": before["expected"], "items": [item()]},
            "/api/session-plans",
            read,
        )
    if operation == "session.booking":
        from tests.test_session_booking_api import payload

        return (
            "sessionScheduling",
            f"/api/sessions/{booking}/booking",
            payload(api, booking),
            "/api/session-booking-saves",
            f"/api/sessions/{booking}/booking-review",
        )
    if operation == "session.outcome":
        from tests.test_session_outcomes_api import measurement, setup_plan

        _, item_id = setup_plan(api, graph)
        read = f"/api/sessions/{booking}/outcome-review"
        before = api.get(read).json()
        return (
            "sessionContent",
            f"/api/sessions/{booking}/outcome",
            {
                "expected": before["expected"],
                "trainerComments": "Reviewed outcome",
                "measurements": [measurement(item_id)],
            },
            "/api/session-outcomes",
            read,
        )
    if operation == "session.acknowledge":
        read = f"/api/sessions/{booking}/acknowledgement-review"
        before = api.get(read).json()
        return (
            "sessionAcknowledgement",
            f"/api/sessions/{booking}/acknowledgement",
            {"expected": before["expected"], "method": "late_no_show"},
            "/api/session-acknowledgements",
            "/api/directory",
        )
    if operation == "session.summary":
        read = f"/api/sessions/{booking}/summary-review"
        before = api.get(read).json()
        return (
            "sessionContent",
            f"/api/sessions/{booking}/summary",
            {"expected": before["expected"], "summary": "Reviewed summary"},
            "/api/session-summaries",
            read,
        )
    raise AssertionError(operation)


def domain_state(api, path):
    response = api.get(path)
    assert response.status_code == 200, response.text
    state = response.json()
    if path == "/api/directory":
        state.pop("serverAt")
    return state


@pytest.mark.parametrize(
    "operation",
    [
        "client.notes",
        "client.details",
        "trainer.details",
        "trainer.approvals",
        "client.deactivate",
        "session.plan",
        "session.summary",
        "session.booking",
        "session.outcome",
        "session.acknowledge",
        "trainer.reactivate",
        "assessment.create",
    ],
)
def test_approved_domain_change_persists_once_with_original_actor_receipt(
    api, graph, identities, operation, domain_db
):
    area, path, body, recovery, read = scenario(api, graph, operation, domain_db)
    use = enable(api, identities, area)
    before = domain_state(api, read)
    key = uuid4()
    result = api.post(path, json=body, headers={"Idempotency-Key": str(key)})
    assert result.status_code == 202, result.text
    # Compare only domain data: proposal notices do not mutate the reviewed aggregate.
    assert domain_state(api, read) == before
    proposal = api.get("/api/admin-requests").json()[0]
    assert proposal["operation"] == operation and proposal["body"]["review"] is not None
    recovered = api.get(f"{recovery}/{key}")
    assert recovered.status_code == 202, recovered.text
    use("owner")
    approved = decision(api, proposal)
    assert approved.status_code == 200, approved.text
    use("admin")
    original = api.get(f"{recovery}/{key}")
    assert original.status_code == 200, original.text
    replay = api.post(path, json=body, headers={"Idempotency-Key": str(key)})
    assert replay.status_code == 200 and replay.json() == original.json(), replay.text
    after = domain_state(api, read)
    assert after != before
    if operation == "client.notes":
        assert after["remarks"] == "Reviewed coaching note"
        assert after["healthNotes"] == before["healthNotes"]
    if operation == "session.summary":
        assert after["summary"] == "Reviewed summary"
    if operation == "assessment.create":
        assert len(after["items"]) == 1
        assert after["items"][0]["answers"] == {"eyes_open_1": 0}
    if operation == "trainer.reactivate":
        trainer = next(row for row in after["trainers"] if row["id"] == str(graph["trainer_id"]))
        assert trainer["status"] == "active" and trainer["version"] == 3
        assert after["clients"] == before["clients"]
    if operation == "session.acknowledge":
        client = next(row for row in after["clients"] if row["id"] == str(graph["client_id"]))
        purchase = next(
            row for row in client["purchases"] if row["id"] == str(graph["purchase_id"])
        )
        assert purchase["used"] == 1
    if operation == "session.outcome":
        assert after["trainerComments"] == "Reviewed outcome"
        assert after["rows"][0]["loadKg"] == 20
    if operation == "session.booking":
        assert after["session"]["startsAt"] == "12:00"
    assert decision(api, proposal).status_code == 403


@pytest.mark.parametrize("uncertain", [False, True])
def test_owner_approval_sends_trainer_invitation_without_admin_second_step(
    api, graph, identities, invitations, uncertain, monkeypatch
):
    from tests.test_trainer_creation import BODY, create, receipt

    use = enable(api, identities, "trainerCreation")
    body = {key: value for key, value in BODY.items() if key != "rates"}
    calls = list(invitations.calls)
    key, decision_key = uuid4(), uuid4()
    submitted = create(api, body, key)
    assert submitted.status_code == 202, submitted.text
    assert invitations.calls[len(calls) :] == ["config"]
    assert receipt(api, key).status_code == 202
    proposal = api.get("/api/admin-requests").json()[0]
    if uncertain:
        original = invitations.send

        def unknown(*args):
            original(*args)
            return False

        monkeypatch.setattr(invitations, "send", unknown)
    use("owner")
    approved = decision(api, proposal, key=decision_key)
    assert approved.status_code == 200, approved.text
    assert invitations.calls.count("send") == calls.count("send") + 1
    assert decision(api, proposal, key=decision_key).status_code == 200
    assert invitations.calls.count("send") == calls.count("send") + 1
    use("admin")
    saved = receipt(api, key)
    assert saved.status_code == 200, saved.text
    assert saved.json()["invitation"] == ("unknown" if uncertain else "sent")
    assert create(api, body, key).json() == saved.json()
    assert invitations.calls.count("send") == calls.count("send") + 1


def test_deactivated_requesting_admin_blocks_invitation_after_provider_setup(
    api, graph, identities, invitations, domain_db
):
    from app.models.people import StaffUser
    from tests.test_trainer_creation import BODY, create

    use = enable(api, identities, "trainerCreation")
    body = {key: value for key, value in BODY.items() if key != "rates"}
    submitted = create(api, body, uuid4())
    assert submitted.status_code == 202, submitted.text
    proposal = api.get("/api/admin-requests").json()[0]
    sends = invitations.calls.count("send")

    def deactivate(stage):
        if stage == "ensure":
            with domain_db.transaction() as session:
                session.get(StaffUser, identities[0]).status = "inactive"

    invitations.hook = deactivate
    use("owner")
    result = decision(api, proposal)
    assert result.status_code == 409, result.text
    assert invitations.calls.count("send") == sends
    current = api.get("/api/admin-requests").json()[0]
    assert current["status"] == "approved"


@pytest.mark.parametrize(
    "operation", ["client.notes", "client.details", "session.plan", "session.summary"]
)
def test_owner_cannot_apply_stale_admin_proposal_over_newer_changes(
    api, graph, identities, operation
):
    area, path, body, recovery, read = scenario(api, graph, operation)
    use = enable(api, identities, area)
    key = uuid4()
    submitted = api.post(path, json=body, headers={"Idempotency-Key": str(key)})
    assert submitted.status_code == 202, submitted.text
    proposal = api.get("/api/admin-requests").json()[0]
    use("owner")
    changed = api.post(path, json=body, headers={"Idempotency-Key": str(uuid4())})
    assert changed.status_code == 200, changed.text
    latest = domain_state(api, read)
    stale = decision(api, proposal)
    assert stale.status_code == 409, stale.text
    assert domain_state(api, read) == latest
    assert api.get("/api/admin-requests").json()[0]["status"] == "pending"
    use("admin")
    assert api.get(f"{recovery}/{key}").status_code == 202


@pytest.mark.parametrize("approved", [True, False])
def test_library_upload_is_free_but_publication_waits_for_owner(
    api,
    graph,
    identities,
    media_store,
    domain_db,
    monkeypatch,
    approved,
    auth_service,
    auth_settings,
    fake_cognito,
):
    from datetime import timedelta

    from sqlalchemy import select

    from app import library_cleanup
    from app.api import exercise_library
    from app.models.media import LibrarySaveIntent, MediaAsset
    from tests.test_exercise_library_api import attach_store, commit, media_input, reserve, upload
    from tests.test_media_storage import PNG

    _, use = identities
    store = attach_store(api, media_store)
    before = api.get("/api/exercise-library").json()
    key, reserved = reserve(api, upload=media_input())
    assert reserved.status_code == 200, reserved.text
    upload(api, key)
    submitted = commit(api, key)
    assert submitted.status_code == 202, submitted.text
    assert api.get("/api/exercise-library").json() == before
    assert api.get(f"/api/exercise-library/save-intents/{key}").status_code == 202
    proposal = api.get("/api/admin-requests").json()[0]
    assert proposal["operation"] == "library.publish"
    with domain_db.transaction() as session:
        intent = session.scalar(
            select(LibrarySaveIntent).where(LibrarySaveIntent.request_key == key)
        )
        deadline = intent.upload_until
        evidence = exercise_library.evidence(session.get(MediaAsset, intent.upload_id))
    monkeypatch.setattr(library_cleanup, "clock", lambda _: deadline + timedelta(days=1))
    assert library_cleanup.run_once(domain_db, store, evidence.bucket) is False
    assert store.verified_bytes(evidence) == PNG
    use("owner")
    preview = api.get(f"/api/admin-requests/{proposal['id']}/attachment")
    assert preview.status_code == 200, preview.text
    assert preview.json()["sha256"] == evidence.sha256
    from tests.test_admin_api import create_admin, login_admin
    from tests.test_staff_api import trainer_login

    foreign = create_admin(
        api, patch={"email": "foreign-library@example.test", "name": "Other Admin"}
    )
    assert foreign.status_code == 200, foreign.text
    login_admin(
        api,
        auth_service,
        auth_settings,
        fake_cognito,
        foreign.json()["id"],
        email="foreign-library@example.test",
    )
    attachment_path = f"/api/admin-requests/{proposal['id']}/attachment"
    assert api.get(attachment_path).status_code == 404
    assert api.get(f"{attachment_path}/check?version={proposal['version']}").status_code == 404
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get(attachment_path).status_code == 403
    assert api.get(f"{attachment_path}/check?version={proposal['version']}").status_code == 403
    use("owner")
    decided = decision(api, proposal, "approved" if approved else "rejected")
    assert decided.status_code == 200, decided.text
    assert api.get(f"/api/admin-requests/{proposal['id']}/attachment").status_code == 404
    use("admin")
    if approved:
        recovered = api.get(f"/api/exercise-library/save-intents/{key}")
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["state"] == "completed"
        assert recovered.json()["result"]["name"] == "New movement"
        assert commit(api, key).json() == recovered.json()["result"]
        assert store.verified_bytes(evidence) == PNG
    else:
        assert api.get("/api/exercise-library").json() == before
        assert commit(api, key).status_code == 409
        assert library_cleanup.run_once(domain_db, store, evidence.bucket) is True
        assert store.head(evidence) is None


def test_admin_profile_probe_preserves_owner_target_then_receipt_lock_order(
    api, graph, domain_db, identities, database_settings
):
    """An Owner holding the target must not wait on an Admin blocked by that same row."""
    from concurrent.futures import ThreadPoolExecutor
    from contextlib import ExitStack
    from threading import Event
    from uuid import UUID

    from sqlalchemy import event, select, text

    from app.api.trainer_details import SaveTrainerDetails, save
    from app.auth.errors import AuthError
    from app.authorization import Principal
    from app.database import Database
    from app.models.people import StaffUser, Trainer

    waiting = Event()
    peer = Database(database_settings)
    admin = Principal(UUID(identities[0]), "Admin", "admin", None)
    owner = Principal(graph["owner_id"], "Owner", "owner", None)
    body = SaveTrainerDetails(expectedVersion=1, patch={"name": "Admin competing name"})

    def observe(connection, cursor, statement, parameters, context, many):
        if "FROM staff_users" in statement and "FOR UPDATE" in statement:
            waiting.set()

    def competing():
        try:
            with peer.transaction() as session:
                save(session, admin, graph["trainer_id"], uuid4(), body)
        except AuthError as failure:
            return failure.code
        return "unexpected_success"

    with ExitStack() as resources, ThreadPoolExecutor(max_workers=1) as pool:
        resources.callback(peer.close)
        with domain_db.transaction() as session:
            session.scalar(
                select(StaffUser).where(StaffUser.id == graph["user_id"]).with_for_update()
            )
            event.listen(peer.engine, "before_cursor_execute", observe)
            try:
                work = pool.submit(competing)
                assert waiting.wait(5), "Admin did not reach the held target row"
                assert session.scalar(text("SELECT pg_try_advisory_xact_lock(714602037)")), (
                    "Admin reversed the target/receipt lock order"
                )
                saved = save(
                    session,
                    owner,
                    graph["trainer_id"],
                    uuid4(),
                    SaveTrainerDetails(expectedVersion=1, patch={"name": "Owner winning name"}),
                )
                assert saved.version == 2
            finally:
                event.remove(peer.engine, "before_cursor_execute", observe)
        assert work.result(timeout=5) == "state_conflict"
    with domain_db.transaction() as session:
        assert session.get(Trainer, graph["trainer_id"]).name == "Owner winning name"
