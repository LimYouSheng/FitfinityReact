"""Server-owned Singapore pay reviews; approval freezes evidence without transferring money."""

import hashlib
import json
import re
from datetime import date, timedelta

from sqlalchemy import or_, select, text

from app.api.remuneration_schemas import PayCycle, PayRecord, PayRow, PaySaved, PayView
from app.api.request_cancellation import DECISION_LOCK
from app.auth.errors import AuthError
from app.authorization import conflict, unavailable
from app.models.communications import Message, MessageReceipt
from app.models.evidence import RemunerationApproval, RemunerationLine
from app.models.people import Client, StaffUser, Trainer
from app.models.training import Acknowledgement, PackagePurchase, TrainingSession


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def cycle_for(day):
    return (
        (day.replace(day=28) + timedelta(days=4)).replace(day=1) if day.day > 15 else day
    ).strftime("%Y-%m")


def cycle(key):
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", key):
        raise AuthError("invalid_cycle", "Choose a valid pay cycle.", 422)
    try:
        first = date.fromisoformat(key + "-01")
        return PayCycle(
            key=key,
            start=(first - timedelta(days=1)).replace(day=16),
            end=first.replace(day=15),
            payout=first.replace(day=16),
        )
    except (ValueError, OverflowError) as error:
        raise AuthError("invalid_cycle", "Choose a valid pay cycle.", 422) from error


def today(session):
    return session.scalar(text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date"))


def allowed(principal, identity=None):
    if principal.role == "admin":
        raise AuthError("forbidden", "Remuneration access is restricted.", 403)
    if identity is not None and principal.role != "owner" and identity != principal.trainer_id:
        raise unavailable()


def bounded(rows):
    result = list(rows)
    if len(result) > 2000:
        raise AuthError("pay_capacity", "Remuneration could not be loaded completely.", 503)
    return result


def source(booking, acknowledgement):
    # Attendance and booking evidence determine later differences; rate/profile edits do not.
    return digest(
        [
            booking.id,
            booking.client_id,
            booking.purchase_id,
            booking.trainer_id,
            booking.training_date,
            booking.starts_at,
            booking.ends_at,
            booking.status,
            acknowledgement.id if acknowledgement else None,
        ]
    )


def band_for(day, start):
    minute = start.hour * 60 + start.minute
    return (
        "peak" if day.weekday() >= 5 or 390 <= minute < 510 or 1080 <= minute < 1230 else "offPeak"
    )


def draft(session, key, trainer, business_date):
    """Calculate flat session pay from persisted attendance and current saved rates."""
    period = cycle(key)
    bookings = bounded(
        session.execute(
            select(TrainingSession, Client, PackagePurchase)
            .join(Client, Client.id == TrainingSession.client_id)
            .join(PackagePurchase, PackagePurchase.id == TrainingSession.purchase_id)
            .where(
                TrainingSession.trainer_id == trainer.id,
                TrainingSession.training_date.between(period.start, period.end),
                TrainingSession.status != "cancelled",
                or_(
                    TrainingSession.status == "completed",
                    (Client.status == "active") & (PackagePurchase.status == "active"),
                ),
            )
            .order_by(TrainingSession.training_date, TrainingSession.starts_at, TrainingSession.id)
            .limit(2001)
        )
    )
    identities = [booking.id for booking, _, _ in bookings]
    acknowledgements = {}
    if identities:
        for ack in session.scalars(
            select(Acknowledgement)
            .where(Acknowledgement.session_id.in_(identities))
            .order_by(Acknowledgement.sequence)
        ):
            acknowledgements[ack.session_id] = ack
    rows, evidence = [], {}
    for booking, client, purchase in bookings:
        ack = acknowledgements.get(booking.id)
        band = band_for(booking.training_date, booking.starts_at)
        billable = booking.status == "completed" and booking.training_date <= business_date
        issues = [] if booking.status == "completed" else ["Session is not completed"]
        if booking.status == "completed" and booking.training_date > business_date:
            issues.append("Future completion date")
        if booking.status == "completed" and ack is None:
            issues.append("Completion evidence is unavailable")
        start, end = booking.starts_at, booking.ends_at
        minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
        row = PayRow(
            sessionId=booking.id,
            source=source(booking, ack),
            clientId=client.id,
            clientName=client.name,
            clientType="Couple" if client.kind == "couple" else "Individual",
            date=booking.training_date,
            **{"from": start.strftime("%H:%M")},
            to=end.strftime("%H:%M"),
            durationMinutes=minutes if billable and ack and ack.method != "late_no_show" else 0,
            status=booking.status,
            billable=billable,
            band=band,
            amountCents=(trainer.peak_rate_cents if band == "peak" else trainer.off_peak_rate_cents)
            if billable
            else None,
            issues=issues,
        )
        rows.append(row)
        evidence[booking.id] = (booking, client, purchase, ack)
    closed = business_date > period.end
    count = sum(bool(row.issues) for row in rows)
    status = (
        "In progress"
        if not closed
        else "No sessions"
        if not rows
        else "Pending review"
        if count
        else "Pending approval"
    )
    if sum(row.amountCents or 0 for row in rows) > 9007199254740991:
        raise AuthError("pay_capacity", "Remuneration exceeds the supported review range.", 503)
    result = PayRecord(
        cycle=period,
        trainerId=trainer.id,
        trainerName=trainer.name,
        rows=rows,
        sessions=sum(row.billable for row in rows),
        totalSessions=len(rows),
        minutes=sum(row.durationMinutes for row in rows),
        amountCents=sum(row.amountCents or 0 for row in rows),
        reviewCount=count,
        closed=closed,
        status=status,
        revision=digest(
            [
                key,
                trainer.id,
                trainer.name,
                trainer.version,
                trainer.peak_rate_cents,
                trainer.off_peak_rate_cents,
                [row.model_dump(mode="json", by_alias=True) for row in rows],
            ]
        ),
    )
    return result, evidence


def approved_record(session, approval, current):
    """Project immutable pay lines separately from later source evidence differences."""
    lines = bounded(
        session.scalars(
            select(RemunerationLine)
            .where(RemunerationLine.approval_id == approval.id)
            .order_by(
                RemunerationLine.training_date,
                RemunerationLine.starts_at,
                RemunerationLine.session_id,
            )
            .limit(2001)
        )
    )
    rows = [
        PayRow(
            sessionId=line.session_id,
            source=line.source_sha256,
            clientId=line.client_id,
            clientName=line.client_name,
            clientType="Couple" if line.client_kind == "couple" else "Individual",
            date=line.training_date,
            **{"from": line.starts_at.strftime("%H:%M")},
            to=line.ends_at.strftime("%H:%M"),
            durationMinutes=line.minutes,
            status="completed",
            billable=True,
            band="peak" if line.band == "peak" else "offPeak",
            amountCents=line.amount_cents,
            issues=[],
        )
        for line in lines
    ]
    return PayRecord(
        cycle=PayCycle(
            key=approval.cycle_key,
            start=approval.cycle_start,
            end=approval.cycle_end,
            payout=approval.payout_date,
        ),
        trainerId=approval.trainer_id,
        trainerName=approval.trainer_name,
        rows=rows,
        sessions=approval.session_count,
        totalSessions=len(rows),
        minutes=approval.total_minutes,
        amountCents=approval.amount_cents,
        reviewCount=0,
        closed=True,
        status="Approved",
        revision=approval.source_sha256,
        approvedAt=approval.created_at,
        approvedBy=approval.actor_id,
        changed={r.sessionId: r.source for r in rows}
        != {r.sessionId: r.source for r in current.rows},
        current=current,
    )


def detail(session, principal, key, identity, business_date=None):
    allowed(principal, identity)
    business_date = business_date or today(session)
    period = cycle(key)
    if key > cycle_for(business_date):
        raise unavailable()
    trainer = session.get(Trainer, identity)
    if trainer is None:
        raise unavailable()
    current, _ = draft(session, period.key, trainer, business_date)
    approval = session.scalar(
        select(RemunerationApproval).where(
            RemunerationApproval.trainer_id == identity, RemunerationApproval.cycle_key == key
        )
    )
    return approved_record(session, approval, current) if approval else current


def listing(session, principal):
    """List past/current scoped cycles; fail explicitly instead of truncating financial records."""
    allowed(principal)
    business_date = today(session)
    current = cycle_for(business_date)
    trainers = bounded(
        session.scalars(
            select(Trainer)
            .where(True if principal.role == "owner" else Trainer.id == principal.trainer_id)
            .order_by(Trainer.name, Trainer.id)
            .limit(2001)
        )
    )
    ids = [trainer.id for trainer in trainers]
    dates = bounded(
        session.scalars(
            select(TrainingSession.training_date)
            .where(
                TrainingSession.trainer_id.in_(ids),
                TrainingSession.status != "cancelled",
                TrainingSession.training_date.is_not(None),
            )
            .distinct()
            .limit(2001)
        )
    )
    keys = {current, *(cycle_for(day) for day in dates)}
    keys.update(
        bounded(
            session.scalars(
                select(RemunerationApproval.cycle_key)
                .where(RemunerationApproval.trainer_id.in_(ids))
                .distinct()
                .limit(2001)
            )
        )
    )
    if len(keys) * len(trainers) > 2000:
        raise AuthError("pay_capacity", "Remuneration could not be loaded completely.", 503)
    views = []
    for key in sorted((key for key in keys if key <= current), reverse=True):
        records = [
            detail(session, principal, key, trainer.id, business_date) for trainer in trainers
        ]
        records = [
            record
            for record, trainer in zip(records, trainers, strict=True)
            if record.rows or trainer.status == "active"
        ]
        views.append(PayView(key=key, cycle=cycle(key), isCurrent=key == current, trainers=records))
    return views


def receipt(session, principal, key):
    principal.owner()
    session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": DECISION_LOCK})
    return session.scalar(
        select(RemunerationApproval).where(
            RemunerationApproval.id == key, RemunerationApproval.actor_id == principal.user_id
        )
    )


def saved(approval):
    return PaySaved(
        id=approval.id,
        trainerId=approval.trainer_id,
        cycle=approval.cycle_key,
        revision=approval.source_sha256,
        approvedAt=approval.created_at,
    )


def reconcile(session, principal, key):
    previous = receipt(session, principal, key)
    if previous is None:
        raise unavailable()
    return saved(previous)


def approve(session, principal, key, identity, request_key, body):
    """Serialize session decisions and lock rate evidence before final approval."""
    previous = receipt(session, principal, request_key)
    if previous:
        if (previous.cycle_key, previous.trainer_id, previous.source_sha256) != (
            key,
            identity,
            body.revision,
        ):
            raise AuthError("idempotency_conflict", "Review this approval before retrying.", 409)
        return saved(previous)
    if session.get(RemunerationApproval, request_key) is not None:
        raise AuthError("idempotency_conflict", "This key belongs to another approval.", 409)
    period = cycle(key)
    scope = select(TrainingSession).where(
        TrainingSession.trainer_id == identity,
        TrainingSession.training_date.between(period.start, period.end),
    )
    bookings = bounded(session.scalars(scope.limit(2001)))
    # Match lifecycle writers: client -> purchase -> session -> trainer. The route's
    # decision barrier prevents concurrent booking insertion/reassignment phantoms.
    for model, ids in (
        (Client, {row.client_id for row in bookings}),
        (PackagePurchase, {row.purchase_id for row in bookings}),
        (TrainingSession, {row.id for row in bookings}),
    ):
        list(
            session.scalars(
                select(model)
                .where(model.id.in_(ids))
                .order_by(model.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
    trainer = session.scalar(
        select(Trainer)
        .where(Trainer.id == identity)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if trainer is None:
        raise unavailable()
    if {row.id for row in bookings} != set(
        session.scalars(scope.with_only_columns(TrainingSession.id))
    ):
        raise conflict()
    viewed, evidence = draft(session, key, trainer, today(session))
    if (
        viewed.revision != body.revision
        or not viewed.closed
        or not viewed.sessions
        or viewed.reviewCount
    ):
        raise conflict()
    if session.scalar(
        select(RemunerationApproval.id).where(
            RemunerationApproval.trainer_id == identity, RemunerationApproval.cycle_key == key
        )
    ):
        raise conflict()
    approval = RemunerationApproval(
        id=request_key,
        trainer_id=identity,
        trainer_name=trainer.name,
        cycle_key=key,
        cycle_start=viewed.cycle.start,
        cycle_end=viewed.cycle.end,
        payout_date=viewed.cycle.payout,
        amount_cents=viewed.amountCents,
        total_minutes=viewed.minutes,
        session_count=viewed.sessions,
        source_sha256=viewed.revision,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(approval)
    session.flush()
    for row in viewed.rows:
        booking, client, purchase, ack = evidence[row.sessionId]
        session.add(
            RemunerationLine(
                approval_id=approval.id,
                trainer_id=identity,
                session_id=booking.id,
                client_id=client.id,
                purchase_id=purchase.id,
                client_name=client.name,
                client_kind=client.kind,
                training_date=booking.training_date,
                starts_at=booking.starts_at,
                ends_at=booking.ends_at,
                session_version=booking.version,
                acknowledgement_id=ack.id,
                acknowledgement_method=ack.method,
                band="peak" if row.band == "peak" else "off_peak",
                minutes=row.durationMinutes,
                amount_cents=row.amountCents,
                source_sha256=row.source,
            )
        )
    notice = Message(
        kind="remuneration_approval",
        title=f"Remuneration approved · {trainer.name} · {key}",
        body=(
            f"{viewed.sessions} completed sessions approved at SGD "
            f"{viewed.amountCents // 100}.{viewed.amountCents % 100:02d} "
            f"for {viewed.cycle.start} to {viewed.cycle.end}. "
            "Open the remuneration breakdown for the approved record."
        ),
        trainer_id=identity,
        remuneration_id=approval.id,
        actor_id=principal.user_id,
        actor_name=principal.name,
    )
    session.add(notice)
    session.flush()
    for user_id in session.scalars(
        select(StaffUser.id).where(
            StaffUser.status == "active",
            or_(StaffUser.role == "owner", StaffUser.id == trainer.user_id),
        )
    ):
        session.add(MessageReceipt(message_id=notice.id, user_id=user_id))
    return saved(approval)
