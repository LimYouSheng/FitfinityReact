"""Real PostgreSQL/HTTP catalogue writes, exact retry evidence and purchased-term preservation."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.api import packages
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.api import PackageSaveReceipt
from app.models.communications import Message, MessageReceipt
from app.models.people import StaffUser
from app.models.training import PackageTemplate, PackageTemplateRevision
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def payload(**patch):
    return {"draft": {"name": "Custom Eighteen", "total": 18, "status": "active"}, **patch}


def save(api, body=None, key=None):
    return api.post(
        "/api/packages", json=body or payload(), headers={"Idempotency-Key": str(key or uuid4())}
    )


def test_create_update_lifecycle_preserves_purchases_and_audits(api, domain_db, graph):
    before = api.get("/api/directory").json()
    result = save(api).json()
    assert result["total_sessions"] == 18 and result["validity_days"] == 135
    assert result["version"] == result["revision"] == 1
    for version, status in [(1, "inactive"), (2, "active")]:
        response = save(
            api,
            payload(
                id=result["id"],
                expectedVersion=version,
                draft={"name": "Edited", "total": 13, "status": status},
            ),
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["version"] == result["revision"] == version + 1
        assert result["status"] == status and result["validity_days"] == 98
    # Editing a purchased template changes only the catalogue, never purchase snapshots.
    response = save(
        api,
        payload(
            id=str(graph["template_id"]),
            expectedVersion=1,
            draft={"name": "New Terms", "total": 36, "status": "inactive"},
        ),
    )
    assert response.status_code == 200, response.text
    after = api.get("/api/directory").json()
    assert before["clients"] == after["clients"]
    assert next(p for p in after["packages"] if p["id"] == result["id"]) == result
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(PackageSaveReceipt)) == 4
        assert session.scalar(select(func.count()).select_from(Message)) == 4
        assert session.scalar(select(func.count()).select_from(MessageReceipt)) == 4
        assert all(
            r.actor_id == graph["owner_id"] for r in session.scalars(select(PackageSaveReceipt))
        )


def test_stale_terms_edit_and_duplicate_name_cannot_write(api, domain_db):
    first = save(api).json()
    edit = payload(id=first["id"], expectedVersion=1)
    assert save(api, edit).status_code == 200
    assert save(api, edit).status_code == 409
    assert (
        save(
            api, payload(draft={"name": " custom eighteen ", "total": 24, "status": "active"})
        ).status_code
        == 409
    )
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(PackageSaveReceipt)) == 2


def test_retry_reconciles_original_result_after_newer_edit(api, domain_db):
    key = uuid4()
    first = save(api, key=key)
    assert first.status_code == 200
    current = first.json()
    assert save(api, payload(id=current["id"], expectedVersion=1)).status_code == 200
    assert save(api, key=key).json() == current
    assert api.get(f"/api/packages/saves/{key}").json() == current
    changed = payload(draft={"name": "Changed", "total": 24, "status": "active"})
    assert save(api, changed, key).status_code == 409
    assert api.get(f"/api/packages/saves/{uuid4()}").status_code == 404
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(PackageSaveReceipt)) == 2


@pytest.mark.parametrize(
    "draft",
    [
        {"name": "", "total": 12, "status": "active"},
        {"name": " " * 2, "total": 12, "status": "active"},
        {"name": "x" * 81, "total": 12, "status": "active"},
        {"name": "Bad", "total": 0, "status": "active"},
        {"name": "Bad", "total": 366, "status": "active"},
        {"name": "Bad", "total": 1.5, "status": "active"},
        {"name": "Bad", "total": True, "status": "active"},
        {"name": "Bad", "total": "12", "status": "active"},
        {"name": "Bad", "total": 12, "status": "deleted"},
        {"name": "Bad", "total": 12, "status": "active", "actor": "owner"},
    ],
)
def test_invalid_drafts_never_write(api, domain_db, draft):
    assert save(api, payload(draft=draft)).status_code == 422
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(PackageSaveReceipt)) == 0


def test_versions_identity_and_transport_are_required(api, graph):
    for body in [
        payload(id=str(graph["template_id"])),
        payload(expectedVersion=1),
        payload(actor="owner"),
    ]:
        assert save(api, body).status_code == 422
    assert save(api, payload(id=str(uuid4()), expectedVersion=1)).status_code == 404
    assert api.post("/api/packages", json=payload()).status_code == 422
    api.headers.pop("X-CSRF-Token")
    assert save(api).status_code == 403


def test_trainer_cannot_save_or_read_receipts(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    key = uuid4()
    assert save(api, key=key).status_code == 200
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert save(api).status_code == 403
    assert api.get(f"/api/packages/saves/{key}").status_code == 403


def test_admin_can_save_but_cannot_reconcile_owner_receipt(api, domain_db, graph):
    key = uuid4()
    assert save(api, key=key).status_code == 200
    with domain_db.transaction() as session:
        admin = StaffUser(name="Operations", email="operations@example.test", role="admin")
        session.add(admin)
        session.flush()
        principal = Principal(admin.id, admin.name, "admin", None)
        with pytest.raises(AuthError) as denied:
            packages.reconcile(session, principal, key)
        assert denied.value.status == 404
        result = packages.save(
            session,
            principal,
            key,
            packages.SavePackage(
                **payload(draft={"name": "Admin Package", "total": 365, "status": "active"})
            ),
        )
        assert result.validity_days == 2738
    with domain_db.transaction() as session:
        assert packages.reconcile(session, principal, key).id == result.id


def test_concurrent_creation_with_same_name_or_key_has_one_effect(domain_db, graph):
    principal = Principal(graph["owner_id"], "Owner Original", "owner", None)
    key = uuid4()

    def command(request_key):
        try:
            with domain_db.transaction() as session:
                return packages.save(
                    session, principal, request_key, packages.SavePackage(**payload())
                ).id
        except AuthError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(command, [key, key]))
    assert results[0] == results[1]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(command, [uuid4(), uuid4()])) == ["duplicate_name", "duplicate_name"]
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(PackageSaveReceipt)) == 1


def test_receipt_is_immutable_and_populated_downgrade_refuses(api, domain_db, migrate):
    assert save(api).status_code == 200
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        record = session.scalar(select(PackageSaveReceipt))
        session.delete(record)
    with pytest.raises(DBAPIError, match="downgrade refused"):
        migrate("downgrade", "20260924_0006")
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(PackageSaveReceipt)) == 1


def test_failed_commit_rolls_back_terms_notice_and_receipt(domain_db, graph):
    principal = Principal(graph["owner_id"], "Owner Original", "owner", None)
    with pytest.raises(RuntimeError), domain_db.transaction() as session:
        packages.save(session, principal, uuid4(), packages.SavePackage(**payload()))
        raise RuntimeError("Abort outer transaction")
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(PackageSaveReceipt)) == 0
        assert session.scalar(select(func.count()).select_from(PackageTemplate)) == 1
        assert session.scalar(select(func.count()).select_from(PackageTemplateRevision)) == 1
