"""Renewal follow-ups depend on remaining usable purchases, not validity ordering."""

from sqlalchemy import Date, and_, cast, func, select

from app.models.training import CreditDebit, PackagePurchase


def usable_purchase():
    """Include active/upcoming purchases with unspent credits; exclude expired/history rows."""
    used = (
        select(func.count(CreditDebit.id))
        .where(CreditDebit.purchase_id == PackagePurchase.id)
        .correlate(PackagePurchase)
        .scalar_subquery()
    )
    today = cast(func.timezone("Asia/Singapore", func.clock_timestamp()), Date)
    return and_(
        PackagePurchase.status == "active",
        PackagePurchase.stage != "archived",
        PackagePurchase.end_date >= today,
        used < PackagePurchase.total_sessions,
    )
