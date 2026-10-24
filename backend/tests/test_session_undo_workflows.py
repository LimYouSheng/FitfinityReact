"""Compensation across real scheduling, assignment and lifecycle owners."""

import pytest
from sqlalchemy import func, select

from app.models.people import Client, LifecycleEvent, StaffUser, Trainer
from app.models.training import AssignmentEvent, CreditDebit, PackagePurchase, TrainingSession
from tests import test_client_assignment_save as assignment
from tests import test_client_deactivation_api as deactivation
from tests import test_client_reactivation_save as reactivation
from tests import test_session_booking_api as booking
from tests import test_session_postponement_api as postponement
from tests import test_trainer_reactivation as trainer_reactivation
from tests.test_client_assignment_review import replacement as replacement
from tests.test_session_postponement_api import future as future
from tests.test_session_undo_api import latest, undo, undo_review
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


@pytest.mark.parametrize("kind", ["booking", "postpone"])
def test_scheduling_compensation_restores_dates_ids_numbers_and_credits(
    api, graph, domain_db, future, kind
):
    with domain_db.transaction() as session:
        before = {
            row.id: (row.training_date, row.starts_at, row.ends_at, row.session_number, row.version)
            for row in session.scalars(select(TrainingSession))
        }
    if kind == "booking":
        result = booking.save(api, graph["session_id"], booking.payload(api, graph["session_id"]))
    else:
        result = postponement.save(api, graph, postponement.review(api, graph))
    assert result.status_code == 200, result.text
    mutation = latest(domain_db)
    restored = undo(api, mutation, undo_review(api, mutation))
    assert restored.status_code == 200, restored.text
    with domain_db.transaction() as session:
        rows = session.scalars(select(TrainingSession)).all()
        assert {r.id for r in rows} == set(before)
        for row in rows:
            assert (row.training_date, row.starts_at, row.ends_at, row.session_number) == before[
                row.id
            ][:4]
            assert row.version >= before[row.id][4]
        assert session.scalar(select(func.count()).select_from(CreditDebit)) == 0


@pytest.mark.parametrize("reactivate", [False, True])
def test_client_lifecycle_undo_preserves_cause_history_and_purchase_terms(
    api, graph, domain_db, reactivate
):
    with domain_db.transaction() as session:
        purchase = session.get(PackagePurchase, graph["purchase_id"])
        terms = (
            purchase.start_date,
            purchase.end_date,
            purchase.total_sessions,
            purchase.purchased_trainer_id,
        )
    result = deactivation.save(api, graph, deactivation.command(deactivation.review(api, graph)))
    assert result.status_code == 200, result.text
    if reactivate:
        result = reactivation.save(api, graph, reactivation.body(api, graph))
        assert result.status_code == 200, result.text
    mutation = latest(domain_db)
    restored = undo(api, mutation, undo_review(api, mutation))
    assert restored.status_code == 200, restored.text
    with domain_db.transaction() as session:
        client, purchase = (
            session.get(Client, graph["client_id"]),
            session.get(PackagePurchase, graph["purchase_id"]),
        )
        assert client.status == purchase.status == ("inactive" if reactivate else "active")
        assert (
            purchase.start_date,
            purchase.end_date,
            purchase.total_sessions,
            purchase.purchased_trainer_id,
        ) == terms
        effect = session.get(LifecycleEvent, purchase.lifecycle_event_id)
        assert effect.cause_id == client.lifecycle_event_id
        assert effect.reason == ("client" if reactivate else "client_reactivated")
        assert session.scalar(select(func.count()).select_from(LifecycleEvent)) == (
            6 if reactivate else 4
        )


def test_assignment_undo_appends_compensation_instead_of_erasing_original_history(
    api, graph, domain_db, replacement
):
    result = assignment.save(api, graph, assignment.payload(api, graph, replacement))
    assert result.status_code == 200, result.text
    mutation = latest(domain_db)
    restored = undo(api, mutation, undo_review(api, mutation))
    assert restored.status_code == 200, restored.text
    with domain_db.transaction() as session:
        assert session.get(Client, graph["client_id"]).trainer_id == graph["trainer_id"]
        assert session.get(PackagePurchase, graph["purchase_id"]).trainer_id == graph["trainer_id"]
        history = session.scalars(
            select(AssignmentEvent).order_by(AssignmentEvent.created_at)
        ).all()
        assert [(r.old_trainer_id, r.new_trainer_id) for r in history] == [
            (graph["trainer_id"], replacement),
            (replacement, graph["trainer_id"]),
        ]


def test_trainer_reactivation_undo_preserves_account_identity_and_status_history(
    api, graph, domain_db
):
    with domain_db.transaction() as session:
        for row in session.scalars(select(TrainingSession)):
            row.status = "cancelled"
    trainer_reactivation.deactivate(domain_db, graph)
    result = trainer_reactivation.save(api, graph)
    assert result.status_code == 200, result.text
    mutation = latest(domain_db)
    restored = undo(api, mutation, undo_review(api, mutation))
    assert restored.status_code == 200, restored.text
    with domain_db.transaction() as session:
        trainer, user = (
            session.get(Trainer, graph["trainer_id"]),
            session.get(StaffUser, graph["user_id"]),
        )
        assert trainer.status == user.status == "inactive"
        assert trainer.user_id == user.id and trainer.version > 3 and user.version > 3
        assert session.scalar(select(func.count()).select_from(LifecycleEvent)) == 2


def test_weekly_undo_uses_weekly_autonomy_and_restores_purchased_slots(
    api, graph, domain_db, future, auth_settings, auth_service, fake_cognito
):
    from app.models.training import PurchaseScheduleSlot
    from tests import test_client_weekly_schedule as weekly
    from tests.test_staff_api import trainer_login

    with domain_db.transaction() as session:
        trainer = session.get(Trainer, graph["trainer_id"])
        trainer.approve_weekly_schedule = False
        trainer.approve_session_time = True
        before = {
            r.id: (r.weekday, r.starts_at, r.ends_at)
            for r in session.scalars(select(PurchaseScheduleSlot))
        }
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    result = weekly.save(api, graph, weekly.payload(api, graph))
    assert result.status_code == 200 and result.json()["outcome"] == "applied", result.text
    mutation = latest(domain_db)
    restored = undo(api, mutation, undo_review(api, mutation))
    assert restored.status_code == 200, restored.text
    with domain_db.transaction() as session:
        assert {
            r.id: (r.weekday, r.starts_at, r.ends_at)
            for r in session.scalars(select(PurchaseScheduleSlot))
        } == before


def test_trainer_deactivation_undo_restores_identity_and_bookings(
    api, graph, domain_db, replacement, future
):
    from tests import test_trainer_deactivation as deactivation

    result = deactivation.save(api, graph, deactivation.payload(api, graph, replacement))
    assert result.status_code == 200, result.text
    mutation = latest(domain_db)
    restored = undo(api, mutation, undo_review(api, mutation))
    assert restored.status_code == 200, restored.text
    with domain_db.transaction() as session:
        trainer = session.get(Trainer, graph["trainer_id"])
        assert trainer.status == session.get(StaffUser, trainer.user_id).status == "active"
        assert trainer.user_id == graph["user_id"]
        assert all(r.trainer_id == trainer.id for r in session.scalars(select(TrainingSession)))
        assert session.scalar(select(func.count()).select_from(LifecycleEvent)) == 2
