"""Conditional, idempotent commit planning (docs/09 A "Commit algorithm").

`plan_commit` re-checks everything against the *current* calendar and returns
the exact writes plus their compensation; it changes nothing itself. The
repository applies the writes (atomically when the platform allows, otherwise
applying `compensation` on failure so no unapproved partial state survives).
"""
import hashlib
import json

from .conflicts import detect_conflicts
from .proposals import approval_status, reservation_slots
from .values import as_num, iso, to_dt


def _digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _error(code, detail, **extra):
    return dict({"status": "error", "code": code, "detail": detail, "writes": [], "compensation": []}, **extra)


def plan_commit(proposal, bookings, resources, approvals, actor_id, idempotency_key, receipts=None,
                maintenance=(), now=None):
    """Plan the writes that commit an authorized reservation proposal.

    Args:
        proposal: {"proposal_id", "requester_id", "lab_id", "creates": [booking dicts with booking_id,
                   resource_id, start, end, user_id, lab_id], "contingent_moves": [{booking_id, resource_id,
                   owner_id, to: {start, end}}], "expected_versions": {booking_id: version}}
        bookings: current instrument + room rows (booking_id/reservation_id, version, start/end).
        resources: dict resource_id -> resource row (for buffers/hours).
        approvals: decisions [{slot_id, actor_id, decision}].
        actor_id: who is committing (must be the requester).
        idempotency_key: e.g. "<requestId>:commit:<proposalId>".
        receipts: dict idempotency_key -> earlier receipt.
    Returns on success {"status": "ok", "receipt", "writes", "compensation", "replayed": bool}
        or {"status": "error", "code": UNAUTHORIZED|MISSING_APPROVAL|OWNER_REJECTED|SLOT_STALE, ...}.
    """
    receipts = receipts or {}
    if idempotency_key in receipts:
        return {"status": "ok", "receipt": receipts[idempotency_key], "writes": [], "compensation": [],
                "replayed": True}
    if actor_id != proposal["requester_id"]:
        return _error("UNAUTHORIZED", "only the requester can commit their proposal")
    status = approval_status(reservation_slots(proposal), approvals)
    if status["rejected"]:
        return _error("OWNER_REJECTED", "a required approver rejected the proposal", rejected_by=status["rejected_by"])
    if not status["complete"]:
        return _error("MISSING_APPROVAL", "approvals still pending", pending=status["pending"])

    def bid(row):
        return row.get("booking_id") or row.get("reservation_id")

    current = {bid(b): b for b in bookings}
    stale = []
    for booking_id, expected in sorted(proposal.get("expected_versions", {}).items()):
        row = current.get(booking_id)
        if row is None or as_num(row.get("version"), 1) != as_num(expected):
            stale.append(booking_id)
    if stale:
        return _error("SLOT_STALE", "bookings changed since the proposal was made", stale_ids=stale)

    moves = proposal.get("contingent_moves", [])
    proposed = [{"resource_id": c["resource_id"], "start": c["start"], "end": c["end"], "ref": c["booking_id"]}
                for c in proposal.get("creates", [])]
    proposed += [{"resource_id": m["resource_id"], "start": m["to"]["start"], "end": m["to"]["end"],
                  "ref": m["booking_id"]} for m in moves]
    ignore = [m["booking_id"] for m in moves] + [c["booking_id"] for c in proposal.get("creates", [])]
    # Rows that merely hold this proposal's own slots must not block it.
    ignore += [bid(b) for b in bookings if b.get("proposal_id") == proposal["proposal_id"]]
    conflicts = detect_conflicts(proposed, bookings, resources, maintenance, ignore_booking_ids=ignore)
    if conflicts:
        return _error("SLOT_STALE", "the calendar changed and the plan no longer fits", conflicts=conflicts)

    writes, compensation = [], []
    for m in moves:
        row = current[m["booking_id"]]
        before = {"start_local": iso(to_dt(row["start_local"])), "end_local": iso(to_dt(row["end_local"])),
                  "version": as_num(row.get("version"), 1)}
        after = {"start_local": m["to"]["start"], "end_local": m["to"]["end"], "version": before["version"] + 1}
        writes.append({"op": "update", "entity": "Booking", "id": m["booking_id"], "expected_version": before["version"],
                       "before": before, "after": after})
        compensation.append({"op": "update", "entity": "Booking", "id": m["booking_id"],
                             "expected_version": after["version"], "before": after, "after": before})
    for c in proposal.get("creates", []):
        after = {"booking_id": c["booking_id"], "resource_id": c["resource_id"], "lab_id": c["lab_id"],
                 "user_id": c["user_id"], "start_local": c["start"], "end_local": c["end"],
                 "status": "confirmed", "flexible": False, "version": 1, "proposal_id": proposal["proposal_id"]}
        writes.append({"op": "create", "entity": c.get("entity", "Booking"), "id": c["booking_id"],
                       "before": None, "after": after})
        compensation.append({"op": "delete", "entity": c.get("entity", "Booking"), "id": c["booking_id"],
                             "before": after, "after": None})
    compensation.reverse()
    receipt = {
        "receipt_id": "rcpt_%s" % _digest([proposal["proposal_id"], idempotency_key]),
        "proposal_id": proposal["proposal_id"], "idempotency_key": idempotency_key,
        "committed_by": actor_id, "committed_at": iso(to_dt(now)) if now else None,
        "booking_ids": [w["id"] for w in writes], "writes_digest": _digest(writes),
    }
    return {"status": "ok", "receipt": receipt, "writes": writes, "compensation": compensation, "replayed": False}


def apply_writes(rows, writes):
    """Apply planned writes to a list of booking rows (pure: returns a new list).

    Raises ValueError on a version mismatch so callers can run compensation.
    """
    def bid(row):
        return row.get("booking_id") or row.get("reservation_id")

    out = {bid(r): dict(r) for r in rows}
    order = [bid(r) for r in rows]
    for w in writes:
        if w["op"] == "update":
            row = out.get(w["id"])
            if row is None or as_num(row.get("version"), 1) != w["expected_version"]:
                raise ValueError("version mismatch on %s" % w["id"])
            row.update(w["after"])
        elif w["op"] == "create":
            if w["id"] in out:
                raise ValueError("duplicate id %s" % w["id"])
            out[w["id"]] = dict(w["after"])
            order.append(w["id"])
        elif w["op"] == "delete":
            out.pop(w["id"], None)
            order = [i for i in order if i != w["id"]]
    return [out[i] for i in order if i in out]
