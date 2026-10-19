"""find_slots: deterministic option search for one experiment request (docs/09 A).

Steps: enumerate 15-min starts in the search window on every capability-matching
instrument the requester is qualified for; drop any start that breaks a hard
constraint; where the only blockers are one flexible booking, propose a
*contingent* owner move instead of pretending the slot is free; attach the
latest feasible prep room before imaging; check supply readiness; score with
Policy weights and return at most `scheduling.max_options` non-overlapping
options plus explanations for everything excluded.
"""
from datetime import datetime, timedelta

from . import policy
from .conflicts import DEFAULT_TZ, detect_conflicts
from .eligibility import capability_match, check_qualifications
from .swap_scoring import score_swap_options
from .values import as_list, hours_between, iso, overlaps, to_dt

HARD_TYPES = {"outside_hours", "maintenance", "unknown_resource"}


def _day_bounds(day, resource, tz):
    open_h, open_m = (int(x) for x in (resource.get("open_local") or "09:00").split(":"))
    close_h, close_m = (int(x) for x in (resource.get("close_local") or "17:00").split(":"))
    start = datetime(day.year, day.month, day.day, open_h, open_m, tzinfo=tz)
    end = datetime(day.year, day.month, day.day, close_h, close_m, tzinfo=tz)
    return start, end


def _ceil_to_step(dt, step_minutes, anchor):
    offset = (dt - anchor).total_seconds() / 60
    steps = -(-offset // step_minutes)
    return anchor + timedelta(minutes=steps * step_minutes)


def _starts(window_start, window_end, duration, step, resource, tz):
    """15-min aligned starts where [start, start+duration) fits the window and staffed hours."""
    day = window_start.astimezone(tz).date()
    last_day = window_end.astimezone(tz).date()
    while day <= last_day:
        open_dt, close_dt = _day_bounds(day, resource, tz)
        if open_dt.weekday() < 5:
            start = _ceil_to_step(max(open_dt, window_start), step, open_dt)
            while start + duration <= min(close_dt, window_end):
                yield start
                start += timedelta(minutes=step)
        day += timedelta(days=1)


def _find_move(conflict, requested, resource, bookings, maintenance, move_step, tz):
    """Earliest same-day slot (same duration) for a flexible booking displaced by `requested`."""
    original_start, original_end = to_dt(conflict["start"]), to_dt(conflict["end"])
    duration = original_end - original_start
    open_dt, close_dt = _day_bounds(original_start.astimezone(tz).date(), resource, tz)
    start = open_dt
    while start + duration <= close_dt:
        if start != original_start:
            candidate = {"resource_id": resource_id_of(resource), "start": iso(start), "end": iso(start + duration),
                         "ref": "move"}
            issues = detect_conflicts([candidate, requested], bookings, {resource_id_of(resource): resource},
                                      maintenance, ignore_booking_ids=[conflict["booking_id"]], tz=tz)
            if not [c for c in issues if c["ref"] == "move"]:
                return candidate
        start += timedelta(minutes=move_step)
    return None


def resource_id_of(resource):
    return resource.get("instrument_id") or resource.get("room_id") or resource.get("resource_id")


def _find_prep(prep, image_start, rooms, room_bookings, maintenance, earliest, step, tz):
    """Latest prep-room session ending at least `transition` before imaging (same day)."""
    duration = timedelta(minutes=int(prep["duration_minutes"]))
    transition = timedelta(minutes=int(prep.get("transition_minutes", 15)))
    best = None
    for room in sorted(rooms, key=resource_id_of):
        if capability_match(room, prep.get("room_capabilities", [])):
            continue
        open_dt, _ = _day_bounds(image_start.astimezone(tz).date(), room, tz)
        lower = max(open_dt, earliest) if earliest else open_dt
        start = _ceil_to_step(image_start - transition - duration, step, open_dt)
        if start + duration > image_start - transition:
            start -= timedelta(minutes=step)
        while start >= lower:
            candidate = {"resource_id": resource_id_of(room), "start": iso(start), "end": iso(start + duration)}
            if not detect_conflicts([candidate], room_bookings, {resource_id_of(room): room}, maintenance, tz=tz):
                if best is None or to_dt(candidate["end"]) > to_dt(best["end"]):
                    best = candidate
                break
            start -= timedelta(minutes=step)
    return best


def find_slots(request, instruments, persons, bookings, rooms=(), room_bookings=(), maintenance=(),
               policies=None, tz=DEFAULT_TZ):
    """Find up to N ranked, hard-constraint-valid options for an experiment request.

    Args:
        request: {
            "requester_id", "lab_id",
            "required_capabilities": [...], "duration_minutes": int,
            "search_start", "search_end": ISO window to search (inclusive of whole sessions),
            "preferred_start", "preferred_end": ISO preferred window (optional),
            "deadline": ISO latest end (optional),
            "prep": {"room_capabilities": [...], "duration_minutes": int,
                     "transition_minutes": int} | None,
            "supplies_ready_at": ISO | None   (from supplies.readiness)
        }
        instruments, rooms: resource rows. persons: person rows. bookings, room_bookings:
            current calendar rows (include held/tentative rows that should block).
        maintenance: maintenance rows. policies: Policy rows or merged map.
    Returns: {
        "status": "ok" | "no_viable_slot",
        "options": [{"option_id", "kind": "direct"|"owner_move", "resource_id", "start", "end",
                     "prep": {...}|None, "contingent_moves": [...], "approvals_required": [...],
                     "hard_constraint_status": "feasible"|"conditional", "score", "score_breakdown"}],
        "blocked_alternatives": [{"resource_id", "code", "missing"}],
        "exclusion_counts": {reason_code: count},
        "assumptions": [...]
    }
    """
    pol = policy.policy_map(policies) if not isinstance(policies, dict) else policies
    step = int(policy.get(pol, "scheduling.slot_step_minutes"))
    move_step = int(policy.get(pol, "scheduling.move_step_minutes"))
    max_options = int(policy.get(pol, "scheduling.max_options"))
    persons_by_id = {p["person_id"]: p for p in persons}
    requester = persons_by_id[request["requester_id"]]
    duration = timedelta(minutes=int(request["duration_minutes"]))
    window_start, window_end = to_dt(request["search_start"]), to_dt(request["search_end"])
    if request.get("deadline"):
        window_end = min(window_end, to_dt(request["deadline"]))
    pref_start = to_dt(request["preferred_start"]) if request.get("preferred_start") else None
    pref_end = to_dt(request["preferred_end"]) if request.get("preferred_end") else None
    supplies_ready = to_dt(request["supplies_ready_at"]) if request.get("supplies_ready_at") else None
    prep = request.get("prep")
    if prep and "transition_minutes" not in prep:
        prep = dict(prep, transition_minutes=int(policy.get(pol, "scheduling.prep_transition_minutes")))

    exclusions = {}
    blocked = []
    candidates = []

    def exclude(code):
        exclusions[code] = exclusions.get(code, 0) + 1

    for inst in sorted(instruments, key=resource_id_of):
        inst_id = resource_id_of(inst)
        if capability_match(inst, request.get("required_capabilities", [])):
            exclude("CAPABILITY_MISMATCH")
            continue
        qual = check_qualifications(requester, inst)
        if not qual["eligible"]:
            blocked.append({"resource_id": inst_id, "code": "NOT_QUALIFIED", "missing": qual["missing"],
                            "detail": "Requires %s; eligible only after qualification or with a qualified operator"
                                      % ", ".join(qual["missing"])})
            continue
        resources = {inst_id: inst}
        for start in _starts(window_start, window_end, duration, step, inst, tz):
            end = start + duration
            requested = {"resource_id": inst_id, "start": iso(start), "end": iso(end), "ref": "request"}
            issues = detect_conflicts([requested], bookings, resources, maintenance, tz=tz)
            if any(c["type"] in HARD_TYPES for c in issues):
                exclude("MAINTENANCE_OR_HOURS")
                continue
            moves = []
            if issues:
                blockers = {c["booking_id"]: c for c in issues}
                if len(blockers) > 1 or not all(c["flexible"] for c in blockers.values()):
                    exclude("BOOKED")
                    continue
                conflict = next(iter(blockers.values()))
                move = _find_move(conflict, requested, inst, bookings, maintenance, move_step, tz)
                if move is None:
                    exclude("NO_MOVE_SLOT_FOR_OWNER")
                    continue
                moves.append({"booking_id": conflict["booking_id"], "owner_id": conflict["owner_id"],
                              "lab_id": conflict["lab_id"], "resource_id": inst_id,
                              "from": {"start": conflict["start"], "end": conflict["end"]},
                              "to": {"start": move["start"], "end": move["end"]}})
            if supplies_ready and supplies_ready > start:
                exclude("ORDER_TOO_LATE")
                continue
            prep_slot = None
            if prep:
                prep_slot = _find_prep(prep, start, rooms, room_bookings, maintenance, supplies_ready, step, tz)
                if prep_slot is None:
                    exclude("NO_PREP_ROOM")
                    continue
            meets = bool(pref_start and pref_end and start >= pref_start and end <= pref_end)
            hours_late = max(0.0, hours_between(pref_end, end)) if pref_end else 0.0
            approvals = [m["owner_id"] for m in moves] + [request["requester_id"]]
            candidates.append({
                "kind": "owner_move" if moves else "direct", "resource_id": inst_id,
                "start": iso(start), "end": iso(end), "prep": prep_slot, "contingent_moves": moves,
                "approvals_required": approvals,
                "hard_constraint_status": "conditional" if moves else "feasible",
                "features": {"meets_preferred_window": meets, "hours_late": round(hours_late, 4),
                             "room_switch_count": 0, "requires_owner_move": bool(moves),
                             "extra_internal_cost_units": 0},
            })

    ranked = score_swap_options(candidates, pol)
    chosen = []
    for option in ranked:
        # Near-duplicates (same resource and kind, overlapping times) collapse to the best one.
        clash = any(o["resource_id"] == option["resource_id"] and o["kind"] == option["kind"]
                    and overlaps(o["start"], o["end"], option["start"], option["end"]) for o in chosen)
        if not clash:
            chosen.append(option)
        if len(chosen) == max_options:
            break
    for i, option in enumerate(chosen, 1):
        option["option_id"] = "opt_%d_%s_%s" % (i, option["resource_id"], to_dt(option["start"]).strftime("%Y%m%d%H%M"))
    assumptions = ["%d-min start increments" % step, "instrument buffers per resource policy",
                   "prep room must end %d min before imaging" % (prep["transition_minutes"] if prep else 0)]
    return {
        "status": "ok" if chosen else "no_viable_slot",
        "options": chosen,
        "blocked_alternatives": blocked,
        "exclusion_counts": exclusions,
        "assumptions": assumptions,
    }
