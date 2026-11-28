"""Explicit report-email intent; approval/preparation alone never queues delivery."""

from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import Field, StrictStr
from sqlalchemy import select, text

from app.api.admin_supervision import digest
from app.api.dependencies import authorized_transaction
from app.api.report_sharing import ReportSelection, review
from app.api.routes import RequestKey
from app.api.schemas import ERROR_RESPONSES, Contract
from app.auth.errors import AuthError
from app.authorization import unavailable
from app.email_delivery import enqueue
from app.models.admin_management import AdminApprovalRequirement
from app.models.admin_requests import AdminOperationRequest
from app.models.email_delivery import EmailReportReceipt
from app.models.people import ClientPerson

router = APIRouter(prefix="/api/report-email", tags=["Report email"], responses=ERROR_RESPONSES)


class EmailReport(ReportSelection):
    expected: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class Recipient(Contract):
    name: str
    email: str


class EmailReview(Contract):
    expected: str
    recipients: list[Recipient]


class EmailQueued(Contract):
    requestId: UUID
    queued: int


def enabled(request):
    if not request.app.state.auth_settings.transactional_email_enabled:
        raise AuthError("EMAIL_NOT_CONFIGURED", "Email sending is not configured yet.", 409)


def inspect(session, principal, body):
    if body.kind != "progress":
        raise unavailable()
    viewed = review(session, principal, body)
    recipients = session.scalars(
        select(ClientPerson)
        .where(
            ClientPerson.client_id == body.targetId,
            ClientPerson.email != "",
        )
        .order_by(ClientPerson.position)
        .with_for_update(read=True)
    ).all()
    if not recipients:
        raise AuthError(
            "EMAIL_RECIPIENT_MISSING", "Add a client email address before sending.", 409
        )
    expected = digest(
        {
            "report": viewed.expected,
            "recipients": [{"id": str(p.id), "name": p.name, "email": p.email} for p in recipients],
        }
    )
    return viewed, recipients, expected


def approved(session, principal, body, viewed):
    if principal.role != "admin":
        return
    policy = session.get(AdminApprovalRequirement, (principal.user_id, "progressReportSharing"))
    if policy is None or not policy.required:
        return
    proposals = session.scalars(
        select(AdminOperationRequest).where(
            AdminOperationRequest.actor_id == principal.user_id,
            AdminOperationRequest.operation == "report.progress",
            AdminOperationRequest.status == "approved",
        )
    )
    if not any(
        p.body.get("body", {}).get("expected") == viewed.expected
        and p.body["body"].get("targetId") == str(body.targetId)
        and p.body["body"].get("purchaseId") == str(body.purchaseId)
        for p in proposals
    ):
        raise AuthError(
            "REPORT_APPROVAL_REQUIRED", "Review and obtain approval for this report first.", 409
        )


def report_text(viewed):
    lines = ["Your recorded exercise progress:"]
    for exercise in viewed.inputs["client"]["strengthProgress"]:
        lines.append(f"\n{exercise['name']}")
        for point in exercise["points"]:
            lines.append(
                f"{point['date']}: {point['load']} kg · {point['reps']} reps · {point['sets']} sets"
            )
    return "\n".join(lines)


def saved(session, principal, key):
    return session.scalar(
        select(EmailReportReceipt).where(
            EmailReportReceipt.actor_id == principal.user_id,
            EmailReportReceipt.request_key == key,
        )
    )


@router.post("/review", response_model=EmailReview)
def review_email(body: ReportSelection, request: Request, key: RequestKey):
    enabled(request)
    with authorized_transaction(request) as (session, principal):
        viewed, people, expected = inspect(session, principal, body)
        approved(session, principal, body, viewed)
        return EmailReview(
            expected=expected, recipients=[Recipient(name=p.name, email=p.email) for p in people]
        )


@router.post("", response_model=EmailQueued)
def queue_email(body: EmailReport, request: Request, key: RequestKey):
    enabled(request)
    with authorized_transaction(request) as (session, principal):
        fingerprint = digest(body.model_dump(mode="json"))
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"email:{principal.user_id}:{fingerprint}"},
        )
        prior = saved(session, principal, key)
        if prior:
            if prior.request_sha256 != fingerprint:
                raise AuthError("idempotency_conflict", "Check the original email request.", 409)
            return EmailQueued.model_validate(prior.result)
        previous_content = session.scalar(
            select(EmailReportReceipt).where(
                EmailReportReceipt.actor_id == principal.user_id,
                EmailReportReceipt.request_sha256 == fingerprint,
            )
        )
        if previous_content:
            return EmailQueued.model_validate(previous_content.result)
        viewed, people, expected = inspect(session, principal, body)
        approved(session, principal, body, viewed)
        if expected != body.expected:
            raise AuthError(
                "VERSION_CONFLICT", "The report or recipients changed. Review again.", 409
            )
        for person in people:
            enqueue(
                session,
                f"report.email:{principal.user_id}:{key}:{person.id}",
                "progress_report",
                person.email,
                {"name": person.name, "report": report_text(viewed)},
            )
        result = EmailQueued(requestId=key, queued=len(people))
        session.add(
            EmailReportReceipt(
                actor_id=principal.user_id,
                request_key=key,
                request_sha256=fingerprint,
                result=result.model_dump(mode="json"),
            )
        )
        return result


@router.get("/{key}", response_model=EmailQueued)
def recover_email(key: UUID, request: Request):
    with authorized_transaction(request) as (session, principal):
        prior = saved(session, principal, key)
        if prior is None:
            raise unavailable()
        return EmailQueued.model_validate(prior.result)
