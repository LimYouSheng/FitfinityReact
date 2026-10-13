"""Purchased-date generation and onboarding matching, independent of HTTP and storage.

Only supplied, covered preference intervals are candidates. Preview results never reserve
time: the purchase transaction must recheck current trainers and occupied sessions.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, time, timedelta
from itertools import combinations


class CadenceUnavailable(ValueError):
    """The selected weekdays cannot fit all purchased sessions within validity."""


@dataclass(frozen=True, order=True)
class WeeklySlot:
    weekday: int
    starts_at: time
    ends_at: time

    def __post_init__(self):
        if (
            type(self.weekday) is not int
            or not 0 <= self.weekday <= 6
            or any(
                type(t) is not time or t.tzinfo is not None or t.second or t.microsecond
                for t in (self.starts_at, self.ends_at)
            )
            or self.starts_at >= self.ends_at
        ):
            raise ValueError("Choose a valid weekday and minute-precision time interval")


@dataclass(frozen=True)
class DatedSlot:
    training_date: date
    slot: WeeklySlot


def generated_dates(start, total, validity_days, schedule):
    """Generate the exact purchased count within inclusive validity, or reject it.

    Iterate weeks, not every validity day; an unusually long historical validity cannot
    turn a bounded 365-session package into unbounded work.
    """
    if (
        type(start) is not date
        or type(total) is not int
        or not 1 <= total <= 365
        or type(validity_days) is not int
        or validity_days < 1
        or not 1 <= len(schedule) <= 7
        or any(not isinstance(slot, WeeklySlot) for slot in schedule)
        or len({slot.weekday for slot in schedule}) != len(schedule)
    ):
        raise ValueError("Review the purchased session count and weekly schedule")
    try:
        end = start + timedelta(days=validity_days - 1)
        first = sorted(((slot.weekday - start.weekday()) % 7, slot) for slot in schedule)
        result = []
        for week in range((total + len(schedule) - 1) // len(schedule)):
            for offset, slot in first:
                day = start + timedelta(days=week * 7 + offset)
                if day > end:
                    raise CadenceUnavailable("The package cadence does not fit its validity")
                result.append(DatedSlot(day, slot))
                if len(result) == total:
                    return result
    except OverflowError:
        raise ValueError("The package exceeds the supported calendar") from None
    raise CadenceUnavailable("The package cadence does not fit its validity")


def covered(slot, availability):
    return any(
        hours.weekday == slot.weekday
        and hours.starts_at <= slot.starts_at
        and hours.ends_at >= slot.ends_at
        for hours in availability
    )


def overlaps(booking, occupied):
    return any(
        other.training_date == booking.training_date
        and other.slot.starts_at < booking.slot.ends_at
        and booking.slot.starts_at < other.slot.ends_at
        for other in occupied
    )


def matching_schedule(start, total, validity_days, frequency, preferences, availability, occupied):
    """Use prototype weekday/preference order and try alternative free intervals.

    Date allocation depends only on selected weekdays. Time alternatives can therefore
    be checked independently instead of searching their Cartesian product.
    """
    if type(frequency) is not int or not 1 <= frequency <= 7:
        raise ValueError("Choose between one and seven sessions per week")
    by_date = defaultdict(list)
    for booking in occupied:
        by_date[booking.training_date].append(booking)
    options = {
        day: list(
            dict.fromkeys(p for p in preferences if p.weekday == day and covered(p, availability))
        )
        for day in range(7)
    }
    days = [day for day, slots in options.items() if slots]
    for selected_days in combinations(days, frequency):
        initial = [options[day][0] for day in selected_days]
        try:
            dated = generated_dates(start, total, validity_days, initial)
        except CadenceUnavailable:
            continue
        chosen = []
        for day in selected_days:
            dates = [booking.training_date for booking in dated if booking.slot.weekday == day]
            available = next(
                (
                    slot
                    for slot in options[day]
                    if all(not overlaps(DatedSlot(d, slot), by_date[d]) for d in dates)
                ),
                None,
            )
            if available is None:
                break
            chosen.append(available)
        if len(chosen) == frequency:
            return chosen
    return []
