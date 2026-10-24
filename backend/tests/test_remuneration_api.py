"""Real PostgreSQL pay eligibility, immutable evidence, authority and competing approvals."""

from datetime import date, time
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.api import remuneration
from app.models.communications import Message
from app.models.evidence import RemunerationApproval, RemunerationLine
from app.models.people import Trainer
from app.models.training import TrainingSession
from app.persistence import acknowledge
from tests.test_admin_api import create_admin, login_admin
from tests.test_admin_api import invitations as invitations
from tests.test_core_schema import DRAWING
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


def complete(domain_db, graph, *, method="signature", both=True):
    with domain_db.transaction() as session:
        ids = [graph["session_id"], *([graph["second_session_id"]] if both else [])]
        for identity in ids:
            booking = session.get(TrainingSession, identity)
            acknowledge(
                session,
                identity,
                booking.version,
                graph["owner_id"],
                method=method,
                **({"signer_name": "Client", "strokes": DRAWING} if method == "signature" else {}),
            )
    return remuneration.cycle_for(graph["start_date"])


def detail(api, graph, key):
    response = api.get(f"/api/remuneration/{key}/{graph['trainer_id']}")
    assert response.status_code == 200, response.text
    return response.json()


def save(api, graph, key, viewed, request_key=None, **patch):
    return api.post(
        f"/api/remuneration/{key}/{graph['trainer_id']}/approval",
        headers={"Idempotency-Key": str(request_key or uuid4())},
        json={"revision": viewed["revision"], **patch},
    )


def test_approval_replays_once_and_retains_frozen_amounts_and_private_receipt(
    api, domain_db, graph
):
    key = complete(domain_db, graph)
    viewed = detail(api, graph, key)
    expected_rate = 8000 if graph["start_date"].weekday() >= 5 else 5500
    assert viewed["amountCents"] == expected_rate * 2
    assert viewed["sessions"] == 2 and viewed["minutes"] == 120
    request_key = uuid4()
    response = save(api, graph, key, viewed, request_key)
    assert response.status_code == 200, response.text
    assert save(api, graph, key, viewed, request_key).json() == response.json()
    assert api.get(f"/api/remuneration-approvals/{request_key}").json() == response.json()
    assert save(api, graph, key, viewed).status_code == 409
    assert save(api, graph, key, viewed, request_key, revision="0" * 64).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(RemunerationApproval)) == 1
        assert session.scalar(select(func.count()).select_from(RemunerationLine)) == 2
        assert (
            session.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.kind == "remuneration_approval")
            )
            == 1
        )
        trainer = session.get(Trainer, graph["trainer_id"])
        trainer.peak_rate_cents = trainer.off_peak_rate_cents = 10000
        trainer.name = "New display name"
        trainer.version += 1
    retained = detail(api, graph, key)
    assert retained["status"] == "Approved" and retained["amountCents"] == expected_rate * 2
    assert retained["trainerName"] == "Trainer One" and retained["changed"] is False
    assert retained["current"]["amountCents"] == 20000
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.get(RemunerationApproval, request_key).amount_cents = 1


def test_no_show_receives_full_pay_zero_minutes_and_correction_flags_original_snapshot(
    api, domain_db, graph
):
    key = complete(domain_db, graph, method="late_no_show")
    viewed = detail(api, graph, key)
    assert viewed["sessions"] == 2 and viewed["minutes"] == 0 and viewed["amountCents"] > 0
    assert save(api, graph, key, viewed).status_code == 200
    with domain_db.transaction() as session:
        booking = session.get(TrainingSession, graph["session_id"])
        acknowledge(
            session,
            booking.id,
            booking.version,
            graph["owner_id"],
            method="signature",
            signer_name="Client",
            strokes=DRAWING,
        )
    retained = detail(api, graph, key)
    assert retained["minutes"] == 0 and retained["changed"] is True
    assert retained["current"]["minutes"] == 60
    assert retained["current"]["amountCents"] == retained["amountCents"]


def test_unfinished_sessions_block_until_frozen_but_completed_inactive_history_is_paid(
    api, domain_db, graph
):
    from tests.test_client_reactivation_review import deactivate

    key = complete(domain_db, graph, both=False)
    viewed = detail(api, graph, key)
    assert viewed["reviewCount"] == 1
    assert save(api, graph, key, viewed).status_code == 409
    deactivate(api, graph)
    frozen = detail(api, graph, key)
    assert frozen["reviewCount"] == 0 and frozen["sessions"] == frozen["totalSessions"] == 1
    assert save(api, graph, key, frozen).status_code == 200


def test_stale_rates_and_forged_financial_values_cannot_approve(api, domain_db, graph):
    key = complete(domain_db, graph)
    viewed = detail(api, graph, key)
    with domain_db.transaction() as session:
        trainer = session.get(Trainer, graph["trainer_id"])
        trainer.off_peak_rate_cents += 100
        trainer.version += 1
    assert save(api, graph, key, viewed).status_code == 409
    assert save(api, graph, key, detail(api, graph, key), amountCents=0).status_code == 422
    assert save(api, graph, key, viewed, actorId=str(graph["owner_id"])).status_code == 422
    with domain_db.transaction() as session:
        assert session.scalar(select(RemunerationApproval)) is None


def test_receipt_and_notice_failures_roll_back_entire_approval(api, domain_db, graph, monkeypatch):
    key = complete(domain_db, graph)
    viewed = detail(api, graph, key)

    def fail(**kwargs):
        raise RuntimeError("Interrupted before notice")

    monkeypatch.setattr(remuneration, "Message", fail)
    request_key = uuid4()
    assert save(api, graph, key, viewed, request_key).status_code == 500
    assert api.get(f"/api/remuneration-approvals/{request_key}").status_code == 404
    with domain_db.transaction() as session:
        assert session.scalar(select(RemunerationApproval)) is None
        assert session.scalar(select(RemunerationLine)) is None


def test_trainer_reads_only_own_pay_and_never_approves_or_recovers_owner_receipts(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    from tests.test_staff_api import trainer_login

    key = complete(domain_db, graph)
    viewed = detail(api, graph, key)
    request_key = uuid4()
    assert save(api, graph, key, viewed, request_key).status_code == 200
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert detail(api, graph, key)["status"] == "Approved"
    views = api.get("/api/remuneration").json()
    assert all(
        record["trainerId"] == str(graph["trainer_id"])
        for view in views
        for record in view["trainers"]
    )
    assert api.get(f"/api/remuneration/{key}/{uuid4()}").status_code == 404
    assert save(api, graph, key, viewed).status_code == 403
    assert api.get(f"/api/remuneration-approvals/{request_key}").status_code == 403


def test_admin_cannot_read_list_detail_or_approve(
    api, invitations, domain_db, graph, auth_service, auth_settings, fake_cognito
):
    key = complete(domain_db, graph)
    viewed = detail(api, graph, key)
    identity = create_admin(api).json()["id"]
    login_admin(api, auth_service, auth_settings, fake_cognito, identity)
    for path in (
        "/api/remuneration",
        f"/api/remuneration/{key}/{graph['trainer_id']}",
        f"/api/remuneration-approvals/{uuid4()}",
    ):
        assert api.get(path).status_code == 403
    assert save(api, graph, key, viewed).status_code == 403


@pytest.mark.parametrize("duplicate", [True, False])
def test_competing_connections_commit_one_approval_and_two_lines(
    api, domain_db, database_settings, graph, duplicate
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import text

    from app.api.remuneration_schemas import ApprovePay
    from app.auth.errors import AuthError
    from app.authorization import Principal
    from app.database import Database

    key = complete(domain_db, graph)
    viewed = detail(api, graph, key)
    request_key, ready = uuid4(), Barrier(2)
    principal = Principal(graph["owner_id"], "Owner Original", "owner", None)
    replicas = [Database(database_settings), Database(database_settings)]

    def apply(pair):
        db, index = pair
        with db.transaction() as session:
            pid = session.scalar(text("SELECT pg_backend_pid()"))
            ready.wait(timeout=5)
            try:
                result = remuneration.approve(
                    session,
                    principal,
                    key,
                    graph["trainer_id"],
                    request_key if duplicate or index == 0 else uuid4(),
                    ApprovePay(revision=viewed["revision"]),
                )
                return pid, result.model_dump(mode="json")
            except AuthError as error:
                return pid, error.status

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(apply, zip(replicas, [0, 1], strict=True)))
    finally:
        for db in replicas:
            db.close()
    assert len({r[0] for r in results}) == 2
    if duplicate:
        assert results[0][1] == results[1][1]
    else:
        assert sum(r[1] == 409 for r in results) == 1
    with domain_db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(RemunerationApproval)) == 1
        assert session.scalar(select(func.count()).select_from(RemunerationLine)) == 2


@pytest.mark.parametrize(
    "start,band",
    [
        (time(6, 29), "offPeak"),
        (time(6, 30), "peak"),
        (time(8, 29), "peak"),
        (time(8, 30), "offPeak"),
        (time(18), "peak"),
        (time(20, 29), "peak"),
        (time(20, 30), "offPeak"),
    ],
)
def test_start_time_band_has_exclusive_ends(start, band):
    assert remuneration.band_for(date(2026, 10, 19), start) == band
    assert remuneration.band_for(date(2026, 10, 18), start) == "peak"


def test_cycle_boundary_and_current_cycle_cannot_be_approved(api, graph):
    assert remuneration.cycle_for(date(2026, 10, 15)) == "2026-10"
    assert remuneration.cycle_for(date(2026, 10, 16)) == "2026-11"
    views = api.get("/api/remuneration").json()
    current = next(view for view in views if view["isCurrent"])
    viewed = detail(api, graph, current["key"])
    assert viewed["closed"] is False
    assert save(api, graph, current["key"], viewed).status_code == 409
    assert api.get(f"/api/remuneration/2026-13/{graph['trainer_id']}").status_code == 422
