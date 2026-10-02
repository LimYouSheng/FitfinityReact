"""Native PostgreSQL concurrency checks: two independent bounded application pools."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select

from app.database import Database
from app.models.training import Acknowledgement, CreditDebit
from app.persistence import PersistenceConflict, acknowledge, add_purchase
from tests.domain_fixtures import purchase_parts

pytestmark = pytest.mark.database


@pytest.mark.parametrize("operation", ["completion", "purchase"])
def test_two_reviewed_writers_commit_only_one_operation(
    database_settings, domain_db, graph, operation
):
    barrier = Barrier(2)

    def write():
        db = Database(database_settings)
        try:
            with db.transaction() as session:
                barrier.wait(timeout=3)
                if operation == "completion":
                    acknowledge(
                        session, graph["session_id"], 1, graph["owner_id"], method="late_no_show"
                    )
                else:
                    add_purchase(
                        session,
                        *purchase_parts(graph),
                        expected_client_version=graph["client_version"],
                    )
            return "committed"
        except PersistenceConflict:
            return "conflict"
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: write(), range(2)))
    assert sorted(results) == ["committed", "conflict"]
    if operation == "completion":
        with domain_db.transaction() as session:
            assert session.scalar(select(func.count()).select_from(Acknowledgement)) == 1
            assert session.scalar(select(func.count()).select_from(CreditDebit)) == 1
