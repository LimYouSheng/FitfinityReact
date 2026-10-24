"""Report audit tests use actual routes, immutable rows and separate PostgreSQL connections."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models.communications import Message
from app.models.evidence import ReportAudit
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


def save(api, graph, key=None, **patch):
    return api.post(
        f"/api/clients/{graph['client_id']}/report-actions",
        headers={"Idempotency-Key": str(key or uuid4())},
        json={"purchaseId": str(graph["purchase_id"]), "kind": "pdf_export", **patch},
    )


def test_report_audit_replays_once_and_retains_immutable_history(api, domain_db, graph):
    from sqlalchemy.exc import DBAPIError

    key = uuid4()
    first = save(api, graph, key)
    assert first.status_code == 200, first.text
    assert save(api, graph, key).json() == first.json()
    assert save(api, graph, key, kind="pdf_share_opened").status_code == 409
    assert api.get(f"/api/report-actions/{key}").json() == first.json()
    assert api.get(f"/api/clients/{graph['client_id']}/report-history").json() == [first.json()]
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ReportAudit)) == 1
        notices = list(
            session.scalars(select(Message).where(Message.title.like("Progress report:%")))
        )
        assert len(notices) == 1
        assert notices[0].body == "PDF export started · Owner Original"
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.scalar(select(ReportAudit)).kind = "pdf_share_opened"
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.scalar(select(ReportAudit)))


@pytest.mark.parametrize(
    "patch",
    [{"kind": "csv_export"}, {"kind": "delivered"}, {"actorId": "forged"}, {"purchaseId": None}],
)
def test_forged_and_unsupported_report_actions_have_no_effect(api, domain_db, graph, patch):
    assert save(api, graph, **patch).status_code == 422
    with domain_db.transaction() as session:
        assert session.scalar(select(ReportAudit)) is None


def test_audit_and_notice_roll_back_together(api, domain_db, graph, monkeypatch):
    from app.api import session_reports

    def fail(**kwargs):
        raise RuntimeError("Interrupted before notification")

    monkeypatch.setattr(session_reports, "Message", fail)
    assert save(api, graph).status_code == 500
    with domain_db.transaction() as session:
        assert session.scalar(select(ReportAudit)) is None


def test_trainer_records_only_visible_clients_and_cannot_read_manager_history(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    from tests.test_staff_api import trainer_login

    owner_key = uuid4()
    assert save(api, graph, owner_key).status_code == 200
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get(f"/api/report-actions/{owner_key}").status_code == 404
    assert save(api, graph, owner_key).status_code == 409
    assert api.get(f"/api/clients/{graph['client_id']}/report-history").status_code == 403
    own_key = uuid4()
    assert save(api, graph, own_key).status_code == 200
    assert api.get(f"/api/report-actions/{own_key}").status_code == 200
    assert save(api, {**graph, "client_id": uuid4()}).status_code == 404
    assert save(api, graph, purchaseId=str(uuid4())).status_code == 404


@pytest.mark.parametrize("duplicate", [True, False])
def test_independent_audit_writes_retain_one_effect_per_identity(
    api, domain_db, database_settings, graph, duplicate
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import text

    from app.api import session_reports
    from app.authorization import Principal
    from app.database import Database
    from app.models.people import StaffUser

    key, ready = uuid4(), Barrier(2)
    with domain_db.transaction() as session:
        user = session.get(StaffUser, graph["owner_id"])
        principal = Principal(user.id, user.name, user.role, None)
    replicas = [Database(database_settings), Database(database_settings)]

    def apply(pair):
        db, index = pair
        with db.transaction() as session:
            pid = session.scalar(text("SELECT pg_backend_pid()"))
            ready.wait(timeout=5)
            result = session_reports.record(
                session,
                principal,
                graph["client_id"],
                key if duplicate else uuid4(),
                session_reports.ReportAction(purchaseId=graph["purchase_id"], kind="pdf_export"),
            )
            return pid, result.model_dump(mode="json")

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(apply, zip(replicas, [1, 2], strict=True)))
    finally:
        for db in replicas:
            db.close()
    assert len({r[0] for r in results}) == 2
    if duplicate:
        assert results[0][1] == results[1][1]
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(ReportAudit)) == (
            1 if duplicate else 2
        )
        assert session.scalar(
            select(func.count()).select_from(Message).where(Message.title.like("Progress report:%"))
        ) == (1 if duplicate else 2)


def test_inactive_client_audit_is_permitted_and_history_stays_purchase_scoped(
    api, domain_db, graph
):
    from tests.test_client_reactivation_review import deactivate

    deactivate(api, graph)
    response = save(api, graph)
    assert response.status_code == 200, response.text
    history = api.get(
        f"/api/clients/{graph['client_id']}/report-history",
        params={"purchase_id": str(graph["purchase_id"])},
    )
    assert history.json() == [response.json()]
    assert (
        api.get(
            f"/api/clients/{graph['client_id']}/report-history",
            params={"purchase_id": str(uuid4())},
        ).status_code
        == 404
    )


@pytest.mark.parametrize("kind", ["pdf_export", "pdf_share_opened", "whatsapp_opened"])
def test_report_action_kinds_record_only_launch_evidence(api, graph, kind):
    response = save(api, graph, kind=kind)
    assert response.status_code == 200, response.text
    assert response.json()["kind"] == kind
    assert set(response.json()) == {"id", "clientId", "packageId", "kind", "at", "by"}


def test_legacy_csv_and_unassigned_purchase_history_remain_readable(api, domain_db, graph):
    with domain_db.transaction() as session:
        legacy = ReportAudit(
            client_id=graph["client_id"],
            purchase_id=None,
            kind="csv_export",
            request_sha256="a" * 64,
            actor_id=graph["owner_id"],
            actor_name="Owner Original",
        )
        session.add(legacy)
        session.flush()
        identity = str(legacy.id)
    rows = api.get(f"/api/clients/{graph['client_id']}/report-history").json()
    assert len(rows) == 1
    assert (
        rows[0]["id"] == identity
        and rows[0]["packageId"] is None
        and rows[0]["kind"] == "csv_export"
    )
    assert (
        api.get(
            f"/api/clients/{graph['client_id']}/report-history",
            params={"purchase_id": str(graph["purchase_id"])},
        ).json()
        == []
    )
