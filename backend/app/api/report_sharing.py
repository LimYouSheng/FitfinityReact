"""Review frozen report content before an explicit device share; never send a report."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import AwareDatetime, Field, StrictBool, StrictStr, model_validator
from sqlalchemy import select

from app.api import session_progress, session_reads
from app.api.admin_supervision import (
    ApprovalPending,
    digest,
    original_proposal,
    pending_response,
    supervised,
)
from app.api.dependencies import authorized_transaction
from app.api.routes import RequestKey
from app.api.schemas import ERROR_RESPONSES, Contract
from app.auth.errors import AuthError
from app.authorization import client_record, conflict, unavailable
from app.models.admin_requests import AdminOperationRequest
from app.models.training import PackagePurchase

router = APIRouter(prefix="/api/report-sharing", tags=["Report sharing"], responses=ERROR_RESPONSES)


class ReportSelection(Contract):
    kind: Literal["progress", "session"]
    targetId: UUID
    purchaseId: UUID
    includeSummary: StrictBool = True
    videoIds: list[UUID] = Field(default_factory=list, max_length=2000)

    @model_validator(mode="after")
    def unique_selection(self):
        if len(set(self.videoIds)) != len(self.videoIds):
            raise ValueError("Select each caption once")
        if self.kind == "progress" and (self.videoIds or not self.includeSummary):
            raise ValueError("Progress reports include all recorded exercises")
        return self


class ShareReport(ReportSelection):
    expected: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    at: AwareDatetime


class ReportReview(Contract):
    expected: str
    kind: Literal["progress", "session"]
    inputs: dict


def automatic_summary(detail):
    """Match the existing client-facing fallback without including private trainer comments."""
    booking = detail.session
    duration = 0
    if booking.startsAt and booking.endsAt:

        def minutes(value):
            return int(value[:2]) * 60 + int(value[3:])

        duration = max(0, minutes(booking.endsAt) - minutes(booking.startsAt))
    lines = [
        f"Session duration: {duration} minutes",
        f"Exercises completed ({len(detail.exercisePlan)}).",
    ]
    for item in detail.exercisePlan:
        values = [
            item.weight,
            f"{item.reps} reps" if item.reps else "",
            f"{item.rounds} rounds" if item.rounds else "",
            f"{item.rest} rest" if item.rest else "",
            *(part.value for part in item.customDetails),
        ]
        description = " · ".join(value for value in values if value)
        lines.append(f"- {item.name}" + (f" — {description}" if description else ""))
    return "\n".join(lines)


def review(session, principal, body):
    """Project only report-visible fields from current scoped persisted records."""
    if body.kind == "progress":
        client = client_record(session, principal, body.targetId)
        purchase = session.get(PackagePurchase, body.purchaseId)
        if purchase is None or purchase.client_id != client.id:
            raise unavailable()
        exercises = []
        for group in session_progress.read(session, principal, client.id).exercises:
            points = [
                point.model_dump(mode="json")
                for point in group.points
                if point.packageId == purchase.id
            ]
            if points:
                exercises.append({"id": str(group.id), "name": group.name, "points": points})
        if not exercises:
            raise AuthError(
                "report_empty", "No completed exercise loads are available to share.", 409
            )
        inputs = {
            "client": {
                "id": str(client.id),
                "name": client.name,
                "reportPackageId": str(purchase.id),
                "strengthProgress": exercises,
            },
            "timeZone": "Asia/Singapore",
        }
        versions = [client.version, purchase.version]
    else:
        detail = session_reads.detail(session, principal, body.targetId)
        if detail.purchase.id != body.purchaseId:
            raise unavailable()
        selected = set(body.videoIds)
        videos = [
            item.model_dump(
                mode="json",
                include={"id", "name", "weight", "reps", "rounds", "rest", "customDetails"},
            )
            for item in detail.exercisePlan
            if item.id in selected and item.videoAttached
        ]
        if len(videos) != len(selected):
            raise conflict()
        summary = (detail.clientSummary or automatic_summary(detail)) if body.includeSummary else ""
        if not summary.strip() and not videos:
            raise AuthError("report_empty", "Select a summary or video captions.", 409)
        booking = detail.session
        inputs = {
            "client": {
                "id": str(detail.client.id),
                "name": detail.client.name,
                "package": detail.purchase.model_dump(mode="json"),
            },
            "session": {
                "id": str(booking.id),
                "packageId": str(booking.purchaseId),
                "date": booking.date.isoformat() if booking.date else None,
                "from": booking.startsAt,
                "to": booking.endsAt,
                "scheduleState": "open" if booking.scheduleState == "open" else "scheduled",
                "sessionNumber": booking.sessionNumber,
            },
            "summary": summary,
            "videos": videos,
        }
        versions = [booking.version]
    return ReportReview(
        kind=body.kind,
        inputs=inputs,
        expected=digest({"kind": body.kind, "inputs": inputs, "versions": versions}),
    )


def checked_review(session, principal, body):
    viewed = review(session, principal, body)
    if viewed.expected != body.expected:
        raise conflict()
    if body.kind == "progress":
        viewed.inputs["at"] = body.at.isoformat()
    return viewed


def receipt(session, principal, key):
    proposal = original_proposal(session, principal, key)
    return (
        proposal
        if proposal
        and proposal.status == "approved"
        and proposal.operation in {"report.progress", "report.session"}
        else None
    )


@supervised("progressReportSharing", "report.progress", ShareReport, receipt=receipt)
def progress(session, principal, key, body):
    if body.kind != "progress":
        raise unavailable()
    return checked_review(session, principal, body)


@supervised("sessionPdfSharing", "report.session", ShareReport, receipt=receipt)
def session_pdf(session, principal, key, body):
    if body.kind != "session":
        raise unavailable()
    return checked_review(session, principal, body)


@router.post("/review", response_model=ReportReview)
def review_report(body: ReportSelection, request: Request, key: RequestKey):
    with authorized_transaction(request) as (session, principal):
        return review(session, principal, body)


@router.post("", response_model=ReportReview, responses={202: {"model": ApprovalPending}})
def authorize_share(body: ShareReport, request: Request, key: RequestKey):
    """Authorization prepares content only; device sharing needs a subsequent explicit click."""
    with authorized_transaction(request) as (session, principal):
        return (progress if body.kind == "progress" else session_pdf)(session, principal, key, body)


@router.get("/{key}", response_model=ReportReview, responses={202: {"model": ApprovalPending}})
def recover_share(key: UUID, request: Request):
    """Recover only the actor's proposal; changed content cannot reuse an old approval."""
    with authorized_transaction(request) as (session, principal):
        proposal = original_proposal(session, principal, key)
        return recover_proposal(session, principal, proposal)


def recover_proposal(session, principal, proposal):
    if proposal is None or proposal.operation not in {"report.progress", "report.session"}:
        raise unavailable()
    if proposal.status == "pending":
        return pending_response(proposal)
    if proposal.status != "approved":
        raise AuthError(
            "approval_closed", "This report was not approved. Review a new request.", 409
        )
    return checked_review(session, principal, ShareReport.model_validate(proposal.body["body"]))


@router.get(
    "/requests/{identity}", response_model=ReportReview, responses={202: {"model": ApprovalPending}}
)
def recover_report_request(identity: UUID, request: Request):
    with authorized_transaction(request) as (session, principal):
        proposal = session.scalar(
            select(AdminOperationRequest).where(
                AdminOperationRequest.id == identity,
                AdminOperationRequest.actor_id == principal.user_id,
            )
        )
        return recover_proposal(session, principal, proposal)
