"""Persisted calendars and individual session evidence with minimal cover context."""

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.api.directory import MAX_RECORDS, bounded
from app.api.session_read_schemas import (
    CalendarSession,
    SessionAcknowledgementRead,
    SessionActorRead,
    SessionCalendar,
    SessionClientLabel,
    SessionDetailRead,
    SessionPlanRead,
    SessionPurchaseLabel,
    SessionResultRead,
    SessionTrainerLabel,
)
from app.auth.errors import AuthError
from app.authorization import session_record, session_scope
from app.models.media import MediaAsset
from app.models.people import Client, Trainer
from app.models.training import (
    Acknowledgement,
    CreditDebit,
    ExercisePlanItem,
    ExerciseResult,
    PackagePurchase,
    TrainingSession,
)
from app.persistence import signature_evidence

MAX_SESSIONS = MAX_RECORDS * 365


def row(booking, principal):
    return CalendarSession(
        readAccess="operations"
        if principal.manages_operations
        else "assigned"
        if booking.trainer_id == principal.trainer_id
        else "historical",
        id=booking.id,
        version=booking.version,
        clientId=booking.client_id,
        purchaseId=booking.purchase_id,
        trainerId=booking.trainer_id,
        scheduleState=booking.schedule_state,
        sessionNumber=booking.session_number,
        date=booking.training_date,
        startsAt=booking.starts_at.strftime("%H:%M") if booking.starts_at else None,
        endsAt=booking.ends_at.strftime("%H:%M") if booking.ends_at else None,
        status=booking.status,
    )


def purchase_label(purchase, used):
    return SessionPurchaseLabel(
        id=purchase.id,
        clientId=purchase.client_id,
        trainerId=purchase.trainer_id,
        name=purchase.name,
        status=purchase.status,
        stage=purchase.stage,
        total=purchase.total_sessions,
        used=used,
        validityDays=purchase.validity_days,
        startDate=purchase.start_date,
        endDate=purchase.end_date,
    )


def calendar(session, principal):
    # One SQL statement observes session and label identities together. Never fetch
    # profiles or contacts merely because a Trainer covers a session for that client.
    used_count = (
        select(func.count())
        .select_from(CreditDebit)
        .where(CreditDebit.purchase_id == PackagePurchase.id)
        .correlate(PackagePurchase)
        .scalar_subquery()
    )
    result = session.execute(
        select(TrainingSession, Client, Trainer, PackagePurchase, used_count)
        .join(Client, TrainingSession.client_id == Client.id)
        .join(Trainer, TrainingSession.trainer_id == Trainer.id)
        .join(PackagePurchase, TrainingSession.purchase_id == PackagePurchase.id)
        .where(
            TrainingSession.id.in_(
                select(TrainingSession.id).where(session_scope(principal)).correlate(None)
            )
        )
        .order_by(TrainingSession.id)
        .limit(MAX_SESSIONS + 1)
    ).all()
    if len(result) > MAX_SESSIONS:
        raise AuthError("calendar_capacity", "The calendar could not be loaded completely.", 503)
    clients, trainers, purchases, used = {}, {}, {}, {}
    for _, client, trainer, purchase, count in result:
        clients[client.id], trainers[trainer.id], purchases[purchase.id] = client, trainer, purchase
        used[purchase.id] = count
    return SessionCalendar(
        viewerId=principal.user_id,
        sessions=[row(booking, principal) for booking, *_ in result],
        clients=[SessionClientLabel.model_validate(c) for c in clients.values()],
        trainers=[SessionTrainerLabel.model_validate(t) for t in trainers.values()],
        purchases=[purchase_label(p, used.get(p.id, 0)) for p in purchases.values()],
    )


def detail(session, principal, identity):
    booking = session_record(session, principal, identity)
    client, trainer, purchase = (
        session.get(Client, booking.client_id),
        session.get(Trainer, booking.trainer_id),
        session.get(PackagePurchase, booking.purchase_id),
    )
    plan = bounded(
        session,
        select(ExercisePlanItem)
        .where(ExercisePlanItem.session_id == identity)
        .order_by(ExercisePlanItem.position, ExercisePlanItem.id),
    )
    results = bounded(
        session,
        select(ExerciseResult)
        .where(ExerciseResult.session_id == identity)
        .order_by(ExerciseResult.id),
    )
    acknowledgements = bounded(
        session,
        select(Acknowledgement)
        .where(Acknowledgement.session_id == identity)
        .order_by(Acknowledgement.sequence),
        2,
    )
    videos = set(
        session.scalars(
            select(MediaAsset.original_plan_item_id).where(
                MediaAsset.session_id == identity,
                MediaAsset.purpose == "session_video",
                MediaAsset.status == "ready",
                MediaAsset.expires_at > datetime.now(UTC),
            )
        )
    )
    history = []
    for entry in acknowledgements:
        signature = None
        if entry.signature is not None:
            if hashlib.sha256(entry.signature).hexdigest() != entry.signature_sha256:
                raise AuthError(
                    "session_evidence", "The session evidence could not be verified.", 503
                )
            try:
                signature = json.loads(entry.signature)
                signature_evidence(signature)
            except (ValueError, TypeError, UnicodeDecodeError) as error:
                raise AuthError(
                    "session_evidence", "The session evidence could not be verified.", 503
                ) from error
        history.append(
            SessionAcknowledgementRead(
                id=entry.id,
                sequence=entry.sequence,
                method=entry.method,
                signerName=entry.signer_name,
                signature=signature,
                note=entry.note,
                recordedAt=entry.created_at,
                recordedBy=SessionActorRead(id=entry.actor_id, name=entry.actor_name),
            )
        )
    used = session.scalar(
        select(func.count()).select_from(CreditDebit).where(CreditDebit.purchase_id == purchase.id)
    )
    return SessionDetailRead(
        session=row(booking, principal),
        client=SessionClientLabel.model_validate(client),
        trainer=SessionTrainerLabel.model_validate(trainer),
        purchase=purchase_label(purchase, used),
        exercisePlan=[
            SessionPlanRead(
                id=p.id,
                version=p.version,
                name=p.name,
                weight=p.weight,
                reps=p.reps,
                rounds=p.rounds,
                rest=p.rest,
                notes=p.notes,
                videoAttached=p.id in videos,
            )
            for p in plan
        ],
        exerciseResults=[
            SessionResultRead(
                id=r.id,
                planItemId=r.plan_item_id,
                name=r.name,
                loadKg=float(r.load_kg),
                reps=r.reps,
                sets=r.sets,
            )
            for r in results
        ],
        acknowledgementHistory=history,
        trainerComments=booking.trainer_comments,
        clientSummary=booking.client_summary,
        whatsappOpenedAt=booking.whatsapp_opened_at,
        whatsappOpenCount=booking.whatsapp_open_count,
    )
