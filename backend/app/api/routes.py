"""Versioned staff contracts; M6 adds domain workflow orchestration and the React API adapter."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, Query, Request
from sqlalchemy import select

from app.api import (
    assessments,
    client_creation,
    client_details,
    client_matching,
    client_notes,
    content,
    directory,
    packages,
    trainer_approvals,
    trainer_details,
    trainer_rates,
    trainer_reactivation,
)
from app.api.dependencies import authorized_transaction
from app.api.schemas import (
    ERROR_RESPONSES,
    AssessmentRevision,
    ClientAssessmentRecords,
    ClientDetail,
    ClientSummary,
    DirectoryPackage,
    DirectorySnapshot,
    FormDefinition,
    NewAssessment,
    Page,
    PersonSummary,
    SaveAssessment,
    ServerClock,
    SessionClient,
    SessionSummary,
    TrainerSummary,
)
from app.authorization import (
    client_record,
    client_scope,
    session_record,
    session_scope,
    trainer_record,
    unavailable,
)
from app.models.assessments import AssessmentFormVersion, ClientAssessment, ClientAssessmentRevision
from app.models.people import Client, ClientPerson, Trainer
from app.models.training import PackagePurchase, TrainingSession

router = APIRouter(prefix="/api", tags=["staff records"], responses=ERROR_RESPONSES)
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=10000)]
RequestKey = Annotated[
    UUID,
    Header(
        alias="Idempotency-Key",
        description="New UUID per save; retain the key and identical body for retries.",
    ),
]


@router.post(
    "/trainers/{trainer_id}/personal-details",
    response_model=trainer_rates.RateState,
    operation_id="saveTrainerDetails",
)
def save_trainer_details(
    trainer_id: UUID, body: trainer_details.SaveTrainerDetails, request: Request, key: RequestKey
):
    """Save reviewed profile fields without changing email, pay or account lifecycle."""
    with authorized_transaction(request, exclusive_user=True) as (session, principal):
        return trainer_details.save(session, principal, trainer_id, key, body)


@router.get(
    "/trainer-detail-saves/{request_key}",
    response_model=trainer_rates.RateState,
    operation_id="reconcileTrainerDetails",
)
def reconcile_trainer_details(request_key: UUID, request: Request):
    """Read this actor's immutable profile-save receipt before retrying an uncertain save."""
    with authorized_transaction(request) as (session, principal):
        return trainer_details.reconcile(session, principal, request_key)


def page(session, statement, model, limit, offset):
    records = session.scalars(statement.limit(limit + 1).offset(offset)).all()
    return {
        "items": [model.model_validate(record) for record in records[:limit]],
        "limit": limit,
        "offset": offset,
        "hasMore": len(records) > limit,
    }


@router.get("/clock", response_model=ServerClock, operation_id="staffClock")
def clock(request: Request):
    """Authenticated server clock; browser clocks cannot set assessment headers."""
    with authorized_transaction(request):
        now = datetime.now(UTC)
        return {
            "serverAt": now,
            "businessDate": now.astimezone(ZoneInfo("Asia/Singapore")).date(),
            "timeZone": "Asia/Singapore",
        }


@router.get("/clients", response_model=Page[ClientSummary], operation_id="listClients")
def clients(request: Request, limit: Limit = 25, offset: Offset = 0):
    """Owner/Admin see all clients; trainers see current/historical clients. No health answers."""
    with authorized_transaction(request) as (session, principal):
        return page(
            session,
            select(Client).where(client_scope(principal)).order_by(Client.id),
            ClientSummary,
            limit,
            offset,
        )


@router.get("/clients/{client_id}", response_model=ClientDetail, operation_id="getClient")
def client(client_id: UUID, request: Request):
    """Scoped general identity projection. Sensitive assessments use separate Owner/Admin routes."""
    with authorized_transaction(request) as (session, principal):
        record = client_record(session, principal, client_id)
        result = ClientSummary.model_validate(record).model_dump()
        result["people"] = [
            PersonSummary.model_validate(person)
            for person in session.scalars(
                select(ClientPerson)
                .where(ClientPerson.client_id == client_id)
                .order_by(ClientPerson.position)
            )
        ]
        return result


@router.get("/trainers", response_model=Page[TrainerSummary], operation_id="listTrainers")
def trainers(request: Request, limit: Limit = 25, offset: Offset = 0):
    """Owner/Admin list trainers; trainers receive their own staff profile only."""
    with authorized_transaction(request) as (session, principal):
        query = select(Trainer).order_by(Trainer.id)
        if not principal.manages_operations:
            query = query.where(Trainer.id == principal.trainer_id)
        return page(session, query, TrainerSummary, limit, offset)


@router.get("/trainers/{trainer_id}", response_model=TrainerSummary, operation_id="getTrainer")
def trainer(trainer_id: UUID, request: Request):
    """Owner/Admin or the active trainer's own profile; guessed IDs grant no access."""
    with authorized_transaction(request) as (session, principal):
        return TrainerSummary.model_validate(trainer_record(session, principal, trainer_id))


@router.get("/sessions", response_model=Page[SessionSummary], operation_id="listSessions")
def sessions(request: Request, limit: Limit = 25, offset: Offset = 0):
    """List only sessions assigned to this trainer, or all for operational staff."""
    with authorized_transaction(request) as (session, principal):
        query = select(TrainingSession).order_by(TrainingSession.training_date, TrainingSession.id)
        if not principal.manages_operations:
            query = query.where(session_scope(principal))
        return page(session, query, SessionSummary, limit, offset)


@router.get("/sessions/{session_id}", response_model=SessionSummary, operation_id="getSession")
def training_session(session_id: UUID, request: Request):
    """Session access follows its stored assigned trainer, not caller-supplied roles."""
    with authorized_transaction(request) as (session, principal):
        return SessionSummary.model_validate(session_record(session, principal, session_id))


@router.get(
    "/assessment-forms",
    response_model=Page[FormDefinition],
    operation_id="listAssessmentForms",
    tags=["assessments"],
)
def definitions(request: Request, limit: Limit = 25, offset: Offset = 0):
    """Frozen form definitions and asset digests for operational staff; no client answers."""
    with authorized_transaction(request) as (session, principal):
        principal.operations()
        return page(
            session,
            select(AssessmentFormVersion).order_by(
                AssessmentFormVersion.form_id, AssessmentFormVersion.version
            ),
            FormDefinition,
            limit,
            offset,
        )


@router.get(
    "/people/{person_id}/assessments",
    response_model=Page[AssessmentRevision],
    operation_id="listPersonAssessments",
    tags=["assessments"],
)
def person_assessments(
    person_id: UUID,
    request: Request,
    limit: Limit = 25,
    offset: Offset = 0,
    formId: Annotated[str | None, Query(max_length=64, pattern=r"^[a-z][a-z0-9_]*$")] = None,
):
    """Owner/Admin current records for one person, including inactive clients; audited reads."""
    with authorized_transaction(request) as (session, principal):
        assessments.person_record(session, principal, person_id)
        assessments.audit(session, principal, person_id, "list")
        query = (
            select(ClientAssessmentRevision)
            .join(
                ClientAssessment,
                (ClientAssessment.id == ClientAssessmentRevision.assessment_id)
                & (ClientAssessment.version == ClientAssessmentRevision.revision),
            )
            .where(ClientAssessment.client_person_id == person_id)
            .order_by(ClientAssessment.created_at.desc(), ClientAssessment.id.desc())
        )
        if formId is not None:
            query = query.where(ClientAssessment.form_id == formId)
        return page(session, query, AssessmentRevision, limit, offset)


@router.post(
    "/people/{person_id}/assessments",
    response_model=AssessmentRevision,
    operation_id="createPersonAssessment",
    tags=["assessments"],
)
def create_assessment(person_id: UUID, body: NewAssessment, request: Request, key: RequestKey):
    """Owner/Admin records an unfilled form with an atomic save and retry receipt.

    Existing occasions are never overwritten. A reassessment requires the current completed
    or voided occasion ID/version; an unfinished draft must be resumed.
    Empty hurdle completion is valid; other forms need an answer.
    """
    with authorized_transaction(request) as (session, principal):
        return assessments.create(session, principal, person_id, key, body)


@router.get(
    "/assessments/{assessment_id}",
    response_model=AssessmentRevision,
    operation_id="getAssessment",
    tags=["assessments"],
)
def assessment(assessment_id: UUID, request: Request):
    """Owner/Admin saved current revision. Inactive records remain viewable and read-only."""
    with authorized_transaction(request) as (session, principal):
        person, record = assessments.assessment_record(session, principal, assessment_id)
        assessments.audit(session, principal, person.id, "view", record.id)
        revision = session.scalar(
            select(ClientAssessmentRevision).where(
                ClientAssessmentRevision.assessment_id == record.id,
                ClientAssessmentRevision.revision == record.version,
            )
        )
        return AssessmentRevision.model_validate(revision)


@router.get(
    "/assessments/{assessment_id}/revisions",
    response_model=Page[AssessmentRevision],
    operation_id="listAssessmentHistory",
    tags=["assessments"],
)
def history(assessment_id: UUID, request: Request, limit: Limit = 25, offset: Offset = 0):
    """Owner/Admin immutable history, newest first; access is audited without answer copies."""
    with authorized_transaction(request) as (session, principal):
        person, record = assessments.assessment_record(session, principal, assessment_id)
        assessments.audit(session, principal, person.id, "history", record.id)
        return page(
            session,
            select(ClientAssessmentRevision)
            .where(ClientAssessmentRevision.assessment_id == record.id)
            .order_by(ClientAssessmentRevision.revision.desc()),
            AssessmentRevision,
            limit,
            offset,
        )


@router.post(
    "/assessments/{assessment_id}/revisions",
    response_model=AssessmentRevision,
    operation_id="saveAssessmentRevision",
    tags=["assessments"],
)
def save_assessment(assessment_id: UUID, body: SaveAssessment, request: Request, key: RequestKey):
    """Owner/Admin explicit save with reviewed version. Corrections/voids require a reason.

    Dates and submitted identity headers are preserved. Retrying the same key/body returns
    its original immutable revision; changed reuse or stale versions returns a safe conflict.
    """
    with authorized_transaction(request) as (session, principal):
        return assessments.save(session, principal, assessment_id, key, body)


@router.get("/directory", response_model=DirectorySnapshot, operation_id="staffDirectory")
def staff_directory(request: Request):
    """Read-only directory for Owner/Admin or the current permanent trainer.

    No assessments, legacy health notes, sessions or unimplemented domains are synthesized.
    Exceeding a collection bound fails explicitly rather than returning a partial directory.
    """
    with authorized_transaction(request) as (session, principal):
        return directory.snapshot(session, principal)


@router.get(
    "/sessions/{session_id}/client", response_model=SessionClient, operation_id="getSessionClient"
)
def session_client(session_id: UUID, request: Request):
    """Minimal client identity from an active assigned session; ends at completion/cancellation.

    This never grants full profile access. Names only; no contacts, health, assessments or packages.
    Historical session evidence uses the separate session authorization boundary.
    """
    with authorized_transaction(request) as (session, principal):
        record = session_record(session, principal, session_id)
        client = session.get(Client, record.client_id)
        purchase = session.get(PackagePurchase, record.purchase_id)
        if (
            record.status not in {"scheduled", "planned"}
            or client.status != "active"
            or purchase.status != "active"
            or (not principal.manages_operations and record.trainer_id != principal.trainer_id)
        ):
            raise unavailable()
        return SessionClient(
            session_id=record.id,
            client_id=client.id,
            name=client.name,
            kind=client.kind,
            person_names=list(
                session.scalars(
                    select(ClientPerson.name)
                    .where(ClientPerson.client_id == client.id)
                    .order_by(ClientPerson.position)
                )
            ),
        )


@router.post("/packages", response_model=DirectoryPackage, operation_id="savePackage")
def save_package(body: packages.SavePackage, request: Request, request_key: RequestKey):
    """Owner/Admin catalogue save with reviewed versions and actor-scoped durable receipts."""
    with authorized_transaction(request) as (session, principal):
        return packages.save(session, principal, request_key, body)


@router.get(
    "/packages/saves/{request_key}",
    response_model=DirectoryPackage,
    operation_id="reconcilePackageSave",
)
def package_save(request_key: UUID, request: Request):
    """Read only this actor's durable save receipt before retrying an uncertain command."""
    with authorized_transaction(request) as (session, principal):
        return packages.reconcile(session, principal, request_key)


@router.post(
    "/trainers/{trainer_id}/approvals",
    response_model=trainer_approvals.ApprovalState,
    operation_id="saveTrainerApprovals",
)
def save_trainer_approvals(
    trainer_id: UUID, body: trainer_approvals.SaveApprovals, request: Request, key: RequestKey
):
    with authorized_transaction(request) as (session, principal):
        return trainer_approvals.save(session, principal, trainer_id, key, body)


@router.get(
    "/trainer-approval-saves/{request_key}",
    response_model=trainer_approvals.ApprovalState,
    operation_id="reconcileTrainerApprovals",
)
def reconcile_trainer_approvals(request_key: UUID, request: Request):
    with authorized_transaction(request) as (session, principal):
        return trainer_approvals.reconcile(session, principal, request_key)


@router.post(
    "/clients/{client_id}/personal-details",
    response_model=client_details.ClientDetailState,
    operation_id="saveClientPersonalDetails",
)
def save_client_details(
    client_id: UUID, body: client_details.SaveClientDetails, request: Request, key: RequestKey
):
    with authorized_transaction(request) as (session, principal):
        return client_details.save(session, principal, client_id, key, body)


@router.get(
    "/client-detail-saves/{request_key}",
    response_model=client_details.ClientDetailState,
    operation_id="reconcileClientPersonalDetails",
)
def reconcile_client_details(request_key: UUID, request: Request):
    with authorized_transaction(request) as (session, principal):
        return client_details.reconcile(session, principal, request_key)


@router.get(
    "/clients/{client_id}/notes",
    response_model=client_notes.NoteView,
    operation_id="getClientNotes",
)
def get_client_notes(client_id: UUID, request: Request):
    """Audited general notes for operational staff or the current assigned Trainer only."""
    with authorized_transaction(request) as (session, principal):
        return client_notes.view(session, principal, client_id)


@router.post(
    "/clients/{client_id}/notes",
    response_model=client_notes.NoteState,
    operation_id="saveClientNotes",
)
def save_client_notes(
    client_id: UUID, body: client_notes.SaveNotes, request: Request, key: RequestKey
):
    """Versioned general-note save; assessment fields are forbidden."""
    with authorized_transaction(request) as (session, principal):
        return client_notes.save(session, principal, client_id, key, body)


@router.get(
    "/client-note-saves/{request_key}",
    response_model=client_notes.NoteState,
    operation_id="reconcileClientNotes",
)
def reconcile_client_notes(request_key: UUID, request: Request):
    """Current assigned authority is rechecked before returning actor-scoped receipts."""
    with authorized_transaction(request) as (session, principal):
        return client_notes.reconcile(session, principal, request_key)


@router.post(
    "/trainers/{trainer_id}/rates",
    response_model=trainer_rates.RateState,
    operation_id="saveTrainerRates",
)
def save_trainer_rates(
    trainer_id: UUID, body: trainer_rates.SaveRates, request: Request, key: RequestKey
):
    """Owner-only integer-cent pay rates; no account, approval or schedule changes."""
    with authorized_transaction(request) as (session, principal):
        return trainer_rates.save(session, principal, trainer_id, key, body)


@router.get(
    "/trainer-rate-saves/{request_key}",
    response_model=trainer_rates.RateState,
    operation_id="reconcileTrainerRates",
)
def reconcile_trainer_rates(request_key: UUID, request: Request):
    """Read the current Owner's original receipt before an explicit retry."""
    with authorized_transaction(request) as (session, principal):
        return trainer_rates.reconcile(session, principal, request_key)


@router.post(
    "/client-onboarding/matches",
    response_model=client_matching.MatchResult,
    operation_id="previewClientTrainerMatches",
)
def preview_client_matches(body: client_matching.MatchRequest, request: Request, key: RequestKey):
    """Owner/Admin preview; every eventual creation must recheck availability at commit."""
    with authorized_transaction(request) as (session, principal):
        return client_matching.preview(session, principal, body)


@router.post("/clients", response_model=client_creation.CreatedClient, operation_id="createClient")
def create_client(body: client_creation.CreateClient, request: Request, key: RequestKey):
    with authorized_transaction(request) as (session, principal):
        return client_creation.create(session, principal, key, body)


@router.get(
    "/client-creations/{request_key}",
    response_model=client_creation.CreatedClient,
    operation_id="reconcileClientCreation",
)
def reconcile_client_creation(request_key: UUID, request: Request):
    with authorized_transaction(request) as (session, principal):
        return client_creation.reconcile(session, principal, request_key)


@router.get(
    "/trainers/{trainer_id}/reactivation",
    response_model=trainer_reactivation.ReactivationReview,
    operation_id="reviewTrainerReactivation",
)
def review_trainer_reactivation(trainer_id: UUID, request: Request):
    """Review the current trainer and linked account before confirmation."""
    with authorized_transaction(request) as (session, principal):
        return trainer_reactivation.review(session, principal, trainer_id)


@router.post(
    "/trainers/{trainer_id}/reactivation",
    response_model=trainer_reactivation.ReactivationState,
    operation_id="reactivateTrainer",
)
def reactivate_trainer(
    trainer_id: UUID,
    body: trainer_reactivation.ReactivateTrainer,
    request: Request,
    key: RequestKey,
):
    """Reactivate the reviewed application account without reviving revoked sessions."""
    with authorized_transaction(request) as (session, principal):
        result = trainer_reactivation.save(session, principal, trainer_id, key, body)
    if body.expectedAccountId:
        request.app.state.auth.drain_revocations(user_id=body.expectedAccountId)
    return result


@router.get(
    "/trainer-reactivations/{request_key}",
    response_model=trainer_reactivation.ReactivationState,
    operation_id="reconcileTrainerReactivation",
)
def reconcile_trainer_reactivation(request_key: UUID, request: Request):
    """Read this actor's receipt before explicitly retrying the identical operation."""
    with authorized_transaction(request) as (session, principal):
        return trainer_reactivation.reconcile(session, principal, request_key)


@router.get(
    "/clients/{client_id}/assessment-records",
    response_model=ClientAssessmentRecords,
    operation_id="getClientAssessmentRecords",
    tags=["assessments"],
)
def client_assessment_records(client_id: UUID, request: Request):
    """Owner/Admin latest occasions per form, with reviewed client/person versions."""
    with authorized_transaction(request) as (session, principal):
        return assessments.current_records(session, principal, client_id)


@router.get(
    "/assessment-saves/{request_key}",
    response_model=AssessmentRevision,
    operation_id="reconcileAssessmentSave",
    tags=["assessments"],
)
def reconcile_assessment_save(request_key: UUID, request: Request):
    """Read this actor's original immutable revision after an interrupted create or save."""
    with authorized_transaction(request) as (session, principal):
        return assessments.reconcile(session, principal, request_key)


@router.get("/content", response_model=list[content.ContentState], operation_id="staffContent")
def staff_content(request: Request):
    """Read the complete bounded staff content catalogue; never public website content."""
    with authorized_transaction(request) as (session, principal):
        return content.records(session, principal)


@router.post("/content", response_model=content.ContentState, operation_id="saveContent")
def save_content(body: content.SaveContent, request: Request, key: RequestKey):
    """Save reviewed staff content and its immutable receipt/Owner notice atomically."""
    with authorized_transaction(request) as (session, principal):
        return content.save(session, principal, key, body)


@router.get(
    "/content-saves/{request_key}",
    response_model=content.ContentState,
    operation_id="reconcileContent",
)
def reconcile_content(request_key: UUID, request: Request):
    """Read only this actor's original saved content after an interrupted response."""
    with authorized_transaction(request) as (session, principal):
        return content.reconcile(session, principal, request_key)
