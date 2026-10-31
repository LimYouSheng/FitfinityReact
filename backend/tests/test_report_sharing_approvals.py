"""Sharing approval binds persisted content and never performs a device/provider action."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models.evidence import ReportAudit
from tests.test_admin_api import invitations as invitations
from tests.test_admin_approvals import decision
from tests.test_admin_approvals import identities as identities
from tests.test_admin_domain_approvals import enable
from tests.test_session_summaries_api import review, save
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


def selection(graph):
    return {
        "kind": "session",
        "targetId": str(graph["session_id"]),
        "purchaseId": str(graph["purchase_id"]),
        "includeSummary": True,
        "videoIds": [],
    }


def prepare(api, graph):
    body = selection(graph)
    response = api.post(
        "/api/report-sharing/review", headers={"Idempotency-Key": str(uuid4())}, json=body
    )
    assert response.status_code == 200, response.text
    return {**body, "expected": response.json()["expected"], "at": "2026-11-01T00:00:00Z"}


@pytest.mark.parametrize("outcome", ["approved", "rejected", "stale"])
def test_report_approval_is_private_frozen_and_has_no_delivery_effect(
    api, graph, domain_db, identities, outcome
):
    use = enable(api, identities, "sessionPdfSharing")
    body, key = prepare(api, graph), uuid4()
    result = api.post("/api/report-sharing", json=body, headers={"Idempotency-Key": str(key)})
    assert result.status_code == 202, result.text
    assert api.get(f"/api/report-sharing/{key}").json() == result.json()
    proposal = api.get("/api/admin-requests").json()[0]
    assert proposal["operation"] == "report.session"
    frozen = proposal["body"]["review"]["proposed"]["inputs"]
    assert frozen["summary"].startswith("Session duration: 60 minutes")
    assert "acknowledgementHistory" not in frozen
    assert "trainerComments" not in frozen
    changed = {**body, "includeSummary": False}
    assert (
        api.post(
            "/api/report-sharing", json=changed, headers={"Idempotency-Key": str(key)}
        ).status_code
        == 409
    )
    assert decision(api, proposal).status_code == 403
    use("owner")
    assert api.get(f"/api/report-sharing/{key}").status_code == 404
    if outcome == "stale":
        assert (
            save(
                api, graph["session_id"], review(api, graph["session_id"]), "Later reviewed text"
            ).status_code
            == 200
        )
    resolved = decision(api, proposal, "rejected" if outcome == "rejected" else "approved")
    assert resolved.status_code == (409 if outcome == "stale" else 200), resolved.text
    use("admin")
    recovered = api.get(f"/api/report-sharing/{key}")
    assert recovered.status_code == {"approved": 200, "rejected": 409, "stale": 202}[outcome], (
        recovered.text
    )
    if outcome == "approved":
        assert recovered.json()["inputs"] == frozen
        assert (
            api.post("/api/report-sharing", json=body, headers={"Idempotency-Key": str(key)}).json()
            == recovered.json()
        )
        use("owner")
        assert (
            save(
                api, graph["session_id"], review(api, graph["session_id"]), "Changed after approval"
            ).status_code
            == 200
        )
        use("admin")
        assert api.get(f"/api/report-sharing/{key}").status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ReportAudit)) == 0


def test_report_authorization_without_policy_is_read_only_and_rejects_foreign_selection(
    api, graph, identities
):
    identities[1]("admin")
    body = prepare(api, graph)
    result = api.post("/api/report-sharing", json=body, headers={"Idempotency-Key": str(uuid4())})
    assert result.status_code == 200, result.text
    assert api.get("/api/admin-requests").json() == []
    assert (
        api.post(
            "/api/report-sharing/review",
            headers={"Idempotency-Key": str(uuid4())},
            json={**selection(graph), "purchaseId": str(uuid4())},
        ).status_code
        == 404
    )
    assert (
        api.post(
            "/api/report-sharing/review",
            headers={"Idempotency-Key": str(uuid4())},
            json={**selection(graph), "videoIds": [str(uuid4())]},
        ).status_code
        == 409
    )
    assert (
        api.post(
            "/api/report-sharing/review",
            headers={"Idempotency-Key": str(uuid4())},
            json={**selection(graph), "includeSummary": False},
        ).status_code
        == 409
    )


def test_progress_sharing_uses_its_separate_policy_and_rechecks_signed_measurements(
    api, graph, domain_db, identities
):
    from app.models.training import TrainingSession
    from app.persistence import acknowledge
    from tests.test_session_outcomes_api import STROKES, measurement, setup_plan
    from tests.test_session_outcomes_api import review as outcome_review
    from tests.test_session_outcomes_api import save as outcome_save

    identities[1]("owner")
    identity, plan_id = setup_plan(api, graph)
    assert (
        outcome_save(
            api, identity, outcome_review(api, identity), [measurement(plan_id)]
        ).status_code
        == 200
    )
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, identity)
        acknowledge(
            session,
            identity,
            booking.version,
            graph["owner_id"],
            method="signature",
            signer_name="Client One",
            strokes=STROKES,
        )
    use = enable(api, identities, "progressReportSharing")
    body = {
        "kind": "progress",
        "targetId": str(graph["client_id"]),
        "purchaseId": str(graph["purchase_id"]),
    }
    viewed = api.post(
        "/api/report-sharing/review", headers={"Idempotency-Key": str(uuid4())}, json=body
    )
    assert viewed.status_code == 200, viewed.text
    assert viewed.json()["inputs"]["client"]["strengthProgress"][0]["points"][0]["load"] == 20
    key = uuid4()
    pending = api.post(
        "/api/report-sharing",
        json={**body, "expected": viewed.json()["expected"], "at": "2026-11-01T00:00:00Z"},
        headers={"Idempotency-Key": str(key)},
    )
    assert pending.status_code == 202, pending.text
    proposal = api.get("/api/admin-requests").json()[0]
    assert proposal["area"] == "progressReportSharing"
    # A progress-only requirement must not gate session PDFs.
    assert (
        api.post(
            "/api/report-sharing",
            json=prepare(api, graph),
            headers={"Idempotency-Key": str(uuid4())},
        ).status_code
        == 200
    )
    use("owner")
    assert decision(api, proposal).status_code == 200
    assert api.get(f"/api/report-sharing/requests/{proposal['id']}").status_code == 404
    use("admin")
    assert (
        api.get(f"/api/report-sharing/requests/{proposal['id']}").json()["inputs"]
        == proposal["body"]["review"]["proposed"]["inputs"]
    )
    use("owner")
    assert (
        outcome_save(
            api, identity, outcome_review(api, identity), [measurement(plan_id, 35)]
        ).status_code
        == 200
    )
    use("admin")
    assert api.get(f"/api/report-sharing/{key}").status_code == 409
