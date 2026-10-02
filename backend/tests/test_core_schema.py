"""Database business invariants. This module always uses the real isolated DB in the gate."""

from decimal import Decimal
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.database import Base
from app.models.communications import ChangeRequest, Message, MessageReceipt, RequestEvent
from app.models.evidence import ReportAudit
from app.models.people import Client, StaffUser, Trainer
from app.models.training import (
    Acknowledgement,
    CreditDebit,
    ExercisePlanItem,
    ExerciseResult,
    PackagePurchase,
    PackageTemplateRevision,
    TrainingSession,
)
from app.persistence import (
    PersistenceConflict,
    acknowledge,
    add_client,
    add_purchase,
    report_action,
    used_credits,
)
from tests.domain_fixtures import person, purchase_parts

pytestmark = pytest.mark.database
DRAWING = [[{"x": 1, "y": 2}, {"x": 20, "y": 5}, {"x": 40, "y": 30}]]


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_migration_matches_canonical_models(domain_db):
    with domain_db.engine.connect() as connection:
        assert set(inspect(connection).get_table_names()) == set(Base.metadata.tables) | {
            "alembic_version"
        }
        assert (
            compare_metadata(
                MigrationContext.configure(connection, opts={"compare_type": True}), Base.metadata
            )
            == []
        )
        assert (
            connection.scalar(text("SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'ff_%'"))
            == 113
        )


def test_populated_downgrade_refuses_before_losing_any_data(domain_db, graph, migrate):
    with pytest.raises(DBAPIError, match="downgrade refused"):
        migrate("downgrade", "base")
    with domain_db.transaction() as session:
        assert count(session, Client) == 1
        assert count(session, TrainingSession) == 2
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "20260924_0006"


def test_couple_has_two_people_in_one_atomic_transaction(domain_db, graph):
    with domain_db.transaction() as session:
        client = add_client(
            session,
            Client(kind="couple", name="Two People", trainer_id=graph["trainer_id"]),
            [person("One"), person("Two")],
        )
        identity = client.id
    with domain_db.transaction() as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM client_people WHERE client_id=:id"), {"id": identity}
            )
            == 2
        )


def test_partial_couple_insert_rolls_back_at_commit(domain_db, graph):
    with pytest.raises(IntegrityError, match="exactly 2"), domain_db.transaction() as session:
        client = Client(kind="couple", name="Incomplete", trainer_id=graph["trainer_id"])
        session.add(client)
        session.flush()
        child = person()
        child.client_id = client.id
        child.position = 1
        session.add(child)
    with domain_db.transaction() as session:
        assert count(session, Client) == 1


@pytest.mark.parametrize("change", ["duplicate_email", "owner_trainer_mapping", "bad_phone"])
def test_staff_identity_and_contact_constraints(domain_db, graph, change):
    with pytest.raises(IntegrityError), domain_db.transaction() as session:
        if change == "duplicate_email":
            session.add(StaffUser(name="Duplicate", email="owner@example.test", role="trainer"))
        else:
            trainer = session.get(Trainer, graph["trainer_id"])
            if change == "owner_trainer_mapping":
                trainer.user_id = graph["owner_id"]
            else:
                trainer.phone_number = "abc"
    with domain_db.transaction() as session:
        assert count(session, StaffUser) == 2
        assert session.get(Trainer, graph["trainer_id"]).user_id == graph["user_id"]


def test_purchase_late_failure_rolls_back_every_child_and_parent(domain_db, graph):
    with pytest.raises(IntegrityError, match="capacity"), domain_db.transaction() as session:
        purchase, slots, preferences, bookings = purchase_parts(graph)
        bookings[1].session_number = 3
        add_purchase(
            session,
            purchase,
            slots,
            preferences,
            bookings,
            expected_client_version=graph["client_version"],
        )
    with domain_db.transaction() as session:
        assert count(session, PackagePurchase) == 1
        assert count(session, TrainingSession) == 2
        assert session.get(Client, graph["client_id"]).version == graph["client_version"]


def test_stale_purchase_review_writes_nothing(domain_db, graph):
    with pytest.raises(PersistenceConflict), domain_db.transaction() as session:
        add_purchase(session, *purchase_parts(graph), expected_client_version=1)
    with domain_db.transaction() as session:
        assert count(session, PackagePurchase) == 1


def test_overlap_rejected_even_when_no_credits_used(domain_db, graph):
    with pytest.raises(IntegrityError, match="follow"), domain_db.transaction() as session:
        # Insert directly to test the database invariant independently of the repository.
        purchase, _, _, _ = purchase_parts(graph, graph["end_date"])
        session.add(purchase)
        session.flush()
    with domain_db.transaction() as session:
        assert used_credits(session, graph["purchase_id"]) == 0
        assert count(session, PackagePurchase) == 1


def test_new_template_revision_cannot_rewrite_purchase_snapshot(domain_db, graph):
    with domain_db.transaction() as session:
        session.add(
            PackageTemplateRevision(
                template_id=graph["template_id"],
                revision=2,
                name="New terms",
                total_sessions=12,
                validity_days=100,
                actor_id=graph["owner_id"],
                actor_name="Ignored input name",
            )
        )
    with pytest.raises(IntegrityError, match="immutable"), domain_db.transaction() as session:
        session.get(PackagePurchase, graph["purchase_id"]).name = "New terms"
    with domain_db.transaction() as session:
        assert session.get(PackagePurchase, graph["purchase_id"]).name == "Two sessions"


def test_missing_purchase_sessions_refused_at_transaction_end(domain_db, graph):
    with (
        pytest.raises(IntegrityError, match="complete schedule"),
        domain_db.transaction() as session,
    ):
        session.add(purchase_parts(graph)[0])
    with domain_db.transaction() as session:
        assert count(session, PackagePurchase) == 1


def test_session_cannot_be_moved_to_another_purchase_identity(domain_db, graph):
    with pytest.raises(IntegrityError, match="immutable field"), domain_db.transaction() as session:
        session.get(TrainingSession, graph["session_id"]).purchase_id = uuid4()


def test_completion_requires_acknowledgement_and_one_debit(domain_db, graph):
    with pytest.raises(IntegrityError, match="commit together"), domain_db.transaction() as session:
        session.get(TrainingSession, graph["session_id"]).status = "completed"
    with domain_db.transaction() as session:
        assert session.get(TrainingSession, graph["session_id"]).status == "scheduled"
        assert count(session, CreditDebit) == 0


def test_no_show_correction_preserves_history_and_uses_one_credit(domain_db, graph):
    with domain_db.transaction() as session:
        first = acknowledge(
            session, graph["session_id"], 1, graph["owner_id"], method="late_no_show", note="Absent"
        )
        first_id = first.id
    with domain_db.transaction() as session:
        second = acknowledge(
            session,
            graph["session_id"],
            2,
            graph["owner_id"],
            method="signature",
            signer_name="Client Original",
            strokes=DRAWING,
        )
        second_id = second.id
    with domain_db.transaction() as session:
        assert count(session, Acknowledgement) == 2
        assert used_credits(session, graph["purchase_id"]) == 1
        assert session.get(Acknowledgement, first_id).method == "late_no_show"
        assert session.get(Acknowledgement, second_id).signer_name == "Client Original"
        assert session.get(TrainingSession, graph["session_id"]).version == 3
    with pytest.raises(PersistenceConflict), domain_db.transaction() as session:
        acknowledge(session, graph["session_id"], 3, graph["owner_id"], method="late_no_show")


def test_failed_signature_never_consumes_credit(domain_db, graph):
    with pytest.raises(ValueError), domain_db.transaction() as session:
        acknowledge(
            session,
            graph["session_id"],
            1,
            graph["owner_id"],
            method="signature",
            signer_name="Client",
            strokes=[],
        )
    with domain_db.transaction() as session:
        assert count(session, CreditDebit) == count(session, Acknowledgement) == 0
        assert session.get(TrainingSession, graph["session_id"]).version == 1


@pytest.mark.parametrize("operation", ["edit", "delete", "second_debit"])
def test_completion_evidence_is_permanent(domain_db, graph, operation):
    with domain_db.transaction() as session:
        acknowledgement = acknowledge(
            session,
            graph["session_id"],
            1,
            graph["owner_id"],
            method="signature",
            signer_name="Client Original",
            strokes=DRAWING,
        )
        identity = acknowledgement.id
    with pytest.raises(IntegrityError), domain_db.transaction() as session:
        if operation == "edit":
            session.get(Acknowledgement, identity).signer_name = "Replacement"
        elif operation == "delete":
            session.delete(session.get(Acknowledgement, identity))
        else:
            session.add(
                CreditDebit(
                    session_id=graph["session_id"],
                    purchase_id=graph["purchase_id"],
                    client_id=graph["client_id"],
                    actor_id=graph["owner_id"],
                    actor_name="Owner",
                )
            )
    with domain_db.transaction() as session:
        session.get(StaffUser, graph["owner_id"]).name = "Owner Renamed"
    with domain_db.transaction() as session:
        assert session.get(Acknowledgement, identity).actor_name == "Owner Original"
        assert session.get(Acknowledgement, identity).signer_name == "Client Original"
        assert used_credits(session, graph["purchase_id"]) == 1


def test_raw_update_must_advance_version(domain_db, graph):
    with pytest.raises(IntegrityError, match="version"), domain_db.transaction() as session:
        session.execute(
            text("UPDATE clients SET name='Overwritten' WHERE id=:id"), {"id": graph["client_id"]}
        )


def test_stale_orm_writer_cannot_overwrite_newer_record(domain_db, graph):
    with domain_db.transaction() as session:
        stale = session.get(Client, graph["client_id"])
    with domain_db.transaction() as session:
        session.get(Client, graph["client_id"]).remarks = "Newer saved value"
    with pytest.raises(StaleDataError), domain_db.transaction() as session:
        stale.remarks = "Old page value"
        session.add(stale)
    with domain_db.transaction() as session:
        assert session.get(Client, graph["client_id"]).remarks == "Newer saved value"


def test_measured_results_allow_versioned_corrections_and_enforce_bounds(domain_db, graph):
    with domain_db.transaction() as session:
        item = ExercisePlanItem(
            session_id=graph["session_id"], position=1, name="Squat", weight="Bodyweight"
        )
        session.add(item)
        session.flush()
        result = ExerciseResult(
            session_id=graph["session_id"],
            plan_item_id=item.id,
            name="Squat",
            load_kg=Decimal("20.5"),
            reps=10,
            sets=3,
        )
        session.add(result)
        session.flush()
        identity = result.id
    with domain_db.transaction() as session:
        session.get(ExerciseResult, identity).load_kg = Decimal("21.75")
    with pytest.raises(IntegrityError), domain_db.transaction() as session:
        session.get(ExerciseResult, identity).reps = 0
    with domain_db.transaction() as session:
        result = session.get(ExerciseResult, identity)
        assert result.load_kg == Decimal("21.75") and result.version == 2


def test_report_retry_is_idempotent_and_payload_bound(domain_db, graph):
    operation = uuid4()
    for _ in range(2):
        with domain_db.transaction() as session:
            assert (
                report_action(
                    session,
                    operation,
                    graph["owner_id"],
                    graph["client_id"],
                    graph["purchase_id"],
                    "pdf_export",
                ).id
                == operation
            )
    with pytest.raises(PersistenceConflict), domain_db.transaction() as session:
        report_action(
            session,
            operation,
            graph["owner_id"],
            graph["client_id"],
            graph["purchase_id"],
            "pdf_share_opened",
        )
    with pytest.raises(ValueError), domain_db.transaction() as session:
        report_action(
            session,
            uuid4(),
            graph["owner_id"],
            graph["client_id"],
            graph["purchase_id"],
            "csv_export",
        )
    with domain_db.transaction() as session:
        assert count(session, ReportAudit) == 1


def test_request_status_and_history_commit_together(domain_db, graph):
    with domain_db.transaction() as session:
        request = ChangeRequest(
            kind="trainer_availability",
            trainer_id=graph["trainer_id"],
            expected_version=1,
            actor_id=graph["user_id"],
            actor_name="Trainer",
        )
        session.add(request)
        session.flush()
        identity = request.id
        session.add(
            RequestEvent(
                request_id=identity,
                sequence=1,
                status="pending",
                actor_id=graph["user_id"],
                actor_name="Trainer",
            )
        )
    with (
        pytest.raises(IntegrityError, match="matching append-only history"),
        domain_db.transaction() as session,
    ):
        request = session.get(ChangeRequest, identity)
        request.status = "cancelled"
        request.resolved_at = session.scalar(select(func.now()))
        request.resolved_by = graph["user_id"]
    with domain_db.transaction() as session:
        request = session.get(ChangeRequest, identity)
        request.status = "cancelled"
        request.resolved_at = session.scalar(select(func.now()))
        request.resolved_by = graph["user_id"]
        session.add(
            RequestEvent(
                request_id=identity,
                sequence=2,
                status="cancelled",
                actor_id=graph["user_id"],
                actor_name="Trainer",
            )
        )
    with (
        pytest.raises(IntegrityError, match="only transition once"),
        domain_db.transaction() as session,
    ):
        session.get(ChangeRequest, identity).status = "rejected"
    with domain_db.transaction() as session:
        assert session.get(ChangeRequest, identity).status == "cancelled"
        assert session.get(TrainingSession, graph["session_id"]).status == "scheduled"


def test_messages_have_independent_user_read_state(domain_db, graph):
    with domain_db.transaction() as session:
        message = Message(
            kind="saved_edit",
            title="Saved",
            body="Updated details",
            actor_id=graph["owner_id"],
            actor_name="Owner",
        )
        session.add(message)
        session.flush()
        receipts = [
            MessageReceipt(message_id=message.id, user_id=identity)
            for identity in [graph["owner_id"], graph["user_id"]]
        ]
        session.add_all(receipts)
        session.flush()
        ids = [receipt.id for receipt in receipts]
    with domain_db.transaction() as session:
        session.get(MessageReceipt, ids[0]).read_at = session.scalar(select(func.now()))
    with domain_db.transaction() as session:
        assert session.get(MessageReceipt, ids[0]).read_at is not None
        assert session.get(MessageReceipt, ids[1]).read_at is None
