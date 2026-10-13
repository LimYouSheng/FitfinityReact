"""Personal notice visibility, financial exclusions and versioned read-state recovery."""

from concurrent.futures import ThreadPoolExecutor
from datetime import time
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.api import messages
from app.api.directory import bounded
from app.api.message_schemas import SaveMessageRead
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.api import MessageReadReceipt
from app.models.communications import (
    ChangeRequest,
    Message,
    MessageReceipt,
    RequestEvent,
    RequestSlot,
)
from app.models.people import Trainer
from app.persistence import add_purchase
from tests.domain_fixtures import purchase_parts
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_evidence_schema import approved
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def notice(session, graph, recipients=None, **fields):
    row = Message(
        kind="saved_edit",
        title="Saved notice",
        body="Stored message body",
        actor_id=graph["owner_id"],
        actor_name="Owner",
        **fields,
    )
    session.add(row)
    session.flush()
    for identity in recipients if recipients is not None else [graph["owner_id"]]:
        session.add(MessageReceipt(message_id=row.id, user_id=identity))
    return row.id


def mark(api, identity, read=True, version=1, key=None, **extra):
    return api.post(
        f"/api/messages/{identity}/read-state",
        json={"expectedVersion": version, "read": read, **extra},
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_read_unread_replay_keeps_original_receipt_without_reapplying(api, domain_db, graph):
    with domain_db.transaction() as session:
        identity = notice(session, graph, [graph["owner_id"], graph["user_id"]])
    original = api.get("/api/messages").json()[0]
    assert original["read"] is False and original["version"] == 1
    assert original["recipientUserId"] == str(graph["owner_id"])
    assert "readBy" not in original and "recipients" not in original
    key = uuid4()
    read = mark(api, identity, key=key)
    assert read.status_code == 200, read.text
    assert read.json()["read"] is True and read.json()["version"] == 2
    assert mark(api, identity, False, 2).json()["version"] == 3
    assert api.get(f"/api/message-read-saves/{key}").json() == read.json()
    assert mark(api, identity, key=key).json() == read.json()
    latest = api.get("/api/messages").json()[0]
    assert latest["version"] == 3 and latest["read"] is False and latest["readAt"] is None
    assert mark(api, identity).status_code == 409
    assert mark(api, identity, False, 1, key).status_code == 409
    with domain_db.transaction() as session:
        other = session.scalar(
            select(MessageReceipt).where(MessageReceipt.user_id == graph["user_id"])
        )
        assert other.version == 1 and other.read_at is None
        assert session.scalar(select(func.count()).select_from(MessageReadReceipt)) == 2


def test_trainer_only_sees_own_notices_and_cannot_read_another_actor_receipt(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    with domain_db.transaction() as session:
        owner_notice = notice(session, graph)
        trainer_notice = notice(session, graph, [graph["user_id"]])
    key = uuid4()
    assert mark(api, owner_notice, key=key).status_code == 200
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert [row["id"] for row in api.get("/api/messages").json()] == [str(trainer_notice)]
    assert mark(api, owner_notice).status_code == 404
    assert api.get(f"/api/message-read-saves/{key}").status_code == 404
    assert mark(api, trainer_notice).status_code == 200
    assert mark(api, trainer_notice, userId=str(graph["owner_id"])).status_code == 422


@pytest.mark.parametrize("financial", ["trainer_rates", "remuneration_pending", "linked_approval"])
def test_admin_owner_notice_visibility_excludes_financial_content_and_keeps_personal_reads(
    api, invitations, domain_db, graph, auth_service, auth_settings, fake_cognito, financial
):
    with domain_db.transaction() as session:
        generic = notice(session, graph)
    identity = create_admin(api).json()["id"]
    with domain_db.transaction() as session:
        approval_id = approved(session, graph)[0].id if financial == "linked_approval" else None
        row = Message(
            kind="saved_edit" if approval_id else financial,
            title="Financial secret",
            body="Rate amounts",
            remuneration_id=approval_id,
            actor_id=graph["owner_id"],
            actor_name="Owner",
        )
        session.add(row)
        session.flush()
        secret = row.id
        for recipient in [graph["owner_id"], UUID(identity)]:
            session.add(MessageReceipt(message_id=row.id, user_id=recipient))
    assert mark(api, generic).status_code == 200
    login_admin(api, auth_service, auth_settings, fake_cognito, identity)
    rows = api.get("/api/messages").json()
    assert str(secret) not in [row["id"] for row in rows]
    entry = next(row for row in rows if row["id"] == str(generic))
    assert entry["version"] == 0 and entry["read"] is False
    assert mark(api, generic, version=0).json()["version"] == 1
    assert mark(api, secret).status_code == 404
    with domain_db.transaction() as session:
        owner = session.scalar(
            select(MessageReceipt).where(
                MessageReceipt.message_id == generic, MessageReceipt.user_id == graph["owner_id"]
            )
        )
        assert owner.version == 2 and owner.read_at is not None


@pytest.mark.parametrize(
    "kind", ["trainer_availability", "fixed_weekly_schedule", "session_time", "session_trainer"]
)
def test_request_projections_keep_exact_old_new_proposal_and_current_status(
    api, domain_db, graph, kind
):
    with domain_db.transaction() as session:
        fields = (
            {}
            if kind == "trainer_availability"
            else {"client_id": graph["client_id"], "purchase_id": graph["purchase_id"]}
        )
        if kind == "session_time":
            fields.update(
                session_id=graph["session_id"],
                old_date=graph["start_date"],
                new_date=graph["start_date"],
                old_start=time(10),
                old_end=time(11),
                new_start=time(11),
                new_end=time(12),
            )
        if kind == "session_trainer":
            source = session.get(Trainer, graph["trainer_id"])
            replacement = Trainer(
                **{
                    c.name: getattr(source, c.name)
                    for c in Trainer.__table__.columns
                    if c.name
                    not in {"id", "user_id", "email", "created_at", "updated_at", "version"}
                }
            )
            replacement.email = "replacement@example.test"
            session.add(replacement)
            session.flush()
            fields.update(session_id=graph["session_id"], replacement_trainer_id=replacement.id)
        request = ChangeRequest(
            kind=kind,
            trainer_id=graph["trainer_id"],
            expected_version=1,
            actor_id=graph["user_id"],
            actor_name="Trainer",
            **fields,
        )
        session.add(request)
        session.flush()
        session.add(
            RequestEvent(
                request_id=request.id,
                sequence=1,
                status="pending",
                actor_id=graph["user_id"],
                actor_name="Trainer",
            )
        )
        if kind in {"trainer_availability", "fixed_weekly_schedule"}:
            slot_id = uuid4()
            for side, hour in [("old", 10), ("new", 11)]:
                session.add(
                    RequestSlot(
                        request_id=request.id,
                        side=side,
                        slot_identity=slot_id,
                        weekday=0,
                        starts_at=time(hour),
                        ends_at=time(hour + 1),
                    )
                )
        identity = notice(session, graph, request_id=request.id, trainer_id=graph["trainer_id"])
    row = next(row for row in api.get("/api/messages").json() if row["id"] == str(identity))
    assert row["request"]["kind"] == kind and row["request"]["status"] == "pending"
    if kind == "session_time":
        assert (
            row["request"]["old_start"] == "10:00:00" and row["request"]["new_start"] == "11:00:00"
        )
    elif kind == "session_trainer":
        assert row["request"]["replacement_trainer_id"] is not None
    else:
        slots = {slot["side"]: slot for slot in row["request"]["slots"]}
        assert slots["old"]["starts_at"] == "10:00:00" and slots["new"]["starts_at"] == "11:00:00"


def test_renewal_status_uses_later_active_purchases(api, domain_db, graph):
    with domain_db.transaction() as session:
        renewal = Message(
            kind="renewal",
            title="Renewal",
            body="Two sessions left",
            client_id=graph["client_id"],
            purchase_id=graph["purchase_id"],
            actor_id=graph["owner_id"],
            actor_name="Owner",
        )
        session.add(renewal)
        session.flush()
        identity = renewal.id
        session.add(MessageReceipt(message_id=identity, user_id=graph["owner_id"]))
    assert (
        next(row for row in api.get("/api/messages").json() if row["id"] == str(identity))[
            "renewalStatus"
        ]
        == "active"
    )
    with domain_db.transaction() as session:
        purchase, slots, preferences, bookings = purchase_parts(graph)
        add_purchase(
            session,
            purchase,
            slots,
            preferences,
            bookings,
            expected_client_version=graph["client_version"],
        )
    assert (
        next(row for row in api.get("/api/messages").json() if row["id"] == str(identity))[
            "renewalStatus"
        ]
        == "renewed"
    )


def test_concurrent_same_key_replays_once_and_stale_other_command_rejects(domain_db, graph):
    with domain_db.transaction() as session:
        identity = notice(session, graph)
    principal = Principal(graph["owner_id"], "Owner", "owner", None)
    key = uuid4()

    def command(request_key):
        try:
            with domain_db.transaction() as session:
                return messages.save(
                    session,
                    principal,
                    identity,
                    request_key,
                    SaveMessageRead(expectedVersion=1, read=True),
                ).model_dump(mode="json")
        except AuthError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(command, [key, key]))
    assert results[0] == results[1]
    assert command(uuid4()) == "state_conflict"
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(MessageReadReceipt)) == 1


def test_rollback_immutable_receipts_and_populated_downgrade(api, domain_db, graph, migrate):
    with domain_db.transaction() as session:
        identity = notice(session, graph)
    principal = Principal(graph["owner_id"], "Owner", "owner", None)
    with pytest.raises(RuntimeError), domain_db.transaction() as session:
        messages.save(
            session, principal, identity, uuid4(), SaveMessageRead(expectedVersion=1, read=True)
        )
        raise RuntimeError("Rollback")
    assert api.get("/api/messages").json()[0]["read"] is False
    assert mark(api, identity).status_code == 200
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.scalar(select(MessageReadReceipt)))
    with pytest.raises(DBAPIError, match="Message read downgrade refused"):
        migrate("downgrade", "20261013_0017")


@pytest.mark.parametrize(
    "patch",
    [{"expectedVersion": -1}, {"expectedVersion": True}, {"read": "true"}, {"actor": "Owner"}],
)
def test_strict_read_state_input_cannot_spoof_authority(api, domain_db, graph, patch):
    with domain_db.transaction() as session:
        identity = notice(session, graph)
    response = api.post(
        f"/api/messages/{identity}/read-state",
        json={"expectedVersion": 1, "read": True, **patch},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422
    assert api.get("/api/messages").json()[0]["read"] is False


def test_complete_collection_and_unknown_targets_fail_closed(api, domain_db, graph, monkeypatch):
    assert mark(api, uuid4()).status_code == 404
    assert api.get(f"/api/message-read-saves/{uuid4()}").status_code == 404
    with domain_db.transaction() as session:
        notice(session, graph)
        notice(session, graph)
    monkeypatch.setattr(
        messages,
        "bounded",
        lambda session, query, maximum=1: bounded(session, query, min(maximum, 1)),
    )
    assert api.get("/api/messages").status_code == 503
