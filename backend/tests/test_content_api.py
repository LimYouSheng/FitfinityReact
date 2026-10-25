"""Real PostgreSQL/HTTP staff content, conflicts and durable actor-scoped recovery."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.api import content
from app.api.directory import bounded
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.api import ContentSaveReceipt
from app.models.communications import Message, MessageReceipt
from app.models.media import ContentEntry
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database
DRAFT = {
    "key": "studio/details",
    "title": "Studio details",
    "body": "Staff content.",
    "status": "draft",
}


def save(api, body=None, key=None):
    return api.post(
        "/api/content",
        json=body or {"draft": DRAFT},
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_create_edit_archive_and_reopen_preserve_original_receipts(api, domain_db, graph):
    assert api.get("/api/content").json() == []
    key = uuid4()
    response = save(api, key=key)
    assert response.status_code == 200, response.text
    original = response.json()
    assert original["version"] == 1
    assert api.get("/api/content").json() == [original]
    result = original
    for status in ["ready", "archived", "draft"]:
        result = save(
            api,
            {
                "id": result["id"],
                "expectedVersion": result["version"],
                "draft": {**DRAFT, "status": status},
            },
        ).json()
        assert result["status"] == status
    assert result["version"] == 4 and result["created_at"] == original["created_at"]
    assert save(api, key=key).json() == original
    assert api.get(f"/api/content-saves/{key}").json() == original
    assert api.get("/api/content").json() == [result]
    with domain_db.transaction() as session:
        evidence = session.scalars(
            select(ContentSaveReceipt).order_by(ContentSaveReceipt.created_at)
        ).all()
        assert len(evidence) == 4 and evidence[0].previous is None
        assert evidence[1].previous == original and evidence[-1].result == result
        assert all(row.actor_id == graph["owner_id"] for row in evidence)
        assert session.scalar(select(func.count()).select_from(Message)) == 4
        assert set(session.scalars(select(MessageReceipt.user_id))) == {graph["owner_id"]}


def test_stale_versions_duplicate_keys_and_conflicting_replays_never_write(api, domain_db):
    key = uuid4()
    original = save(api, key=key).json()
    body = {"id": original["id"], "expectedVersion": 1, "draft": DRAFT}
    assert save(api, body).json()["version"] == 2
    assert save(api, body).status_code == 409
    assert save(api).status_code == 409
    assert save(api, {"draft": {**DRAFT, "title": "Changed"}}, key).status_code == 409
    assert api.get(f"/api/content-saves/{uuid4()}").status_code == 404
    assert save(api, {**body, "id": str(uuid4())}).status_code == 404
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ContentSaveReceipt)) == 2


@pytest.mark.parametrize(
    "patch",
    [
        {"key": "Upper"},
        {"key": "invalid//key"},
        {"key": "x" * 121},
        {"title": " "},
        {"title": "x" * 181},
        {"body": " "},
        {"body": "x" * 20001},
        {"body": 123},
        {"status": "published"},
        {"actor": "forged"},
    ],
)
def test_invalid_content_is_rejected_without_receipts(api, domain_db, patch):
    assert save(api, {"draft": {**DRAFT, **patch}}).status_code == 422
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ContentSaveReceipt)) == 0


def test_reviewed_identity_and_request_key_are_required(api):
    for body in [
        {"draft": DRAFT, "id": str(uuid4())},
        {"draft": DRAFT, "expectedVersion": 1},
        {"draft": DRAFT, "actor": "forged"},
    ]:
        assert save(api, body).status_code == 422
    assert api.post("/api/content", json={"draft": DRAFT}).status_code == 422


def test_trainer_cannot_read_write_or_reconcile(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    key = uuid4()
    assert save(api, key=key).status_code == 200
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get("/api/content").status_code == 403
    assert api.get(f"/api/content-saves/{key}").status_code == 403
    assert save(api).status_code == 403


def test_admin_edits_but_cannot_reconcile_owner_receipt(
    api, invitations, auth_service, auth_settings, fake_cognito, domain_db, graph
):
    key = uuid4()
    original = save(api, key=key).json()
    identity = create_admin(api).json()["id"]
    login_admin(api, auth_service, auth_settings, fake_cognito, identity)
    assert api.get("/api/content").json() == [original]
    assert api.get(f"/api/content-saves/{key}").status_code == 404
    response = save(
        api,
        {"id": original["id"], "expectedVersion": 1, "draft": {**DRAFT, "body": "Admin edit"}},
        key,
    )
    assert response.status_code == 200, response.text
    assert api.get(f"/api/content-saves/{key}").json() == response.json()
    with domain_db.transaction() as session:
        receipt = session.scalar(
            select(ContentSaveReceipt).where(ContentSaveReceipt.actor_id != graph["owner_id"])
        )
        assert str(receipt.actor_id) == identity and receipt.previous == original
        notice = session.scalar(
            select(Message)
            .where(Message.content_id == receipt.content_id)
            .order_by(Message.created_at.desc())
        )
        assert set(
            session.scalars(
                select(MessageReceipt.user_id).where(MessageReceipt.message_id == notice.id)
            )
        ) == {graph["owner_id"]}


def test_concurrent_same_key_and_duplicate_key_create_once(domain_db, graph):
    principal = Principal(graph["owner_id"], "Owner", "owner", None)
    key = uuid4()

    def command(request_key):
        try:
            with domain_db.transaction() as session:
                return content.save(
                    session, principal, request_key, content.SaveContent(draft=DRAFT)
                ).id
        except AuthError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(command, [key, key]))
    assert results[0] == results[1]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(command, [uuid4(), uuid4()])) == ["duplicate_key", "duplicate_key"]
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ContentSaveReceipt)) == 1


def test_immutable_receipts_populated_downgrade_and_transaction_rollback(
    api, domain_db, graph, migrate
):
    assert save(api).status_code == 200
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.scalar(select(ContentSaveReceipt)))
    with pytest.raises(DBAPIError, match="populated attribution downgrade refused"):
        migrate("downgrade", "20261013_0016")
    principal = Principal(graph["owner_id"], "Owner", "owner", None)
    with pytest.raises(RuntimeError), domain_db.transaction() as session:
        content.save(
            session, principal, uuid4(), content.SaveContent(draft={**DRAFT, "key": "other"})
        )
        raise RuntimeError("Rollback")
    with domain_db.transaction() as session:
        for model in [ContentEntry, ContentSaveReceipt, Message, MessageReceipt]:
            assert session.scalar(select(func.count()).select_from(model)) == 1


def test_complete_collection_refuses_capacity_instead_of_truncating(api, monkeypatch):
    assert save(api).status_code == 200
    assert save(api, {"draft": {**DRAFT, "key": "second"}}).status_code == 200
    monkeypatch.setattr(content, "bounded", lambda session, query: bounded(session, query, 1))
    assert api.get("/api/content").status_code == 503
