"""Owner-scoped assessment use cases. Outer authenticated transaction owns atomicity."""

import hashlib
import json
from functools import wraps
from uuid import UUID

from sqlalchemy import select, text

from app.api.schemas import AssessmentRevision
from app.assessment_persistence import create_assessment, save_assessment
from app.auth.errors import AuthError
from app.authorization import client_record, conflict, unavailable
from app.models.api import ApiReceipt, AssessmentAccess
from app.models.assessments import ClientAssessment, ClientAssessmentRevision
from app.models.people import ClientPerson
from app.persistence import PersistenceConflict


def person_record(session, principal, person_id, *, write=False):
    principal.operations()  # Sensitive health access is not inherited from historical assignment.
    found = session.get(ClientPerson, person_id)
    if found is None:
        raise unavailable()
    client_record(session, principal, found.client_id, write=write)
    return session.scalar(
        select(ClientPerson)
        .where(ClientPerson.id == person_id)
        .with_for_update(read=not write)
        .execution_options(populate_existing=True)
    )


def assessment_record(session, principal, identity, *, write=False):
    principal.operations()
    found = session.get(ClientAssessment, identity)
    if found is None:
        raise unavailable()
    person = person_record(session, principal, found.client_person_id, write=write)
    record = session.scalar(
        select(ClientAssessment)
        .where(ClientAssessment.id == identity)
        .with_for_update(read=not write)
        .execution_options(populate_existing=True)
    )
    return person, record


def audit(session, principal, person_id, action, assessment_id=None):
    session.add(
        AssessmentAccess(
            client_person_id=person_id,
            action=action,
            assessment_id=assessment_id,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )


def replay(session, principal, key: UUID, operation, target, body):
    # The auth-account lock serializes one actor's requests before checking this unique key.
    payload = json.dumps(
        {"operation": operation, "target": str(target), "body": body.model_dump(mode="json")},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    receipt = session.scalar(
        select(ApiReceipt).where(
            ApiReceipt.actor_id == principal.user_id, ApiReceipt.request_key == key
        )
    )
    if receipt and (receipt.operation != operation or receipt.request_sha256 != digest):
        raise AuthError(
            "idempotency_conflict", "This request key was already used for another request.", 409
        )
    return receipt, digest


def remember(session, principal, key, operation, digest, revision):
    session.add(
        ApiReceipt(
            request_key=key,
            operation=operation,
            request_sha256=digest,
            revision_id=revision.id,
            actor_id=principal.user_id,
            actor_name=principal.name,
        )
    )
    return AssessmentRevision.model_validate(revision)


def safe_answers(fn):
    @wraps(fn)
    def run(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except PersistenceConflict:
            raise conflict() from None
        except (ValueError, UnicodeError):
            raise AuthError("validation_error", "Request validation failed.", 422) from None

    return run


@safe_answers
def create(session, principal, person_id, key, body):
    person = person_record(session, principal, person_id, write=True)
    previous, digest = replay(session, principal, key, "assessment_create", person_id, body)
    if previous:
        revision = session.get(ClientAssessmentRevision, previous.revision_id)
        audit(session, principal, person_id, "replay", revision.assessment_id)
        return AssessmentRevision.model_validate(revision)
    if person.version != body.expectedPersonVersion:
        raise conflict()
    if session.scalar(
        select(ClientAssessment.id)
        .where(
            ClientAssessment.client_person_id == person_id, ClientAssessment.form_id == body.formId
        )
        .limit(1)
    ):
        raise AuthError(
            "assessment_exists", "This form already has a record. Open its saved history.", 409
        )
    day = session.scalar(text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date"))
    revision = create_assessment(
        session, person_id, body.formId, body.formVersion, principal.user_id, day, body.answers
    )
    if body.event == "completed":
        revision = save_assessment(
            session,
            revision.assessment_id,
            revision.revision,
            principal.user_id,
            day,
            body.answers,
            event="completed",
        )
    audit(session, principal, person_id, "create", revision.assessment_id)
    return remember(session, principal, key, "assessment_create", digest, revision)


@safe_answers
def save(session, principal, assessment_id, key, body):
    person, record = assessment_record(session, principal, assessment_id, write=True)
    previous, digest = replay(session, principal, key, "assessment_save", assessment_id, body)
    if previous:
        audit(session, principal, person.id, "replay", assessment_id)
        return AssessmentRevision.model_validate(
            session.get(ClientAssessmentRevision, previous.revision_id)
        )
    current = session.scalar(
        select(ClientAssessmentRevision).where(
            ClientAssessmentRevision.assessment_id == record.id,
            ClientAssessmentRevision.revision == record.version,
        )
    )
    revision = save_assessment(
        session,
        record.id,
        body.expectedVersion,
        principal.user_id,
        current.assessment_date,
        body.answers,
        event=body.event,
        reason=body.reason,
    )
    audit(session, principal, person.id, "save", record.id)
    return remember(session, principal, key, "assessment_save", digest, revision)
