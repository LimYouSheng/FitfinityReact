"""Concurrent purchase coaching scope excludes future, inactive and expired relationships."""

from datetime import time, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.auth.errors import AuthError
from app.authorization import Principal, client_write
from app.models.people import Client
from app.persistence import add_client, add_purchase
from tests.domain_fixtures import person, purchase_parts
from tests.test_client_assignment_review import replacement as replacement
from tests.test_package_reactivation_review import freeze
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


@pytest.mark.parametrize("state", ["active", "future", "inactive", "expired"])
def test_concurrent_purchase_grants_only_current_coaching_scope(
    api,
    domain_db,
    graph,
    replacement,
    auth_settings,
    auth_service,
    fake_cognito,
    state,
):
    with domain_db.transaction() as session:
        client = session.get(Client, graph["client_id"])
        client.trainer_id = replacement
        session.flush()
        today = session.scalar(
            text("SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Singapore')::date")
        )
        start = today + timedelta(days=1 if state == "future" else -91 if state == "expired" else 0)
        purchased, slots, preferences, bookings = purchase_parts(graph, start)
        # Existing fixture books tomorrow at10:00. This purchase has a separate12:00 slot.
        slots[0].starts_at = slots[0].purchased_starts_at = time(12)
        slots[0].ends_at = slots[0].purchased_ends_at = time(13)
        for booking in bookings:
            booking.starts_at, booking.ends_at = time(12), time(13)
        add_purchase(
            session, purchased, slots, preferences, bookings, expected_client_version=client.version
        )
        if state == "inactive":
            freeze(session, graph, purchased)
        foreign = add_client(
            session,
            Client(name="Unrelated client", kind="individual", trainer_id=replacement),
            [person("Unrelated")],
        )
        foreign_id = foreign.id
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    response = api.get("/api/directory")
    assert response.status_code == 200, response.text
    visible = {row["id"] for row in response.json()["clients"]}
    assert visible == ({str(graph["client_id"])} if state == "active" else set())
    assert str(foreign_id) not in visible
    assert api.get("/api/assessment-forms").status_code == 403
    notes_path = f"/api/clients/{graph['client_id']}/notes"
    notes = api.get(notes_path)
    assert notes.status_code == (200 if state == "active" else 404)
    assert api.get(f"/api/clients/{foreign_id}/notes").status_code == 404
    principal = Principal(graph["user_id"], "Trainer", "trainer", graph["trainer_id"])
    if state == "active":
        saved = api.post(
            notes_path,
            json={
                "expectedVersion": notes.json()["version"],
                "patch": {"remarks": "Concurrent purchase coaching note"},
            },
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert saved.status_code == 200, saved.text
        assert api.get(notes_path).json()["remarks"] == "Concurrent purchase coaching note"
        with domain_db.transaction() as session:
            assert (
                client_write(session, principal, graph["client_id"], coaching=True).id
                == graph["client_id"]
            )
    else:
        with pytest.raises(AuthError) as denied, domain_db.transaction() as session:
            client_write(session, principal, graph["client_id"], coaching=True)
        assert denied.value.status == 404
