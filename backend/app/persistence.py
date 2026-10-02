"""Internal persistence primitives. Call inside Database.transaction(), after authorization.

These functions never commit, expose HTTP endpoints or trust a browser actor/clock. M5.3/M5.4
will supply the authenticated principal; M6 services own scheduling and workflow orchestration.
"""

import hashlib
import json
import math
from collections.abc import Sequence
from datetime import date, time
from uuid import UUID

from sqlalchemy import Date, Time, Uuid, and_, column, func, or_, select, text, values
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, SessionTransactionOrigin

from app.models.common import Versioned
from app.models.evidence import ReportAudit
from app.models.people import Client, ClientPerson, StaffUser, Trainer
from app.models.training import (
    Acknowledgement,
    CreditDebit,
    PackagePurchase,
    PurchasePreference,
    PurchaseScheduleSlot,
    TrainingSession,
)


class PersistenceConflict(ValueError):
    """The reviewed identity/version or operation payload no longer matches."""


def require_transaction(session: Session) -> None:
    transaction = session.get_transaction()
    if transaction is None or transaction.origin is not SessionTransactionOrigin.BEGIN:
        raise RuntimeError("An explicit outer transaction is required")


def reviewed[T: Versioned](
    session: Session, model: type[T], identity: UUID, expected_version: int
) -> T:
    """Lock and refresh the reviewed row. ORM versioning also catches stale detached writers."""
    require_transaction(session)
    if type(expected_version) is not int or expected_version < 1:
        raise PersistenceConflict("A positive reviewed version is required")
    record = session.scalar(
        select(model)
        .where(model.id == identity)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if record is None or record.version != expected_version:
        raise PersistenceConflict("Record changed; refresh and review again")
    return record


def add_client(session: Session, client: Client, people: Sequence[ClientPerson]) -> Client:
    require_transaction(session)
    if len(people) != (2 if client.kind == "couple" else 1):
        raise ValueError("Review every person's details")
    session.add(client)
    session.flush()
    for position, person in enumerate(people, 1):
        person.client_id, person.position = client.id, position
        session.add(person)
    session.flush()
    return client


def require_valid_session_schedule(
    training_date: date,
    starts_at: time,
    ends_at: time,
) -> None:
    """Persistence accepts real calendar dates and minute-precision local intervals only."""
    if (
        type(training_date) is not date
        or type(starts_at) is not time
        or type(ends_at) is not time
        or any(
            value.tzinfo is not None or value.second or value.microsecond
            for value in (starts_at, ends_at)
        )
        or starts_at >= ends_at
    ):
        raise ValueError("Choose a valid date, start time and end time")


def add_purchase(
    session: Session,
    purchase: PackagePurchase,
    slots: Sequence[PurchaseScheduleSlot],
    preferences: Sequence[PurchasePreference],
    bookings: Sequence[TrainingSession],
    *,
    expected_client_version: int,
) -> PackagePurchase:
    """Persist a reviewed aggregate, including every generated session, without a partial commit."""
    require_transaction(session)
    for booking in bookings:
        require_valid_session_schedule(booking.training_date, booking.starts_at, booking.ends_at)
    client = reviewed(session, Client, purchase.client_id, expected_client_version)
    if client.status != "active":
        raise PersistenceConflict("Client is inactive")
    if len(slots) != purchase.sessions_per_week or len(bookings) != purchase.total_sessions:
        raise ValueError("Complete purchase schedule and session set required")
    if any(booking.client_id != client.id for booking in bookings):
        raise ValueError("Session belongs to another client")
    # All competing scheduling writers use client then sorted trainer locks. Database range
    # constraints independently protect purchase dates; future M6 rescheduling uses this order.
    trainer_ids = sorted({purchase.trainer_id, *(booking.trainer_id for booking in bookings)})
    trainers = session.scalars(
        select(Trainer).where(Trainer.id.in_(trainer_ids)).order_by(Trainer.id).with_for_update()
    ).all()
    if len(trainers) != len(trainer_ids) or any(trainer.status != "active" for trainer in trainers):
        raise PersistenceConflict("Active assigned trainers required")
    proposed = values(
        column("trainer_id", Uuid),
        column("training_date", Date),
        column("starts_at", Time),
        column("ends_at", Time),
        name="proposed",
    ).data([(b.trainer_id, b.training_date, b.starts_at, b.ends_at) for b in bookings])
    conflict = session.scalar(
        select(TrainingSession.id)
        .join(PackagePurchase, TrainingSession.purchase_id == PackagePurchase.id)
        .join(Client, TrainingSession.client_id == Client.id)
        .join(
            proposed,
            (TrainingSession.training_date == proposed.c.training_date)
            & (TrainingSession.starts_at < proposed.c.ends_at)
            & (TrainingSession.ends_at > proposed.c.starts_at)
            & (
                (TrainingSession.trainer_id == proposed.c.trainer_id)
                | (TrainingSession.client_id == client.id)
            ),
        )
        .where(
            or_(
                TrainingSession.status == "completed",
                and_(
                    Client.status == "active",
                    PackagePurchase.status == "active",
                    TrainingSession.status.in_(("scheduled", "planned")),
                ),
            ),
        )
        .limit(1)
    )
    if conflict is not None:
        raise PersistenceConflict("Purchase conflicts with an existing booking")
    for index, booking in enumerate(bookings):
        if any(
            booking.training_date == other.training_date
            and booking.starts_at < other.ends_at
            and other.starts_at < booking.ends_at
            for other in bookings[index + 1 :]
        ):
            raise PersistenceConflict("Purchase contains overlapping bookings")
    session.add(purchase)
    session.flush()
    for child in [*slots, *preferences]:
        child.purchase_id = purchase.id
        session.add(child)
    session.flush()
    for booking in bookings:
        booking.purchase_id = purchase.id
        session.add(booking)
    # Touch the aggregate even when only child rows changed, invalidating other review screens.
    client.version += 1
    session.flush()
    return purchase


def signature_evidence(strokes: object) -> tuple[bytes, str]:
    """Validate the established 600x200 drawing bounds, then encode immutable signature bytes."""
    if not isinstance(strokes, list) or not 1 <= len(strokes) <= 100:
        raise ValueError("Draw a valid signature")
    distance, count, normalized = 0.0, 0, []
    for stroke in strokes:
        if not isinstance(stroke, list) or not stroke:
            raise ValueError("Signature strokes must contain points")
        points = []
        for point in stroke:
            if not isinstance(point, dict):
                raise ValueError("Signature point is invalid")
            x, y = point.get("x"), point.get("y")
            if any(type(value) not in (int, float) for value in (x, y)):
                raise ValueError("Signature coordinates must be finite numbers")
            count += 1
            if not 0 <= x <= 600 or not 0 <= y <= 200 or count > 10000:
                raise ValueError("Signature exceeds drawing limits")
            if points:
                distance += math.hypot(x - points[-1]["x"], y - points[-1]["y"])
            points.append({"x": x, "y": y})
        normalized.append(points)
    if count < 3 or distance < 15:
        raise ValueError("Draw a complete signature")
    payload = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return payload, hashlib.sha256(payload).hexdigest()


def acknowledge(
    session: Session,
    session_id: UUID,
    expected_version: int,
    actor_id: UUID,
    *,
    method: str,
    signer_name: str | None = None,
    strokes: object = None,
    note: str = "",
) -> Acknowledgement:
    require_transaction(session)
    identity = session.get(TrainingSession, session_id)
    if identity is None:
        raise PersistenceConflict("Session is unavailable")
    # Lifecycle operations take this same client -> purchase -> session order, so eligibility
    # cannot change between our check and completion. Ownership columns are immutable.
    client = session.scalar(
        select(Client)
        .where(Client.id == identity.client_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    purchase = session.scalar(
        select(PackagePurchase)
        .where(PackagePurchase.id == identity.purchase_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    booking = reviewed(session, TrainingSession, session_id, expected_version)
    actor = session.get(StaffUser, actor_id)
    if (
        client.status != "active"
        or purchase.status != "active"
        or actor is None
        or actor.status != "active"
    ):
        raise PersistenceConflict("Active client, purchase and stored actor required")
    today = session.scalar(text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date"))
    if booking.training_date > today or booking.status == "cancelled":
        raise PersistenceConflict("Session is not eligible for completion")
    signature = digest = None
    if method == "signature":
        if not signer_name or not signer_name.strip():
            raise ValueError("Signer name is required")
        signer_name = signer_name.strip()
        signature, digest = signature_evidence(strokes)
    elif method != "late_no_show" or signer_name is not None or strokes is not None:
        raise ValueError("Choose signature or late/no-show acknowledgement")
    previous = session.scalar(
        select(Acknowledgement)
        .where(Acknowledgement.session_id == session_id)
        .order_by(Acknowledgement.sequence.desc())
        .limit(1)
    )
    if previous and (previous.method != "late_no_show" or method != "signature"):
        raise PersistenceConflict("Only a no-show can be corrected to a signature")
    acknowledgement = Acknowledgement(
        session_id=session_id,
        sequence=2 if previous else 1,
        method=method,
        signer_name=signer_name,
        signature=signature,
        signature_sha256=digest,
        note=note.strip(),
        actor_id=actor.id,
        actor_name=actor.name,
    )
    session.add(acknowledgement)
    if previous is None:
        session.add(
            CreditDebit(
                session_id=session_id,
                client_id=booking.client_id,
                purchase_id=booking.purchase_id,
                actor_id=actor.id,
                actor_name=actor.name,
            )
        )
        booking.status = "completed"
    else:
        booking.version += 1
    session.flush()
    return acknowledgement


def report_action(
    session: Session,
    operation_id: UUID,
    actor_id: UUID,
    client_id: UUID,
    purchase_id: UUID,
    kind: str,
) -> ReportAudit:
    """Audit retries share one identity; a different payload cannot reuse that identity."""
    require_transaction(session)
    if kind not in ("pdf_export", "pdf_share_opened", "whatsapp_opened"):
        raise ValueError("New CSV audit entries are not supported")
    if not isinstance(purchase_id, UUID):
        raise ValueError("An explicit purchase identity is required for new report actions")
    actor = session.get(StaffUser, actor_id)
    if actor is None:
        raise ValueError("Stored actor required")
    digest = hashlib.sha256(
        json.dumps(
            [str(actor_id), str(client_id), str(purchase_id), kind], separators=(",", ":")
        ).encode()
    ).hexdigest()
    session.execute(
        insert(ReportAudit)
        .values(
            id=operation_id,
            actor_id=actor.id,
            actor_name=actor.name,
            client_id=client_id,
            purchase_id=purchase_id,
            kind=kind,
            request_sha256=digest,
        )
        .on_conflict_do_nothing(index_elements=[ReportAudit.id])
    )
    saved = session.get(ReportAudit, operation_id)
    if saved.request_sha256 != digest:
        raise PersistenceConflict("Operation identity already belongs to another report action")
    return saved


def used_credits(session: Session, purchase_id: UUID) -> int:
    """Usage is derived from the unique ledger, never maintained as a second mutable counter."""
    return session.scalar(
        select(func.count()).select_from(CreditDebit).where(CreditDebit.purchase_id == purchase_id)
    )
