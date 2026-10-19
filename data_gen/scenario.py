"""Fixed scenario constants for the `imaging_tuesday_v1` synthetic demo.

All dates are fictional scenario dates (see docs/05-DATA-FIXTURES.md). Nothing
here is live institutional data.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

SCENARIO_ID = "imaging_tuesday_v1"
PROVENANCE = "synthetic:" + SCENARIO_ID
RANDOM_SEED = 20261103
TZ_NAME = "America/Chicago"
TZ = ZoneInfo(TZ_NAME)

# Scenario clock: planning happens before the Thu Oct 29 last safe order date.
SCENARIO_NOW = datetime(2026, 10, 28, 10, 0, tzinfo=TZ)

DEMO_WEEK_MONDAY = date(2026, 11, 2)
HISTORY_WEEKS = 6
HISTORY_WEEK_MONDAYS = [DEMO_WEEK_MONDAY - timedelta(weeks=n) for n in range(HISTORY_WEEKS, 0, -1)]

# Staffed hours: Mon-Fri 09:00-17:00 = 40 h/week for every instrument and room.
DAY_OPEN = time(9, 0)
DAY_CLOSE = time(17, 0)
STAFFED_HOURS_PER_WEEK = 40

CANONICAL_REQUEST = (
    "I need to image GFP-tagged cells Tuesday morning: three hours on a confocal, "
    "a prep room beforehand, and enough anti-GFP antibody and coverslips. "
    "I need the results by Wednesday."
)


def week_days(monday):
    """Return the five weekday dates starting at `monday`."""
    return [monday + timedelta(days=i) for i in range(5)]


def local_dt(day, hhmm):
    """Build a tz-aware America/Chicago datetime from a date and 'HH:MM'."""
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime.combine(day, time(hour, minute), tzinfo=TZ)


def iso_local(dt):
    return dt.isoformat()


def iso_utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
