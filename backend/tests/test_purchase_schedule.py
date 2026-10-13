"""Calendar/interval regressions for the server counterpart of prototype matching."""

from datetime import UTC, date, time

import pytest

from app.purchase_schedule import (
    CadenceUnavailable,
    DatedSlot,
    WeeklySlot,
    generated_dates,
    matching_schedule,
)


def slot(day=0, start=10, end=11):
    return WeeklySlot(day, time(start), time(end))


def test_purchase_dates_start_midweek_cross_leap_day_and_include_last_valid_day():
    schedule = [slot(0), slot(3)]
    actual = generated_dates(date(2028, 2, 28), 4, 11, schedule)
    assert [item.training_date.isoformat() for item in actual] == [
        "2028-02-28",
        "2028-03-02",
        "2028-03-06",
        "2028-03-09",
    ]
    assert [item.slot.weekday for item in actual] == [0, 3, 0, 3]
    with pytest.raises(CadenceUnavailable):
        generated_dates(date(2028, 2, 28), 4, 10, schedule)
    assert generated_dates(date(2028, 2, 29), 1, 7, schedule)[0].training_date == date(2028, 3, 2)


@pytest.mark.parametrize(
    "args",
    [
        (True, time(10), time(11)),
        (7, time(10), time(11)),
        (0, time(11), time(11)),
        (0, time(12), time(11)),
        (0, time(10, 0, 1), time(11)),
        (0, time(10, tzinfo=UTC), time(11)),
    ],
)
def test_rejects_invalid_or_nonlocal_slots(args):
    with pytest.raises(ValueError):
        WeeklySlot(*args)


@pytest.mark.parametrize(
    "total,days,schedule",
    [
        (True, 90, [slot()]),
        (366, 90, [slot()]),
        (1, 0, [slot()]),
        (1, 90, []),
        (2, 90, [slot(), slot(0, 12, 13)]),
    ],
)
def test_rejects_invalid_purchase_terms_and_duplicate_weekdays(total, days, schedule):
    with pytest.raises(ValueError):
        generated_dates(date(2026, 10, 12), total, days, schedule)


def test_matching_tries_other_times_and_days_without_changing_preferences():
    preferences = [slot(), slot(0, 11, 12), slot(2), slot(4)]
    hours = [slot(0, 9, 18), slot(2, 9, 18), slot(4, 9, 18)]
    occupied = [DatedSlot(date(2026, 10, 19), slot()), DatedSlot(date(2026, 10, 14), slot(2))]
    before = preferences.copy()
    chosen = matching_schedule(date(2026, 10, 12), 4, 90, 2, preferences, hours, occupied)
    assert chosen == [slot(0, 11, 12), slot(4)]
    assert preferences == before
    # Occupancy after the purchased last session does not reserve every future week.
    assert matching_schedule(date(2026, 10, 12), 1, 90, 1, [slot()], hours, occupied) == [slot()]


def test_matching_never_fabricates_hours_or_returns_partial_cadence():
    assert matching_schedule(date(2026, 10, 12), 2, 90, 1, [slot()], [slot(0, 11, 12)], []) == []
    assert matching_schedule(date(2026, 10, 12), 2, 90, 2, [slot(), slot()], [slot()], []) == []
    assert matching_schedule(date(2026, 10, 12), 2, 7, 1, [slot()], [slot()], []) == []


def test_calendar_boundary_and_long_validity_are_bounded():
    assert len(generated_dates(date(2026, 10, 12), 365, 1000000, [slot()])) == 365
    with pytest.raises(ValueError, match="supported calendar"):
        generated_dates(date(9999, 12, 31), 1, 2, [slot(4)])
