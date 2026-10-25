"""Owner rate changes preserve current authority and exact integer-cent evidence."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.api import trainer_rates as commands
from app.auth.errors import AuthError
from app.authorization import Principal
from app.models.api import TrainerRateReceipt
from app.models.people import Trainer
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database
RATES = {"peak": 6543, "offPeak": 4321}


def save(api, graph, body=None, key=None):
    return api.post(
        f"/api/trainers/{graph['trainer_id']}/rates",
        json=body if body is not None else {"expectedVersion": 1, "rates": RATES},
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_rate_save_is_versioned_and_preserves_other_directory_data(api, domain_db, graph):
    before = api.get("/api/directory").json()
    key = uuid4()
    result = save(api, graph, key=key)
    assert result.status_code == 200, result.text
    assert result.json() == {"id": str(graph["trainer_id"]), "version": 2}
    after = api.get("/api/directory").json()
    assert after["clients"] == before["clients"] and after["packages"] == before["packages"]
    old = next(t for t in before["trainers"] if t["id"] == str(graph["trainer_id"]))
    new = next(t for t in after["trainers"] if t["id"] == str(graph["trainer_id"]))
    assert new == {**old, "version": 2, "peak_rate_cents": 6543, "off_peak_rate_cents": 4321}
    assert save(api, graph, key=key).json() == result.json()
    assert api.get(f"/api/trainer-rate-saves/{key}").json() == result.json()
    assert save(api, graph).status_code == 409
    assert (
        save(api, graph, {"expectedVersion": 1, "rates": {**RATES, "peak": 1}}, key).status_code
        == 409
    )
    with domain_db.transaction() as session:
        evidence = session.scalar(select(TrainerRateReceipt))
        assert evidence.previous == {
            "peak": old["peak_rate_cents"],
            "offPeak": old["off_peak_rate_cents"],
        }
        assert evidence.rates == RATES and evidence.result == result.json()


@pytest.mark.parametrize(
    "rates",
    [
        {},
        {"peak": 1},
        {**RATES, "peak": True},
        {**RATES, "peak": -1},
        {**RATES, "peak": 1.2},
        {**RATES, "peak": "123"},
        {**RATES, "peak": 9007199254740992},
        {**RATES, "email": "injected@example.test"},
    ],
)
def test_invalid_rates_never_write(api, graph, rates):
    assert save(api, graph, {"expectedVersion": 1, "rates": rates}).status_code == 422


def test_trainer_and_admin_cannot_write_or_read_rate_receipts(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    key = uuid4()
    assert save(api, graph, key=key).status_code == 200
    with domain_db.transaction() as session:
        admin = Principal(graph["owner_id"], "Admin", "admin", None)
        with pytest.raises(AuthError) as denied:
            commands.reconcile(session, admin, key)
        assert denied.value.status == 403
        with pytest.raises(AuthError) as denied:
            commands.save(
                session,
                admin,
                graph["trainer_id"],
                uuid4(),
                commands.SaveRates(expectedVersion=2, rates=RATES),
            )
        assert denied.value.status == 403
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert save(api, graph).status_code == 403
    assert api.get(f"/api/trainer-rate-saves/{key}").status_code == 403


def test_concurrent_retry_has_one_effect_and_evidence_cannot_be_deleted(
    api, domain_db, graph, migrate
):
    principal = Principal(graph["owner_id"], "Owner", "owner", None)
    key = uuid4()
    body = commands.SaveRates(expectedVersion=1, rates=RATES)

    def submit(_):
        with domain_db.transaction() as session:
            return commands.save(session, principal, graph["trainer_id"], key, body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert results[0] == results[1]
    with domain_db.transaction() as session:
        assert len(session.scalars(select(TrainerRateReceipt)).all()) == 1
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.scalar(select(TrainerRateReceipt)))
    with pytest.raises(DBAPIError, match="populated attribution downgrade refused"):
        migrate("downgrade", "20261013_0011")


def test_rollback_leaves_rates_and_receipt_unchanged(domain_db, graph):
    with domain_db.transaction() as session:
        before = session.get(Trainer, graph["trainer_id"]).peak_rate_cents
    with pytest.raises(RuntimeError), domain_db.transaction() as session:
        commands.save(
            session,
            Principal(graph["owner_id"], "Owner", "owner", None),
            graph["trainer_id"],
            uuid4(),
            commands.SaveRates(expectedVersion=1, rates=RATES),
        )
        raise RuntimeError("Discard transaction")
    with domain_db.transaction() as session:
        assert session.get(Trainer, graph["trainer_id"]).peak_rate_cents == before
        assert not session.scalars(select(TrainerRateReceipt)).all()
