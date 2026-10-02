"""Internal assessment storage. Authorize before calling; M5.4 owns HTTP/access policy.

Explicit saves append snapshots, not keystrokes. The caller owns the outer transaction.
Database triggers derive names, dates of birth and recording timestamps from stored data.
No browser importer, HTTP routes, clinical scoring or training clearance is supplied here.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessment_validation import validate_answers
from app.models.assessments import (
    AssessmentFormVersion,
    ClientAssessment,
    ClientAssessmentRevision,
)
from app.models.people import Client, ClientPerson, StaffUser
from app.persistence import PersistenceConflict, require_transaction, reviewed


def _active_person(session: Session, person_id: UUID) -> ClientPerson:
    identity = session.get(ClientPerson, person_id)
    if identity is None:
        raise PersistenceConflict("Assessment person is unavailable")
    # Follow existing aggregate lock order: client, then its person, then assessment.
    client = session.scalar(
        select(Client)
        .where(Client.id == identity.client_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    person = session.scalar(
        select(ClientPerson)
        .where(ClientPerson.id == person_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if client is None or person is None or client.status != "active":
        raise PersistenceConflict("Assessment person is inactive or unavailable")
    return person


def _record(
    session: Session,
    assessment: ClientAssessment,
    actor_id: UUID,
    assessment_date: date,
    answers: object,
    event: str,
    reason: str | None,
) -> ClientAssessmentRevision:
    if type(assessment_date) is not date:
        raise ValueError("A calendar assessment date is required")
    if event not in {"draft", "completed", "correction", "voided"}:
        raise ValueError("Unsupported assessment event")
    actor = session.get(StaffUser, actor_id, populate_existing=True)
    if actor is None or actor.status != "active":
        raise PersistenceConflict("Active recording staff required")
    definition = session.get(AssessmentFormVersion, (assessment.form_id, assessment.form_version))
    if definition is None:
        raise ValueError("Unknown assessment form version")
    previous = session.scalar(
        select(ClientAssessmentRevision).where(
            ClientAssessmentRevision.assessment_id == assessment.id,
            ClientAssessmentRevision.revision == assessment.version - 1,
        )
    )
    prior_status = previous.status if previous else None
    valid_events = {
        None: {"draft"},
        "draft": {"draft", "completed", "voided"},
        "completed": {"correction", "voided"},
        "voided": set(),
    }
    if event not in valid_events[prior_status]:
        raise PersistenceConflict("Assessment state changed; review its current revision")
    if event in {"correction", "voided"}:
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 2000 or "\x00" in reason:
            raise ValueError("A correction or void reason is required")
        reason = reason.strip()
    elif reason is not None:
        raise ValueError("A reason is only valid for a correction or void")
    if event == "voided":
        if answers != previous.answers or assessment_date != previous.assessment_date:
            raise ValueError("Voiding must preserve the prior answers and assessment date")
    validated = validate_answers(
        answers, definition.definition, completed=event in {"completed", "correction"}
    )
    person = session.get(ClientPerson, assessment.client_person_id)
    revision = ClientAssessmentRevision(
        assessment_id=assessment.id,
        revision=assessment.version,
        previous_revision=assessment.version - 1 if previous else None,
        form_id=assessment.form_id,
        form_version=assessment.form_version,
        status="completed" if event in {"completed", "correction"} else event,
        event=event,
        assessment_date=assessment_date,
        actor_id=actor_id,
        actor_name=actor.name,
        assessor_id=actor_id,
        assessor_name=actor.name,
        client_name=person.name,
        client_birthday=person.birthday,
        answers=validated,
        reason=reason,
    )
    session.add(revision)
    session.flush()
    session.refresh(revision)  # Return server-derived snapshots, including corrections.
    return revision


def create_assessment(
    session: Session,
    person_id: UUID,
    form_id: str,
    form_version: int,
    actor_id: UUID,
    assessment_date: date,
    answers: object,
) -> ClientAssessmentRevision:
    require_transaction(session)
    _active_person(session, person_id)
    if type(form_version) is not int or form_version < 1:
        raise ValueError("A positive form version is required")
    if session.get(AssessmentFormVersion, (form_id, form_version)) is None:
        raise ValueError("Unknown assessment form version")
    assessment = ClientAssessment(
        client_person_id=person_id,
        form_id=form_id,
        form_version=form_version,
        actor_id=actor_id,
        actor_name="Server snapshot",
    )
    session.add(assessment)
    session.flush()
    return _record(session, assessment, actor_id, assessment_date, answers, "draft", None)


def save_assessment(
    session: Session,
    assessment_id: UUID,
    expected_version: int,
    actor_id: UUID,
    assessment_date: date,
    answers: object,
    *,
    event: str = "draft",
    reason: str | None = None,
) -> ClientAssessmentRevision:
    require_transaction(session)
    identity = session.get(ClientAssessment, assessment_id)
    if identity is None:
        raise PersistenceConflict("Assessment is unavailable")
    _active_person(session, identity.client_person_id)
    assessment = reviewed(session, ClientAssessment, assessment_id, expected_version)
    assessment.version += 1
    session.flush()
    return _record(session, assessment, actor_id, assessment_date, answers, event, reason)
