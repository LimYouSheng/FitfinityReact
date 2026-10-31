"""Owner-only Admin lifecycle, immutable retries and real stored supervision policy."""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.admin_management import APPROVAL_AREAS, AdminManagementReceipt
from app.models.people import StaffUser
from app.models.staff import AdminProfile
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


@pytest.fixture
def administrator(domain_db):
    with domain_db.transaction() as session:
        user = StaffUser(
            name="Synthetic Admin", email=f"admin-{uuid4()}@example.test", role="admin"
        )
        session.add(user)
        session.flush()
        session.add(
            AdminProfile(
                user_id=user.id,
                phone_country_code="+65",
                phone_number="81234567",
                birthday=date(1990, 1, 1),
                gender="Other",
            )
        )
        return user.id


def change(api, identity, body, key=None):
    return api.post(
        f"/api/staff/admins/{identity}", json=body, headers={"Idempotency-Key": str(key or uuid4())}
    )


def test_admin_details_replay_and_stale_review(api, domain_db, administrator):
    path = f"/api/staff/admins/{administrator}"
    before = api.get(path).json()
    body = {
        "expectedVersion": before["version"],
        "operation": "details",
        "details": {**before["details"], "name": "Corrected Admin"},
    }
    key = uuid4()
    saved = change(api, administrator, body, key)
    assert saved.status_code == 200, saved.text
    assert saved.json()["details"]["name"] == "Corrected Admin"
    assert change(api, administrator, body, key).json() == saved.json()
    assert api.get(f"/api/staff/admins/changes/{key}").json() == saved.json()
    assert change(api, administrator, body).status_code == 409
    assert (
        change(
            api, administrator, {**body, "details": {**body["details"], "name": "Different"}}, key
        ).status_code
        == 409
    )
    with domain_db.transaction() as session:
        receipts = session.scalars(
            select(AdminManagementReceipt).where(AdminManagementReceipt.admin_id == administrator)
        ).all()
        assert len(receipts) == 1
        assert receipts[0].previous["details"]["name"] == "Synthetic Admin"


def test_admin_status_retains_profile_and_policy(api, domain_db, administrator):
    path = f"/api/staff/admins/{administrator}"
    before = api.get(path).json()
    settings = {area: True for area in APPROVAL_AREAS}
    updated = change(
        api,
        administrator,
        {
            "expectedVersion": before["version"],
            "operation": "approvals",
            "approvalNeeded": settings,
        },
    )
    assert updated.status_code == 200, updated.text
    assert api.get(path).json()["approvalNeeded"] == settings
    disabled = change(
        api,
        administrator,
        {"expectedVersion": updated.json()["version"], "operation": "deactivate"},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["status"] == "inactive"
    enabled = change(
        api,
        administrator,
        {"expectedVersion": disabled.json()["version"], "operation": "reactivate"},
    )
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["status"] == "active"
    assert enabled.json()["details"] == before["details"]
    assert enabled.json()["approvalNeeded"] == settings
    with domain_db.transaction() as session:
        assert session.get(StaffUser, administrator).status == "active"


def test_admin_cannot_change_email_or_inject_role(api, administrator):
    before = api.get(f"/api/staff/admins/{administrator}").json()
    body = {
        "expectedVersion": before["version"],
        "operation": "details",
        "details": {**before["details"], "email": "different@example.test"},
    }
    assert change(api, administrator, body).status_code == 422
    assert change(api, administrator, {**body, "role": "owner"}).status_code == 422
    assert api.get(f"/api/staff/admins/{administrator}").json() == before


def test_admin_rejects_unknown_or_partial_approval_policy(api, administrator):
    before = api.get(f"/api/staff/admins/{administrator}").json()
    body = {
        "expectedVersion": before["version"],
        "operation": "approvals",
        "approvalNeeded": {"clientCreation": True},
    }
    assert change(api, administrator, body).status_code == 422
    body["approvalNeeded"] = {**before["approvalNeeded"], "financialAccess": True}
    assert change(api, administrator, body).status_code == 422
    assert api.get(f"/api/staff/admins/{administrator}").json() == before


@pytest.mark.parametrize("area", ["reports", "progressReports", "sessionReports"])
def test_report_export_approval_is_not_a_supported_policy(api, administrator, area):
    before = api.get(f"/api/staff/admins/{administrator}").json()
    assert not {"reports", "progressReports", "sessionReports"}.intersection(
        before["approvalNeeded"]
    )
    body = {
        "expectedVersion": before["version"],
        "operation": "approvals",
        "approvalNeeded": {**before["approvalNeeded"], area: True},
    }
    assert change(api, administrator, body).status_code == 422
    assert api.get(f"/api/staff/admins/{administrator}").json() == before


def test_trainer_cannot_read_manage_or_recover_admin_accounts(
    api,
    administrator,
    domain_db,
    graph,
    auth_settings,
    auth_service,
    fake_cognito,
):
    before = api.get(f"/api/staff/admins/{administrator}").json()
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get("/api/staff/admins").status_code == 403
    assert api.get(f"/api/staff/admins/{administrator}").status_code == 403
    assert api.get(f"/api/staff/admins/changes/{uuid4()}").status_code == 403
    assert (
        change(
            api, administrator, {"expectedVersion": before["version"], "operation": "deactivate"}
        ).status_code
        == 403
    )
    with domain_db.transaction() as session:
        assert session.get(StaffUser, administrator).status == "active"
        assert session.scalars(select(AdminManagementReceipt)).all() == []


def test_admin_lifecycle_revokes_old_login_and_requires_new_login_after_reactivation(
    api,
    invitations,
    auth_service,
    auth_settings,
    fake_cognito,
):
    created = create_admin(api)
    assert created.status_code == 200, created.text
    identity = created.json()["id"]
    before = api.get(f"/api/staff/admins/{identity}").json()
    owner_cookies, owner_csrf = dict(api.cookies), api.headers["X-CSRF-Token"]
    owner_claims, owner_attributes = dict(fake_cognito.claims), dict(fake_cognito.user_changes)
    login_admin(api, auth_service, auth_settings, fake_cognito, identity)
    admin_cookies, admin_csrf = dict(api.cookies), api.headers["X-CSRF-Token"]
    admin_claims, admin_attributes = dict(fake_cognito.claims), dict(fake_cognito.user_changes)
    assert api.get("/api/staff/admins").status_code == 403
    assert (
        change(
            api, identity, {"expectedVersion": before["version"], "operation": "deactivate"}
        ).status_code
        == 403
    )

    def use(cookies, csrf):
        api.cookies.clear()
        api.cookies.update(cookies)
        api.headers["X-CSRF-Token"] = csrf
        fake_cognito.claims, fake_cognito.user_changes = (
            (owner_claims, owner_attributes)
            if cookies == owner_cookies
            else (admin_claims, admin_attributes)
        )

    use(owner_cookies, owner_csrf)
    disabled = change(
        api, identity, {"expectedVersion": before["version"], "operation": "deactivate"}
    )
    assert disabled.status_code == 200, disabled.text
    use(admin_cookies, admin_csrf)
    assert api.get("/api/staff/admins").status_code == 401
    use(owner_cookies, owner_csrf)
    enabled = change(
        api, identity, {"expectedVersion": disabled.json()["version"], "operation": "reactivate"}
    )
    assert enabled.status_code == 200, enabled.text
    use(admin_cookies, admin_csrf)
    assert api.get("/api/staff/admins").status_code == 401
    login_admin(api, auth_service, auth_settings, fake_cognito, identity)
    # Authenticated again, but fixed Admin authority still cannot manage accounts.
    assert api.get("/api/staff/admins").status_code == 403


def test_new_admin_defaults_require_library_and_content_only(api, invitations, domain_db):
    from app.models.admin_management import AdminApprovalRequirement

    created = create_admin(api)
    assert created.status_code == 200, created.text
    identity = created.json()["id"]
    response = api.get(f"/api/staff/admins/{identity}")
    assert response.status_code == 200, response.text
    assert response.json()["approvalNeeded"] == {
        area: area in {"exerciseLibrary", "content"} for area in APPROVAL_AREAS
    }
    with domain_db.transaction() as session:
        policies = session.scalars(
            select(AdminApprovalRequirement).where(AdminApprovalRequirement.user_id == identity)
        ).all()
        assert {row.area for row in policies if row.required} == {"exerciseLibrary", "content"}
