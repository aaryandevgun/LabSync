"""Read-side helpers for the UI and CLI (approval queue, calendar, plan detail, inbox) and the
developer-only demo reset. These are not agent tools; the agents use `tools.py`.

Same conventions as tools.py: repository first, JSON in, JSON out, permission-scoped reads.
"""
import hmac
import os

from labsync_core.values import to_dt

from . import approvals as approval_store
from . import audit
from .tools import ADMIN_ROLES, _actor, _calendar, _deny, _err, _ok

RESET_TOKEN_ENV = "LABSYNC_RESET_TOKEN"


def list_approval_queue(repo, actor_id):
    """The actor's approval inbox (docs/01 /approvals).

    Returns:
        {"status": "ok", "waiting_on_me": [...], "requested_by_me": [...], "history": [...]}
        waiting_on_me holds only requests that were actually sent (status pending) and are the
        actor's turn; `not_sent` owner-move slots stay invisible to the owner until requested.
    """
    actor = _actor(repo, actor_id)
    if actor is None:
        return _err("UNKNOWN_ACTOR", "Unknown actor.")
    rows = repo.list_records("Approval")
    waiting, mine, history = [], [], []
    for a in rows:
        if a["approver_id"] == actor_id and a["status"] == "pending":
            if _is_turn(repo, a):
                waiting.append(_card(repo, a))
        elif a["approver_id"] == actor_id and a["status"] == "decided":
            history.append(_card(repo, a))
        if a["requested_by"] == actor_id and a["approver_id"] != actor_id and a["status"] != "decided":
            mine.append(_card(repo, a))
    key = lambda c: (c["created_at"], c["approval_id"])
    return _ok(repo, waiting_on_me=sorted(waiting, key=key), requested_by_me=sorted(mine, key=key),
               history=sorted(history, key=key), source_record_ids=[a["approval_id"] for a in rows
                                                                    if a["approver_id"] == actor_id])


def _is_turn(repo, record):
    """True if every earlier slot on the same entity is decided (approvals are ordered)."""
    earlier = [a for a in approval_store.for_entity(repo, record["entity_kind"], record["entity_id"])
               if a["slot_order"] < record["slot_order"]]
    return all(a["status"] == "decided" and a["decision"] == "approve" for a in earlier)


def _card(repo, a):
    entity = repo.get_record(a["entity_kind"], a["entity_id"]) or {}
    return {"approval_id": a["approval_id"], "entity_kind": a["entity_kind"], "entity_id": a["entity_id"],
            "entity_state": entity.get("state"), "slot_kind": a["slot_kind"], "approver_id": a["approver_id"],
            "status": a["status"], "decision": a["decision"], "impact": a.get("impact"),
            "message": a.get("message"), "created_at": a["created_at"], "decided_at": a["decided_at"]}


def get_calendar(repo, actor_id, resource_ids, day):
    """Bookings, room reservations and held (not confirmed) slots for some resources on one day.

    Other labs' rows show only time, resource and status ("busy"); no person or lab names.
    Args:
        resource_ids (list[str]), day (str): "2026-11-03".
    """
    actor = _actor(repo, actor_id)
    if actor is None:
        return _err("UNKNOWN_ACTOR", "Unknown actor.")
    bookings, rooms = _calendar(repo)
    rows = []
    for b in bookings + rooms:
        if b["resource_id"] not in resource_ids or b.get("status") in ("cancelled",):
            continue
        if to_dt(b["start_local"]).date().isoformat() != day:
            continue
        own = b.get("lab_id") == actor["lab_id"] or actor.get("role") in ADMIN_ROLES
        rows.append({"booking_id": b.get("booking_id") or b.get("reservation_id"), "resource_id": b["resource_id"],
                     "start": b["start_local"], "end": b["end_local"],
                     "status": "held" if b.get("status") == "held" else b.get("status") or "confirmed",
                     "lab_id": b.get("lab_id") if own else None, "user_id": b.get("user_id") if own else None,
                     "flexible": b.get("flexible") if own else None, "version": b.get("version")})
    rows.sort(key=lambda r: (r["resource_id"], r["start"]))
    return _ok(repo, day=day, rows=rows, source_record_ids=[r["booking_id"] for r in rows])


def get_plan(repo, actor_id, plan_id):
    """A plan with its proposals and approval progress. Requester's lab or admins only."""
    plan = repo.get_record("ExperimentPlan", plan_id)
    actor = _actor(repo, actor_id)
    if plan is None:
        return _err("NOT_FOUND", "Unknown plan.")
    if actor is None or (actor["lab_id"] != plan["lab_id"] and actor.get("role") not in ADMIN_ROLES):
        return _deny(repo, actor_id, "get_plan", "ExperimentPlan", plan_id)
    proposals = [p for p in repo.list_records("ReservationProposal") if p["plan_id"] == plan_id]
    for p in proposals:
        p["approvals"] = [_card(repo, a) for a in approval_store.for_entity(repo, "ReservationProposal", p["proposal_id"])]
    orders = [o for o in repo.list_records("OrderProposal") if o.get("plan_id") == plan_id]
    return _ok(repo, plan=plan, proposals=proposals, orders=orders,
               source_record_ids=[plan_id] + [p["proposal_id"] for p in proposals] + [o["order_id"] for o in orders])


def list_notifications(repo, actor_id):
    """In-app notifications for the actor, newest first (never email)."""
    notes = [n for n in repo.list_records("Notification") if n["recipient_id"] == actor_id]
    notes.sort(key=lambda n: n["created_at"], reverse=True)
    return _ok(repo, notifications=notes, source_record_ids=[n["notification_id"] for n in notes])


def reset_demo(repo, actor_id, token):
    """Developer-only: restore the exact `imaging_tuesday_v1` seed (docs/03). Requires the token in
    the LABSYNC_RESET_TOKEN environment variable; refuses if it is unset. Never touches real data:
    it only calls repo.reset_to_seed(), which the C3 implementation must limit to the demo sandbox."""
    expected = os.environ.get(RESET_TOKEN_ENV)
    if not expected or not isinstance(token, str) or not hmac.compare_digest(expected, token):
        return _deny(repo, actor_id, "reset_demo", "Demo", "imaging_tuesday_v1", code="RESET_NOT_ALLOWED")
    repo.reset_to_seed()
    audit.record(repo, actor_id, "reset_demo", "Demo", "imaging_tuesday_v1", after={"seed": "imaging_tuesday_v1"})
    return _ok(repo, reset="imaging_tuesday_v1")
