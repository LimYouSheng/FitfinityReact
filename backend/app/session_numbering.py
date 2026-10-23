"""Chronological display positions never replace permanent session identities."""

from sqlalchemy import select

from app.models.training import PackagePurchase, TrainingSession
from app.persistence import require_transaction


def renumber_purchase(session, purchase_id):
    """Renumber a locked purchase in the caller's transaction after booking edits.

    The caller owns authorization and locks the client before the purchase. Flush
    booking dates first so database guards can verify each resulting position.
    Completed evidence stays attached to the same session ID.
    """
    require_transaction(session)
    with session.no_autoflush:
        purchase = session.scalar(
            select(PackagePurchase).where(PackagePurchase.id == purchase_id).with_for_update()
        )
    if purchase is None:
        raise ValueError("Purchase not found")
    session.flush()
    records = session.scalars(
        select(TrainingSession)
        .where(TrainingSession.purchase_id == purchase_id)
        .order_by(TrainingSession.id)
        .with_for_update()
    ).all()
    booked = sorted(
        (row for row in records if row.schedule_state == "booked"),
        key=lambda row: (row.training_date, row.starts_at, str(row.id)),
    )
    changed = []
    for number, row in enumerate(booked, start=1):
        if row.session_number != number:
            row.session_number = number
            row.version += 1
            changed.append(row.id)
    session.flush()
    return changed
