"""Small, deterministic relational fixtures; all records live in the isolated test database."""

from datetime import date, time, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.database import Database
from app.models.people import Client, ClientPerson, StaffUser, Trainer
from app.models.training import (
    PackagePurchase,
    PackageTemplate,
    PackageTemplateRevision,
    PurchaseScheduleSlot,
    TrainingSession,
)
from app.persistence import add_client, add_purchase


@pytest.fixture
def domain_db(database_settings, migrate):
    migrate()
    db = Database(database_settings)
    yield db
    db.close()


def person(name="Client One"):
    return ClientPerson(
        name=name,
        email="client@example.test",
        phone_country_code="+65",
        phone_number="91234567",
        birthday=date(1990, 1, 1),
        gender="Other",
        emergency_name="Contact One",
        emergency_relationship="Friend",
        emergency_country_code="+65",
        emergency_number="91234568",
    )


def purchase_parts(graph, start_date=None, *, client_id=None, stage="queued"):
    start = start_date or graph["end_date"] + timedelta(days=1)
    client = client_id or graph["client_id"]
    slot_id = uuid4()
    purchase = PackagePurchase(
        client_id=client,
        template_id=graph["template_id"],
        template_revision=1,
        name="Two sessions",
        total_sessions=2,
        validity_days=90,
        sessions_per_week=1,
        free_gym=False,
        start_date=start,
        end_date=start + timedelta(days=89),
        purchased_trainer_id=graph["trainer_id"],
        trainer_id=graph["trainer_id"],
        stage=stage,
    )
    slot = PurchaseScheduleSlot(
        id=slot_id,
        weekday=start.weekday(),
        starts_at=time(10),
        ends_at=time(11),
        purchased_weekday=start.weekday(),
        purchased_starts_at=time(10),
        purchased_ends_at=time(11),
    )
    bookings = [
        TrainingSession(
            client_id=client,
            trainer_id=graph["trainer_id"],
            session_number=number,
            schedule_slot_id=slot_id,
            training_date=start + timedelta(days=(number - 1) * 7),
            starts_at=time(10),
            ends_at=time(11),
        )
        for number in (1, 2)
    ]
    return purchase, [slot], [], bookings


@pytest.fixture
def graph(domain_db):
    with domain_db.transaction() as session:
        owner = StaffUser(name="Owner Original", email="owner@example.test", role="owner")
        user = StaffUser(name="Trainer One", email="trainer@example.test", role="trainer")
        session.add_all([owner, user])
        session.flush()
        trainer = Trainer(
            user_id=user.id,
            name=user.name,
            email=user.email,
            birthday=date(1985, 1, 1),
            phone_country_code="+65",
            phone_number="91234569",
            gender="Other",
            trainer_type="Strength",
            peak_rate_cents=8000,
            off_peak_rate_cents=5500,
        )
        session.add(trainer)
        session.flush()
        client = add_client(
            session, Client(kind="individual", name="Client One", trainer_id=trainer.id), [person()]
        )
        template = PackageTemplate()
        session.add(template)
        session.flush()
        session.add(
            PackageTemplateRevision(
                template_id=template.id,
                revision=1,
                name="Two sessions",
                total_sessions=2,
                validity_days=90,
                actor_id=owner.id,
                actor_name=owner.name,
            )
        )
        session.flush()
        today = session.scalar(
            text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date")
        )
        start = (today.replace(day=1) - timedelta(days=45)).replace(day=16)
        values = {
            "owner_id": owner.id,
            "user_id": user.id,
            "trainer_id": trainer.id,
            "client_id": client.id,
            "template_id": template.id,
            "start_date": start,
            "end_date": start + timedelta(days=89),
        }
        purchase, slots, preferences, bookings = purchase_parts(values, start, stage="current")
        add_purchase(session, purchase, slots, preferences, bookings, expected_client_version=1)
        values.update(
            purchase_id=purchase.id,
            session_id=bookings[0].id,
            second_session_id=bookings[1].id,
            client_version=client.version,
        )
        return values
