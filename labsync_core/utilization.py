"""find_utilization_gaps: overload rebalancing and underuse detection (docs/02 M2.2-M2.3, docs/09 D-E).

Utilization = confirmed session hours / available staffed hours, with
maintenance hours removed from the denominator. Overload transfers are concrete
booking moves (not abstract volume) that respect qualifications and buffers on
the target and conserve total hours. Underuse is only flagged when the low use
persists across history, never from a single week.
"""
from datetime import datetime, timedelta

from . import policy
from .conflicts import DEFAULT_TZ, INACTIVE_STATUSES, detect_conflicts
from .eligibility import check_qualifications, equivalent
from .values import as_bool, as_num, hours_between, iso, to_date, to_dt


def _week_bounds(week_start, tz):
    monday = to_date(week_start)
    start = datetime(monday.year, monday.month, monday.day, tzinfo=tz)
    return start, start + timedelta(days=5)


def _rid(resource):
    return resource.get("instrument_id") or resource.get("resource_id")


def week_bookings(bookings, resource_id, week_start, tz=DEFAULT_TZ):
    start, end = _week_bounds(week_start, tz)
    return [b for b in bookings if b["resource_id"] == resource_id and b.get("status") not in INACTIVE_STATUSES
            and start <= to_dt(b["start_local"]) < end]


def weekly_utilization(bookings, resource, week_start, maintenance=(), tz=DEFAULT_TZ):
    """Booked vs available hours for one resource-week.

    Returns {"resource_id", "booked_hours", "available_hours", "maintenance_hours", "utilization"}.
    """
    rid = _rid(resource)
    booked = sum(hours_between(b["start_local"], b["end_local"]) for b in week_bookings(bookings, rid, week_start, tz))
    w_start, w_end = _week_bounds(week_start, tz)
    down = 0.0
    for mw in maintenance:
        if mw["resource_id"] == rid:
            s, e = max(to_dt(mw["start_local"]), w_start), min(to_dt(mw["end_local"]), w_end)
            down += max(0.0, (e - s).total_seconds() / 3600)
    available = float(as_num(resource.get("staffed_hours_per_week"), 40)) - down
    return {"resource_id": rid, "booked_hours": booked, "available_hours": available, "maintenance_hours": down,
            "utilization": round(booked / available, 4) if available else None}


def plan_transfer(source, target, bookings, persons, week_start, maintenance=(), tz=DEFAULT_TZ):
    """Greedy earliest-first move of flexible source bookings onto an equivalent target.

    A booking moves only if it is flexible, its owner is qualified on the target, it fits
    the target calendar (buffers, maintenance, hours) alongside earlier planned moves,
    and moving it doesn't push the target above the source. Same times, other instrument.
    """
    persons_by_id = {p["person_id"]: p for p in persons}
    src_id, tgt_id = _rid(source), _rid(target)
    src_hours = weekly_utilization(bookings, source, week_start, maintenance, tz)["booked_hours"]
    tgt_hours = weekly_utilization(bookings, target, week_start, maintenance, tz)["booked_hours"]
    before = (src_hours, tgt_hours)
    target_rows = [b for b in bookings if b["resource_id"] == tgt_id]
    moves, excluded = [], []
    for b in sorted(week_bookings(bookings, src_id, week_start, tz), key=lambda r: (to_dt(r["start_local"]), r["booking_id"])):
        if not as_bool(b.get("flexible")):
            continue
        hours = hours_between(b["start_local"], b["end_local"])
        owner = persons_by_id.get(b["user_id"], {})
        qual = check_qualifications(owner, target)
        if not qual["eligible"]:
            excluded.append({"booking_id": b["booking_id"], "reason": "NOT_QUALIFIED", "missing": qual["missing"]})
            continue
        candidate = {"resource_id": tgt_id, "start": b["start_local"], "end": b["end_local"]}
        planned = [{"booking_id": m["booking_id"], "resource_id": tgt_id, "start_local": m["start"],
                    "end_local": m["end"], "status": "planned"} for m in moves]
        if detect_conflicts([candidate], target_rows + planned, {tgt_id: target}, maintenance, tz=tz):
            excluded.append({"booking_id": b["booking_id"], "reason": "TARGET_CONFLICT"})
            continue
        if src_hours - hours < tgt_hours + hours:
            excluded.append({"booking_id": b["booking_id"], "reason": "WOULD_INVERT_IMBALANCE"})
            continue
        src_hours -= hours
        tgt_hours += hours
        moves.append({"booking_id": b["booking_id"], "owner_id": b["user_id"], "lab_id": b["lab_id"],
                      "hours": hours, "start": iso(to_dt(b["start_local"])), "end": iso(to_dt(b["end_local"])),
                      "from_resource": src_id, "to_resource": tgt_id})
    avail_s = weekly_utilization(bookings, source, week_start, maintenance, tz)["available_hours"]
    avail_t = weekly_utilization(bookings, target, week_start, maintenance, tz)["available_hours"]
    movable = sum(m["hours"] for m in moves)
    return {
        "source": src_id, "target": tgt_id, "movable_hours": movable,
        "before": {"source_hours": before[0], "target_hours": before[1],
                   "source_utilization": round(before[0] / avail_s, 4), "target_utilization": round(before[1] / avail_t, 4)},
        "after": {"source_hours": src_hours, "target_hours": tgt_hours,
                  "source_utilization": round(src_hours / avail_s, 4), "target_utilization": round(tgt_hours / avail_t, 4)},
        "total_hours_before": before[0] + before[1], "total_hours_after": src_hours + tgt_hours,
        "moves": moves, "excluded": excluded,
        "required_approvals": sorted({m["owner_id"] for m in moves}),
        "reason": None if moves else "No flexible booking can move safely (qualification, buffer or calendar)",
        "value_unit": "hours of congestion relieved (not money)",
    }


def _history(demand_history, rid):
    rows = sorted((r for r in demand_history if r["resource_id"] == rid), key=lambda r: r["week_start"])
    return [{"week_start": r["week_start"], "booked_hours": float(as_num(r["booked_hours"])),
             "requested_hours": float(as_num(r["requested_hours"])),
             "utilization": round(float(as_num(r["booked_hours"])) /
                                  (float(as_num(r["staffed_hours"])) - float(as_num(r.get("maintenance_hours"), 0))), 4)}
            for r in rows]


def find_utilization_gaps(bookings, instruments, persons, week_start, maintenance=(), demand_history=(),
                          policies=None, tz=DEFAULT_TZ):
    """Overloaded and underused instruments for one week, with concrete transfer plans.

    Args:
        bookings: instrument booking rows for (at least) the week. instruments, persons: rows.
        week_start: Monday (ISO date). maintenance: rows. demand_history: weekly demand rows
            (week_start, resource_id, booked_hours, requested_hours, staffed_hours).
        policies: `utilization.overload_threshold`, `underuse.utilization_threshold`,
            `underuse.min_low_weeks_of_6`.
    Returns: {"utilization": [...], "overloads": [transfer plans], "underused": [...]}
    """
    pol = policy.policy_map(policies) if not isinstance(policies, dict) else policies
    overload_at = float(policy.get(pol, "utilization.overload_threshold"))
    underuse_at = float(policy.get(pol, "underuse.utilization_threshold"))
    min_low = int(policy.get(pol, "underuse.min_low_weeks_of_6"))
    instruments = sorted(instruments, key=_rid)
    util = {_rid(i): weekly_utilization(bookings, i, week_start, maintenance, tz) for i in instruments}

    overloads = []
    for src in instruments:
        u = util[_rid(src)]["utilization"]
        if u is None or u < overload_at:
            continue
        targets = [t for t in instruments if t is not src and equivalent(src, t)
                   and util[_rid(t)]["utilization"] is not None and util[_rid(t)]["utilization"] < u]
        for tgt in sorted(targets, key=lambda t: (util[_rid(t)]["utilization"], _rid(t))):
            overloads.append(plan_transfer(src, tgt, bookings, persons, week_start, maintenance, tz))

    underused = []
    for inst in instruments:
        rid = _rid(inst)
        u = util[rid]["utilization"]
        if u is None or u >= underuse_at:
            continue
        hist = _history(demand_history, rid)
        low_weeks = sum(1 for h in hist if h["utilization"] < underuse_at)
        siblings = [t for t in instruments if t is not inst and equivalent(inst, t)]
        overflow = []
        for sib in siblings:
            sib_hist = _history(demand_history, _rid(sib))
            unmet = [h["requested_hours"] - h["booked_hours"] for h in sib_hist]
            if unmet and sum(unmet) > 0:
                overflow.append({"resource_id": _rid(sib), "avg_unmet_hours_per_week": round(sum(unmet) / len(unmet), 2),
                                 "utilization": util[_rid(sib)]["utilization"]})
        persistent = len(hist) > 0 and low_weeks >= min_low
        underused.append({
            "resource_id": rid, "utilization": u, "booked_hours": util[rid]["booked_hours"],
            "available_hours": util[rid]["available_hours"], "history": hist, "low_weeks": low_weeks,
            "weeks_observed": len(hist), "persistent": persistent, "overflow_sources": overflow,
            "status": "advisory" if persistent else "insufficient_trend",
            "suggested_next_steps": ["publish available capacity to qualified users",
                                     "match overflow demand from equivalent instruments",
                                     "compare borrow / extend staffed hours / buy before any purchase"],
            "caveat": "Low use does not mean the instrument is obsolete; no sale or purchase is implied.",
        })
    return {"week_start": to_date(week_start).isoformat(), "utilization": [util[_rid(i)] for i in instruments],
            "overloads": overloads, "underused": underused}
