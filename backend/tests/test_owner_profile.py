"""Owner contact persistence and verified same-identity email changes with fake Cognito."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.owner_profile import OwnerProfileReceipt
from app.models.people import StaffIdentity, StaffUser
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def details(record, **patch):
    return {
        "name": "Updated Owner",
        "email": record["email"],
        "phone_country_code": "+65",
        "phone_number": "91234567",
        "birthday": "1990-01-02",
        "gender": "Other",
        **patch,
    }


def test_owner_profile_persists_and_reconciles_without_duplicate_save(api, domain_db):
    initial = api.get("/api/owner-profile").json()
    key = str(uuid4())
    body = {"expectedVersion": initial["version"], "details": details(initial)}
    saved = api.post("/api/owner-profile", json=body, headers={"Idempotency-Key": key})
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == initial["version"] + 1
    assert api.get("/api/owner-profile").json() == saved.json()
    assert (
        api.post("/api/owner-profile", json=body, headers={"Idempotency-Key": key}).json()
        == saved.json()
    )
    assert api.get(f"/api/owner-profile/saves/{key}").json() == saved.json()
    with domain_db.transaction() as session:
        assert len(session.scalars(select(OwnerProfileReceipt)).all()) == 1
    assert (
        api.post(
            "/api/owner-profile", json=body, headers={"Idempotency-Key": str(uuid4())}
        ).status_code
        == 409
    )


def test_profile_does_not_allow_unverified_email_or_foreign_role(
    api, domain_db, graph, auth_service, auth_settings, fake_cognito
):
    initial = api.get("/api/owner-profile").json()
    body = {
        "expectedVersion": initial["version"],
        "details": details(initial, email="other@example.test"),
    }
    assert (
        api.post(
            "/api/owner-profile", json=body, headers={"Idempotency-Key": str(uuid4())}
        ).status_code
        == 409
    )
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get("/api/owner-profile").status_code == 403
    assert (
        api.post(
            "/api/owner-profile", json=body, headers={"Idempotency-Key": str(uuid4())}
        ).status_code
        == 403
    )


def test_owner_email_requires_code_and_keeps_identity(
    api, domain_db, graph, fake_cognito, monkeypatch
):
    initial = api.get("/api/owner-profile").json()
    address = "new-owner@example.test"
    with domain_db.transaction() as session:
        identity = session.scalar(
            select(StaffIdentity).where(StaffIdentity.user_id == graph["owner_id"])
        )
        original_identity = (identity.id, identity.subject, identity.provider_username)
    requested = api.post(
        "/api/owner-profile/email-change",
        json={"email": address, "expectedVersion": initial["version"]},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert requested.status_code == 200, requested.text
    change = requested.json()["id"]
    with domain_db.transaction() as session:
        assert session.get(StaffUser, graph["owner_id"]).email == initial["email"]
    fake_cognito.user_changes["UserAttributes"] = [
        {"Name": "sub", "Value": original_identity[1]},
        {"Name": "email_verified", "Value": "true"},
        {"Name": "email", "Value": initial["email"]},
    ]
    sent = []
    monkeypatch.setattr(
        fake_cognito,
        "request_email_change",
        lambda access, email: sent.append(email),
        raising=False,
    )

    def verify(access, code):
        from app.auth.errors import AuthError

        if code != "123456":
            raise AuthError("INVALID_CODE", "Invalid code", 400)
        fake_cognito.user_changes["UserAttributes"] = [
            {"Name": "sub", "Value": original_identity[1]},
            {"Name": "email_verified", "Value": "true"},
            {"Name": "email", "Value": address},
        ]

    monkeypatch.setattr(fake_cognito, "verify_email_change", verify, raising=False)
    assert api.post(f"/auth/email-change/{change}/send", json={}).status_code == 200
    assert sent == [address]
    assert (
        api.post(f"/auth/email-change/{change}/verify", json={"code": "000000"}).status_code == 400
    )
    with domain_db.transaction() as session:
        assert session.get(StaffUser, graph["owner_id"]).email == initial["email"]
    response = api.post(f"/auth/email-change/{change}/verify", json={"code": "123456"})
    assert response.status_code == 200, response.text
    assert response.json()["signedOut"]
    with domain_db.transaction() as session:
        assert session.get(StaffUser, graph["owner_id"]).email == address
        identity = session.get(StaffIdentity, original_identity[0])
        assert (identity.subject, identity.provider_username) == original_identity[1:]


def test_owner_profile_blocks_populated_downgrade(api, migrate):
    from sqlalchemy.exc import DBAPIError

    initial = api.get("/api/owner-profile").json()
    saved = api.post(
        "/api/owner-profile",
        json={"expectedVersion": initial["version"], "details": details(initial)},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert saved.status_code == 200, saved.text
    with pytest.raises(DBAPIError, match="populated owner profile downgrade refused"):
        migrate("downgrade", "20261101_0052")
    assert api.get("/api/owner-profile").json() == saved.json()
