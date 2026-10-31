"""Derive client charts from scoped, signed, persisted measured outcomes."""

from datetime import date
from uuid import UUID

from sqlalchemy import exists, select

from app.api.schemas import Contract
from app.auth.errors import AuthError
from app.authorization import can_coach_client, client_record, session_scope, unavailable
from app.models.training import Acknowledgement, ExerciseResult, TrainingSession


class ProgressPoint(Contract):
    id: UUID
    sessionId: UUID
    packageId: UUID
    date: date
    load: float
    reps: int
    sets: int


class ProgressExercise(Contract):
    id: UUID
    name: str
    points: list[ProgressPoint]


class ClientProgress(Contract):
    clientId: UUID
    exercises: list[ProgressExercise]


def read(session, principal, identity):
    """Full-profile authority is required; temporary cover never expands client-history access."""
    client = client_record(session, principal, identity)
    if not can_coach_client(session, principal, client.id):
        raise unavailable()
    rows = session.execute(
        select(ExerciseResult, TrainingSession)
        .join(TrainingSession, ExerciseResult.session_id == TrainingSession.id)
        .where(
            TrainingSession.client_id == identity,
            TrainingSession.status == "completed",
            TrainingSession.training_date.is_not(None),
            session_scope(principal),
            ExerciseResult.retired_at.is_(None),
            exists().where(
                Acknowledgement.session_id == TrainingSession.id,
                Acknowledgement.method == "signature",
            ),
        )
        .order_by(TrainingSession.training_date, TrainingSession.id, ExerciseResult.id)
        .limit(2001)
    ).all()
    if len(rows) > 2000:
        raise AuthError("progress_capacity", "Client progress could not be loaded completely.", 503)
    groups = {}
    for result, booking in rows:
        key = result.name.casefold()
        group = groups.setdefault(key, ProgressExercise(id=result.id, name=result.name, points=[]))
        group.points.append(
            ProgressPoint(
                id=result.id,
                sessionId=booking.id,
                packageId=booking.purchase_id,
                date=booking.training_date,
                load=float(result.load_kg),
                reps=result.reps,
                sets=result.sets,
            )
        )
    return ClientProgress(clientId=identity, exercises=list(groups.values()))
