"""Owner-scoped assessment use cases. Outer authenticated transaction owns atomicity."""

import hashlib
import json
from functools import wraps
from uuid import UUID

from sqlalchemy import select, text

from app.api.schemas import AssessmentRevision, ClientAssessmentRecords, PersonAssessmentRecords
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
    values = body.model_dump(mode="json")
    # Preserve hashes of existing receipts created before these optional review fields existed.
    for field in ("previousAssessmentId", "expectedPreviousVersion"):
        if values.get(field) is None:
            values.pop(field, None)
    if operation == "assessment_save" and values.get("expectedPersonVersion") is None:
        values.pop("expectedPersonVersion", None)
    payload = json.dumps(
        {"operation": operation, "target": str(target), "body": values},
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
    previous_occasion = session.scalar(
        select(ClientAssessment)
        .where(
            ClientAssessment.client_person_id == person_id, ClientAssessment.form_id == body.formId
        )
        .order_by(ClientAssessment.created_at.desc(), ClientAssessment.id.desc())
        .limit(1)
    )
    if previous_occasion:
        if body.previousAssessmentId is None:
            raise AuthError(
                "assessment_exists", "This form already has a record. Open its saved history.", 409
            )
        previous_revision = session.scalar(
            select(ClientAssessmentRevision).where(
                ClientAssessmentRevision.assessment_id == previous_occasion.id,
                ClientAssessmentRevision.revision == previous_occasion.version,
            )
        )
        if (
            previous_occasion.id != body.previousAssessmentId
            or previous_occasion.version != body.expectedPreviousVersion
            or previous_revision.status == "draft"
        ):
            raise conflict()
    elif body.previousAssessmentId is not None:
        raise conflict()
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
    if body.expectedPersonVersion is not None and person.version != body.expectedPersonVersion:
        raise conflict()
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


def reconcile(session, principal, key):
    principal.operations()
    # authorized_transaction holds this actor's auth-account lock, serializing writes and reads.
    previous = session.scalar(
        select(ApiReceipt).where(
            ApiReceipt.actor_id == principal.user_id,
            ApiReceipt.request_key == key,
        )
    )
    if previous is None:
        raise unavailable()
    revision = session.get(ClientAssessmentRevision, previous.revision_id)
    person, record = assessment_record(session, principal, revision.assessment_id)
    audit(session, principal, person.id, "replay", record.id)
    return AssessmentRevision.model_validate(revision)


def current_records(session, principal, client_id):
    principal.operations()
    client = client_record(session, principal, client_id)
    people = session.scalars(
        select(ClientPerson)
        .where(
            ClientPerson.client_id == client_id,
        )
        .order_by(ClientPerson.position)
        .with_for_update(read=True)
    ).all()
    result = []
    for person in people:
        # One current revision per form's newest occasion. Later corrections to an older
        # occasion cannot replace the newest occasion in the profile overview.
        records = session.scalars(
            select(ClientAssessmentRevision)
            .join(
                ClientAssessment,
                (ClientAssessment.id == ClientAssessmentRevision.assessment_id)
                & (ClientAssessment.version == ClientAssessmentRevision.revision),
            )
            .where(ClientAssessment.client_person_id == person.id)
            .distinct(ClientAssessment.form_id)
            .order_by(
                ClientAssessment.form_id,
                ClientAssessment.created_at.desc(),
                ClientAssessment.id.desc(),
            )
        ).all()
        audit(session, principal, person.id, "list")
        result.append(
            PersonAssessmentRecords(
                id=person.id,
                version=person.version,
                records=[AssessmentRevision.model_validate(record) for record in records],
            )
        )
    day = session.scalar(text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date"))
    return ClientAssessmentRecords(
        id=client.id, version=client.version, businessDate=day, people=result
    )
