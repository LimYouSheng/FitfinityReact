"""Revalidate frozen proposals and apply them through the existing domain owners."""

from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.api import client_weekly_schedule as weekly
from app.api import client_weekly_schedule_save as weekly_save
from app.api import session_booking_review as booking_review
from app.api import session_booking_save as booking_save
from app.api import session_postponement as postponement
from app.api import trainer_availability as availability
from app.authorization import conflict
from app.models.communications import RequestSlot
from app.models.people import Trainer, TrainerAvailability


def context(session, principal, request):
    """Take domain locks before the request lock, matching proposal writers."""
    if request.kind == "trainer_availability":
        trainer = session.scalar(
            select(Trainer).where(Trainer.id == request.trainer_id).with_for_update()
        )
        slots = session.scalars(
            select(TrainerAvailability)
            .where(TrainerAvailability.trainer_id == request.trainer_id)
            .with_for_update()
        ).all()
        return trainer, slots
    if request.kind == "fixed_weekly_schedule":
        return weekly.inspect(session, principal, request.client_id, write=True)
    if request.kind == "session_postpone":
        return postponement.review_context(
            session, principal, request.session_id, write=True, resolving=request.id
        )
    return booking_review.inspect(session, principal, request.session_id, write=True)


def windows(rows, side):
    return sorted(
        [
            {
                "weekday": row.weekday,
                "startsAt": row.starts_at.strftime("%H:%M"),
                "endsAt": row.ends_at.strftime("%H:%M"),
            }
            for row in rows
            if row.side == side
        ],
        key=lambda row: (row["weekday"], row["startsAt"], row["endsAt"]),
    )


def apply(session, principal, request, viewed):
    """Apply the still-current proposal within the decision transaction."""
    if request.kind == "trainer_availability":
        trainer, current = viewed
        if (
            trainer is None
            or trainer.status != "active"
            or trainer.version != request.expected_version
        ):
            raise conflict()
        rows = session.scalars(
            select(RequestSlot).where(RequestSlot.request_id == request.id)
        ).all()
        before, after = windows(rows, "old"), windows(rows, "new")
        if availability.snapshot(current) != before:
            raise conflict()
        validated = availability.SaveAvailability(expectedVersion=trainer.version, slots=after)
        if before == after:
            raise conflict()
        availability.apply_availability(
            session, principal, trainer, [slot.model_dump() for slot in validated.slots]
        )
        return
    if request.kind == "fixed_weekly_schedule":
        view, client, purchase, trainer, slots, bookings, now = viewed
        if (
            purchase.id != request.purchase_id
            or purchase.version != request.expected_version
            or trainer.id != request.trainer_id
        ):
            raise conflict()
        rows = session.scalars(
            select(RequestSlot).where(RequestSlot.request_id == request.id)
        ).all()
        before = sorted(
            (str(row.slot_identity), row.weekday, row.starts_at, row.ends_at)
            for row in rows
            if row.side == "old"
        )
        if before != sorted(
            (str(row.id), row.weekday, row.starts_at, row.ends_at) for row in slots
        ):
            raise conflict()
        body = weekly.SaveClientWeeklySchedule(
            expected=view.expected,
            slots=[
                {
                    "id": row.slot_identity,
                    "weekday": row.weekday,
                    "startsAt": row.starts_at.strftime("%H:%M"),
                    "endsAt": row.ends_at.strftime("%H:%M"),
                }
                for row in rows
                if row.side == "new"
            ],
        )
        planned = weekly.changes(session, view, slots, bookings, now, body)
        weekly_save.apply_weekly(
            session, principal, client, purchase, trainer, slots, planned, body
        )
        return
    if request.kind == "session_postpone":
        _, booking, client, purchase, trainer, _ = viewed
        if (
            booking.version != request.expected_version
            or trainer.id != request.trainer_id
            or (booking.training_date, booking.starts_at, booking.ends_at)
            != (request.old_date, request.old_start, request.old_end)
        ):
            raise conflict()
        postponement.apply_postponement(session, principal, booking, client, purchase)
        return
    view, booking, client, purchase, bookings, trainers, pending, _ = viewed
    if (
        booking.version != request.expected_version
        or booking.trainer_id != request.trainer_id
        or any(row.id != request.id for row in pending)
    ):
        raise conflict()
    requester = next(row for row in trainers if row.id == request.trainer_id)
    if requester.status != "active":
        raise conflict()
    if request.kind == "session_time":
        if (booking.training_date, booking.starts_at, booking.ends_at) != (
            request.old_date,
            request.old_start,
            request.old_end,
        ):
            raise conflict()
        now = session.scalar(select(func.clock_timestamp())).astimezone(ZoneInfo("Asia/Singapore"))
        current = (now.date(), now.time().replace(tzinfo=None))
        if (
            booking.schedule_state == "booked"
            and (booking.training_date, booking.starts_at) <= current
        ) or (request.new_date, request.new_start) <= current:
            raise conflict()
        target_date, start, end, trainer_id = (
            request.new_date,
            request.new_start,
            request.new_end,
            booking.trainer_id,
        )
    else:
        target_date, start, end, trainer_id = (
            booking.training_date,
            booking.starts_at,
            booking.ends_at,
            request.replacement_trainer_id,
        )
    replacement = next(
        (row for row in trainers if row.id == trainer_id and row.status == "active"), None
    )
    if replacement is None:
        raise conflict()
    if booking.schedule_state == "open" and request.kind == "session_trainer":
        booking_save.apply_open_reassignment(
            session, principal, booking, client, purchase, trainer_id
        )
        return
    body = booking_review.SaveSessionBooking(
        expected=view.expected,
        date=target_date.isoformat(),
        startsAt=start.strftime("%H:%M"),
        endsAt=end.strftime("%H:%M"),
        trainerId=trainer_id,
    )
    if not booking_review.validate_change(session, view, booking, trainers, [], body):
        raise conflict()
    booking_save.apply_booking(
        session, principal, booking, client, purchase, bookings, trainers, body
    )
