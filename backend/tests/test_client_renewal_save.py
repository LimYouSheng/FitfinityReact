"""Renewal is one reviewed, idempotent purchase aggregate, never a current-package rewrite."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.api import client_renewal_save
from app.api.client_matching import DAYS
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.api import ClientRenewalReceipt
from app.models.communications import Message, MessageReceipt
from app.models.people import Client, ClientPerson, Trainer, TrainerAvailability
from app.models.training import (
    PackagePurchase,
    PackageTemplate,
    PurchasePreference,
    PurchaseScheduleSlot,
    TrainingSession,
)
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_client_deactivation_api import row_values
from tests.test_client_renewal_review import another_trainer, body, read
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


@pytest.fixture
def ready(api, domain_db, graph):
    viewed = read(api, graph)
    payload = body(graph, viewed)
    day = date.fromisoformat(payload["startDate"]).weekday()
    with domain_db.transaction() as session:
        session.add(
            TrainerAvailability(
                trainer_id=graph["trainer_id"], weekday=day, starts_at=time(9), ends_at=time(18)
            )
        )
    return {
        **payload,
        "trainerId": str(graph["trainer_id"]),
        "trainerVersion": 1,
        "fixedWeeklySchedule": [{"day": DAYS[day], "from": "10:00", "to": "11:00"}],
    }


def save(api, graph, payload, key=None):
    return api.post(
        f"/api/clients/{graph['client_id']}/packages",
        json=payload,
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def counts(domain_db):
    with domain_db.transaction() as session:
        return {
            model.__tablename__: session.scalar(select(func.count()).select_from(model))
            for model in [
                PackagePurchase,
                TrainingSession,
                Message,
                MessageReceipt,
                ClientRenewalReceipt,
            ]
        }


def test_atomic_future_purchase_preserves_current_people_sessions_and_settings(
    api, domain_db, graph, ready
):
    with domain_db.transaction() as session:
        client_before = row_values(session.get(Client, graph["client_id"]))
        current_before = row_values(session.get(PackagePurchase, graph["purchase_id"]))
        sessions_before = [
            row_values(s)
            for s in session.scalars(select(TrainingSession).order_by(TrainingSession.id))
        ]
        people_before = [
            row_values(p) for p in session.scalars(select(ClientPerson).order_by(ClientPerson.id))
        ]
        other = another_trainer(session)
        ready["trainerId"] = str(other.id)
        session.add(
            TrainerAvailability(
                trainer_id=other.id,
                weekday=date.fromisoformat(ready["startDate"]).weekday(),
                starts_at=time(9),
                ends_at=time(18),
            )
        )
    response = save(api, graph, ready)
    assert response.status_code == 200, response.text
    result = response.json()
    assert (
        result["id"] == str(graph["client_id"])
        and result["version"] == client_before["version"] + 1
    )
    with domain_db.transaction() as session:
        client = session.get(Client, graph["client_id"])
        assert {
            k: v for k, v in row_values(client).items() if k not in {"version", "updated_at"}
        } == {k: v for k, v in client_before.items() if k not in {"version", "updated_at"}}
        assert row_values(session.get(PackagePurchase, graph["purchase_id"])) == current_before
        assert [
            row_values(s)
            for s in session.scalars(
                select(TrainingSession)
                .where(TrainingSession.purchase_id == graph["purchase_id"])
                .order_by(TrainingSession.id)
            )
        ] == sessions_before
        assert [
            row_values(p) for p in session.scalars(select(ClientPerson).order_by(ClientPerson.id))
        ] == people_before
        purchase = session.get(PackagePurchase, UUID(result["purchaseId"]))
        assert (
            purchase.stage == "queued"
            and purchase.status == "active"
            and purchase.activated_at is None
        )
        assert str(purchase.trainer_id) == ready["trainerId"]
        assert purchase.template_revision == 1 and purchase.name == "Two sessions"
        assert (
            len(
                session.scalars(
                    select(TrainingSession).where(TrainingSession.purchase_id == purchase.id)
                ).all()
            )
            == 2
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(PurchasePreference)
                .where(PurchasePreference.purchase_id == purchase.id)
            )
            == 1
        )
        notice = session.scalar(select(Message).where(Message.title.like("Package added:%")))
        assert notice.trainer_id == graph["trainer_id"]
        assert set(
            session.scalars(
                select(MessageReceipt.user_id).where(MessageReceipt.message_id == notice.id)
            )
        ) == {graph["owner_id"], graph["user_id"]}
    directory = api.get("/api/directory").json()
    client = next(c for c in directory["clients"] if c["id"] == result["id"])
    assert (
        next(p for p in client["purchases"] if p["id"] == result["purchaseId"])["stage"] == "queued"
    )
    assert next(p for p in client["purchases"] if p["stage"] == "current")["id"] == str(
        graph["purchase_id"]
    )


def test_replay_reconciliation_and_conflicting_reuse_preserve_original_result(
    api, domain_db, graph, ready
):
    key = uuid4()
    result = save(api, graph, ready, key)
    assert result.status_code == 200, result.text
    before = counts(domain_db)
    with domain_db.transaction() as session:
        session.get(Client, graph["client_id"]).remarks = "Later edit"
    assert save(api, graph, ready, key).json() == result.json()
    assert api.get(f"/api/client-renewals/{key}").json() == result.json()
    changed = {**ready, "genderPreference": "Female trainer preferred"}
    assert save(api, graph, changed, key).status_code == 409
    assert counts(domain_db) == before
    assert api.get(f"/api/client-renewals/{uuid4()}").status_code == 404


@pytest.mark.parametrize("target", ["client", "package", "trainer", "hours"])
def test_current_authority_and_reviewed_terms_rechecked_at_save(
    api, domain_db, graph, ready, target
):
    with domain_db.transaction() as session:
        if target == "hours":
            row = session.scalar(
                select(TrainerAvailability).where(
                    TrainerAvailability.trainer_id == graph["trainer_id"]
                )
            )
            row.starts_at, row.ends_at = time(12), time(18)
        else:
            model, key = {
                "client": (Client, "client_id"),
                "package": (PackageTemplate, "template_id"),
                "trainer": (Trainer, "trainer_id"),
            }[target]
            session.get(model, graph[key]).version += 1
    before = counts(domain_db)
    assert save(api, graph, ready).status_code == 409
    assert counts(domain_db) == before


def test_client_conflict_rechecked_even_when_chosen_trainer_is_free(api, domain_db, graph, ready):
    with domain_db.transaction() as session:
        other = another_trainer(session)
        ready["trainerId"] = str(other.id)
        day = date.fromisoformat(ready["startDate"])
        session.add(
            TrainerAvailability(
                trainer_id=other.id, weekday=day.weekday(), starts_at=time(9), ends_at=time(18)
            )
        )
        booking = session.get(TrainingSession, graph["session_id"])
        booking.training_date, booking.schedule_slot_id = day, None
    before = counts(domain_db)
    assert save(api, graph, ready).status_code == 409
    assert counts(domain_db) == before


def test_saved_subinterval_of_preference_is_accepted_without_widening(api, domain_db, graph, ready):
    ready["clientPreferences"][0].update({"from": "09:00", "to": "12:00"})
    result = save(api, graph, ready)
    assert result.status_code == 200, result.text
    with domain_db.transaction() as session:
        slot = session.scalar(
            select(PurchaseScheduleSlot).where(
                PurchaseScheduleSlot.purchase_id == UUID(result.json()["purchaseId"])
            )
        )
        assert slot.starts_at == time(10) and slot.ends_at == time(11)


@pytest.mark.parametrize(
    "patch",
    [
        {"startDate": "2000-01-01"},
        {"expected": "invalid"},
        {"trainerVersion": True},
        {"fixedWeeklySchedule": []},
        {"sessionsPerWeek": 2},
        {"actorId": str(uuid4())},
    ],
)
def test_invalid_or_untrusted_inputs_never_partially_write(api, domain_db, graph, ready, patch):
    before = counts(domain_db)
    assert save(api, graph, {**ready, **patch}).status_code == 422
    assert counts(domain_db) == before


def test_admin_can_save_and_other_actor_receipts_remain_private(
    api, domain_db, graph, ready, auth_service, auth_settings, fake_cognito, invitations
):
    key = uuid4()
    assert save(api, graph, ready, key).status_code == 200
    created = create_admin(api).json()
    login_admin(api, auth_service, auth_settings, fake_cognito, created["id"])
    assert api.get(f"/api/client-renewals/{key}").status_code == 404
    reviewed = read(api, graph)
    next_body = {
        **ready,
        "startDate": reviewed["minimumStartDate"],
        "expected": reviewed["expected"],
    }
    assert save(api, graph, next_body).status_code == 200
    api.headers.pop("X-CSRF-Token")
    assert save(api, graph, next_body).status_code == 403


def test_trainer_cannot_save_or_reconcile(
    api, domain_db, graph, ready, auth_settings, auth_service, fake_cognito
):
    key = uuid4()
    assert save(api, graph, ready, key).status_code == 200
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert save(api, graph, ready).status_code == 403
    assert api.get(f"/api/client-renewals/{key}").status_code == 403


def test_duplicate_concurrent_commands_create_one_purchase_and_notice(api, domain_db, graph, ready):
    principal = Principal(graph["owner_id"], "Owner Original", "owner", None)
    payload = client_renewal_save.RenewPackage.model_validate(ready)
    key = uuid4()

    def commit():
        with domain_db.transaction() as session:
            return client_renewal_save.save(
                session, principal, graph["client_id"], key, payload
            ).model_dump(mode="json")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: commit(), range(2)))
    assert results[0] == results[1]
    assert counts(domain_db) == {
        "package_purchases": 2,
        "training_sessions": 4,
        "messages": 1,
        "message_receipts": 2,
        "client_renewal_receipts": 1,
    }


def test_rollback_and_immutable_receipt_prevent_partial_or_lossy_changes(
    api, domain_db, graph, ready, monkeypatch, migrate
):
    before = counts(domain_db)
    key = uuid4()

    def reject(*args):
        raise AuthError("invalid_request", "Fixture rejects transaction.", 422)

    original = client_renewal_save.notify
    monkeypatch.setattr(client_renewal_save, "notify", reject)
    assert save(api, graph, ready, key).status_code == 422
    assert counts(domain_db) == before
    assert api.get(f"/api/client-renewals/{key}").status_code == 404
    monkeypatch.setattr(client_renewal_save, "notify", original)
    assert save(api, graph, ready, key).status_code == 200
    with pytest.raises(DBAPIError, match="immutable"):
        with domain_db.transaction() as session:
            session.execute(text("UPDATE client_renewal_receipts SET actor_name = 'Changed'"))
    with pytest.raises(DBAPIError, match="populated attribution downgrade refused"):
        migrate("downgrade", "20261013_0025")
