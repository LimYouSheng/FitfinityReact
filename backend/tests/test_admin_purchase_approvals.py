"""Approved onboarding/purchases preserve wire aliases and immutable purchased evidence."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.models.people import Client
from app.models.training import PackagePurchase, TrainingSession
from tests.test_admin_api import invitations as invitations
from tests.test_admin_approvals import decision
from tests.test_admin_approvals import identities as identities
from tests.test_admin_domain_approvals import enable
from tests.test_client_creation import body as creation_body
from tests.test_client_matching import declared_hours
from tests.test_client_renewal_save import ready as ready
from tests.test_staff_api import api as api

pytestmark = [pytest.mark.database, pytest.mark.parametrize("graph", ["future"], indirect=True)]


def approve(api, identities, path, body, area, operation):
    use = enable(api, identities, area)
    key = uuid4()
    result = api.post(path, json=body, headers={"Idempotency-Key": str(key)})
    assert result.status_code == 202, result.text
    proposal = api.get("/api/admin-requests").json()[0]
    assert proposal["operation"] == operation
    use("owner")
    applied = decision(api, proposal)
    assert applied.status_code == 200, applied.text
    assert (
        proposal["body"]["body"]["clientPreferences"][0]["from"]
        == body["clientPreferences"][0]["from"]
    )
    assert (
        proposal["body"]["body"]["fixedWeeklySchedule"][0]["from"]
        == body["fixedWeeklySchedule"][0]["from"]
    )
    use("admin")
    return key


def test_owner_approved_onboarding_preserves_schedule_aliases_and_original_admin(
    api, graph, domain_db, identities
):
    declared_hours(domain_db, graph)
    body = creation_body(graph)
    key = approve(api, identities, "/api/clients", body, "clientCreation", "client.create")
    response = api.get(f"/api/client-creations/{key}")
    assert response.status_code == 200, response.text
    assert (
        api.post("/api/clients", json=body, headers={"Idempotency-Key": str(key)}).json()
        == response.json()
    )
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(Client)) == 2
        created = session.get(Client, UUID(response.json()["id"]))
        assert created.name == "New Client"
        bookings = list(
            session.scalars(select(TrainingSession).where(TrainingSession.client_id == created.id))
        )
        assert len(bookings) == 2
        assert all(row.starts_at.hour == 11 and row.ends_at.hour == 12 for row in bookings)
        assert session.get(PackagePurchase, graph["purchase_id"]).client_id == graph["client_id"]


def test_owner_approved_additional_purchase_preserves_independent_original_package(
    api, graph, domain_db, identities, ready
):
    path = f"/api/clients/{graph['client_id']}/packages"
    key = approve(api, identities, path, ready, "clientPackages", "client.purchase")
    response = api.get(f"/api/client-renewals/{key}")
    assert response.status_code == 200, response.text
    assert (
        api.post(path, json=ready, headers={"Idempotency-Key": str(key)}).json() == response.json()
    )
    with domain_db.transaction() as session:
        purchases = list(session.scalars(select(PackagePurchase)))
        assert len(purchases) == 2
        assert session.get(PackagePurchase, graph["purchase_id"]).start_date == graph["start_date"]
        original = session.get(TrainingSession, graph["session_id"])
        assert original.purchase_id == graph["purchase_id"] and original.starts_at.hour == 10
