"""Dismissal authority, immutable history and exact retry/no-op semantics."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.api import renewal_dismissal
from app.api.message_schemas import DismissRenewal
from app.authorization import Principal
from app.models.api import RenewalDismissal, RenewalDismissalReceipt
from app.models.communications import Message, MessageReceipt
from app.models.people import Client, LifecycleEvent, Trainer
from app.models.training import PackagePurchase
from app.persistence import add_purchase
from tests.domain_fixtures import purchase_parts
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def reminder(domain_db, graph):
    with domain_db.transaction() as session:
        row = Message(
            kind="renewal",
            title="Renewal follow-up",
            body="Two sessions remain",
            client_id=graph["client_id"],
            purchase_id=graph["purchase_id"],
            actor_id=graph["owner_id"],
            actor_name="Owner",
        )
        session.add(row)
        session.flush()
        for user in [graph["owner_id"], graph["user_id"]]:
            session.add(MessageReceipt(message_id=row.id, user_id=user))
        return row.id


def dismiss(api, identity, graph, key=None, version=None, **extra):
    return api.post(
        f"/api/messages/{identity}/dismiss-renewal",
        headers={"Idempotency-Key": str(key or uuid4())},
        json={"expectedClientVersion": version or graph["client_version"], **extra},
    )


def test_owner_removes_globally_preserving_message_personal_reads_and_purchase(
    api, domain_db, graph
):
    identity = reminder(domain_db, graph)
    with domain_db.transaction() as session:
        before = {
            c.name: getattr(session.get(PackagePurchase, graph["purchase_id"]), c.name)
            for c in PackagePurchase.__table__.columns
        }
    key = uuid4()
    result = dismiss(api, identity, graph, key)
    assert result.status_code == 200, result.text
    assert result.json()["renewalStatus"] == "removed"
    assert result.json()["renewalDismissal"]["by"]["id"] == str(graph["owner_id"])
    assert api.get(f"/api/renewal-dismissal-saves/{key}").json() == result.json()
    assert dismiss(api, identity, graph, key).json() == result.json()
    assert dismiss(api, identity, graph).json() == result.json()
    row = next(row for row in api.get("/api/messages").json() if row["id"] == str(identity))
    assert row["renewalStatus"] == "removed" and not row["read"] and row["version"] == 1
    assert row["renewalDismissal"] == result.json()["renewalDismissal"]
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(RenewalDismissal)) == 1
        assert session.scalar(select(func.count()).select_from(RenewalDismissalReceipt)) == 2
        assert {
            c.name: getattr(session.get(PackagePurchase, graph["purchase_id"]), c.name)
            for c in PackagePurchase.__table__.columns
        } == before


def test_admin_can_remove_nonfinancial_owner_reminder(
    api, invitations, domain_db, graph, auth_service, auth_settings, fake_cognito
):
    identity = reminder(domain_db, graph)
    admin = create_admin(api).json()["id"]
    login_admin(api, auth_service, auth_settings, fake_cognito, admin)
    result = dismiss(api, identity, graph)
    assert result.status_code == 200, result.text
    assert result.json()["renewalDismissal"]["by"]["id"] == admin


def test_current_trainer_can_remove_but_historical_recipient_cannot(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    identity = reminder(domain_db, graph)
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    key = uuid4()
    assert dismiss(api, identity, graph, key).status_code == 200
    with domain_db.transaction() as session:
        client = session.get(Client, graph["client_id"])
        source = session.get(Trainer, graph["trainer_id"])
        other = Trainer(
            **{
                c.name: getattr(source, c.name)
                for c in Trainer.__table__.columns
                if c.name not in {"id", "user_id", "email", "created_at", "updated_at", "version"}
            }
        )
        other.email = "other@example.test"
        session.add(other)
        session.flush()
        client.trainer_id = other.id
        client.version += 1
    assert any(row["id"] == str(identity) for row in api.get("/api/messages").json())
    assert dismiss(api, identity, graph, key).status_code == 404
    assert api.get(f"/api/renewal-dismissal-saves/{key}").status_code == 404


def test_renewed_noop_receipt_never_becomes_a_new_dismissal_on_replay(api, domain_db, graph):
    identity = reminder(domain_db, graph)
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
        session.flush()
        next_id = purchase.id
        version = session.get(Client, graph["client_id"]).version
    key = uuid4()
    saved = dismiss(api, identity, graph, key, version)
    assert saved.json() == {
        "id": str(identity),
        "renewalStatus": "renewed",
        "renewalDismissal": None,
    }
    with domain_db.transaction() as session:
        purchase = session.get(PackagePurchase, next_id)
        event = LifecycleEvent(
            purchase_id=next_id,
            status="inactive",
            reason="owner",
            actor_id=graph["owner_id"],
            actor_name="Owner",
        )
        session.add(event)
        session.flush()
        purchase.lifecycle_event_id = event.id
        purchase.status = "inactive"
        purchase.version += 1
    assert dismiss(api, identity, graph, key, version).json() == saved.json()
    assert api.get(f"/api/renewal-dismissal-saves/{key}").json() == saved.json()
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(RenewalDismissal)) == 0
    assert dismiss(api, identity, graph, version=version).json()["renewalStatus"] == "removed"


def test_stale_review_and_changed_key_body_reject_before_new_effects(api, domain_db, graph):
    identity = reminder(domain_db, graph)
    assert dismiss(api, identity, graph, version=graph["client_version"] + 1).status_code == 409
    key = uuid4()
    assert dismiss(api, identity, graph, key).status_code == 200
    assert dismiss(api, identity, graph, key, graph["client_version"] + 1).status_code == 409
    assert dismiss(api, uuid4(), graph).status_code == 404
    assert api.get(f"/api/renewal-dismissal-saves/{uuid4()}").status_code == 404


def test_concurrent_different_actors_preserve_one_global_dismissal(domain_db, graph):
    identity = reminder(domain_db, graph)
    principals = [
        Principal(graph["owner_id"], "Owner", "owner", None),
        Principal(graph["user_id"], "Trainer", "trainer", graph["trainer_id"]),
    ]

    def command(principal):
        with domain_db.transaction() as session:
            return renewal_dismissal.save(
                session,
                principal,
                identity,
                uuid4(),
                DismissRenewal(expectedClientVersion=graph["client_version"]),
            ).model_dump(mode="json")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(command, principals))
    assert results[0] == results[1]
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(RenewalDismissal)) == 1
        assert session.scalar(select(func.count()).select_from(RenewalDismissalReceipt)) == 2


def test_rollback_immutable_dismissal_and_receipt_refuse_populated_downgrade(
    api, domain_db, graph, migrate
):
    identity = reminder(domain_db, graph)
    with pytest.raises(RuntimeError), domain_db.transaction() as session:
        renewal_dismissal.save(
            session,
            Principal(graph["owner_id"], "Owner", "owner", None),
            identity,
            uuid4(),
            DismissRenewal(expectedClientVersion=graph["client_version"]),
        )
        raise RuntimeError("rollback")
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(RenewalDismissal)) == 0
        assert session.scalar(select(func.count()).select_from(RenewalDismissalReceipt)) == 0
    assert dismiss(api, identity, graph).status_code == 200
    for model in [RenewalDismissal, RenewalDismissalReceipt]:
        with pytest.raises(DBAPIError), domain_db.transaction() as session:
            session.delete(session.scalar(select(model)))
    with pytest.raises(DBAPIError, match="populated attribution downgrade refused"):
        migrate("downgrade", "20261013_0018")


@pytest.mark.parametrize(
    "patch", [{"expectedClientVersion": True}, {"expectedClientVersion": -1}, {"actor": "Owner"}]
)
def test_strict_review_rejects_spoofed_authority(api, domain_db, graph, patch):
    identity = reminder(domain_db, graph)
    response = api.post(
        f"/api/messages/{identity}/dismiss-renewal",
        headers={"Idempotency-Key": str(uuid4())},
        json={"expectedClientVersion": graph["client_version"], **patch},
    )
    assert response.status_code == 422


def test_nonrenewal_and_nonrecipient_receipt_are_inaccessible(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    from tests.test_message_api import notice

    with domain_db.transaction() as session:
        identity = notice(session, graph)
    assert dismiss(api, identity, graph).status_code == 404
    identity = reminder(domain_db, graph)
    key = uuid4()
    assert dismiss(api, identity, graph, key).status_code == 200
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get(f"/api/renewal-dismissal-saves/{key}").status_code == 404
