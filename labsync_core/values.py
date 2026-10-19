"""Coercion and interval helpers shared by every module.

Time intervals are half-open `[start, end)` and always timezone-aware.
"""
from datetime import date, datetime, timedelta


def to_dt(value):
    """Parse an ISO 8601 string (or pass through a datetime). Naive values are rejected."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise TypeError("expected datetime or ISO string, got %r" % (value,))
    if dt.tzinfo is None:
        raise ValueError("naive datetime not allowed: %s" % value)
    return dt


def to_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def iso(dt):
    return dt.isoformat()


def as_list(value):
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [v for v in value.split(";") if v]
    return list(value)


def as_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")


def as_num(value, default=0):
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return value
    num = float(value)
    return int(num) if num.is_integer() else num


def hours_between(start, end):
    return (to_dt(end) - to_dt(start)).total_seconds() / 3600


def overlaps(a_start, a_end, b_start, b_end):
    """True when half-open intervals [a_start, a_end) and [b_start, b_end) intersect."""
    return to_dt(a_start) < to_dt(b_end) and to_dt(b_start) < to_dt(a_end)


def violates_buffer(a_start, a_end, b_start, b_end, buffer_minutes):
    """True when two sessions on one resource are closer than `buffer_minutes`.

    The buffer is applied once, between the sessions: they are compatible iff the
    gap between them is at least the buffer (docs/09: don't double-apply).
    """
    gap = timedelta(minutes=buffer_minutes)
    return to_dt(a_start) < to_dt(b_end) + gap and to_dt(b_start) < to_dt(a_end) + gap


def business_days_before(day, n):
    """The date `n` business days (Mon-Fri) before `day`."""
    day = to_date(day)
    while n > 0:
        day -= timedelta(days=1)
        if day.weekday() < 5:
            n -= 1
    return day


def add_business_days(day, n):
    day = to_date(day)
    while n > 0:
        day += timedelta(days=1)
        if day.weekday() < 5:
            n -= 1
    return day
