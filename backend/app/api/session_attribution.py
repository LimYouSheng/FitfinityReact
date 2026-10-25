"""Read only the attribution evidence for an independently authorized session."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select

from app.api.directory import bounded
from app.api.schemas import Contract
from app.api.session_read_schemas import SessionActorRead
from app.authorization import session_record
from app.models.communications import ChangeRequest, SessionEvent
from app.models.people import Trainer
from app.models.session_attribution import (
    SessionTrainerAssignmentHistory,
    SessionTrainerAttribution,
)


class AssignmentRead(Contract):
    id: UUID
    oldTrainerId: UUID
    newTrainerId: UUID
    recordedBy: SessionActorRead
    recordedAt: datetime
    reason: str
    requestId: UUID | None
    requestedBy: SessionActorRead | None


class AttributionRead(Contract):
    sessionId: UUID
    originalState: Literal["captured", "legacy_unresolved"]
    original: SessionActorRead | None
    assigned: SessionActorRead
    performedBy: SessionActorRead | None
    history: list[AssignmentRead]


def read(session, principal, identity):
    """No client-profile authority or arbitrary Trainer details are exposed by history."""
    booking = session_record(session, principal, identity)
    attribution = session.get(SessionTrainerAttribution, identity)

    def label(trainer_id):
        if trainer_id is None:
            return None
        trainer = session.get(Trainer, trainer_id)
        return SessionActorRead(id=trainer.id, name=trainer.name)

    def requester(event):
        if event.request_id is None:
            return None
        request = session.get(ChangeRequest, event.request_id)
        return SessionActorRead(id=request.actor_id, name=request.actor_name)

    events = bounded(
        session,
        select(SessionEvent)
        .join(
            SessionTrainerAssignmentHistory,
            SessionTrainerAssignmentHistory.event_id == SessionEvent.id,
        )
        .where(SessionEvent.session_id == identity)
        .order_by(SessionEvent.created_at, SessionEvent.session_version, SessionEvent.id),
    )
    return AttributionRead(
        sessionId=identity,
        originalState=attribution.original_state,
        original=label(attribution.original_trainer_id),
        assigned=label(booking.assigned_trainer_id),
        performedBy=label(attribution.performed_by_trainer_id),
        history=[
            AssignmentRead(
                id=event.id,
                oldTrainerId=event.old_trainer_id,
                newTrainerId=event.new_trainer_id,
                recordedBy=SessionActorRead(id=event.actor_id, name=event.actor_name),
                recordedAt=event.created_at,
                reason=event.note,
                requestId=event.request_id,
                requestedBy=requester(event),
            )
            for event in events
        ],
    )
