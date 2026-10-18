"""Small calendar helpers shared by the domain modules."""

from __future__ import annotations

import calendar
from datetime import date, timedelta


def clamp_day(year: int, month: int, day: int) -> date:
    """date(year, month, day), moved back to the month's last day if it doesn't exist."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def add_months(d: date, months: int) -> date:
    index = d.year * 12 + d.month - 1 + months
    return clamp_day(index // 12, index % 12 + 1, d.day)


def months_window_start(as_of: date, months: int) -> date:
    """First day of the window covering `months` months up to and including as_of."""
    return add_months(as_of, -months) + timedelta(days=1)


def month_keys(as_of: date, months: int) -> list[tuple[int, int]]:
    """The last `months` calendar months, oldest first, ending with as_of's month."""
    keys = []
    for back in range(months - 1, -1, -1):
        d = add_months(date(as_of.year, as_of.month, 1), -back)
        keys.append((d.year, d.month))
    return keys


def week_start(d: date) -> date:
    """Monday of the week containing d (forecast weeks run Monday to Sunday)."""
    return d - timedelta(days=d.weekday())


def previous_period(start: date, end: date) -> tuple[date, date]:
    """The period of the same length just before [start, end]. Whole calendar months map to the
    same number of whole months before (Sep -> Aug, Q3 -> Q2); anything else to the same number
    of days."""
    following = end + timedelta(days=1)
    if start.day == 1 and following.day == 1:
        months = (following.year - start.year) * 12 + following.month - start.month
        return add_months(start, -months), start - timedelta(days=1)
    length = end - start + timedelta(days=1)
    return start - length, start - timedelta(days=1)
