"""Email approval reserves only the reviewed address; it never impersonates the Trainer."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.models.email_changes import StaffEmailChange
from app.models.people import StaffUser, Trainer
from tests.test_admin_api import invitations as invitations
from tests.test_admin_approvals import decision
from tests.test_admin_approvals import identities as identities
from tests.test_admin_domain_approvals import enable
from tests.test_email_changes import NEW_EMAIL, post, request_email
from tests.test_email_changes import email_flow as email_flow
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


@pytest.mark.parametrize("outcome", ["approved", "rejected", "stale"])
def test_email_request_waits_for_review_and_preserves_provider_verification(
    api, graph, domain_db, identities, email_flow, outcome
):
    use = enable(api, identities, "trainerDetails")
    key = uuid4()
    pending = request_email(api, graph, key=key)
    assert pending.status_code == 202, pending.text
    assert request_email(api, graph, key=key).json() == pending.json()
    assert request_email(api, graph, key=key, email="changed@example.test").status_code == 409
    assert api.get(f"/api/trainer-email-requests/{key}").status_code == 202
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(StaffEmailChange)) == 0
        assert session.get(Trainer, graph["trainer_id"]).email == email_flow["old"]
    proposal = api.get("/api/admin-requests").json()[0]
    assert proposal["operation"] == "trainer.email"
    assert proposal["body"]["body"]["email"] == NEW_EMAIL
    assert proposal["body"]["review"]["before"]["email"] == email_flow["old"]
    assert decision(api, proposal).status_code == 403
    use("owner")
    assert api.get(f"/api/trainer-email-requests/{key}").status_code == 404
    if outcome == "stale":
        with domain_db.transaction() as session:
            session.get(Trainer, graph["trainer_id"]).version += 1
    decision_key = uuid4()
    result = decision(
        api, proposal, "rejected" if outcome == "rejected" else "approved", decision_key
    )
    assert result.status_code == (409 if outcome == "stale" else 200), result.text
    if outcome != "stale":
        assert decision(api, proposal, outcome, decision_key).json() == result.json()
        assert api.get(f"/api/admin-requests/decisions/{decision_key}").json() == result.json()
    use("admin")
    recovered = api.get(f"/api/trainer-email-requests/{key}")
    assert recovered.status_code == {"approved": 200, "rejected": 409, "stale": 202}[outcome]
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(StaffEmailChange)) == int(
            outcome == "approved"
        )
        assert session.get(StaffUser, graph["user_id"]).email == email_flow["old"]
        assert session.get(Trainer, graph["trainer_id"]).email == email_flow["old"]
    assert email_flow["sent"] == email_flow["verified"] == 0
    if outcome == "approved":
        assert request_email(api, graph, key=key).json() == recovered.json()
        assert post(api, recovered.json(), "send").status_code == 404
        email_flow["login"]()
        assert post(api, recovered.json(), "send").status_code == 200
        assert post(api, recovered.json(), "verify", code="123456").status_code == 200
        with domain_db.transaction() as session:
            assert session.get(Trainer, graph["trainer_id"]).email == NEW_EMAIL
            assert session.get(StaffEmailChange, UUID(recovered.json()["id"])).actor_id == UUID(
                identities[0]
            )
        assert email_flow["sent"] == email_flow["verified"] == 1


def test_email_correction_approval_rechecks_current_runtime_cutover(
    api, graph, domain_db, identities, email_flow, auth_settings
):
    use = identities[1]
    use("owner")
    old = request_email(api, graph).json()
    auth_settings.staff_email_corrections_enabled = True
    use = enable(api, identities, "trainerDetails")
    key = uuid4()
    pending = api.post(
        f"/api/trainers/{graph['trainer_id']}/email-change",
        json={"expectedVersion": 1, "email": "corrected@example.test", "supersedes": old["id"]},
        headers={"Idempotency-Key": str(key)},
    )
    assert pending.status_code == 202, pending.text
    proposal = api.get("/api/admin-requests").json()[0]
    auth_settings.staff_email_corrections_enabled = False
    use("owner")
    result = decision(api, proposal)
    assert (
        result.status_code == 409
        and result.json()["error"]["code"] == "EMAIL_CORRECTION_UNAVAILABLE"
    )
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(StaffEmailChange)) == 1
        original = session.get(StaffEmailChange, UUID(old["id"]))
        assert original.state == "requested" and original.reservation_released_at is None
    assert email_flow["sent"] == email_flow["verified"] == 0
