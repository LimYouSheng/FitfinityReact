"""Self-only availability requests/direct changes preserve bookings and retry evidence."""

from concurrent.futures import ThreadPoolExecutor
from datetime import time
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.api import trainer_availability as command
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.api import TrainerAvailabilityReceipt
from app.models.communications import ChangeRequest, Message, MessageReceipt, RequestEvent
from app.models.people import StaffUser, Trainer, TrainerAvailability
from app.models.training import TrainingSession
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database
SLOTS = [
    {"weekday": 1, "startsAt": "09:00", "endsAt": "10:00"},
    {"weekday": 1, "startsAt": "10:00", "endsAt": "11:00"},
]


@pytest.fixture
def trainer_api(api, domain_db, graph, auth_settings, auth_service, fake_cognito):
    with domain_db.transaction() as session:
        session.add(
            TrainerAvailability(
                trainer_id=graph["trainer_id"], weekday=0, starts_at=time(10), ends_at=time(11)
            )
        )
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    return api


def actor(graph):
    return Principal(graph["user_id"], "Trainer", "trainer", graph["trainer_id"])


def save(api, graph, version=1, slots=None, key=None, **extra):
    return api.post(
        f"/api/trainers/{graph['trainer_id']}/availability",
        json={"expectedVersion": version, "slots": SLOTS if slots is None else slots, **extra},
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def direct(domain_db, graph):
    with domain_db.transaction() as session:
        row = session.get(Trainer, graph["trainer_id"])
        row.approve_availability = False
        session.flush()
        return row.version


def windows(session, graph):
    return command.snapshot(
        session.scalars(
            select(TrainerAvailability).where(TrainerAvailability.trainer_id == graph["trainer_id"])
        ).all()
    )


@pytest.mark.parametrize("supervised", [True, False])
@pytest.mark.parametrize("empty", [True, False])
def test_save_respects_current_controls_and_preserves_every_booking(
    trainer_api, domain_db, graph, supervised, empty
):
    version = 1 if supervised else direct(domain_db, graph)
    with domain_db.transaction() as session:
        before = windows(session, graph)
        bookings = [
            (row.id, row.version, row.training_date, row.starts_at)
            for row in session.scalars(select(TrainingSession).order_by(TrainingSession.id))
        ]
    response = save(trainer_api, graph, version, [] if empty else SLOTS)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["outcome"] == ("requested" if supervised else "applied")
    assert result["trainer"] == {
        "id": str(graph["trainer_id"]),
        "version": version + (not supervised),
    }
    assert bool(result["requestId"]) == supervised
    with domain_db.transaction() as session:
        assert windows(session, graph) == (before if supervised else [] if empty else SLOTS)
        assert bookings == [
            (row.id, row.version, row.training_date, row.starts_at)
            for row in session.scalars(select(TrainingSession).order_by(TrainingSession.id))
        ]
        assert session.scalar(select(func.count()).select_from(Message)) == (2 if supervised else 1)
        assert session.scalar(select(func.count()).select_from(MessageReceipt)) == 2
        assert session.scalar(select(func.count()).select_from(ChangeRequest)) == int(supervised)
    inbox = trainer_api.get("/api/messages").json()
    assert len(inbox) == 1 and inbox[0]["read"] is False
    if supervised:
        assert inbox[0]["request"]["status"] == "pending"
        assert any(slot["side"] == "old" for slot in inbox[0]["request"]["slots"])
        proposed = [slot for slot in inbox[0]["request"]["slots"] if slot["side"] == "new"]
        assert len(proposed) == (0 if empty else 2)


def test_receipt_replay_survives_later_changes_without_reapplying(trainer_api, domain_db, graph):
    version = direct(domain_db, graph)
    key = uuid4()
    original = save(trainer_api, graph, version, key=key)
    assert original.status_code == 200, original.text
    assert save(trainer_api, graph, version + 1, []).status_code == 200
    assert save(trainer_api, graph, version, key=key).json() == original.json()
    assert trainer_api.get(f"/api/trainer-availability-saves/{key}").json() == original.json()
    assert save(trainer_api, graph, version, [], key).status_code == 409
    with domain_db.transaction() as session:
        assert windows(session, graph) == []
        assert session.scalar(select(func.count()).select_from(Message)) == 2


def test_identical_pending_proposal_with_new_key_reuses_history_and_notices(
    trainer_api, domain_db, graph
):
    first = save(trainer_api, graph)
    assert first.status_code == 200, first.text
    assert save(trainer_api, graph).json() == first.json()
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(RequestEvent)) == 1
        assert session.scalar(select(func.count()).select_from(Message)) == 2
        assert session.scalar(select(func.count()).select_from(TrainerAvailabilityReceipt)) == 2


def test_owner_and_foreign_target_cannot_change_availability(api, domain_db, graph):
    assert save(api, graph).status_code == 403
    assert api.get(f"/api/trainer-availability-saves/{uuid4()}").status_code == 403
    with pytest.raises(AuthError) as failure, domain_db.transaction() as session:
        command.save(
            session,
            actor(graph),
            uuid4(),
            uuid4(),
            command.SaveAvailability(expectedVersion=1, slots=SLOTS),
        )
    assert failure.value.status == 404


@pytest.mark.parametrize(
    "patch",
    [
        {"slots": [{"weekday": True, "startsAt": "09:00", "endsAt": "10:00"}]},
        {"slots": [{"weekday": 7, "startsAt": "09:00", "endsAt": "10:00"}]},
        {"slots": [{"weekday": 1, "startsAt": "09:00:30", "endsAt": "10:00"}]},
        {"slots": [{"weekday": 1, "startsAt": "11:00", "endsAt": "10:00"}]},
        {"slots": [SLOTS[0], SLOTS[0]]},
        {"slots": [SLOTS[0], {"weekday": 1, "startsAt": "09:30", "endsAt": "11:00"}]},
        {"expectedVersion": True},
        {"actorId": "forged"},
    ],
)
def test_invalid_or_overlapping_windows_never_write(trainer_api, domain_db, graph, patch):
    body = {"expectedVersion": 1, "slots": SLOTS, **patch}
    response = trainer_api.post(
        f"/api/trainers/{graph['trainer_id']}/availability",
        json=body,
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(TrainerAvailabilityReceipt)) == 0


def test_stale_and_unchanged_availability_are_rejected(trainer_api, domain_db, graph):
    assert save(trainer_api, graph, 2).status_code == 409
    with domain_db.transaction() as session:
        before = windows(session, graph)
    assert save(trainer_api, graph, slots=before).status_code == 422


def test_concurrent_identical_saves_create_one_request(domain_db, graph):
    key = uuid4()

    def write(_):
        with domain_db.transaction() as session:
            return command.save(
                session,
                actor(graph),
                graph["trainer_id"],
                key,
                command.SaveAvailability(expectedVersion=1, slots=SLOTS),
            ).model_dump(mode="json")

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(write, range(3)))
    assert results[0] == results[1] == results[2]
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ChangeRequest)) == 1
        assert session.scalar(select(func.count()).select_from(Message)) == 2


def test_notice_failure_rolls_back_direct_availability_change(domain_db, graph, monkeypatch):
    version = direct(domain_db, graph)
    with domain_db.transaction() as session:
        before = windows(session, graph)

    def fail(*args):
        raise RuntimeError("notice failed")

    monkeypatch.setattr(command, "notify", fail)
    with pytest.raises(RuntimeError), domain_db.transaction() as session:
        command.save(
            session,
            actor(graph),
            graph["trainer_id"],
            uuid4(),
            command.SaveAvailability(expectedVersion=version, slots=SLOTS),
        )
    with domain_db.transaction() as session:
        assert windows(session, graph) == before
        assert session.get(Trainer, graph["trainer_id"]).version == version
        assert session.scalar(select(func.count()).select_from(TrainerAvailabilityReceipt)) == 0


def test_receipts_are_immutable_and_cannot_be_downgraded(domain_db, graph, migrate):
    with domain_db.transaction() as session:
        command.save(
            session,
            actor(graph),
            graph["trainer_id"],
            uuid4(),
            command.SaveAvailability(expectedVersion=1, slots=SLOTS),
        )
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.execute(text("DELETE FROM trainer_availability_receipts"))
    with pytest.raises(DBAPIError, match="Trainer availability downgrade refused"):
        migrate("downgrade", "20261013_0024")


def test_inactive_trainer_cannot_save_with_an_old_session(trainer_api, domain_db, graph):
    with domain_db.transaction() as session:
        session.get(StaffUser, graph["user_id"]).status = "inactive"
    assert save(trainer_api, graph).status_code == 401
