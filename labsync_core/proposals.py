"""State machines and approval rules (docs/10 "Core state machines", docs/00 roles).

Agents propose, people approve. These functions decide whether a transition or
an approval is allowed; they never perform one. Authorization is checked here
(server-side logic), not in the UI.
"""

STATE_MACHINES = {
    "ExperimentPlan": {
        "draft": {"options_ready", "needs_revision", "cancelled"},
        "options_ready": {"approval_pending", "needs_revision", "cancelled"},
        "approval_pending": {"ready_to_commit", "needs_revision", "cancelled"},
        "ready_to_commit": {"committed", "needs_revision", "failed", "cancelled"},
        "needs_revision": {"options_ready", "cancelled"},
        "failed": {"needs_revision", "cancelled"},
        "committed": set(), "cancelled": set(),
    },
    # "submitted" is the held state: the slot blocks other proposals, nothing is confirmed.
    "ReservationProposal": {
        "draft": {"submitted"},
        "submitted": {"owner_approval_pending", "requester_approval_pending", "stale", "cancelled"},
        "owner_approval_pending": {"requester_approval_pending", "rejected", "stale", "cancelled"},
        "requester_approval_pending": {"authorized", "rejected", "stale", "cancelled"},
        "authorized": {"committed", "stale", "failed"},
        "committed": set(), "rejected": set(), "stale": set(), "failed": set(), "cancelled": set(),
    },
    # No submitted_to_vendor / received: the demo never purchases.
    "OrderProposal": {
        "draft": {"awaiting_lab_approval", "cancelled"},
        "awaiting_lab_approval": {"awaiting_fund_approval", "rejected", "cancelled"},
        "awaiting_fund_approval": {"approved_request", "rejected", "cancelled"},
        "approved_request": set(), "rejected": set(), "cancelled": set(),
    },
    # "executed" only with a real backing receipt, so it is not reachable here.
    "DepartmentInsight": {
        "detected": {"reviewed", "dismissed"},
        "reviewed": {"action_proposed", "dismissed"},
        "action_proposed": {"pending_approvals", "dismissed"},
        "pending_approvals": {"approved", "dismissed"},
        "approved": set(), "dismissed": set(),
    },
}

HELD_STATES = {"submitted", "owner_approval_pending", "requester_approval_pending", "authorized"}


def can_transition(kind, current, target):
    """Returns {"ok": bool, "code": None | "INVALID_TRANSITION" | "UNKNOWN_KIND", "allowed": [...]}."""
    machine = STATE_MACHINES.get(kind)
    if machine is None or current not in machine:
        return {"ok": False, "code": "UNKNOWN_KIND", "allowed": []}
    allowed = sorted(machine[current])
    ok = target in machine[current]
    return {"ok": ok, "code": None if ok else "INVALID_TRANSITION", "allowed": allowed}


# ---------- approval slots ----------

def reservation_slots(proposal):
    """One slot per displaced owner, then the requester's final confirmation (always required)."""
    slots = [{"slot_id": "owner:%s" % m["booking_id"], "kind": "owner_move", "approver_id": m["owner_id"],
              "booking_id": m["booking_id"], "lab_id": m.get("lab_id")}
             for m in proposal.get("contingent_moves", [])]
    slots.append({"slot_id": "requester", "kind": "requester_confirm", "approver_id": proposal["requester_id"],
                  "lab_id": proposal.get("lab_id")})
    return slots


def order_slots(order, labs):
    """Lab approval, then fund approval. In the demo the lab manager records the simulated fund sign-off."""
    manager = {l["lab_id"]: l["manager_id"] for l in labs}[order["lab_id"]]
    return [{"slot_id": "lab", "kind": "lab_approval", "approver_id": manager, "lab_id": order["lab_id"]},
            {"slot_id": "fund", "kind": "fund_approval", "approver_id": manager, "lab_id": order["lab_id"]}]


def insight_slots(insight):
    return [{"slot_id": "approver:%s" % pid, "kind": "admin" if pid == "dept_admin" else "lab_owner",
             "approver_id": pid} for pid in insight["required_approvals"]]


def approval_status(slots, approvals):
    """Summarize decisions against slots.

    approvals: [{"slot_id", "actor_id", "decision": "approve"|"reject"}] (latest per slot wins).
    Returns {"complete", "rejected", "pending": [slot_ids], "approved": [...], "rejected_by": [...]}.
    """
    latest = {}
    for a in approvals:
        latest[a["slot_id"]] = a
    approved = [s["slot_id"] for s in slots if latest.get(s["slot_id"], {}).get("decision") == "approve"]
    rejected = [s["slot_id"] for s in slots if latest.get(s["slot_id"], {}).get("decision") == "reject"]
    pending = [s["slot_id"] for s in slots if s["slot_id"] not in approved and s["slot_id"] not in rejected]
    return {"complete": not pending and not rejected, "rejected": bool(rejected), "pending": pending,
            "approved": approved, "rejected_by": [latest[s]["actor_id"] for s in rejected]}


def authorize_decision(slots, approvals, slot_id, actor, ordered=True):
    """May `actor` decide `slot_id` now?

    Rules: the named approver decides their own slot; a core scheduler may also decide an
    owner_move slot (facility override per docs/00); nobody decides for the requester. When
    `ordered`, the requester's confirmation opens only after every owner slot is approved.
    Returns {"authorized": bool, "code": None | "UNAUTHORIZED_APPROVAL" | "APPROVAL_OUT_OF_ORDER" |
             "UNKNOWN_SLOT" | "ALREADY_DECIDED"}.
    """
    slot = next((s for s in slots if s["slot_id"] == slot_id), None)
    if slot is None:
        return {"authorized": False, "code": "UNKNOWN_SLOT"}
    is_named = actor["person_id"] == slot["approver_id"]
    is_scheduler = actor.get("role") == "core_scheduler" and slot["kind"] == "owner_move"
    if not (is_named or is_scheduler):
        return {"authorized": False, "code": "UNAUTHORIZED_APPROVAL"}
    status = approval_status(slots, approvals)
    if slot_id not in status["pending"]:
        return {"authorized": False, "code": "ALREADY_DECIDED"}
    if ordered:
        idx = [s["slot_id"] for s in slots].index(slot_id)
        if any(s["slot_id"] not in status["approved"] for s in slots[:idx]):
            return {"authorized": False, "code": "APPROVAL_OUT_OF_ORDER"}
    return {"authorized": True, "code": None}


def reservation_state(proposal, approvals):
    """Derive the ReservationProposal state from its approvals (never 'committed')."""
    slots = reservation_slots(proposal)
    status = approval_status(slots, approvals)
    if status["rejected"]:
        return "rejected"
    if status["complete"]:
        return "authorized"
    owner_pending = [s for s in slots if s["kind"] == "owner_move" and s["slot_id"] in status["pending"]]
    return "owner_approval_pending" if owner_pending else "requester_approval_pending"
