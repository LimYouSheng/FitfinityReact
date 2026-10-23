"""Verify atomic request decisions through real HTTP and PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import time
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.api import request_cancellation
from app.api import request_resolution as command
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.api import RequestResolutionReceipt
from app.models.communications import (
    ChangeRequest,
    Message,
    MessageReceipt,
    RequestEvent,
    RequestSlot,
)
from app.models.people import StaffUser, Trainer, TrainerAvailability
from app.models.training import PackagePurchase, PurchaseScheduleSlot, TrainingSession
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_open_sessions import make_open
from tests.test_session_postponement_api import future as future
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database
KINDS = [
    "trainer_availability",
    "fixed_weekly_schedule",
    "session_time",
    "session_trainer",
    "session_postpone",
]


def seed(db, graph, kind, replacement=None):
    with db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        trainer = session.get(Trainer, graph["trainer_id"])
        purchase = session.get(PackagePurchase, graph["purchase_id"])
        fields = (
            {}
            if kind == "trainer_availability"
            else {"client_id": graph["client_id"], "purchase_id": purchase.id}
        )
        if kind.startswith("session_"):
            fields["session_id"] = booking.id
        if kind in {"session_time", "session_postpone"}:
            fields.update(
                old_date=booking.training_date, old_start=booking.starts_at, old_end=booking.ends_at
            )
        if kind == "session_time":
            fields.update(new_date=booking.training_date, new_start=time(12), new_end=time(13))
        if kind == "session_trainer":
            fields["replacement_trainer_id"] = replacement
        version = (
            trainer.version
            if kind == "trainer_availability"
            else purchase.version
            if kind == "fixed_weekly_schedule"
            else booking.version
        )
        row = ChangeRequest(
            kind=kind,
            trainer_id=trainer.id,
            expected_version=version,
            actor_id=graph["user_id"],
            actor_name="Trainer",
            **fields,
        )
        session.add(row)
        session.flush()
        session.add(
            RequestEvent(
                request_id=row.id,
                sequence=1,
                status="pending",
                actor_id=graph["user_id"],
                actor_name="Trainer",
            )
        )
        if kind == "trainer_availability":
            session.add(
                RequestSlot(
                    request_id=row.id,
                    side="new",
                    slot_identity=uuid4(),
                    weekday=1,
                    starts_at=time(9),
                    ends_at=time(10),
                )
            )
        if kind == "fixed_weekly_schedule":
            for slot in session.scalars(
                select(PurchaseScheduleSlot).where(PurchaseScheduleSlot.purchase_id == purchase.id)
            ):
                for side, start, end in [
                    ("old", slot.starts_at, slot.ends_at),
                    ("new", time(12), time(13)),
                ]:
                    session.add(
                        RequestSlot(
                            request_id=row.id,
                            side=side,
                            slot_identity=slot.id,
                            weekday=slot.weekday,
                            starts_at=start,
                            ends_at=end,
                        )
                    )
        return row.id


def resolve(api, identity, decision="approved", version=1, key=None):
    return api.post(
        f"/api/requests/{identity}/resolve",
        json={"expectedVersion": version, "decision": decision},
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def bookings(db):
    with db.transaction() as session:
        return [
            (
                row.id,
                row.version,
                row.schedule_state,
                row.training_date,
                row.starts_at,
                row.ends_at,
                row.trainer_id,
                row.session_number,
            )
            for row in session.scalars(select(TrainingSession).order_by(TrainingSession.id))
        ]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_decision_is_atomic_idempotent_and_applies_only_approved_intent(
    api, domain_db, graph, future, replacement, kind, decision
):
    identity = seed(domain_db, graph, kind, replacement)
    before, key = bookings(domain_db), uuid4()
    result = resolve(api, identity, decision, key=key)
    assert result.status_code == 200, result.text
    saved = result.json()
    assert saved["id"] == str(identity) and saved["status"] == decision and saved["version"] == 2
    assert saved["by"]["id"] == str(graph["owner_id"])
    assert resolve(api, identity, decision, key=key).json() == saved
    assert api.get(f"/api/request-resolutions/{key}").json() == saved
    assert (
        resolve(
            api, identity, "rejected" if decision == "approved" else "approved", key=key
        ).status_code
        == 409
    )
    assert resolve(api, identity, decision).status_code == 409
    with domain_db.transaction() as session:
        assert session.get(ChangeRequest, identity).status == decision
        assert (
            session.scalar(
                select(func.count())
                .select_from(RequestEvent)
                .where(RequestEvent.request_id == identity)
            )
            == 2
        )
        assert session.scalar(select(func.count()).select_from(RequestResolutionReceipt)) == 1
        assert (
            session.scalar(
                select(func.count()).select_from(Message).where(Message.kind == "request_decision")
            )
            == 1
        )
        booking = session.get(TrainingSession, graph["session_id"])
        purchase = session.get(PackagePurchase, graph["purchase_id"])
        assert purchase.total_sessions == 2 and purchase.end_date == graph["end_date"]
        if decision == "approved":
            if kind == "session_postpone":
                assert booking.schedule_state == "open" and booking.training_date is None
            if kind == "session_time":
                assert booking.starts_at == time(12) and booking.ends_at == time(13)
            if kind == "session_trainer":
                assert booking.trainer_id == replacement
            if kind == "fixed_weekly_schedule":
                assert all(
                    row.starts_at == time(12) for row in session.scalars(select(TrainingSession))
                )
            if kind == "trainer_availability":
                assert session.scalar(
                    select(TrainerAvailability).where(
                        TrainerAvailability.trainer_id == graph["trainer_id"]
                    )
                ).starts_at == time(9)
    if decision == "rejected" or kind == "trainer_availability":
        assert bookings(domain_db) == before


@pytest.mark.parametrize("kind", KINDS)
def test_stale_approval_is_rejected_but_rejection_can_retire_the_proposal(
    api, domain_db, graph, future, replacement, kind
):
    identity = seed(domain_db, graph, kind, replacement)
    with domain_db.transaction() as session:
        model, target = (
            (Trainer, graph["trainer_id"])
            if kind == "trainer_availability"
            else (PackagePurchase, graph["purchase_id"])
            if kind == "fixed_weekly_schedule"
            else (TrainingSession, graph["session_id"])
        )
        session.get(model, target).version += 1
    before = bookings(domain_db)
    assert resolve(api, identity).status_code == 409
    assert resolve(api, identity, "rejected").status_code == 200
    assert bookings(domain_db) == before


@pytest.mark.parametrize("kind", KINDS)
def test_notice_failure_rolls_back_domain_decision_and_receipt(
    api, domain_db, graph, future, replacement, kind, monkeypatch
):
    identity = seed(domain_db, graph, kind, replacement)
    before = bookings(domain_db)
    monkeypatch.setattr(
        command, "notify", lambda *_: (_ for _ in ()).throw(RuntimeError("notice failure"))
    )
    assert resolve(api, identity).status_code == 500
    assert bookings(domain_db) == before
    with domain_db.transaction() as session:
        assert session.get(ChangeRequest, identity).status == "pending"
        assert session.scalar(select(func.count()).select_from(RequestResolutionReceipt)) == 0
        assert session.scalar(select(func.count()).select_from(RequestEvent)) == 1
        if kind == "trainer_availability":
            assert (
                session.scalar(
                    select(TrainerAvailability).where(
                        TrainerAvailability.trainer_id == graph["trainer_id"]
                    )
                )
                is None
            )


def test_trainer_cannot_decide_or_read_operations_receipts(
    api, domain_db, graph, future, auth_settings, auth_service, fake_cognito
):
    identity = seed(domain_db, graph, "session_postpone")
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert resolve(api, identity).status_code == 403
    assert resolve(api, identity, "rejected").status_code == 403
    assert api.get(f"/api/request-resolutions/{uuid4()}").status_code == 403


def test_admin_can_decide_but_cannot_read_owner_receipt(
    api, domain_db, graph, future, invitations, auth_service, auth_settings, fake_cognito
):
    identity = seed(domain_db, graph, "session_postpone")
    key = uuid4()
    assert resolve(api, identity, "rejected", key=key).status_code == 200
    admin = create_admin(api).json()["id"]
    login_admin(api, auth_service, auth_settings, fake_cognito, admin)
    assert api.get(f"/api/request-resolutions/{key}").status_code == 404
    next_id = seed(domain_db, graph, "session_postpone")
    assert resolve(api, next_id).status_code == 200


def test_open_session_trainer_approval_preserves_undated_state(api, domain_db, graph, replacement):
    with domain_db.transaction() as session:
        make_open(session, graph["session_id"])
    identity = seed(domain_db, graph, "session_trainer", replacement)
    result = resolve(api, identity)
    assert result.status_code == 200, result.text
    with domain_db.transaction() as session:
        row = session.get(TrainingSession, graph["session_id"])
        assert (
            row.trainer_id == replacement
            and row.schedule_state == "open"
            and row.training_date is None
        )
        decision = session.scalar(select(Message).where(Message.kind == "request_decision"))
        recipients = set(
            session.scalars(
                select(MessageReceipt.user_id).where(MessageReceipt.message_id == decision.id)
            )
        )
        assert recipients == {
            graph["owner_id"],
            graph["user_id"],
            session.get(Trainer, replacement).user_id,
        }


def test_missing_and_stale_decision_versions_do_not_write(api, domain_db, graph, future):
    assert resolve(api, uuid4()).status_code == 404
    identity = seed(domain_db, graph, "session_postpone")
    assert resolve(api, identity, version=2).status_code == 409
    assert resolve(api, identity, decision="cancelled").status_code == 422


def test_concurrent_duplicate_decision_has_one_effect(api, domain_db, graph, future):
    identity = seed(domain_db, graph, "session_postpone")
    key = uuid4()
    principal = Principal(graph["owner_id"], "Owner", "owner", None)

    def run(_):
        with domain_db.transaction() as session:
            return command.save(
                session,
                principal,
                identity,
                key,
                command.ResolveRequest(expectedVersion=1, decision="approved"),
            ).model_dump(mode="json")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert results[0] == results[1]
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(RequestResolutionReceipt)) == 1


def test_immutable_receipts_block_lossy_downgrade(api, domain_db, graph, future, migrate):
    identity = seed(domain_db, graph, "session_postpone")
    assert resolve(api, identity).status_code == 200
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.scalar(select(RequestResolutionReceipt)))
    with pytest.raises(DBAPIError, match="resolution downgrade refused"):
        migrate("downgrade", "20261023_0033")


@pytest.fixture
def replacement(domain_db, graph):
    with domain_db.transaction() as session:
        source = session.get(Trainer, graph["trainer_id"])
        row = Trainer(
            **{
                c.name: getattr(source, c.name)
                for c in Trainer.__table__.columns
                if c.name not in {"id", "user_id", "email", "created_at", "updated_at", "version"}
            }
        )
        user = StaffUser(
            name="Replacement Trainer", email="replacement-resolution@example.test", role="trainer"
        )
        session.add(user)
        session.flush()
        row.user_id = user.id
        row.email = user.email
        session.add(row)
        session.flush()
        for day in range(7):
            session.add(
                TrainerAvailability(
                    trainer_id=row.id, weekday=day, starts_at=time(9), ends_at=time(18)
                )
            )
        return row.id


def test_availability_decision_domain_transaction(domain_db, graph):
    identity = seed(domain_db, graph, "trainer_availability")
    with domain_db.transaction() as session:
        result = command.save(
            session,
            Principal(graph["owner_id"], "Owner", "owner", None),
            identity,
            uuid4(),
            command.ResolveRequest(expectedVersion=1, decision="approved"),
        )
        assert result.status == "approved"


@pytest.mark.parametrize("other", ["rejected", "cancelled"])
def test_competing_decision_or_cancellation_has_one_authoritative_winner(
    domain_db, graph, future, other
):
    identity = seed(domain_db, graph, "session_postpone")
    ready = Barrier(2)

    def run(decision):
        ready.wait(timeout=5)
        try:
            with domain_db.transaction() as session:
                if decision == "cancelled":
                    result = request_cancellation.save(
                        session,
                        Principal(graph["user_id"], "Trainer", "trainer", graph["trainer_id"]),
                        identity,
                        uuid4(),
                        request_cancellation.CancelRequest(expectedVersion=1),
                    )
                else:
                    result = command.save(
                        session,
                        Principal(graph["owner_id"], "Owner", "owner", None),
                        identity,
                        uuid4(),
                        command.ResolveRequest(expectedVersion=1, decision=decision),
                    )
                return result.status
        except AuthError as error:
            assert error.status == 409
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ["approved", other]))
    assert results.count("conflict") == 1
    winner = next(value for value in results if value != "conflict")
    with domain_db.transaction() as session:
        assert session.get(ChangeRequest, identity).status == winner
        assert session.scalar(select(func.count()).select_from(RequestEvent)) == 2
        assert session.get(TrainingSession, graph["session_id"]).schedule_state == (
            "open" if winner == "approved" else "booked"
        )


def test_http_owner_approval_and_trainer_cancellation_have_one_committed_winner(
    api, domain_db, graph, future, auth_settings, auth_service, fake_cognito, monkeypatch
):
    identity = seed(domain_db, graph, "session_postpone")
    trainer_api = TestClient(api.app, base_url="https://testserver")
    trainer_api.headers.update(api.headers)
    trainer_login(trainer_api, domain_db, graph, auth_settings, auth_service, fake_cognito)

    def provider_user(access):
        # The shared single-user provider fixture must support both signed identities
        # concurrently; signature, cookies, CSRF and local authority remain real.
        claims = auth_service.verifier.verify(access)
        return {
            "Username": claims["username"],
            "UserMFASettingList": ["SOFTWARE_TOKEN_MFA"],
            "UserAttributes": [
                {"Name": "sub", "Value": claims["sub"]},
                {"Name": "email_verified", "Value": "true"},
            ],
        }

    monkeypatch.setattr(fake_cognito, "user", provider_user)
    ready = Barrier(2)

    def run(decision):
        ready.wait(timeout=5)
        if decision == "approved":
            return resolve(api, identity)
        return trainer_api.post(
            f"/api/requests/{identity}/cancel",
            json={"expectedVersion": 1},
            headers={"Idempotency-Key": str(uuid4())},
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, ["approved", "cancelled"]))
        assert sorted(response.status_code for response in results) == [200, 409], [
            response.text for response in results
        ]
        winner = next(
            response.json()["status"] for response in results if response.status_code == 200
        )
        with domain_db.transaction() as session:
            assert session.get(ChangeRequest, identity).status == winner
            assert session.scalar(select(func.count()).select_from(RequestEvent)) == 2
            assert session.get(TrainingSession, graph["session_id"]).schedule_state == (
                "open" if winner == "approved" else "booked"
            )
    finally:
        trainer_api.close()
