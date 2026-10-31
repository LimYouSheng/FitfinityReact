"""Versioned staff contracts; M6 adds domain workflow orchestration and the React API adapter."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, Query, Request
from sqlalchemy import select

from app.api import (
    assessments,
    client_assignment,
    client_assignment_save,
    client_creation,
    client_deactivation,
    client_details,
    client_matching,
    client_notes,
    client_reactivation,
    client_reactivation_save,
    client_renewal,
    client_renewal_save,
    client_weekly_schedule,
    client_weekly_schedule_save,
    content,
    directory,
    messages,
    package_reactivation_save,
    packages,
    remuneration,
    remuneration_schemas,
    renewal_dismissal,
    request_cancellation,
    request_resolution,
    session_acknowledgements,
    session_attribution,
    session_booking_review,
    session_booking_save,
    session_changes,
    session_handoffs,
    session_outcomes,
    session_plans,
    session_postponement,
    session_progress,
    session_read_schemas,
    session_reads,
    session_reports,
    session_summaries,
    trainer_approvals,
    trainer_availability,
    trainer_deactivation,
    trainer_deactivation_save,
    trainer_details,
    trainer_rates,
    trainer_reactivation,
)
from app.api.admin_supervision import ApprovalPending
from app.api.dependencies import authorized_transaction
from app.api.message_schemas import (
    DismissRenewal,
    MessageReadState,
    PersonalMessage,
    RenewalState,
    SaveMessageRead,
)
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
    responses={202: {"model": ApprovalPending}},
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
    responses={202: {"model": ApprovalPending}},
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
    responses={202: {"model": ApprovalPending}},
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
    responses={202: {"model": ApprovalPending}},
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
        return directory.snapshot(
            session,
            principal,
            email_corrections=request.app.state.auth_settings.staff_email_corrections_enabled,
        )


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


@router.post(
    "/packages",
    response_model=DirectoryPackage,
    operation_id="savePackage",
    responses={202: {"model": ApprovalPending}},
)
def save_package(body: packages.SavePackage, request: Request, request_key: RequestKey):
    """Owner/Admin catalogue save with reviewed versions and actor-scoped durable receipts."""
    with authorized_transaction(request) as (session, principal):
        return packages.save(session, principal, request_key, body)


@router.get(
    "/packages/saves/{request_key}",
    response_model=DirectoryPackage,
    operation_id="reconcilePackageSave",
    responses={202: {"model": ApprovalPending}},
)
def package_save(request_key: UUID, request: Request):
    """Read only this actor's durable save receipt before retrying an uncertain command."""
    with authorized_transaction(request) as (session, principal):
        return packages.reconcile(session, principal, request_key)


@router.post(
    "/trainers/{trainer_id}/approvals",
    response_model=trainer_approvals.ApprovalState,
    operation_id="saveTrainerApprovals",
    responses={202: {"model": ApprovalPending}},
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
    responses={202: {"model": ApprovalPending}},
)
def reconcile_trainer_approvals(request_key: UUID, request: Request):
    with authorized_transaction(request) as (session, principal):
        return trainer_approvals.reconcile(session, principal, request_key)


@router.post(
    "/clients/{client_id}/personal-details",
    response_model=client_details.ClientDetailState,
    operation_id="saveClientPersonalDetails",
    responses={202: {"model": ApprovalPending}},
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
    responses={202: {"model": ApprovalPending}},
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
    responses={202: {"model": ApprovalPending}},
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
    responses={202: {"model": ApprovalPending}},
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


@router.post(
    "/clients",
    response_model=client_creation.CreatedClient,
    operation_id="createClient",
    responses={202: {"model": ApprovalPending}},
)
def create_client(body: client_creation.CreateClient, request: Request, key: RequestKey):
    with authorized_transaction(request, advisory_lock=request_cancellation.DECISION_LOCK) as (
        session,
        principal,
    ):
        return client_creation.create(session, principal, key, body)


@router.get(
    "/client-creations/{request_key}",
    response_model=client_creation.CreatedClient,
    operation_id="reconcileClientCreation",
    responses={202: {"model": ApprovalPending}},
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
    responses={202: {"model": ApprovalPending}},
)
def reactivate_trainer(
    trainer_id: UUID,
    body: trainer_reactivation.ReactivateTrainer,
    request: Request,
    key: RequestKey,
):
    """Reactivate the reviewed application account without reviving revoked sessions."""
    with authorized_transaction(request, advisory_lock=request_cancellation.DECISION_LOCK) as (
        session,
        principal,
    ):
        result = trainer_reactivation.save(session, principal, trainer_id, key, body)
    if body.expectedAccountId:
        request.app.state.auth.drain_revocations(user_id=body.expectedAccountId)
    return result


@router.get(
    "/trainer-reactivations/{request_key}",
    response_model=trainer_reactivation.ReactivationState,
    operation_id="reconcileTrainerReactivation",
    responses={202: {"model": ApprovalPending}},
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
    responses={202: {"model": ApprovalPending}},
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


@router.post(
    "/content",
    response_model=content.ContentState,
    operation_id="saveContent",
    responses={202: {"model": ApprovalPending}},
)
def save_content(body: content.SaveContent, request: Request, key: RequestKey):
    """Save reviewed staff content and its immutable receipt/Owner notice atomically."""
    with authorized_transaction(request) as (session, principal):
        return content.save(session, principal, key, body)


@router.get(
    "/content-saves/{request_key}",
    response_model=content.ContentState,
    operation_id="reconcileContent",
    responses={202: {"model": ApprovalPending}},
)
def reconcile_content(request_key: UUID, request: Request):
    """Read only this actor's original saved content after an interrupted response."""
    with authorized_transaction(request) as (session, principal):
        return content.reconcile(session, principal, request_key)


@router.get("/messages", response_model=list[PersonalMessage], operation_id="personalMessages")
def personal_messages(request: Request):
    """Read this recipient's messages and personal read state, with Admin financial exclusions."""
    with authorized_transaction(request) as (session, principal):
        return messages.records(session, principal)


@router.post(
    "/messages/{message_id}/read-state",
    response_model=MessageReadState,
    operation_id="saveMessageReadState",
)
def save_message_read_state(
    message_id: UUID, body: SaveMessageRead, request: Request, key: RequestKey
):
    """Save only the authenticated recipient's reviewed read state with a durable receipt."""
    with authorized_transaction(request) as (session, principal):
        return messages.save(session, principal, message_id, key, body)


@router.get(
    "/message-read-saves/{request_key}",
    response_model=MessageReadState,
    operation_id="reconcileMessageReadState",
)
def reconcile_message_read_state(request_key: UUID, request: Request):
    """Reconcile this actor's original read-state command without changing newer read state."""
    with authorized_transaction(request) as (session, principal):
        return messages.reconcile(session, principal, request_key)


@router.post(
    "/messages/{message_id}/dismiss-renewal",
    response_model=RenewalState,
    operation_id="dismissRenewal",
)
def dismiss_renewal(message_id: UUID, body: DismissRenewal, request: Request, key: RequestKey):
    """Recheck current assignment and remove only this follow-up, retaining immutable evidence."""
    with authorized_transaction(request) as (session, principal):
        return renewal_dismissal.save(session, principal, message_id, key, body)


@router.get(
    "/renewal-dismissal-saves/{request_key}",
    response_model=RenewalState,
    operation_id="reconcileRenewalDismissal",
)
def reconcile_renewal_dismissal(request_key: UUID, request: Request):
    """Read this actor's original dismissal result without changing the reminder."""
    with authorized_transaction(request) as (session, principal):
        return renewal_dismissal.reconcile(session, principal, request_key)


@router.get(
    "/clients/{client_id}/deactivation",
    response_model=client_deactivation.DeactivationReview,
    operation_id="reviewClientDeactivation",
)
def review_client_deactivation(client_id: UUID, request: Request):
    """Review the exact client and purchases before deactivation."""
    with authorized_transaction(request) as (session, principal):
        return client_deactivation.review(session, principal, client_id)


@router.post(
    "/clients/{client_id}/deactivation",
    response_model=client_deactivation.DeactivationState,
    operation_id="deactivateClient",
    responses={202: {"model": ApprovalPending}},
)
def deactivate_client(
    client_id: UUID, body: client_deactivation.DeactivateClient, request: Request, key: RequestKey
):
    """Atomically freeze the reviewed active client and purchases without deleting history."""
    with authorized_transaction(request, advisory_lock=request_cancellation.DECISION_LOCK) as (
        session,
        principal,
    ):
        return client_deactivation.save(session, principal, client_id, key, body)


@router.get(
    "/client-deactivations/{request_key}",
    response_model=client_deactivation.DeactivationState,
    operation_id="reconcileClientDeactivation",
    responses={202: {"model": ApprovalPending}},
)
def reconcile_client_deactivation(request_key: UUID, request: Request):
    """Read only this actor's original committed deactivation result."""
    with authorized_transaction(request) as (session, principal):
        return client_deactivation.reconcile(session, principal, request_key)


@router.get(
    "/clients/{client_id}/reactivation-review",
    response_model=client_reactivation.ClientReactivationReview,
    operation_id="reviewClientReactivation",
)
def review_client_reactivation(client_id: UUID, request: Request):
    """Review retained bookings; this endpoint never reactivates records."""
    with authorized_transaction(request) as (session, principal):
        return client_reactivation.review(session, principal, client_id)


@router.post(
    "/clients/{client_id}/reactivation-review",
    response_model=client_reactivation.ClientReactivationReview,
    operation_id="previewClientReactivationDates",
)
def preview_client_reactivation_dates(
    client_id: UUID, body: client_reactivation.ReactivationDates, request: Request, key: RequestKey
):
    """Check proposed dates against current occupancy without saving changes."""
    with authorized_transaction(request) as (session, principal):
        return client_reactivation.review(session, principal, client_id, body)


@router.post(
    "/clients/{client_id}/reactivation",
    response_model=client_reactivation_save.ClientReactivationState,
    operation_id="reactivateClient",
    responses={202: {"model": ApprovalPending}},
)
def reactivate_client(
    client_id: UUID, body: client_reactivation.ReactivationDates, request: Request, key: RequestKey
):
    """Restore the reviewed client, causal purchases and conflict-free retained calendar."""
    with authorized_transaction(request, advisory_lock=request_cancellation.DECISION_LOCK) as (
        session,
        principal,
    ):
        return client_reactivation_save.save(session, principal, client_id, key, body)


@router.get(
    "/client-reactivations/{request_key}",
    response_model=client_reactivation_save.ClientReactivationState,
    operation_id="reconcileClientReactivation",
    responses={202: {"model": ApprovalPending}},
)
def reconcile_client_reactivation(request_key: UUID, request: Request):
    """Reconcile only this actor's original successful command."""
    with authorized_transaction(request) as (session, principal):
        return client_reactivation_save.reconcile(session, principal, request_key)


@router.post(
    "/requests/{request_id}/cancel",
    response_model=request_cancellation.CancellationState,
    operation_id="cancelOwnedRequest",
)
def cancel_owned_request(
    request_id: UUID, body: request_cancellation.CancelRequest, request: Request, key: RequestKey
):
    """Withdraw only this active Trainer's reviewed pending proposal."""
    with authorized_transaction(request, advisory_lock=request_cancellation.DECISION_LOCK) as (
        session,
        principal,
    ):
        return request_cancellation.save(session, principal, request_id, key, body)


@router.get(
    "/request-cancellations/{request_key}",
    response_model=request_cancellation.CancellationState,
    operation_id="reconcileRequestCancellation",
)
def reconcile_request_cancellation(request_key: UUID, request: Request):
    """Return only this actor's original cancellation receipt."""
    with authorized_transaction(request, advisory_lock=request_cancellation.DECISION_LOCK) as (
        session,
        principal,
    ):
        return request_cancellation.reconcile(session, principal, request_key)


@router.post(
    "/trainers/{trainer_id}/availability",
    response_model=trainer_availability.AvailabilityState,
    operation_id="saveTrainerAvailability",
)
def save_trainer_availability(
    trainer_id: UUID, body: trainer_availability.SaveAvailability, request: Request, key: RequestKey
):
    """Apply the current Trainer's reviewed availability or retain its supervised proposal."""
    with authorized_transaction(request, exclusive_user=True) as (session, principal):
        return trainer_availability.save(session, principal, trainer_id, key, body)


@router.get(
    "/trainer-availability-saves/{request_key}",
    response_model=trainer_availability.AvailabilityState,
    operation_id="reconcileTrainerAvailability",
)
def reconcile_trainer_availability(request_key: UUID, request: Request):
    """Reconcile this Trainer's original availability save without reapplying or sending notices."""
    with authorized_transaction(request) as (session, principal):
        return trainer_availability.reconcile(session, principal, request_key)


@router.get(
    "/clients/{client_id}/renewal-review",
    response_model=client_renewal.RenewalReview,
    operation_id="reviewClientPackageRenewal",
)
def review_client_package_renewal(client_id: UUID, request: Request):
    with authorized_transaction(request) as (session, principal):
        return client_renewal.review(session, principal, client_id)


@router.post(
    "/clients/{client_id}/renewal-matches",
    response_model=client_matching.MatchResult,
    operation_id="previewClientRenewalMatches",
)
def preview_client_renewal_matches(
    client_id: UUID, body: client_renewal.RenewalMatchRequest, request: Request, key: RequestKey
):
    """Recheck the client and trainer calendars; this preview does not create a purchase."""
    with authorized_transaction(request) as (session, principal):
        return client_renewal.matches(session, principal, client_id, body)


@router.post(
    "/clients/{client_id}/packages",
    response_model=client_renewal_save.ClientRenewalState,
    operation_id="renewClientPackage",
    responses={202: {"model": ApprovalPending}},
)
def renew_client_package(
    client_id: UUID, body: client_renewal_save.RenewPackage, request: Request, key: RequestKey
):
    """Atomically add the reviewed purchase and sessions without changing current settings."""
    with authorized_transaction(request, advisory_lock=request_cancellation.DECISION_LOCK) as (
        session,
        principal,
    ):
        return client_renewal_save.save(session, principal, client_id, key, body)


@router.get(
    "/client-renewals/{request_key}",
    response_model=client_renewal_save.ClientRenewalState,
    operation_id="reconcileClientRenewal",
    responses={202: {"model": ApprovalPending}},
)
def reconcile_client_renewal(request_key: UUID, request: Request):
    """Read this actor's original committed renewal before an explicit identical retry."""
    with authorized_transaction(request) as (session, principal):
        return client_renewal_save.reconcile(session, principal, request_key)


@router.get(
    "/clients/{client_id}/packages/{purchase_id}/reactivation-review",
    response_model=client_reactivation.PackageReactivationReview,
    operation_id="reviewPackageReactivation",
)
def review_package_reactivation(client_id: UUID, purchase_id: UUID, request: Request):
    """Review only the selected inactive purchase of an active client; never write."""
    with authorized_transaction(request) as (session, principal):
        return client_reactivation.review(session, principal, client_id, package_id=purchase_id)


@router.post(
    "/clients/{client_id}/packages/{purchase_id}/reactivation-review",
    response_model=client_reactivation.PackageReactivationReview,
    operation_id="previewPackageReactivationDates",
)
def preview_package_reactivation_dates(
    client_id: UUID,
    purchase_id: UUID,
    body: client_reactivation.ReactivationDates,
    request: Request,
    key: RequestKey,
):
    """Check selected-purchase replacement dates against the complete occupied calendar."""
    with authorized_transaction(request) as (session, principal):
        return client_reactivation.review(
            session, principal, client_id, body, package_id=purchase_id
        )


@router.post(
    "/clients/{client_id}/packages/{purchase_id}/reactivation",
    response_model=package_reactivation_save.PackageReactivationState,
    operation_id="reactivatePackage",
    responses={202: {"model": ApprovalPending}},
)
def reactivate_package(
    client_id: UUID,
    purchase_id: UUID,
    body: client_reactivation.ReactivationDates,
    request: Request,
    key: RequestKey,
):
    """Restore only the reviewed purchase and its conflict-free retained calendar."""
    with authorized_transaction(request, advisory_lock=request_cancellation.DECISION_LOCK) as (
        session,
        principal,
    ):
        return package_reactivation_save.save(session, principal, client_id, purchase_id, key, body)


@router.get(
    "/package-reactivations/{request_key}",
    response_model=package_reactivation_save.PackageReactivationState,
    operation_id="reconcilePackageReactivation",
    responses={202: {"model": ApprovalPending}},
)
def reconcile_package_reactivation(request_key: UUID, request: Request):
    """Read only the current actor's original accepted purchase restoration."""
    with authorized_transaction(request) as (session, principal):
        return package_reactivation_save.reconcile(session, principal, request_key)


@router.get(
    "/clients/{client_id}/trainer-assignment-review",
    response_model=client_assignment.AssignmentReview,
    operation_id="reviewClientTrainerAssignment",
)
def review_client_trainer_assignment(
    client_id: UUID, request: Request, purchaseId: UUID | None = None
):
    with authorized_transaction(request) as (session, principal):
        return client_assignment.review(session, principal, client_id, purchaseId)


@router.post(
    "/clients/{client_id}/trainer-assignment",
    response_model=client_assignment_save.AssignmentState,
    operation_id="saveClientTrainerAssignment",
    responses={202: {"model": ApprovalPending}},
)
def save_client_trainer_assignment(
    client_id: UUID, body: client_assignment_save.SaveAssignment, request: Request, key: RequestKey
):
    with authorized_transaction(request, advisory_lock=request_cancellation.DECISION_LOCK) as (
        session,
        principal,
    ):
        return client_assignment_save.save(session, principal, client_id, key, body)


@router.get(
    "/client-trainer-assignments/{request_key}",
    response_model=client_assignment_save.AssignmentState,
    operation_id="reconcileClientTrainerAssignment",
    responses={202: {"model": ApprovalPending}},
)
def reconcile_client_trainer_assignment(request_key: UUID, request: Request):
    with authorized_transaction(request) as (session, principal):
        return client_assignment_save.reconcile(session, principal, request_key)


@router.get(
    "/trainers/{trainer_id}/deactivation-review",
    response_model=trainer_deactivation.TrainerDeactivationReview,
    operation_id="reviewTrainerDeactivation",
)
def review_trainer_deactivation(trainer_id: UUID, request: Request):
    with authorized_transaction(request) as (session, principal):
        return trainer_deactivation.review(session, principal, trainer_id)


@router.post(
    "/trainers/{trainer_id}/deactivation-review",
    response_model=trainer_deactivation.TrainerDeactivationReview,
    operation_id="previewTrainerDeactivation",
)
def preview_trainer_deactivation(
    trainer_id: UUID,
    body: trainer_deactivation.TrainerDeactivationSelection,
    request: Request,
    key: RequestKey,
):
    with authorized_transaction(request) as (session, principal):
        return trainer_deactivation.preview(session, principal, trainer_id, body)


@router.post(
    "/trainers/{trainer_id}/deactivation",
    response_model=trainer_deactivation_save.TrainerDeactivationState,
    operation_id="saveTrainerDeactivation",
    responses={202: {"model": ApprovalPending}},
)
def save_trainer_deactivation(
    trainer_id: UUID,
    body: trainer_deactivation.TrainerDeactivationSelection,
    request: Request,
    key: RequestKey,
):
    with authorized_transaction(request, advisory_lock=request_cancellation.DECISION_LOCK) as (
        session,
        principal,
    ):
        return trainer_deactivation_save.save(session, principal, trainer_id, key, body)


@router.get(
    "/trainer-deactivations/{request_key}",
    response_model=trainer_deactivation_save.TrainerDeactivationState,
    operation_id="reconcileTrainerDeactivation",
    responses={202: {"model": ApprovalPending}},
)
def reconcile_trainer_deactivation(request_key: UUID, request: Request):
    with authorized_transaction(request) as (session, principal):
        return trainer_deactivation_save.reconcile(session, principal, request_key)


@router.get(
    "/clients/{client_id}/weekly-schedule-review",
    response_model=client_weekly_schedule.ClientWeeklyReview,
    operation_id="reviewClientWeeklySchedule",
)
def review_client_weekly_schedule(client_id: UUID, request: Request):
    with authorized_transaction(request) as (session, principal):
        return client_weekly_schedule.review(session, principal, client_id)


@router.post(
    "/clients/{client_id}/weekly-schedule-review",
    response_model=client_weekly_schedule.ClientWeeklyPreview,
    operation_id="previewClientWeeklySchedule",
)
def preview_client_weekly_schedule(
    client_id: UUID,
    body: client_weekly_schedule.SaveClientWeeklySchedule,
    request: Request,
    key: RequestKey,
):
    with authorized_transaction(request) as (session, principal):
        return client_weekly_schedule.preview(session, principal, client_id, body)


@router.post(
    "/clients/{client_id}/weekly-schedule",
    response_model=client_weekly_schedule_save.ClientWeeklyState,
    operation_id="saveClientWeeklySchedule",
    responses={202: {"model": ApprovalPending}},
)
def save_client_weekly_schedule(
    client_id: UUID,
    body: client_weekly_schedule.SaveClientWeeklySchedule,
    request: Request,
    key: RequestKey,
):
    with authorized_transaction(request, advisory_lock=request_cancellation.DECISION_LOCK) as (
        session,
        principal,
    ):
        return client_weekly_schedule_save.save(session, principal, client_id, key, body)


@router.get(
    "/client-weekly-schedules/{request_key}",
    response_model=client_weekly_schedule_save.ClientWeeklyState,
    operation_id="reconcileClientWeeklySchedule",
    responses={202: {"model": ApprovalPending}},
)
def reconcile_client_weekly_schedule(request_key: UUID, request: Request):
    with authorized_transaction(request) as (session, principal):
        return client_weekly_schedule_save.reconcile(session, principal, request_key)


@router.get(
    "/session-calendar",
    response_model=session_read_schemas.SessionCalendar,
    operation_id="readSessionCalendar",
)
def read_session_calendar(request: Request):
    with authorized_transaction(request) as (session, principal):
        return session_reads.calendar(session, principal)


@router.get(
    "/sessions/{session_id}/details",
    response_model=session_read_schemas.SessionDetailRead,
    operation_id="readSessionDetails",
)
def read_session_details(session_id: UUID, request: Request):
    with authorized_transaction(request) as (session, principal):
        return session_reads.detail(session, principal, session_id)


@router.get(
    "/sessions/{session_id}/attribution",
    response_model=session_attribution.AttributionRead,
    operation_id="readSessionAttribution",
)
def read_session_attribution(session_id: UUID, request: Request):
    """Read scoped original, assigned and performed Trainer evidence and assignment history."""
    with authorized_transaction(request) as (session, principal):
        return session_attribution.read(session, principal, session_id)


@router.get(
    "/sessions/{session_id}/booking-review",
    response_model=session_booking_review.SessionBookingReview,
    operation_id="reviewSessionBooking",
)
def review_session_booking(session_id: UUID, request: Request):
    """Review current Owner/Admin booking authority and chronological context."""
    with authorized_transaction(request) as (session, principal):
        return session_booking_review.review(session, principal, session_id)


@router.post(
    "/sessions/{session_id}/booking",
    response_model=session_booking_save.SessionBookingState,
    operation_id="saveSessionBooking",
    responses={202: {"model": ApprovalPending}},
)
def save_session_booking(
    session_id: UUID,
    body: session_booking_review.SaveSessionBooking,
    request: Request,
    key: RequestKey,
):
    """Atomically save a reviewed booking and retain its exact retry result."""
    with authorized_transaction(request, advisory_lock=request_cancellation.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_booking_save.save(session, principal, session_id, key, body)


@router.get(
    "/session-booking-saves/{request_key}",
    response_model=session_booking_save.SessionBookingState,
    operation_id="reconcileSessionBooking",
    responses={202: {"model": ApprovalPending}},
)
def reconcile_session_booking(request_key: UUID, request: Request):
    """Read only this actor's original booking receipt after an interrupted response."""
    with authorized_transaction(request) as (session, principal):
        return session_booking_save.reconcile(session, principal, request_key)


@router.get(
    "/sessions/{session_id}/postponement-review",
    response_model=session_postponement.PostponementReview,
    operation_id="reviewSessionPostponement",
)
def review_session_postponement(session_id: UUID, request: Request):
    """Review an eligible current booking and the current Trainer approval requirement."""
    with authorized_transaction(request) as (session, principal):
        return session_postponement.review(session, principal, session_id)


@router.post(
    "/sessions/{session_id}/postponement",
    response_model=session_postponement.PostponementState,
    operation_id="postponeSession",
    responses={202: {"model": ApprovalPending}},
)
def postpone_session(
    session_id: UUID, body: session_postponement.PostponeSession, request: Request, key: RequestKey
):
    """Atomically release this booking or persist its supervised proposal."""
    with authorized_transaction(request, advisory_lock=request_cancellation.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_postponement.save(session, principal, session_id, key, body)


@router.get(
    "/session-postponements/{request_key}",
    response_model=session_postponement.PostponementState,
    operation_id="reconcileSessionPostponement",
    responses={202: {"model": ApprovalPending}},
)
def reconcile_session_postponement(request_key: UUID, request: Request):
    """Recover only this actor's original postponement outcome without resubmitting it."""
    with authorized_transaction(request) as (session, principal):
        return session_postponement.reconcile(session, principal, request_key)


@router.post(
    "/requests/{request_id}/resolve",
    response_model=request_resolution.ResolutionState,
    operation_id="resolveStaffRequest",
    responses={202: {"model": ApprovalPending}},
)
def resolve_staff_request(
    request_id: UUID, body: request_resolution.ResolveRequest, request: Request, key: RequestKey
):
    """Apply or reject an operations-reviewed proposal atomically."""
    with authorized_transaction(request, advisory_lock=request_cancellation.DECISION_LOCK) as (
        session,
        principal,
    ):
        return request_resolution.save(session, principal, request_id, key, body)


@router.get(
    "/request-resolutions/{request_key}",
    response_model=request_resolution.ResolutionState,
    operation_id="reconcileRequestResolution",
    responses={202: {"model": ApprovalPending}},
)
def reconcile_request_resolution(request_key: UUID, request: Request):
    """Reconcile only the current operations actor's original decision."""
    with authorized_transaction(request, advisory_lock=request_cancellation.DECISION_LOCK) as (
        session,
        principal,
    ):
        return request_resolution.reconcile(session, principal, request_key)


@router.get(
    "/sessions/{session_id}/change-review",
    response_model=session_changes.SessionChangeReview,
    operation_id="reviewTrainerSessionChange",
)
def review_trainer_session_change(
    session_id: UUID, kind: session_changes.ChangeKind, request: Request
):
    """Review only the assigned Trainer's booking and current approval requirement."""
    with authorized_transaction(request, advisory_lock=request_cancellation.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_changes.review(session, principal, session_id, kind)


@router.post(
    "/sessions/{session_id}/time-change",
    response_model=session_changes.SessionChangeState,
    operation_id="requestSessionTimeChange",
)
def request_session_time_change(
    session_id: UUID, body: session_changes.ChangeTime, request: Request, key: RequestKey
):
    """Apply autonomous time changes or persist the exact supervised proposal."""
    with authorized_transaction(request, advisory_lock=request_cancellation.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_changes.save(session, principal, session_id, key, "time", body)


@router.post(
    "/sessions/{session_id}/trainer-change",
    response_model=session_changes.SessionChangeState,
    operation_id="requestSessionTrainerChange",
)
def request_session_trainer_change(
    session_id: UUID, body: session_changes.ChangeTrainer, request: Request, key: RequestKey
):
    """Retain current assignment until policy permits the reviewed replacement."""
    with authorized_transaction(request, advisory_lock=request_cancellation.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_changes.save(session, principal, session_id, key, "trainer", body)


@router.get(
    "/session-changes/{request_key}",
    response_model=session_changes.SessionChangeState,
    operation_id="reconcileTrainerSessionChange",
)
def reconcile_trainer_session_change(request_key: UUID, request: Request):
    """Recover the originating Trainer's immutable result after reassignment or transport loss."""
    with authorized_transaction(request, advisory_lock=request_cancellation.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_changes.reconcile(session, principal, request_key)


@router.get("/sessions/{session_id}/plan-review", response_model=session_plans.PlanReview)
def review_session_plan(session_id: UUID, request: Request):
    """Review only a currently editable plan; bind scope and stored item versions."""
    with authorized_transaction(request, advisory_lock=session_plans.PLAN_LOCK) as (
        session,
        principal,
    ):
        return session_plans.review(session, principal, session_id)


@router.post(
    "/sessions/{session_id}/plan",
    response_model=session_plans.PlanSaved,
    responses={202: {"model": ApprovalPending}},
)
def save_session_plan(
    session_id: UUID, body: session_plans.SavePlan, request: Request, key: RequestKey
):
    """Replace the reviewed plan atomically without deleting result/media identities."""
    with authorized_transaction(request, advisory_lock=session_plans.PLAN_LOCK) as (
        session,
        principal,
    ):
        return session_plans.save(session, principal, session_id, key, body)


@router.get(
    "/session-plans/{request_key}",
    response_model=session_plans.PlanCopied | session_plans.PlanSaved,
    responses={202: {"model": ApprovalPending}},
)
def reconcile_session_plan(request_key: UUID, request: Request):
    """Return only the authenticated actor's original plan receipt."""
    with authorized_transaction(request, advisory_lock=session_plans.PLAN_LOCK) as (
        session,
        principal,
    ):
        return session_plans.reconcile(session, principal, request_key)


@router.get("/sessions/{session_id}/previous-plan", response_model=session_plans.PreviousPlan)
def previous_session_plan(session_id: UUID, request: Request):
    """Preview the latest permitted previous plan without changing either session."""
    with authorized_transaction(request, advisory_lock=session_plans.PLAN_LOCK) as (
        session,
        principal,
    ):
        return session_plans.previous(session, principal, session_id)


@router.post(
    "/sessions/{session_id}/copy-plan",
    response_model=session_plans.PlanCopied,
    responses={202: {"model": ApprovalPending}},
)
def copy_session_plan(
    session_id: UUID, body: session_plans.CopyPlan, request: Request, key: RequestKey
):
    """Apply only the confirmed source and target versions; recover by the original key."""
    with authorized_transaction(request, advisory_lock=session_plans.PLAN_LOCK) as (
        session,
        principal,
    ):
        return session_plans.copy_previous(session, principal, session_id, key, body)


@router.get("/sessions/{session_id}/outcome-review", response_model=session_outcomes.OutcomeReview)
def review_session_outcome(session_id: UUID, request: Request):
    """Review current measurement identities and correction authority."""
    with authorized_transaction(request, advisory_lock=session_outcomes.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_outcomes.review(session, principal, session_id)


@router.post(
    "/sessions/{session_id}/outcome",
    response_model=session_outcomes.OutcomeSaved,
    responses={202: {"model": ApprovalPending}},
)
def save_session_outcome(
    session_id: UUID, body: session_outcomes.SaveOutcome, request: Request, key: RequestKey
):
    """Correct measured outcomes atomically while preserving completion evidence."""
    with authorized_transaction(request, advisory_lock=session_outcomes.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_outcomes.save(session, principal, session_id, key, body)


@router.get(
    "/session-outcomes/{request_key}",
    response_model=session_outcomes.OutcomeSaved,
    responses={202: {"model": ApprovalPending}},
)
def reconcile_session_outcome(request_key: UUID, request: Request):
    """Read the authenticated actor's original outcome receipt."""
    with authorized_transaction(request, advisory_lock=session_outcomes.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_outcomes.reconcile(session, principal, request_key)


@router.get("/clients/{client_id}/progress", response_model=session_progress.ClientProgress)
def read_client_progress(client_id: UUID, request: Request):
    """Project only permitted persisted signed-session measurements."""
    with authorized_transaction(request) as (session, principal):
        return session_progress.read(session, principal, client_id)


@router.get("/sessions/{session_id}/summary-review", response_model=session_summaries.SummaryReview)
def review_session_summary(session_id: UUID, request: Request):
    """Review current text and authority before replacing the client-facing summary."""
    with authorized_transaction(request, advisory_lock=session_summaries.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_summaries.review(session, principal, session_id)


@router.post(
    "/sessions/{session_id}/summary",
    response_model=session_summaries.SummarySaved,
    responses={202: {"model": ApprovalPending}},
)
def save_session_summary(
    session_id: UUID, body: session_summaries.SaveSummary, request: Request, key: RequestKey
):
    """Persist a reviewed summary without recording completion or delivery."""
    with authorized_transaction(request, advisory_lock=session_summaries.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_summaries.save(session, principal, session_id, key, body)


@router.get(
    "/session-summaries/{request_key}",
    response_model=session_summaries.SummarySaved,
    responses={202: {"model": ApprovalPending}},
)
def reconcile_session_summary(request_key: UUID, request: Request):
    """Recover only the authenticated actor's original summary receipt."""
    with authorized_transaction(request, advisory_lock=session_summaries.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_summaries.reconcile(session, principal, request_key)


@router.get(
    "/sessions/{session_id}/acknowledgement-review",
    response_model=session_acknowledgements.AcknowledgementReview,
)
def review_session_acknowledgement(session_id: UUID, request: Request):
    """Review current authority, completion evidence and credit balance."""
    with authorized_transaction(request, advisory_lock=session_acknowledgements.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_acknowledgements.review(session, principal, session_id)


@router.post(
    "/sessions/{session_id}/acknowledgement",
    response_model=session_acknowledgements.AcknowledgementSaved,
    responses={202: {"model": ApprovalPending}},
)
def save_session_acknowledgement(
    session_id: UUID,
    body: session_acknowledgements.SaveAcknowledgement,
    request: Request,
    key: RequestKey,
):
    """Atomically persist acknowledgement, completion, credit and original-command receipt."""
    with authorized_transaction(request, advisory_lock=session_acknowledgements.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_acknowledgements.save(session, principal, session_id, key, body)


@router.get(
    "/session-acknowledgements/{request_key}",
    response_model=session_acknowledgements.AcknowledgementSaved,
    responses={202: {"model": ApprovalPending}},
)
def reconcile_session_acknowledgement(request_key: UUID, request: Request):
    """Recover only the authenticated actor's original acknowledgement receipt."""
    with authorized_transaction(request, advisory_lock=session_acknowledgements.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_acknowledgements.reconcile(session, principal, request_key)


@router.post("/clients/{client_id}/report-actions", response_model=session_reports.ReportEvent)
def record_progress_report(
    client_id: UUID, body: session_reports.ReportAction, request: Request, key: RequestKey
):
    """Record a browser report action without claiming external delivery."""
    with authorized_transaction(request, advisory_lock=session_reports.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_reports.record(session, principal, client_id, key, body)


@router.get("/report-actions/{request_key}", response_model=session_reports.ReportEvent)
def recover_progress_report(request_key: UUID, request: Request):
    """Recover only this actor's original audit, without repeating a device action."""
    with authorized_transaction(request, advisory_lock=session_reports.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_reports.reconcile(session, principal, request_key)


@router.get("/clients/{client_id}/report-history", response_model=list[session_reports.ReportEvent])
def read_progress_report_history(
    client_id: UUID, request: Request, purchase_id: UUID | None = None
):
    """Owner/Admin history retains actor, package and original action evidence."""
    with authorized_transaction(request) as (session, principal):
        return session_reports.history(session, principal, client_id, purchase_id)


@router.get("/remuneration", response_model=list[remuneration_schemas.PayView])
def list_remuneration(request: Request):
    """Owner all-trainer or Trainer self-only cycles; Admin financial access is forbidden."""
    with authorized_transaction(request, advisory_lock=remuneration.DECISION_LOCK) as (
        session,
        principal,
    ):
        return remuneration.listing(session, principal)


@router.get("/remuneration/{cycle_key}/{trainer_id}", response_model=remuneration_schemas.PayRecord)
def remuneration_detail(cycle_key: str, trainer_id: UUID, request: Request):
    """Current calculation alongside immutable approved amounts and later evidence differences."""
    with authorized_transaction(request, advisory_lock=remuneration.DECISION_LOCK) as (
        session,
        principal,
    ):
        return remuneration.detail(session, principal, cycle_key, trainer_id)


@router.post(
    "/remuneration/{cycle_key}/{trainer_id}/approval", response_model=remuneration_schemas.PaySaved
)
def approve_remuneration(
    cycle_key: str,
    trainer_id: UUID,
    body: remuneration_schemas.ApprovePay,
    request: Request,
    key: RequestKey,
):
    """Owner approval binds the reviewed source and atomically records immutable pay evidence."""
    with authorized_transaction(request, advisory_lock=remuneration.DECISION_LOCK) as (
        session,
        principal,
    ):
        return remuneration.approve(session, principal, cycle_key, trainer_id, key, body)


@router.get("/remuneration-approvals/{request_key}", response_model=remuneration_schemas.PaySaved)
def remuneration_approval_receipt(request_key: UUID, request: Request):
    """Original active Owner can recover an approval without repeating its financial effect."""
    with authorized_transaction(request, advisory_lock=remuneration.DECISION_LOCK) as (
        session,
        principal,
    ):
        return remuneration.reconcile(session, principal, request_key)


@router.get("/sessions/{session_id}/handoff-review", response_model=session_handoffs.HandoffReview)
def review_session_handoff(session_id: UUID, request: Request):
    """Legacy compatibility review; current PDF exports do not invoke the opening marker."""
    with authorized_transaction(request, advisory_lock=session_handoffs.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_handoffs.review(session, principal, session_id)


@router.post("/sessions/{session_id}/handoff", response_model=session_handoffs.HandoffSaved)
def mark_session_handoff(
    session_id: UUID, body: session_handoffs.MarkHandoff, request: Request, key: RequestKey
):
    """Record an opening exactly once per intent, without claiming delivery or changing credits."""
    with authorized_transaction(request, advisory_lock=session_handoffs.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_handoffs.save(session, principal, session_id, key, body)


@router.get("/session-handoffs/{request_key}", response_model=session_handoffs.HandoffSaved)
def recover_session_handoff(request_key: UUID, request: Request):
    """Recover only the active original actor's opening result without another write."""
    with authorized_transaction(request, advisory_lock=session_handoffs.DECISION_LOCK) as (
        session,
        principal,
    ):
        return session_handoffs.reconcile(session, principal, request_key)
