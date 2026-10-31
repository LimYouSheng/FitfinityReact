"""Capture reviewable business state without exposing a client-selected executable target."""

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from app.authorization import unavailable
from app.models.people import Client, ClientPerson, Trainer
from app.models.training import TrainingSession


def review_snapshot(session, principal, operation, values):
    """The frozen command carries its target label and available full domain review."""
    from app.api import (
        client_assignment,
        client_deactivation,
        client_reactivation,
        client_renewal,
        client_weekly_schedule,
        package_action_review,
        session_acknowledgements,
        session_booking_review,
        session_outcomes,
        session_plans,
        session_postponement,
        session_summaries,
        trainer_deactivation,
        trainer_reactivation,
    )

    if operation in {"report.progress", "report.session"}:
        from app.api.report_sharing import checked_review

        viewed = checked_review(session, principal, values["body"])
        return {
            "subject": viewed.inputs["client"]["name"],
            "proposed": viewed.model_dump(mode="json"),
        }
    if operation == "library.publish":
        from app.api.library_approval import snapshot

        return snapshot(session, principal, values["key"])
    if operation == "undo.clientPackages":
        from app.api.package_action_undo import inspect

        view = inspect(session, principal, values["identity"])[0]
        return {
            "subject": "Restore deleted package sessions",
            "proposed": view.model_dump(mode="json"),
        }
    if operation.startswith("undo."):
        from app.api.session_undo_approval import snapshot

        return jsonable_encoder(snapshot(session, principal, values["identity"]))
    identity = values.get("identity") or values.get("client_id") or values.get("trainer_id")
    body = values["body"]
    before = None
    readers = {
        "client.deactivate": client_deactivation.review,
        "trainer.reactivate": trainer_reactivation.review,
        "trainer.deactivate": trainer_deactivation.review,
        "client.assignment": client_assignment.review,
        "client.weekly": client_weekly_schedule.review,
        "client.purchase": client_renewal.review,
        "session.booking": session_booking_review.review,
        "session.postpone": session_postponement.review,
        "session.plan": session_plans.review,
        "session.copy_plan": session_plans.previous,
        "session.outcome": session_outcomes.review,
        "session.summary": session_summaries.review,
        "session.acknowledge": session_acknowledgements.review,
    }
    if operation == "client.assignment":
        before = client_assignment.review(session, principal, identity, body.purchaseId)
    elif operation == "trainer.email":
        trainer = session.get(Trainer, identity)
        if trainer is None:
            raise unavailable()
        before = {"email": trainer.email, "version": trainer.version}
    elif operation in readers:
        before = readers[operation](session, principal, identity)
    elif operation in {"client.reactivate", "purchase.reactivate"}:
        before = client_reactivation.review(
            session, principal, identity, body, package_id=values.get("purchase_id")
        )
    elif operation == "purchase.action":
        before = package_action_review.review(
            session, principal, identity, values["purchase_id"], body.operation
        )
    elif operation == "request.resolve":
        from app.models.communications import ChangeRequest, RequestSlot

        row = session.get(ChangeRequest, identity)
        if row is None:
            raise unavailable()
        before = {column.name: getattr(row, column.name) for column in row.__table__.columns}
        before["slots"] = [
            {column.name: getattr(slot, column.name) for column in slot.__table__.columns}
            for slot in session.scalars(
                select(RequestSlot).where(RequestSlot.request_id == identity)
            )
        ]
    subject = None
    if identity:
        if operation.startswith("client.") or operation.startswith("purchase."):
            row = session.get(Client, identity)
            subject = row.name if row else None
        elif operation.startswith("trainer."):
            row = session.get(Trainer, identity)
            subject = row.name if row else None
        elif operation.startswith("session."):
            row = session.get(TrainingSession, identity)
            client = session.get(Client, row.client_id) if row else None
            subject = f"{client.name} · session {row.id}" if client else None
    if operation.startswith("assessment."):
        from app.models.assessments import ClientAssessment, ClientAssessmentRevision

        person_id = values.get("person_id")
        if operation == "assessment.save":
            assessment = session.get(ClientAssessment, values["assessment_id"])
            if assessment is None:
                raise unavailable()
            person_id = assessment.client_person_id
            revision = session.scalar(
                select(ClientAssessmentRevision).where(
                    ClientAssessmentRevision.assessment_id == assessment.id,
                    ClientAssessmentRevision.revision == assessment.version,
                )
            )
            if revision:
                from app.api.schemas import AssessmentRevision

                before = AssessmentRevision.model_validate(revision)
        person = session.get(ClientPerson, person_id)
        if person is None:
            raise unavailable()
        subject = person.name
    return jsonable_encoder({"subject": subject, "before": before})
