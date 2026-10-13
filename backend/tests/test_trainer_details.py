"""Profile saves preserve account/security boundaries and exact optional contacts."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.api import trainer_details as commands
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.api import TrainerDetailReceipt
from app.models.people import StaffUser, Trainer
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def save(api, graph, patch=None, version=1, key=None):
    return api.post(
        f"/api/trainers/{graph['trainer_id']}/personal-details",
        json={
            "expectedVersion": version,
            "patch": patch
            if patch is not None
            else {
                "name": "Renamed Trainer",
                "phone": {"countryCode": "+60", "number": ""},
                "birthday": None,
                "gender": "Other",
                "trainerType": "Custom Coaching",
                "qualifications": "Updated credentials",
                "publicProfile": "Hidden",
            },
        },
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_profile_save_syncs_name_and_clears_optional_contacts_without_email_or_rates(
    api, domain_db, graph, migrate
):
    before = api.get("/api/directory").json()
    key = uuid4()
    response = save(api, graph, key=key)
    assert response.status_code == 200, response.text
    assert response.json() == {"id": str(graph["trainer_id"]), "version": 2}
    assert save(api, graph, key=key).json() == response.json()
    assert api.get(f"/api/trainer-detail-saves/{key}").json() == response.json()
    assert save(api, graph).status_code == 409
    after = api.get("/api/directory").json()
    expected_clients = deepcopy(before["clients"])
    for client in expected_clients:
        for purchase in client["purchases"]:
            if purchase["trainer_id"] == str(graph["trainer_id"]):
                purchase["trainer_name"] = "Renamed Trainer"
    assert after["clients"] == expected_clients and after["packages"] == before["packages"]
    original = next(t for t in before["trainers"] if t["id"] == str(graph["trainer_id"]))
    current = next(t for t in after["trainers"] if t["id"] == str(graph["trainer_id"]))
    assert current == {
        **original,
        "version": 2,
        "name": "Renamed Trainer",
        "birthday": None,
        "phone_country_code": "+60",
        "phone_number": "",
        "gender": "Other",
        "trainer_type": "Custom Coaching",
        "qualifications": "Updated credentials",
        "public_profile": False,
    }
    with domain_db.transaction() as session:
        user = session.get(StaffUser, graph["user_id"])
        assert user.name == "Renamed Trainer" and user.email == original["email"]
        evidence = session.scalar(select(TrainerDetailReceipt))
        assert set(evidence.result) == {"id", "version"}
    with pytest.raises(DBAPIError, match="Trainer details downgrade refused"):
        migrate("downgrade", "20261013_0013")


@pytest.mark.parametrize(
    "patch",
    [
        {},
        {"name": " "},
        {"name": None},
        {"email": "unverified@example.test"},
        {"rates": {"peak": 1}},
        {"role": "owner"},
        {"status": "inactive"},
        {"birthday": "2026-02-31"},
        {"birthday": 0},
        {"phone": {"countryCode": "+65", "number": "bad"}},
        {"phone": None},
        {"publicProfile": True},
        {"gender": ""},
        {"trainerType": ""},
    ],
)
def test_invalid_or_protected_fields_cannot_mutate(api, graph, patch):
    assert save(api, graph, patch).status_code == 422


def test_trainer_can_edit_only_own_non_name_fields(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    key = uuid4()
    assert save(api, graph, {"qualifications": "Owner-edited"}, key=key).status_code == 200
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get(f"/api/trainer-detail-saves/{key}").status_code == 404
    assert save(api, graph, {"name": "Forged"}, version=2).status_code == 403
    response = save(api, graph, {"qualifications": "Trainer-edited"}, version=2)
    assert response.status_code == 200, response.text
    with domain_db.transaction() as session:
        principal = Principal(graph["user_id"], "Trainer", "trainer", uuid4())
        with pytest.raises(AuthError) as denied:
            commands.save(
                session,
                principal,
                graph["trainer_id"],
                uuid4(),
                commands.SaveTrainerDetails(expectedVersion=3, patch={"qualifications": "Other"}),
            )
        assert denied.value.status == 403


def test_admin_can_update_profile_but_response_and_receipt_never_include_rates(
    api, invitations, domain_db, graph, auth_service, auth_settings, fake_cognito
):
    identity = create_admin(api).json()["id"]
    login_admin(api, auth_service, auth_settings, fake_cognito, identity)
    key = uuid4()
    response = save(api, graph, {"name": "Admin-edited"}, key=key)
    assert response.status_code == 200, response.text
    assert response.json() == {"id": str(graph["trainer_id"]), "version": 2}
    assert api.get(f"/api/trainer-detail-saves/{key}").json() == response.json()
    assert not any(
        value in api.get("/api/directory").text for value in ["peak_rate", "off_peak_rate"]
    )
    with domain_db.transaction() as session:
        evidence = session.scalar(select(TrainerDetailReceipt))
        assert str(evidence.actor_id) == identity
        assert evidence.result == response.json()


def test_concurrent_idempotent_profile_retry_records_one_save(domain_db, graph, api):
    key = uuid4()
    principal = Principal(graph["owner_id"], "Owner", "owner", None)
    body = commands.SaveTrainerDetails(expectedVersion=1, patch={"qualifications": "Once"})

    def submit(_):
        with domain_db.transaction() as session:
            return commands.save(session, principal, graph["trainer_id"], key, body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert results[0] == results[1]
    with domain_db.transaction() as session:
        assert len(session.scalars(select(TrainerDetailReceipt)).all()) == 1
        assert session.get(Trainer, graph["trainer_id"]).version == 2
    with pytest.raises(DBAPIError, match="immutable"), domain_db.transaction() as session:
        session.delete(session.scalar(select(TrainerDetailReceipt)))


def test_manager_can_edit_inactive_target_without_reactivating_it(api, domain_db, graph):
    with domain_db.transaction() as session:
        trainer = session.get(Trainer, graph["trainer_id"])
        trainer.status = "inactive"
    assert (
        save(api, graph, {"qualifications": "Retained credentials"}, version=2).status_code == 200
    )
    with domain_db.transaction() as session:
        assert session.get(Trainer, graph["trainer_id"]).status == "inactive"
