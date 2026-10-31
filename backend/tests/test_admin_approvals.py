"""Real PostgreSQL proposal/decision boundaries, no production providers or data."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models.admin_requests import AdminOperationDecision, AdminOperationRequest
from app.models.api import ContentSaveReceipt
from app.models.media import ContentEntry
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_content_api import DRAFT, save
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


@pytest.fixture
def identities(api, invitations, auth_settings, auth_service, fake_cognito):
    created = create_admin(api)
    assert created.status_code == 200, created.text
    identity = created.json()["id"]
    path = f"/api/staff/admins/{identity}"
    admin = api.get(path).json()
    changed = api.post(
        path,
        json={
            "expectedVersion": admin["version"],
            "operation": "approvals",
            "approvalNeeded": {**admin["approvalNeeded"], "content": True},
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert changed.status_code == 200, changed.text

    def capture():
        return (
            dict(api.cookies),
            api.headers["X-CSRF-Token"],
            dict(fake_cognito.claims),
            dict(fake_cognito.user_changes),
        )

    owner = capture()
    login_admin(api, auth_service, auth_settings, fake_cognito, identity)
    administrator = capture()

    def use(role):
        cookies, csrf, claims, attributes = owner if role == "owner" else administrator
        api.cookies.clear()
        api.cookies.update(cookies)
        api.headers["X-CSRF-Token"] = csrf
        fake_cognito.claims, fake_cognito.user_changes = claims, attributes

    return identity, use


def decision(api, proposal, action="approved", key=None):
    return api.post(
        f"/api/admin-requests/{proposal['id']}/decision",
        json={"expectedVersion": proposal["version"], "decision": action},
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_submission_never_writes_content_and_owner_approval_applies_once(
    api, domain_db, identities
):
    admin_id, use = identities
    key = uuid4()
    proposed = save(api, key=key)
    assert proposed.status_code == 202, proposed.text
    assert save(api, key=key).json() == proposed.json()
    assert api.get(f"/api/content-saves/{key}").json() == proposed.json()
    assert (
        len(
            [
                row
                for row in api.get("/api/messages").json()
                if row["kind"] == "admin_operation_request"
            ]
        )
        == 1
    )
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ContentEntry)) == 0
        assert session.scalar(select(func.count()).select_from(ContentSaveReceipt)) == 0
        assert session.scalar(select(func.count()).select_from(AdminOperationRequest)) == 1
    proposal = api.get("/api/admin-requests").json()[0]
    assert proposal["actorId"] == admin_id and proposal["body"] == {"body": {"draft": DRAFT}}
    assert decision(api, proposal).status_code == 403
    use("owner")
    assert (
        len(
            [
                row
                for row in api.get("/api/messages").json()
                if row["kind"] == "admin_operation_request"
            ]
        )
        == 1
    )
    decision_key = uuid4()
    approved = decision(api, proposal, key=decision_key)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert decision(api, proposal, key=decision_key).json() == approved.json()
    assert api.get(f"/api/admin-requests/decisions/{decision_key}").json() == approved.json()
    assert decision(api, proposal).status_code == 409
    use("admin")
    original = api.get(f"/api/content-saves/{key}")
    assert original.status_code == 200 and original.json()["title"] == DRAFT["title"]
    assert save(api, key=key).json() == original.json()
    assert api.get(f"/api/admin-requests/decisions/{decision_key}").status_code == 404
    assert (
        len(
            [
                row
                for row in api.get("/api/messages").json()
                if row["kind"] == "admin_operation_decision"
            ]
        )
        == 1
    )
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ContentEntry)) == 1
        assert session.scalar(select(func.count()).select_from(ContentSaveReceipt)) == 1
        assert session.scalar(select(func.count()).select_from(AdminOperationDecision)) == 1


@pytest.mark.parametrize("action", ["rejected", "cancelled"])
def test_closed_proposal_never_applies_and_changed_key_intent_conflicts(
    api, domain_db, identities, action
):
    _, use = identities
    key = uuid4()
    assert save(api, key=key).status_code == 202
    assert save(api, {"draft": {**DRAFT, "title": "Changed"}}, key).status_code == 409
    proposal = api.get("/api/admin-requests").json()[0]
    if action == "rejected":
        use("owner")
    result = decision(api, proposal, action)
    assert result.status_code == 200, result.text
    use("admin")
    assert save(api, key=key).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ContentEntry)) == 0


def test_approval_rechecks_stale_content_and_preserves_pending_proposal(api, domain_db, identities):
    _, use = identities
    use("owner")
    original = save(api).json()
    change = {
        "id": original["id"],
        "expectedVersion": original["version"],
        "draft": {**DRAFT, "title": "Admin proposal"},
    }
    use("admin")
    assert save(api, change).status_code == 202
    proposal = api.get("/api/admin-requests").json()[0]
    use("owner")
    assert save(api, {**change, "draft": {**DRAFT, "title": "New Owner change"}}).status_code == 200
    assert decision(api, proposal).status_code == 409
    assert api.get("/api/admin-requests").json()[0]["status"] == "pending"
    with domain_db.transaction() as session:
        assert session.scalar(select(ContentEntry)).title == "New Owner change"
        assert session.scalar(select(func.count()).select_from(AdminOperationDecision)) == 0


def test_deactivation_blocks_pending_approval_but_owner_can_reject(api, domain_db, identities):
    admin_id, use = identities
    assert save(api).status_code == 202
    proposal = api.get("/api/admin-requests").json()[0]
    use("owner")
    path = f"/api/staff/admins/{admin_id}"
    current = api.get(path).json()
    disabled = api.post(
        path,
        json={"expectedVersion": current["version"], "operation": "deactivate"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert disabled.status_code == 200, disabled.text
    assert decision(api, proposal).status_code == 409
    assert api.get("/api/admin-requests").json()[0]["status"] == "pending"
    assert decision(api, proposal, "rejected").status_code == 200
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ContentEntry)) == 0
        assert session.scalar(select(func.count()).select_from(AdminOperationDecision)) == 1


def test_failed_domain_write_rolls_back_proposal_decision_and_can_be_retried(
    api, domain_db, identities, monkeypatch
):
    from app.api.admin_supervision import COMMANDS, Command

    _, use = identities
    key = uuid4()
    assert save(api, key=key).status_code == 202
    proposal = api.get("/api/admin-requests").json()[0]
    use("owner")
    original = COMMANDS["content.save"]

    def interrupted(*args, **kwargs):
        from app.auth.errors import AuthError

        original.function(*args, **kwargs)
        raise AuthError("interrupted", "Synthetic interruption before commit.", 503)

    monkeypatch.setitem(
        COMMANDS,
        "content.save",
        Command(original.area, interrupted, original.schema, original.target),
    )
    decision_key = uuid4()
    assert decision(api, proposal, key=decision_key).status_code == 503
    assert api.get("/api/admin-requests").json()[0]["status"] == "pending"
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ContentEntry)) == 0
        assert session.scalar(select(func.count()).select_from(ContentSaveReceipt)) == 0
        assert session.scalar(select(func.count()).select_from(AdminOperationDecision)) == 0
    monkeypatch.setitem(COMMANDS, "content.save", original)
    assert decision(api, proposal, key=decision_key).status_code == 200
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ContentEntry)) == 1
        assert session.scalar(select(func.count()).select_from(ContentSaveReceipt)) == 1
        assert session.scalar(select(func.count()).select_from(AdminOperationDecision)) == 1


def test_foreign_admin_cannot_read_or_cancel_another_proposal(
    api, identities, auth_service, auth_settings, fake_cognito
):
    _, use = identities
    assert save(api).status_code == 202
    proposal = api.get("/api/admin-requests").json()[0]
    use("owner")
    foreign = create_admin(
        api, patch={"email": "foreign-approval@example.test", "name": "Foreign Admin"}
    )
    assert foreign.status_code == 200, foreign.text
    login_admin(
        api,
        auth_service,
        auth_settings,
        fake_cognito,
        foreign.json()["id"],
        email="foreign-approval@example.test",
    )
    assert api.get("/api/admin-requests").json() == []
    assert not any(
        row["kind"].startswith("admin_operation_") for row in api.get("/api/messages").json()
    )
    assert decision(api, proposal, "cancelled").status_code == 404
    assert decision(api, proposal).status_code == 403
    use("owner")
    assert api.get("/api/admin-requests").json()[0]["status"] == "pending"


def test_decision_requires_csrf_and_cannot_change_its_original_intent(api, identities):
    _, use = identities
    assert save(api).status_code == 202
    proposal = api.get("/api/admin-requests").json()[0]
    use("owner")
    token = api.headers.pop("X-CSRF-Token")
    assert decision(api, proposal).status_code == 403
    api.headers["X-CSRF-Token"] = token
    key = uuid4()
    assert decision(api, proposal, "rejected", key).status_code == 200
    assert decision(api, proposal, "approved", key).status_code == 409


def test_competing_approve_and_reject_commit_exactly_one_decision(api, domain_db, identities):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from uuid import UUID

    from app.api.admin_requests import AdminDecision, decide
    from app.auth.errors import AuthError
    from app.authorization import Principal

    _, use = identities
    assert save(api).status_code == 202
    proposal = api.get("/api/admin-requests").json()[0]
    use("owner")
    owner = api.get("/me").json()["user"]
    principal = Principal(UUID(owner["id"]), owner["name"], "owner", None)
    barrier = Barrier(2)

    def act(action):
        barrier.wait(timeout=10)
        try:
            with domain_db.transaction() as session:
                result = decide(
                    session,
                    principal,
                    UUID(proposal["id"]),
                    uuid4(),
                    AdminDecision(expectedVersion=proposal["version"], decision=action),
                )
                return result.status
        except AuthError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(act, action) for action in ["approved", "rejected"]]
        results = [future.result(timeout=15) for future in futures]
    assert results.count(409) == 1
    winning = next(result for result in results if result != 409)
    assert winning in ["approved", "rejected"]
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(AdminOperationDecision)) == 1
        assert session.scalar(select(AdminOperationRequest)).status == winning
        assert session.scalar(select(func.count()).select_from(ContentEntry)) == (
            1 if winning == "approved" else 0
        )
        assert session.scalar(select(func.count()).select_from(ContentSaveReceipt)) == (
            1 if winning == "approved" else 0
        )


def test_proposal_and_decision_evidence_cannot_be_rewritten_or_deleted(api, domain_db, identities):
    from sqlalchemy import delete, update
    from sqlalchemy.exc import DBAPIError

    _, use = identities
    assert save(api).status_code == 202
    proposal = api.get("/api/admin-requests").json()[0]
    for statement in [
        update(AdminOperationRequest).values(body={"rewritten": True}),
        delete(AdminOperationRequest),
    ]:
        with pytest.raises(DBAPIError):
            with domain_db.transaction() as session:
                session.execute(statement)
    use("owner")
    assert decision(api, proposal).status_code == 200
    for statement in [
        update(AdminOperationRequest).values(status="pending", version=3),
        update(AdminOperationDecision).values(result={"rewritten": True}),
        delete(AdminOperationDecision),
    ]:
        with pytest.raises(DBAPIError):
            with domain_db.transaction() as session:
                session.execute(statement)
    assert api.get("/api/admin-requests").json()[0]["status"] == "approved"
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(AdminOperationDecision)) == 1
        assert session.scalar(select(ContentEntry)).title == DRAFT["title"]


def test_package_policy_freezes_review_without_cross_domain_receipt_leak(
    api, domain_db, identities
):
    from app.models.api import PackageSaveReceipt
    from app.models.training import PackageTemplateRevision
    from tests.test_package_api import save as save_package

    admin_id, use = identities
    use("owner")
    path = f"/api/staff/admins/{admin_id}"
    current = api.get(path).json()
    result = api.post(
        path,
        json={
            "expectedVersion": current["version"],
            "operation": "approvals",
            "approvalNeeded": {**current["approvalNeeded"], "packageCatalogue": True},
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert result.status_code == 200, result.text
    use("admin")
    key = uuid4()
    result = save_package(api, key=key)
    assert result.status_code == 202, result.text
    assert api.get(f"/api/packages/saves/{key}").json() == result.json()
    assert api.get(f"/api/content-saves/{key}").status_code == 404
    with domain_db.transaction() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(PackageTemplateRevision)
                .where(PackageTemplateRevision.name == "Custom Eighteen")
            )
            == 0
        )
    proposal = api.get("/api/admin-requests").json()[0]
    use("owner")
    assert decision(api, proposal).status_code == 200
    use("admin")
    saved = save_package(api, key=key)
    assert saved.status_code == 200 and saved.json()["total_sessions"] == 18
    assert api.get(f"/api/packages/saves/{key}").json() == saved.json()
    with domain_db.transaction() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(PackageTemplateRevision)
                .where(PackageTemplateRevision.name == "Custom Eighteen")
            )
            == 1
        )
        assert session.scalar(select(func.count()).select_from(PackageSaveReceipt)) == 1
