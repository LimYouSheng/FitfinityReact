"""Remuneration, typed requests, lifecycle and durable media metadata constraints."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.models.communications import ChangeRequest
from app.models.evidence import RemunerationApproval, RemunerationLine
from app.models.media import MediaAsset, MediaDeletion
from app.models.people import Client, LifecycleEvent, Trainer
from app.models.training import ExercisePlanItem, PackagePurchase, TrainingSession
from app.persistence import acknowledge
from tests.test_core_schema import DRAWING, count

pytestmark = pytest.mark.database


def test_client_deactivation_and_purchase_cause_commit_atomically(domain_db, graph):
    with pytest.raises(IntegrityError), domain_db.transaction() as session:
        session.get(Client, graph["client_id"]).status = "inactive"
    with domain_db.transaction() as session:
        cause = LifecycleEvent(
            client_id=graph["client_id"],
            status="inactive",
            reason="owner",
            actor_id=graph["owner_id"],
            actor_name="Owner",
        )
        session.add(cause)
        session.flush()
        effect = LifecycleEvent(
            purchase_id=graph["purchase_id"],
            status="inactive",
            reason="client",
            cause_id=cause.id,
            actor_id=graph["owner_id"],
            actor_name="Owner",
        )
        session.add(effect)
        session.flush()
        client = session.get(Client, graph["client_id"])
        purchase = session.get(PackagePurchase, graph["purchase_id"])
        client.status, client.lifecycle_event_id = "inactive", cause.id
        purchase.status, purchase.lifecycle_event_id = "inactive", effect.id
    with domain_db.transaction() as session:
        client = session.get(Client, graph["client_id"])
        purchase = session.get(PackagePurchase, graph["purchase_id"])
        assert client.status == purchase.status == "inactive"
        assert (
            session.get(LifecycleEvent, purchase.lifecycle_event_id).cause_id
            == client.lifecycle_event_id
        )


def approved(session, graph, *, wrong_total=False):
    acknowledgement = acknowledge(
        session,
        graph["session_id"],
        1,
        graph["owner_id"],
        method="signature",
        signer_name="Client",
        strokes=DRAWING,
    )
    booking = session.get(TrainingSession, graph["session_id"])
    cycle_start = booking.training_date.replace(day=16)
    cycle_end = (cycle_start.replace(day=1) + timedelta(days=32)).replace(day=15)
    band = "peak" if booking.training_date.weekday() >= 5 else "off_peak"
    amount = 8000 if band == "peak" else 5500
    approval = RemunerationApproval(
        trainer_id=graph["trainer_id"],
        trainer_name="Trainer One",
        cycle_key=cycle_end.strftime("%Y-%m"),
        cycle_start=cycle_start,
        cycle_end=cycle_end,
        payout_date=cycle_end + timedelta(days=1),
        amount_cents=amount + 1 if wrong_total else amount,
        total_minutes=60,
        session_count=1,
        source_sha256="1" * 64,
        actor_id=graph["owner_id"],
        actor_name="Owner",
    )
    session.add(approval)
    session.flush()
    line = RemunerationLine(
        approval_id=approval.id,
        trainer_id=graph["trainer_id"],
        session_id=booking.id,
        client_id=booking.client_id,
        purchase_id=booking.purchase_id,
        client_name="Client One",
        client_kind="individual",
        training_date=booking.training_date,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        session_version=booking.version,
        acknowledgement_id=acknowledgement.id,
        acknowledgement_method="signature",
        band=band,
        minutes=60,
        amount_cents=amount,
        source_sha256="2" * 64,
    )
    session.add(line)
    session.flush()
    return approval, line


def test_approval_totals_reconcile_atomically_with_lines(domain_db, graph):
    with pytest.raises(IntegrityError, match="reconcile"), domain_db.transaction() as session:
        approved(session, graph, wrong_total=True)
    with domain_db.transaction() as session:
        assert count(session, RemunerationApproval) == count(session, RemunerationLine) == 0
        assert session.get(TrainingSession, graph["session_id"]).status == "scheduled"


@pytest.mark.parametrize("operation", ["header", "line", "delete", "append"])
def test_approved_pay_cannot_change_after_commit(domain_db, graph, operation):
    with domain_db.transaction() as session:
        approval, line = approved(session, graph)
        approval_id, line_id, amount = approval.id, line.id, approval.amount_cents
    with pytest.raises(IntegrityError), domain_db.transaction() as session:
        if operation == "header":
            session.get(RemunerationApproval, approval_id).amount_cents += 100
        elif operation == "line":
            session.get(RemunerationLine, line_id).amount_cents += 100
        elif operation == "delete":
            session.delete(session.get(RemunerationLine, line_id))
        else:
            source = session.get(RemunerationLine, line_id)
            copied = {
                column.name: getattr(source, column.name)
                for column in RemunerationLine.__table__.c
                if column.name not in ("id", "created_at")
            }
            session.add(RemunerationLine(id=uuid4(), **copied))
    with domain_db.transaction() as session:
        trainer = session.get(Trainer, graph["trainer_id"])
        trainer.peak_rate_cents += 100
        trainer.off_peak_rate_cents += 100
    with domain_db.transaction() as session:
        assert session.get(RemunerationApproval, approval_id).amount_cents == amount
        assert session.get(RemunerationLine, line_id).amount_cents == amount


@pytest.mark.parametrize("kind", ["session_time", "session_trainer", "fixed_weekly_schedule"])
def test_requests_cannot_omit_their_typed_target(domain_db, graph, kind):
    with pytest.raises(IntegrityError), domain_db.transaction() as session:
        session.add(
            ChangeRequest(
                kind=kind,
                trainer_id=graph["trainer_id"],
                expected_version=1,
                actor_id=graph["user_id"],
                actor_name="Trainer",
            )
        )


def test_media_expiry_and_identity_survive_deletion_retries(domain_db, graph):
    with domain_db.transaction() as session:
        item = ExercisePlanItem(session_id=graph["session_id"], position=1, name="Squat")
        session.add(item)
        session.flush()
        expires = session.scalar(select(func.now())) + timedelta(days=7)
        media = MediaAsset(
            purpose="session_video",
            status="ready",
            bucket="private-local-test",
            object_key=str(uuid4()),
            original_filename="training.mp4",
            content_type="video/mp4",
            size_bytes=1024,
            content_sha256="a" * 64,
            uploaded_by=graph["owner_id"],
            client_id=graph["client_id"],
            purchase_id=graph["purchase_id"],
            session_id=graph["session_id"],
            original_session_id=graph["session_id"],
            original_plan_item_id=item.id,
            expires_at=expires,
        )
        session.add(media)
        session.flush()
        identity = media.id
    with pytest.raises(IntegrityError, match="immutable field"), domain_db.transaction() as session:
        session.get(MediaAsset, identity).expires_at = expires + timedelta(days=7)
    with domain_db.transaction() as session:
        session.get(MediaAsset, identity).status = "delete_pending"
        job = MediaDeletion(media_id=identity, reason="removed")
        session.add(job)
        session.flush()
        job_id = job.id
    with domain_db.transaction() as session:
        job = session.get(MediaDeletion, job_id)
        job.attempts += 1
        job.error_code = "TEMPORARY_STORAGE_ERROR"
    with domain_db.transaction() as session:
        media = session.get(MediaAsset, identity)
        job = session.get(MediaDeletion, job_id)
        assert media.expires_at == expires and media.status == "delete_pending"
        assert job.status == "pending" and job.attempts == 1 and job.completed_at is None
    with pytest.raises(IntegrityError), domain_db.transaction() as session:
        session.add(MediaDeletion(media_id=identity, reason="removed"))


def test_future_acknowledgement_is_rejected_using_database_clock(domain_db, graph):
    with domain_db.transaction() as session:
        future = session.scalar(
            text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date")
        ) + timedelta(days=1)
        booking = session.get(TrainingSession, graph["session_id"])
        booking.training_date = future
    from app.persistence import PersistenceConflict

    with pytest.raises(PersistenceConflict), domain_db.transaction() as session:
        acknowledge(session, graph["session_id"], 2, graph["owner_id"], method="late_no_show")
