"""Real PostgreSQL assessment history, atomic saves and independent writers."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.assessment_persistence import create_assessment, save_assessment
from app.database import Database
from app.models.assessments import (
    AssessmentFormVersion,
    ClientAssessment,
    ClientAssessmentRevision,
)
from app.models.people import Client, ClientPerson, StaffUser
from app.persistence import PersistenceConflict, add_client
from tests.domain_fixtures import person

pytestmark = pytest.mark.database
DAY = date(2026, 9, 21)


@pytest.fixture
def assessment(domain_db, graph):
    with domain_db.transaction() as session:
        person_id = session.scalar(
            select(ClientPerson.id).where(ClientPerson.client_id == graph["client_id"])
        )
        record = create_assessment(
            session, person_id, "balance", 1, graph["owner_id"], DAY, {"eyes_open_1": 0}
        )
        return {"id": record.assessment_id, "person_id": person_id, "first": record.id}


def change(session, graph, assessment, version, *, event="draft", answers=None, reason=None):
    return save_assessment(
        session,
        assessment["id"],
        version,
        graph["owner_id"],
        DAY,
        {"eyes_open_1": 3.5} if answers is None else answers,
        event=event,
        reason=reason,
    )


def test_migration_preserves_populated_m53_and_legacy_notes(domain_db, graph, migrate):
    with domain_db.transaction() as session:
        client_person = session.scalar(select(ClientPerson))
        client_person.health_notes = "Historical owner note; do not infer answers"
        identity = client_person.id
    migrate("downgrade", "20260915_0003")
    migrate()
    migrate()
    with domain_db.transaction() as session:
        assert session.get(ClientPerson, identity).health_notes.startswith("Historical owner")
        assert session.scalar(select(func.count()).select_from(Client)) == 1
        assert session.scalar(select(func.count()).select_from(AssessmentFormVersion)) == 11
        assert session.scalar(select(func.count()).select_from(ClientAssessment)) == 0
        assert session.scalar(text("SELECT count(*) FROM training_sessions")) == 2
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "20260924_0006"


def test_saved_assessment_prevents_destructive_downgrade(domain_db, assessment, migrate):
    with pytest.raises(DBAPIError, match="assessment downgrade refused"):
        migrate("downgrade", "20260915_0003")
    with domain_db.transaction() as session:
        assert session.get(ClientAssessmentRevision, assessment["first"]).answers == {
            "eyes_open_1": 0
        }
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "20260924_0006"


def test_draft_completion_correction_preserves_submitted_names_and_values(
    domain_db, graph, assessment
):
    with domain_db.transaction() as session:
        completed = change(session, graph, assessment, 1, event="completed")
        completed_id = completed.id
        assert completed.actor_name == completed.assessor_name == "Owner Original"
        assert completed.client_name == "Client One"
    with domain_db.transaction() as session:
        session.get(ClientPerson, assessment["person_id"]).name = "Renamed client"
        session.get(StaffUser, graph["owner_id"]).name = "Renamed owner"
    with domain_db.transaction() as session:
        corrected = change(
            session,
            graph,
            assessment,
            2,
            event="correction",
            reason="Corrected transcription",
            answers={"eyes_open_1": 4},
        )
        assert corrected.actor_name == "Renamed owner"
        assert corrected.assessor_name == "Owner Original"
        assert corrected.client_name == "Client One"
        assert corrected.client_birthday == date(1990, 1, 1)
        assert corrected.previous_revision == 2 and corrected.revision == 3
        assert corrected.created_at.tzinfo is not None
        original = session.get(ClientAssessmentRevision, completed_id)
        assert original.answers == {"eyes_open_1": 3.5}
        assert original.actor_name == "Owner Original"
        assert session.get(ClientAssessment, assessment["id"]).version == 3


def test_void_preserves_evidence_and_cannot_reopen(domain_db, graph, assessment):
    with domain_db.transaction() as session:
        result = change(
            session,
            graph,
            assessment,
            1,
            event="voided",
            reason="Wrong assessment occasion",
            answers={"eyes_open_1": 0},
        )
        assert result.status == "voided" and result.answers == {"eyes_open_1": 0}
    with pytest.raises(PersistenceConflict), domain_db.transaction() as session:
        change(session, graph, assessment, 2)
    with domain_db.transaction() as session:
        assert session.get(ClientAssessment, assessment["id"]).version == 2


@pytest.mark.parametrize("action", ["revision_edit", "revision_delete", "root_delete", "form_edit"])
def test_history_and_form_definitions_are_immutable(domain_db, assessment, action):
    with pytest.raises(IntegrityError, match="immutable"), domain_db.transaction() as session:
        if action == "revision_edit":
            session.get(ClientAssessmentRevision, assessment["first"]).answers = {"eyes_open_1": 99}
        elif action == "revision_delete":
            session.delete(session.get(ClientAssessmentRevision, assessment["first"]))
        elif action == "root_delete":
            session.delete(session.get(ClientAssessment, assessment["id"]))
        else:
            session.get(AssessmentFormVersion, ("balance", 1)).title = "Rewritten definition"


@pytest.mark.parametrize("action", ["missing_revision", "wrong_person", "wrong_form", "stale"])
def test_root_and_revision_cannot_diverge(domain_db, graph, assessment, action):
    failure = PersistenceConflict if action == "stale" else IntegrityError
    with pytest.raises(failure), domain_db.transaction() as session:
        if action == "stale":
            change(session, graph, assessment, 9)
        else:
            root = session.get(ClientAssessment, assessment["id"])
            root.version += 1
            if action == "wrong_person":
                root.client_person_id = uuid4()
            elif action == "wrong_form":
                root.form_id = "hurdle_step"
    with domain_db.transaction() as session:
        assert session.get(ClientAssessment, assessment["id"]).version == 1
        assert session.scalar(select(func.count()).select_from(ClientAssessmentRevision)) == 1


@pytest.mark.parametrize(
    "answers", [{}, {"eyes_open_1": "5"}, {"eyes_open_1": -1}, {"notes": "old"}]
)
def test_failed_completion_rolls_back_pointer_and_revision(domain_db, graph, assessment, answers):
    with pytest.raises(ValueError), domain_db.transaction() as session:
        change(session, graph, assessment, 1, event="completed", answers=answers)
    with domain_db.transaction() as session:
        assert session.get(ClientAssessment, assessment["id"]).version == 1
        assert session.scalar(select(func.count()).select_from(ClientAssessmentRevision)) == 1


def test_unchecked_hurdle_and_new_reassessment_remain_separate(domain_db, graph, assessment):
    with domain_db.transaction() as session:
        draft = create_assessment(
            session, assessment["person_id"], "hurdle_step", 1, graph["owner_id"], DAY, {}
        )
        result = save_assessment(
            session, draft.assessment_id, 1, graph["owner_id"], DAY, {}, event="completed"
        )
        assert result.answers == {} and result.status == "completed"
        another = create_assessment(
            session, assessment["person_id"], "balance", 1, graph["owner_id"], DAY, {}
        )
        assert another.assessment_id != assessment["id"] and another.status == "draft"


def test_couple_people_and_history_are_independent(domain_db, graph):
    with domain_db.transaction() as session:
        first, second = person("Couple A"), person("Couple B")
        add_client(
            session,
            Client(kind="couple", name="Couple", trainer_id=graph["trainer_id"]),
            [first, second],
        )
        one = create_assessment(
            session, first.id, "balance", 1, graph["owner_id"], DAY, {"eyes_open_1": 1}
        )
        two = create_assessment(
            session, second.id, "balance", 1, graph["owner_id"], DAY, {"eyes_open_1": 2}
        )
        assert one.assessment_id != two.assessment_id
        assert one.client_name == "Couple A" and two.client_name == "Couple B"
        assert one.answers != two.answers


@pytest.mark.parametrize(
    "failure", ["wrong_form", "bad_value", "wrong_previous", "skip_revision", "blank_completion"]
)
def test_raw_sql_cannot_bypass_revision_and_answer_checks(domain_db, graph, assessment, failure):
    with pytest.raises(IntegrityError), domain_db.transaction() as session:
        session.execute(
            text("UPDATE client_assessments SET version=version+1 WHERE id=:id"),
            {"id": assessment["id"]},
        )
        original = session.get(ClientAssessmentRevision, assessment["first"])
        values = {
            column.name: getattr(original, column.name)
            for column in ClientAssessmentRevision.__table__.columns
        }
        values.update(id=uuid4(), revision=2, previous_revision=1)
        if failure == "wrong_form":
            values["form_id"] = "hurdle_step"
        elif failure == "bad_value":
            values["answers"] = {"eyes_open_1": "5"}
        elif failure == "wrong_previous":
            values["previous_revision"] = None
        elif failure == "skip_revision":
            values["revision"] = 3
        else:
            values.update(status="completed", event="completed", answers={})
        session.execute(ClientAssessmentRevision.__table__.insert().values(**values))
    with domain_db.transaction() as session:
        assert session.get(ClientAssessment, assessment["id"]).version == 1


def test_two_reviewed_assessment_writers_commit_one_revision(
    database_settings, domain_db, graph, assessment
):
    barrier = Barrier(2)

    def write():
        db = Database(database_settings)
        try:
            with db.transaction() as session:
                barrier.wait(timeout=3)
                change(session, graph, assessment, 1, event="completed")
            return "committed"
        except PersistenceConflict:
            return "conflict"
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(lambda _: write(), range(2))) == ["committed", "conflict"]
    with domain_db.transaction() as session:
        assert session.get(ClientAssessment, assessment["id"]).version == 2
        assert session.scalar(select(func.count()).select_from(ClientAssessmentRevision)) == 2
