"""Booking layouts: hand-placed demo-week sessions plus seeded filler.

Demo-critical sessions are fixed by hand so the planted numbers hold exactly
(docs/05 "Derivation checks"). Everything else is laid out by a seeded random
generator that respects staffed hours, buffers and maintenance windows.
"""
import math

from .scenario import DEMO_WEEK_MONDAY, HISTORY_WEEK_MONDAYS, week_days

OPEN_MIN = 9 * 60
CLOSE_MIN = 17 * 60
QUARTER = 15
MAX_DAY_QUARTERS = 30  # 7.5 h of sessions per day leaves room for buffers
MAX_SESSION_QUARTERS = 16  # 4 h


def hhmm(minutes):
    return "%02d:%02d" % (minutes // 60, minutes % 60)


def _mins(text):
    hour, minute = (int(part) for part in text.split(":"))
    return hour * 60 + minute


# (day offset from demo Monday, start, end, user_id, flexible, booking_id or None)
DEMO_FIXED_INSTRUMENT_SESSIONS = {
    "confocal_1": [
        (0, "09:00", "13:00", "riley_rivera", False, None),
        (0, "13:15", "16:45", "moreno_mgr", False, None),
        (1, "09:00", "09:45", "sam_chen", False, None),
        (1, "10:00", "12:00", "chen_owner", True, "bk_chen_confocal"),
        (1, "15:45", "17:00", "riley_rivera", False, None),
        # The 8 flexible hours whose owners hold confocal_2_cert and fit on Confocal-2.
        (2, "09:00", "13:00", "riley_rivera", True, None),
        (2, "13:15", "16:45", "chen_owner", False, None),
        (3, "09:00", "13:00", "sam_chen", True, None),
        (3, "13:15", "16:45", "morgan", False, None),
        (4, "09:00", "13:00", "chen_owner", False, None),
        (4, "13:15", "16:45", "sam_chen", False, None),
    ],
    "confocal_2": [
        (0, "09:00", "12:00", "sam_chen", False, None),
        (1, "13:00", "15:00", "riley_rivera", False, None),
        (4, "09:00", "12:00", "riley_rivera", False, None),
    ],
    "flow_2": [
        (2, "10:00", "12:00", "jordan_patel", False, None),
        (4, "13:00", "15:00", "riley_rivera", False, None),
    ],
}

# Demo-week booked-hour targets for instruments filled by the seeded layout.  # assumption
DEMO_FILLER_INSTRUMENT_HOURS = {
    "flow_1": 30, "pcr_1": 18, "pcr_2": 10, "centrifuge_1": 12,
    "plate_reader_1": 14, "sequencer_1": 9, "microscope_wide_1": 11,
}

# Planted 6-week history series (docs/05). Others are seeded around a base.
HISTORY_BOOKED_HOURS = {
    "confocal_1": [24, 29, 31, 28, 33, 34],
    "confocal_2": [7, 10, 8, 9, 6, 8],
    "flow_2": [6, 5, 7, 4, 6, 5],
    "flow_1": [27, 29, 30, 28, 31, 30],  # assumption: busy sibling for overflow demand
}
HISTORY_BASE_HOURS = {"pcr_1": 17, "pcr_2": 10, "centrifuge_1": 11, "plate_reader_1": 13,
                      "sequencer_1": 9, "microscope_wide_1": 10}  # assumption
# Requested-but-unbooked hours per history week (latent demand).  # assumption
HISTORY_UNMET_HOURS = {
    "confocal_1": [2, 3, 4, 4, 5, 6],
    "confocal_2": [0, 1, 0, 1, 0, 0],
    "flow_2": [0, 0, 0, 0, 0, 0],
    "flow_1": [3, 4, 3, 5, 4, 5],
}

# Rooms (demo week). Tuesday prep rooms are fixed so prep_a 09:00-09:45 stays free.
DEMO_FIXED_ROOM_SESSIONS = {
    "prep_a": [(1, "10:30", "12:00", "jordan_patel", "Neuron culture prep")],
    "prep_b": [(1, "09:00", "11:00", "rivera_mgr", "Extraction prep")],
}
DEMO_FILLER_ROOM_HOURS = {"prep_a": 12, "prep_b": 10, "analysis_room": 14, "consult_room": 6}  # assumption
ROOM_FILLER_SKIP_DAYS = {"prep_a": {1}, "prep_b": {1}}  # keep Tuesday prep rooms hand-placed


def _split_sessions(rng, quarters):
    """Split a day's booked quarters into 1-3 sessions of at most 4 h."""
    count = max(1, math.ceil(quarters / MAX_SESSION_QUARTERS))
    if quarters >= 8 and count == 1 and rng.random() < 0.4:
        count = 2
    base, extra = divmod(quarters, count)
    sizes = [base + (1 if i < extra else 0) for i in range(count)]
    return [s for s in sizes if s > 0]


def layout_day(rng, quarters, buffer_minutes, window=(OPEN_MIN, CLOSE_MIN)):
    """Place `quarters` of sessions in `window` with buffers between sessions.

    Returns a list of (start_min, end_min). Raises ValueError if they can't fit.
    """
    if quarters <= 0:
        return []
    sizes = _split_sessions(rng, quarters)
    gap = math.ceil(buffer_minutes / QUARTER) * QUARTER
    needed = sum(sizes) * QUARTER + gap * (len(sizes) - 1)
    slack = (window[1] - window[0]) - needed
    if slack < 0:
        raise ValueError("sessions do not fit in window")
    slack_quarters = slack // QUARTER
    # Spread slack across len(sizes)+1 gaps (before, between, after).
    extras = [0] * (len(sizes) + 1)
    for _ in range(slack_quarters):
        extras[rng.randrange(len(extras))] += 1
    sessions = []
    cursor = window[0] + extras[0] * QUARTER
    for i, size in enumerate(sizes):
        start = cursor
        end = start + size * QUARTER
        sessions.append((start, end))
        cursor = end + gap + extras[i + 1] * QUARTER
    return sessions


def distribute_week(rng, total_hours, day_windows):
    """Split weekly hours (multiple of 0.25) across days, capped per day."""
    total_quarters = int(round(total_hours * 4))
    days = [d for d, w in day_windows.items() if w is not None]
    caps = {d: min(MAX_DAY_QUARTERS, (day_windows[d][1] - day_windows[d][0]) // QUARTER - 2) for d in days}
    if total_quarters > sum(caps.values()):
        raise ValueError("weekly hours exceed capacity")
    alloc = {d: 0 for d in days}
    remaining = total_quarters
    while remaining > 0:
        open_days = [d for d in days if alloc[d] < caps[d]]
        d = rng.choice(open_days)
        step = min(remaining, caps[d] - alloc[d], rng.choice([2, 4, 6, 8]))
        alloc[d] += step
        remaining -= step
    return alloc


def filler_week(rng, monday, total_hours, buffer_minutes, blocked=None, skip_days=()):
    """Seeded sessions for one resource-week: list of (date, start_min, end_min)."""
    blocked = blocked or {}
    windows = {}
    for offset, day in enumerate(week_days(monday)):
        if offset in skip_days:
            windows[offset] = None
            continue
        window = (OPEN_MIN, CLOSE_MIN)
        if day in blocked:
            b_start, b_end = blocked[day]
            # Use the larger free side of a maintenance block.
            window = (b_end, CLOSE_MIN) if CLOSE_MIN - b_end >= b_start - OPEN_MIN else (OPEN_MIN, b_start)
        windows[offset] = window
    alloc = distribute_week(rng, total_hours, windows)
    out = []
    for offset in sorted(alloc):
        day = week_days(monday)[offset]
        for start, end in layout_day(rng, alloc[offset], buffer_minutes, windows[offset]):
            out.append((day, start, end))
    return out


def history_targets(rng):
    """Booked hours per instrument for each of the 6 history weeks."""
    targets = {k: list(v) for k, v in HISTORY_BOOKED_HOURS.items()}
    for inst, base in HISTORY_BASE_HOURS.items():
        targets[inst] = [base + rng.choice([-2, -1, 0, 1, 2]) for _ in HISTORY_WEEK_MONDAYS]
    return targets


def unmet_hours(rng, inst):
    if inst in HISTORY_UNMET_HOURS:
        return list(HISTORY_UNMET_HOURS[inst])
    return [rng.choice([0, 0, 1, 2]) for _ in HISTORY_WEEK_MONDAYS]


def demo_fixed(inst):
    for offset, start, end, user, flexible, booking_id in DEMO_FIXED_INSTRUMENT_SESSIONS.get(inst, []):
        yield week_days(DEMO_WEEK_MONDAY)[offset], _mins(start), _mins(end), user, flexible, booking_id
