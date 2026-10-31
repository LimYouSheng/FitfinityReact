"""Owner review cannot be bypassed by compensating an earlier session change."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.models.session_mutations import SessionMutation, SessionMutationUndo
from app.models.training import TrainingSession
from tests.test_admin_api import invitations as invitations
from tests.test_admin_approvals import decision
from tests.test_admin_approvals import identities as identities
from tests.test_admin_domain_approvals import enable
from tests.test_package_actions import future as future
from tests.test_session_summaries_api import review, save
from tests.test_session_undo_api import change_summary, undo, undo_review
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


@pytest.mark.parametrize("outcome", ["approved", "rejected", "stale"])
def test_admin_undo_uses_original_approval_area_and_preserves_history(
    api, graph, domain_db, identities, outcome
):
    use = identities[1]
    use("admin")
    identity, mutation, version = change_summary(api, graph, domain_db)
    use = enable(api, identities, "sessionContent")
    viewed, key = undo_review(api, mutation), uuid4()
    pending = undo(api, mutation, viewed, key)
    assert pending.status_code == 202, pending.text
    assert api.get(f"/api/session-undos/{key}").json() == pending.json()
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, identity).client_summary == "A new reviewed summary"
        assert session.get(TrainingSession, identity).version == version
        assert session.scalar(select(func.count()).select_from(SessionMutationUndo)) == 0
    proposal = api.get("/api/admin-requests").json()[0]
    assert proposal["operation"] == "undo.sessionContent"
    assert proposal["body"]["review"]["subject"] == "Undo session.summary"
    assert any(
        row["restore"].get("client_summary") == ""
        for row in proposal["body"]["review"]["proposed"]
        if row["restore"]
    )
    assert decision(api, proposal).status_code == 403
    use("owner")
    assert api.get(f"/api/session-undos/{key}").status_code == 404
    if outcome == "stale":
        assert save(api, identity, review(api, identity), "Later Owner summary").status_code == 200
    decision_key = uuid4()
    resolved = decision(
        api, proposal, "rejected" if outcome == "rejected" else "approved", decision_key
    )
    assert resolved.status_code == (409 if outcome == "stale" else 200), resolved.text
    if outcome != "stale":
        assert decision(api, proposal, outcome, decision_key).json() == resolved.json()
    use("admin")
    recovered = api.get(f"/api/session-undos/{key}")
    assert recovered.status_code == {"approved": 200, "rejected": 409, "stale": 202}[outcome], (
        recovered.text
    )
    with domain_db.transaction() as session:
        assert (
            session.get(TrainingSession, identity).client_summary
            == {
                "approved": "",
                "rejected": "A new reviewed summary",
                "stale": "Later Owner summary",
            }[outcome]
        )
        assert session.get(SessionMutation, mutation).operation == "session.summary"
        rows = list(session.scalars(select(SessionMutationUndo)))
        assert len(rows) == int(outcome == "approved")
        if rows:
            assert rows[0].actor_id == UUID(identities[0])
    if outcome == "approved":
        assert undo(api, mutation, viewed, key).json() == recovered.json()


@pytest.mark.parametrize("outcome", ["approved", "rejected"])
def test_package_deletion_undo_requires_its_own_purchase_approval(
    api, graph, domain_db, identities, future, outcome
):
    from app.models.training import PackagePurchase
    from tests.test_package_actions import review as package_review
    from tests.test_package_actions import save as package_save

    use = identities[1]
    use("owner")
    purchase_id, bookings = future
    assert package_save(api, graph, package_review(api, graph, purchase_id)).status_code == 200
    deleted = package_save(
        api, graph, package_review(api, graph, purchase_id, "delete_sessions")
    ).json()
    use = enable(api, identities, "clientPackages")
    path = f"/api/package-actions/{deleted['id']}"
    viewed = api.get(path + "/undo-review")
    assert viewed.status_code == 200, viewed.text
    key = uuid4()
    body = {"expected": viewed.json()["expected"]}
    pending = api.post(path + "/undo", json=body, headers={"Idempotency-Key": str(key)})
    assert pending.status_code == 202, pending.text
    assert api.get(f"/api/package-undos/{key}").status_code == 202
    proposal = api.get("/api/admin-requests").json()[0]
    assert proposal["operation"] == "undo.clientPackages"
    with domain_db.transaction() as session:
        assert all(session.get(TrainingSession, identity) is None for identity in bookings)
    use("owner")
    resolved = decision(api, proposal, outcome)
    assert resolved.status_code == 200, resolved.text
    use("admin")
    recovered = api.get(f"/api/package-undos/{key}")
    assert recovered.status_code == (200 if outcome == "approved" else 409), recovered.text
    with domain_db.transaction() as session:
        assert session.get(PackagePurchase, purchase_id).status == "inactive"
        assert all(
            (session.get(TrainingSession, identity) is not None) == (outcome == "approved")
            for identity in bookings
        )
        assert session.get(TrainingSession, graph["session_id"]).version == 1
    if outcome == "approved":
        assert (
            api.post(path + "/undo", json=body, headers={"Idempotency-Key": str(key)}).json()
            == recovered.json()
        )
