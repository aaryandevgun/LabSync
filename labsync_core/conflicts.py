"""detect_conflicts: hard-constraint check of proposed sessions against a calendar."""
from datetime import time
from zoneinfo import ZoneInfo

from .values import as_bool, iso, overlaps, to_dt, violates_buffer

DEFAULT_TZ = ZoneInfo("America/Chicago")
# Statuses that no longer occupy a resource.
INACTIVE_STATUSES = {"cancelled", "rejected", "released", "expired"}


def _hhmm(text, default):
    if not text:
        return default
    hour, minute = (int(part) for part in text.split(":"))
    return time(hour, minute)


def _resource_id(row):
    return row.get("resource_id") or row.get("room_id")


def _booking_id(row):
    return row.get("booking_id") or row.get("reservation_id")


def outside_staffed_hours(resource, start, end, tz=DEFAULT_TZ):
    """True if the session is not within one weekday's open..close window (local time)."""
    s, e = to_dt(start).astimezone(tz), to_dt(end).astimezone(tz)
    open_t = _hhmm(resource.get("open_local"), time(9, 0))
    close_t = _hhmm(resource.get("close_local"), time(17, 0))
    return (s.weekday() >= 5 or s.date() != e.date()
            or s.timetz().replace(tzinfo=None) < open_t or e.timetz().replace(tzinfo=None) > close_t)


def detect_conflicts(proposed, existing, resources, maintenance=None, ignore_booking_ids=(), tz=DEFAULT_TZ):
    """Check proposed sessions against existing bookings, buffers, maintenance and hours.

    Args:
        proposed: list of {"resource_id", "start", "end", optional "ref"}.
        existing: booking rows (instrument `booking_id` or room `reservation_id`) with
            resource/room id, start_local/end_local (or start/end), status, owner, flexible.
        resources: dict resource_id -> instrument/room row (buffer_minutes, open/close).
        maintenance: rows with resource_id, start_local, end_local.
        ignore_booking_ids: bookings to treat as absent (e.g. the one being moved).
    Returns: list of conflict dicts, one per problem, each with
        type: "outside_hours" | "maintenance" | "overlap" | "buffer" | "unknown_resource",
        ref, resource_id, and for booking conflicts booking_id, owner_id, lab_id, flexible.
    Proposed sessions are also checked against each other.
    """
    ignore = set(ignore_booking_ids)
    by_resource = {}
    for row in existing:
        if row.get("status") in INACTIVE_STATUSES or _booking_id(row) in ignore:
            continue
        by_resource.setdefault(_resource_id(row), []).append(row)
    conflicts = []
    for idx, item in enumerate(proposed):
        res_id = item["resource_id"]
        ref = item.get("ref", idx)
        resource = resources.get(res_id)
        if resource is None:
            conflicts.append({"type": "unknown_resource", "ref": ref, "resource_id": res_id})
            continue
        start, end = to_dt(item["start"]), to_dt(item["end"])
        if not start < end or outside_staffed_hours(resource, start, end, tz):
            conflicts.append({"type": "outside_hours", "ref": ref, "resource_id": res_id})
        for mw in maintenance or []:
            if mw["resource_id"] == res_id and overlaps(start, end, mw["start_local"], mw["end_local"]):
                conflicts.append({"type": "maintenance", "ref": ref, "resource_id": res_id,
                                  "maintenance_id": mw.get("maintenance_id")})
        buffer = int(resource.get("buffer_minutes") or 0)
        others = list(by_resource.get(res_id, []))
        others += [dict(p, booking_id="proposed:%s" % p.get("ref", j), start_local=p["start"], end_local=p["end"])
                   for j, p in enumerate(proposed) if j != idx and p["resource_id"] == res_id]
        for row in others:
            o_start = row.get("start_local") or row.get("start")
            o_end = row.get("end_local") or row.get("end")
            if overlaps(start, end, o_start, o_end):
                kind = "overlap"
            elif violates_buffer(start, end, o_start, o_end, buffer):
                kind = "buffer"
            else:
                continue
            conflicts.append({
                "type": kind, "ref": ref, "resource_id": res_id, "booking_id": _booking_id(row),
                "owner_id": row.get("user_id"), "lab_id": row.get("lab_id"),
                "flexible": as_bool(row.get("flexible", False)), "status": row.get("status"),
                "start": iso(to_dt(o_start)), "end": iso(to_dt(o_end)),
            })
    return conflicts
