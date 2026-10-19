"""Agent tool functions (docs/06 tool registry), one function per tool.

Every tool takes the repository first (injected by the host: C3 or the CLI, never
by the agent) followed by JSON-serializable keyword arguments, and returns a
JSON-serializable dict:

    {"status": "ok", ..., "source_record_ids": [...], "data_timestamp": ISO, "assumptions": [...], "warnings": [...]}
    {"status": "error", "code": "<STRUCTURED_CODE>", "message": "..."}

Rules enforced here, not in the UI:
  * Reads never write. Proposals never touch confirmed bookings.
  * Every state change writes an AuditEvent; every proposed change opens Approval requests.
  * Nothing confirms a booking, places an order or applies a recommendation without the
    required Approval records. Orders stop at `approved_request` (no purchasing).
"""
from labsync_core import policy as core_policy
from labsync_core.commit import plan_commit
from labsync_core.eligibility import capability_match, check_qualifications
from labsync_core.forecast import forecast_resource
from labsync_core.materials import find_shared_materials
from labsync_core.proposals import (HELD_STATES, approval_status, authorize_decision, can_transition,
                                    insight_slots, order_slots, reservation_slots, reservation_state)
from labsync_core.slots import find_slots
from labsync_core.supplies import check_stock, quote, supply_readiness
from labsync_core.utilization import find_utilization_gaps, weekly_utilization
from labsync_core.values import as_bool, as_list, as_num, iso, overlaps, to_dt

from . import approvals as approval_store
from . import audit
from .repository import CommitWriteError
from .schemas import validate_parsed_goal

ADMIN_ROLES = {"department_admin"}
SHIP_TO_DEFAULT = "north_bio_receiving"  # assumption: every lab receives at the building dock


# ---------------------------------------------------------------- helpers

def _ok(repo, **payload):
    payload.setdefault("source_record_ids", [])
    payload.setdefault("assumptions", [])
    payload.setdefault("warnings", [])
    payload["source_record_ids"] = sorted(set(payload["source_record_ids"]))
    return dict({"status": "ok", "data_timestamp": repo.now()}, **payload)


def _err(code, message, **extra):
    return dict({"status": "error", "code": code, "message": message}, **extra)


def _actor(repo, actor_id):
    return repo.get_record("Person", actor_id)


def _deny(repo, actor_id, operation, entity_kind, entity_id, code="PERMISSION_DENIED"):
    """Audit a refused attempt; the returned error never echoes restricted data."""
    audit.record(repo, actor_id, operation, entity_kind, entity_id, status="denied", detail=code)
    return _err(code, "You are not authorized for this action.")


def _policies(repo):
    return core_policy.policy_map(repo.list_records("Policy"))


def _index(rows, key):
    return {r[key]: r for r in rows}


def _calendar(repo, exclude_plan_id=None):
    """Confirmed instrument and room rows plus 'held' rows for open proposals.

    A held proposal blocks its requested slots and its owner-move targets for everyone else.
    """
    bookings = repo.list_records("Booking")
    rooms = repo.list_records("RoomReservation")
    for p in repo.list_records("ReservationProposal"):
        if p["state"] not in HELD_STATES or p["plan_id"] == exclude_plan_id:
            continue
        for c in p["creates"]:
            row = {"booking_id": "hold:%s" % c["booking_id"], "resource_id": c["resource_id"],
                   "start_local": c["start"], "end_local": c["end"], "status": "held", "flexible": "false",
                   "user_id": c["user_id"], "lab_id": c["lab_id"], "proposal_id": p["proposal_id"]}
            (rooms if c.get("entity") == "RoomReservation" else bookings).append(row)
        for m in p["contingent_moves"]:
            bookings.append({"booking_id": "hold:move:%s" % m["booking_id"], "resource_id": m["resource_id"],
                             "start_local": m["to"]["start"], "end_local": m["to"]["end"], "status": "held",
                             "flexible": "false", "user_id": m["owner_id"], "lab_id": m["lab_id"],
                             "proposal_id": p["proposal_id"]})
    return bookings, rooms


def _resources(repo):
    res = _index(repo.list_records("Instrument"), "instrument_id")
    res.update(_index(repo.list_records("Room"), "room_id"))
    return res


def _transition(repo, kind, record, target, actor_id, operation, lab_ids=(), source_ids=(), detail=None):
    check = can_transition(kind, record["state"], target)
    if not check["ok"]:
        raise ValueError("%s %s: %s -> %s not allowed" % (kind, record.get(_id_field(kind)), record["state"], target))
    before = record["state"]
    record = dict(record, state=target, updated_at=repo.now())
    repo.save_record(kind, record)
    audit.record(repo, actor_id, operation, kind, record[_id_field(kind)], request_id=record.get("request_id"),
                 source_ids=source_ids, before={"state": before}, after={"state": target}, lab_ids=lab_ids,
                 detail=detail)
    return record


def _id_field(kind):
    from .repository import ID_FIELDS
    return ID_FIELDS[kind]


def _scheduling_request(plan):
    """Translate a validated ParsedGoal into a labsync_core.slots request."""
    goal = plan["goal"]
    instrument = next((s for s in goal["steps"] if s["kind"] == "instrument"), None)
    prep = next((s for s in goal["steps"] if s["kind"] == "prep_room" and s["required"]), None)
    if instrument is None:
        return None
    start = goal["desiredStart"]
    deadline = goal["deadline"]
    duration = instrument["durationMinutes"]
    preferred_end = goal["preferredEnd"] or iso(to_dt(start) + _minutes(duration))
    search_end = deadline or iso(to_dt(start) + _minutes(2 * 24 * 60))
    caps = sorted(set(instrument["requiredCapabilities"]) | set(goal["requiredCapabilities"]))
    return {
        "requester_id": plan["requester_id"], "lab_id": plan["lab_id"], "required_capabilities": caps,
        "duration_minutes": duration, "search_start": start, "search_end": search_end,
        "preferred_start": start, "preferred_end": preferred_end, "deadline": deadline,
        "prep": ({"room_capabilities": prep["requiredCapabilities"] or ["wet_prep"],
                  "duration_minutes": prep["durationMinutes"]} if prep else None),
    }


def _minutes(n):
    from datetime import timedelta
    return timedelta(minutes=n)


def _plan_readiness(repo, plan):
    goal = plan["goal"]
    items = [{"sku_id": s["skuId"], "quantity": s["quantity"]} for s in goal["supplies"]]
    if not items or not goal["desiredStart"]:
        return None
    skus = _index(repo.list_records("SupplySku"), "sku_id")
    return supply_readiness(plan["lab_id"], items, skus, repo.list_records("Stock"), to_dt(repo.now()).date(),
                            goal["desiredStart"])


# ---------------------------------------------------------------- catalog / qualifications

def catalog_find_resources(repo, actor_id, capabilities, resource_type="any"):
    """List instruments and/or rooms that offer every requested capability. Read only.

    Args:
        actor_id (str): the signed-in person (catalog data is not lab-restricted).
        capabilities (list[str]): e.g. ["gfp_imaging", "confocal_imaging"] or ["wet_prep"].
        resource_type (str): "instrument", "room" or "any".
    Returns:
        {"status": "ok", "resources": [{"resource_id", "resource_type", "name", "kind", "capabilities",
         "required_qualifications", "buffer_minutes", "open_local", "close_local"}]}
    """
    if _actor(repo, actor_id) is None:
        return _err("UNKNOWN_ACTOR", "Unknown actor.")
    out = []
    if resource_type in ("instrument", "any"):
        for r in repo.list_records("Instrument"):
            if not capability_match(r, capabilities):
                out.append({"resource_id": r["instrument_id"], "resource_type": "instrument", "name": r["name"],
                            "kind": r["kind"], "capabilities": as_list(r["capabilities"]),
                            "required_qualifications": as_list(r["required_qualifications"]),
                            "buffer_minutes": int(as_num(r["buffer_minutes"])), "open_local": r["open_local"],
                            "close_local": r["close_local"]})
    if resource_type in ("room", "any"):
        for r in repo.list_records("Room"):
            if not capability_match(r, capabilities):
                out.append({"resource_id": r["room_id"], "resource_type": "room", "name": r["name"],
                            "kind": r["kind"], "capabilities": as_list(r["capabilities"]),
                            "required_qualifications": [], "buffer_minutes": int(as_num(r["buffer_minutes"])),
                            "open_local": r["open_local"], "close_local": r["close_local"]})
    out.sort(key=lambda r: r["resource_id"])
    return _ok(repo, resources=out, source_record_ids=[r["resource_id"] for r in out])


def resource_check_qualifications(repo, actor_id, user_id, resource_id):
    """Check whether a person may operate an instrument unsupervised. Read only.

    Args:
        actor_id (str): the signed-in person.
        user_id (str): person id, e.g. "morgan".
        resource_id (str): instrument id, e.g. "confocal_2".
    Returns:
        {"status": "ok", "eligible": bool, "missing": [qualification ids], "code": null | "NOT_QUALIFIED"}
    """
    if _actor(repo, actor_id) is None:
        return _err("UNKNOWN_ACTOR", "Unknown actor.")
    person = repo.get_record("Person", user_id)
    resource = repo.get_record("Instrument", resource_id) or repo.get_record("Room", resource_id)
    if person is None or resource is None:
        return _err("NOT_FOUND", "Unknown person or resource.")
    result = check_qualifications(person, resource)
    return _ok(repo, **result, source_record_ids=[user_id, resource_id])


# ---------------------------------------------------------------- planning

def plan_create_draft(repo, actor_id, parsed_goal, request_id=None):
    """Save a validated ParsedGoal as an editable ExperimentPlan draft (internal draft write).

    Args:
        actor_id (str): the requester; must equal parsed_goal.requesterId and belong to labId.
        parsed_goal (dict): output of the Lab Agent's request parsing (see agents/ schema).
        request_id (str, optional): correlation id for the whole request.
    Returns:
        {"status": "ok", "plan_id", "state": "draft", "needs_input": [...], "scheduling_request": {...}}
        or {"status": "error", "code": "INVALID_PLAN", "errors": [...]} (nothing written).
    """
    actor = _actor(repo, actor_id)
    if actor is None:
        return _err("UNKNOWN_ACTOR", "Unknown actor.")
    skus = {s["sku_id"] for s in repo.list_records("SupplySku")}
    caps = set()
    for r in repo.list_records("Instrument") + repo.list_records("Room"):
        caps |= set(as_list(r["capabilities"]))
    errors, warnings = validate_parsed_goal(parsed_goal, skus, caps)
    if not errors:
        if parsed_goal["requesterId"] != actor_id or parsed_goal["labId"] != actor["lab_id"]:
            errors.append("requesterId/labId must match the signed-in actor")
    if errors:
        audit.record(repo, actor_id, "plan_create_draft", "ExperimentPlan", None, request_id=request_id,
                     status="rejected", detail="INVALID_PLAN", lab_ids=[actor["lab_id"]])
        return _err("INVALID_PLAN", "The parsed plan failed validation; nothing was saved.", errors=errors)
    plan_id = repo.next_id("plan")
    request_id = request_id or repo.next_id("req")
    plan = {"plan_id": plan_id, "request_id": request_id, "lab_id": actor["lab_id"], "requester_id": actor_id,
            "goal": parsed_goal, "state": "draft", "needs_input": list(parsed_goal["missingInformation"]),
            "warnings": warnings, "created_at": repo.now(), "version": 1}
    plan["scheduling_request"] = _scheduling_request(plan) if not plan["needs_input"] else None
    repo.save_record("ExperimentPlan", plan)
    audit.record(repo, actor_id, "plan_create_draft", "ExperimentPlan", plan_id, request_id=request_id,
                 after={"state": "draft"}, lab_ids=[actor["lab_id"]])
    return _ok(repo, plan_id=plan_id, request_id=request_id, state="draft", needs_input=plan["needs_input"],
               scheduling_request=plan["scheduling_request"], warnings=warnings, source_record_ids=[plan_id])


def _search(repo, plan):
    """Run the deterministic scheduler for a plan against the live calendar (other holds included)."""
    request = dict(plan["scheduling_request"])
    readiness = _plan_readiness(repo, plan)
    if readiness and readiness.get("ready_at"):
        request["supplies_ready_at"] = readiness["ready_at"]
    bookings, rooms = _calendar(repo, exclude_plan_id=plan["plan_id"])
    result = find_slots(request, repo.list_records("Instrument"), repo.list_records("Person"), bookings,
                        repo.list_records("Room"), rooms, repo.list_records("MaintenanceWindow"), _policies(repo))
    return result, readiness


def scheduler_find_slots(repo, actor_id, plan_id):
    """Compute ranked booking options for a plan with the deterministic scheduler. Read only.

    Args:
        actor_id (str): the plan's requester.
        plan_id (str): from plan_create_draft.
    Returns:
        {"status": "ok", "options": [...], "blocked_alternatives": [...], "exclusion_counts": {...},
         "supply_readiness": {...} | null}. Options carry option_id, kind ("direct"|"owner_move"),
         times, prep slot, contingent_moves, approvals_required, score and score_breakdown.
        Option ids are deterministic: the same calendar gives the same ids, so booking_propose can
        re-check the chosen option. Errors: NOT_FOUND, PERMISSION_DENIED, MISSING_INFORMATION.
    """
    plan = repo.get_record("ExperimentPlan", plan_id)
    if plan is None:
        return _err("NOT_FOUND", "Unknown plan.")
    if plan["requester_id"] != actor_id:
        return _deny(repo, actor_id, "scheduler_find_slots", "ExperimentPlan", plan_id)
    if plan["needs_input"] or plan["scheduling_request"] is None:
        return _err("MISSING_INFORMATION", "The plan needs more information before searching.",
                    needs_input=plan["needs_input"] or ["instrument step"])
    result, readiness = _search(repo, plan)
    sources = [plan_id] + [o["resource_id"] for o in result["options"]]
    sources += [m["booking_id"] for o in result["options"] for m in o["contingent_moves"]]
    sources += [b["resource_id"] for b in result["blocked_alternatives"]]
    return _ok(repo, plan_id=plan_id, status_detail=result["status"], options=result["options"],
               blocked_alternatives=result["blocked_alternatives"], exclusion_counts=result["exclusion_counts"],
               supply_readiness=readiness, assumptions=result["assumptions"], source_record_ids=sources)


# ---------------------------------------------------------------- supplies

def stock_get_availability(repo, actor_id, lab_id, sku_ids):
    """Show a lab's own stock for given SKUs. Read only; only members of that lab may look.

    Args:
        actor_id (str), lab_id (str), sku_ids (list[str]).
    Returns:
        {"status": "ok", "lab_id", "items": [{"sku_id", "on_hand", "expiry_dates"}]} or PERMISSION_DENIED.
    """
    actor = _actor(repo, actor_id)
    if actor is None or actor["lab_id"] != lab_id:
        return _deny(repo, actor_id, "stock_get_availability", "Stock", lab_id)
    rows = [s for s in repo.list_records("Stock") if s["lab_id"] == lab_id and s["sku_id"] in sku_ids]
    items = []
    for sku in sku_ids:
        mine = [r for r in rows if r["sku_id"] == sku]
        items.append({"sku_id": sku, "on_hand": sum(as_num(r["quantity"]) for r in mine),
                      "expiry_dates": sorted(r["expiry_date"] for r in mine if r["expiry_date"])})
    return _ok(repo, lab_id=lab_id, items=items, source_record_ids=[r["stock_id"] for r in rows])


def supply_quote(repo, actor_id, items, needed_by=None):
    """Synthetic price quote and, if `needed_by` is given, readiness for the actor's lab. Read only.

    Args:
        actor_id (str).
        items (list[{"sku_id", "quantity"}]).
        needed_by (str, optional): ISO time the supplies must be on hand (e.g. prep start).
    Returns:
        {"status": "ok", "quote": {...lines, shipping_by_vendor, total_usd, status: "estimate"},
         "readiness": {...status, last_safe_order_date, ready_at, code} | null}
        Prices are synthetic assumptions; this is never a purchase.
    """
    actor = _actor(repo, actor_id)
    skus = _index(repo.list_records("SupplySku"), "sku_id")
    unknown = [i["sku_id"] for i in items if i["sku_id"] not in skus]
    if actor is None or unknown:
        return _err("NOT_FOUND", "Unknown actor or SKU.", unknown_skus=unknown)
    q = quote(items, skus)
    readiness = None
    if needed_by:
        readiness = supply_readiness(actor["lab_id"], items, skus, repo.list_records("Stock"),
                                     to_dt(repo.now()).date(), needed_by)
    return _ok(repo, quote=q, readiness=readiness, assumptions=q["assumptions"],
               source_record_ids=[i["sku_id"] for i in items])


def supply_create_order_draft(repo, actor_id, plan_id, idempotency_key):
    """Draft supply order requests for a plan's shortfall (docs/01 SupplyRequest.createDraft).

    One OrderProposal per SKU line, state `awaiting_lab_approval`, with lab and fund Approval
    requests. Nothing is purchased: the furthest an order can go is `approved_request`.

    Args:
        actor_id (str): the plan's requester.
        plan_id (str).
        idempotency_key (str): retries with the same key return the same orders.
    Returns:
        {"status": "ok", "orders": [...], "readiness": {...}} ; "orders": [] when stock covers the plan.
    """
    plan = repo.get_record("ExperimentPlan", plan_id)
    if plan is None:
        return _err("NOT_FOUND", "Unknown plan.")
    if plan["requester_id"] != actor_id:
        return _deny(repo, actor_id, "supply_create_order_draft", "ExperimentPlan", plan_id)
    existing = [o for o in repo.list_records("OrderProposal") if o.get("idempotency_key") == idempotency_key]
    if existing:
        return _ok(repo, orders=existing, replayed=True, source_record_ids=[o["order_id"] for o in existing])
    items = [{"sku_id": s["skuId"], "quantity": s["quantity"]} for s in plan["goal"]["supplies"]]
    skus = _index(repo.list_records("SupplySku"), "sku_id")
    shortfall = [s for s in check_stock(plan["lab_id"], items, repo.list_records("Stock")) if s["shortfall"] > 0]
    readiness = _plan_readiness(repo, plan)
    labs = repo.list_records("Lab")
    orders = []
    now = repo.now()
    for line in shortfall:
        sku = skus[line["sku_id"]]
        order = {
            "order_id": repo.next_id("po"), "line_id": None, "lab_id": plan["lab_id"], "requester_id": actor_id,
            "sku_id": line["sku_id"], "vendor_id": sku["vendor_id"], "quantity": line["shortfall"],
            "unit_price_usd": as_num(sku["base_price_usd"]), "shipping_usd": as_num(sku["shipping_per_order_usd"]),
            "state": "draft", "created_local": now,
            "need_by_date": to_dt(plan["goal"]["desiredStart"]).date().isoformat() if plan["goal"]["desiredStart"] else "",
            "ship_to": SHIP_TO_DEFAULT, "funding_hint_id": "", "plan_id": plan_id, "request_id": plan["request_id"],
            "idempotency_key": idempotency_key, "provenance": "app",
        }
        order["line_id"] = order["order_id"] + "_l1"
        repo.save_record("OrderProposal", order)
        audit.record(repo, actor_id, "supply_create_order_draft", "OrderProposal", order["order_id"],
                     request_id=plan["request_id"], after={"state": "draft", "quantity": order["quantity"]},
                     lab_ids=[plan["lab_id"]], source_ids=[plan_id, line["sku_id"]])
        order = _transition(repo, "OrderProposal", order, "awaiting_lab_approval", actor_id, "order_submit_for_approval",
                            lab_ids=[plan["lab_id"]])
        approval_store.open_requests(repo, "OrderProposal", order["order_id"], order_slots(order, labs), actor_id,
                                     plan["request_id"])
        orders.append(order)
    return _ok(repo, orders=orders, readiness=readiness, replayed=False,
               assumptions=["synthetic prices", "proposal only: awaiting lab and fund authorization"],
               source_record_ids=[plan_id] + [o["order_id"] for o in orders])


# ---------------------------------------------------------------- proposals and negotiation

def booking_propose(repo, actor_id, plan_id, option_id, idempotency_key):
    """Hold one scheduler option as a ReservationProposal. Proposal only: no booking changes.

    The held slots block other proposals until the proposal is committed, rejected or goes stale.
    Opens Approval requests: one per displaced owner (not sent until liaison_request_change) and
    the requester's final confirmation.

    Args:
        actor_id (str): the plan's requester.
        plan_id (str), option_id (str): an option_id returned by scheduler_find_slots for this plan.
        idempotency_key (str): retries with the same key return the same proposal.
    Returns:
        {"status": "ok", "proposal_id", "state", "held": [...], "contingent_moves": [...], "approvals": [...]}
        Errors: NOT_FOUND, PERMISSION_DENIED, UNKNOWN_OPTION, SLOT_STALE.
    """
    plan = repo.get_record("ExperimentPlan", plan_id)
    if plan is None:
        return _err("NOT_FOUND", "Unknown plan.")
    if plan["requester_id"] != actor_id:
        return _deny(repo, actor_id, "booking_propose", "ExperimentPlan", plan_id)
    for p in repo.list_records("ReservationProposal"):
        if p["idempotency_key"] == idempotency_key:
            return _ok(repo, proposal_id=p["proposal_id"], state=p["state"], replayed=True,
                       source_record_ids=[p["proposal_id"]])
    if plan["state"] not in ("draft", "options_ready", "needs_revision"):
        return _err("PLAN_NOT_OPEN", "This plan already has a proposal in progress or is closed.", state=plan["state"])
    if plan["scheduling_request"] is None:
        return _err("MISSING_INFORMATION", "The plan needs more information before proposing.")
    # Re-run the scheduler on the live calendar (including other holds): the option must still be offered.
    result, _ = _search(repo, plan)
    option = next((o for o in result["options"] if o["option_id"] == option_id), None)
    if option is None:
        return _err("SLOT_STALE", "That option is not available now. Search again.")
    moved = [m["booking_id"] for m in option["contingent_moves"]]
    proposal_id = repo.next_id("prop")
    creates = [{"booking_id": "bk_%s_img" % proposal_id, "entity": "Booking", "resource_id": option["resource_id"],
                "start": option["start"], "end": option["end"], "user_id": actor_id, "lab_id": plan["lab_id"]}]
    if option["prep"]:
        creates.append({"booking_id": "rr_%s_prep" % proposal_id, "entity": "RoomReservation",
                        "resource_id": option["prep"]["resource_id"], "start": option["prep"]["start"],
                        "end": option["prep"]["end"], "user_id": actor_id, "lab_id": plan["lab_id"]})
    expected = {m["booking_id"]: as_num(repo.get_record("Booking", m["booking_id"]).get("version"), 1)
                for m in option["contingent_moves"]}
    proposal = {"proposal_id": proposal_id, "plan_id": plan_id, "request_id": plan["request_id"],
                "requester_id": actor_id, "lab_id": plan["lab_id"], "option_id": option_id, "kind": option["kind"],
                "creates": creates, "contingent_moves": option["contingent_moves"], "expected_versions": expected,
                "state": "draft", "idempotency_key": idempotency_key, "created_at": repo.now()}
    repo.save_record("ReservationProposal", proposal)
    audit.record(repo, actor_id, "booking_propose", "ReservationProposal", proposal_id, request_id=plan["request_id"],
                 after={"state": "draft", "creates": creates, "moves": option["contingent_moves"]},
                 lab_ids=[plan["lab_id"]] + [m["lab_id"] for m in option["contingent_moves"]],
                 source_ids=[plan_id] + moved)
    proposal = _transition(repo, "ReservationProposal", proposal, "submitted", actor_id, "booking_hold",
                           lab_ids=[plan["lab_id"]])
    records = approval_store.open_requests(repo, "ReservationProposal", proposal_id, reservation_slots(proposal),
                                           actor_id, plan["request_id"], held_slot_kinds=("owner_move",))
    proposal = _transition(repo, "ReservationProposal", proposal, reservation_state(proposal, []), actor_id,
                           "booking_await_approvals", lab_ids=[plan["lab_id"]])
    if plan["state"] != "options_ready":
        plan = _transition(repo, "ExperimentPlan", plan, "options_ready", actor_id, "plan_options_chosen",
                           lab_ids=[plan["lab_id"]])
    _transition(repo, "ExperimentPlan", plan, "approval_pending", actor_id, "plan_await_approvals",
                lab_ids=[plan["lab_id"]])
    return _ok(repo, proposal_id=proposal_id, state=proposal["state"], held=creates,
               contingent_moves=option["contingent_moves"], approvals=records, replayed=False,
               assumptions=["held slots block other proposals; nothing is confirmed until commit"],
               source_record_ids=[proposal_id, plan_id] + moved)


def _owner_impact(repo, proposal, move):
    """What the displaced owner needs to judge a move, limited to their own lab's bookings.
    `person_conflicts` lists the booker's own sessions that overlap the proposed new time."""
    day = to_dt(move["from"]["start"]).date()
    own = [b for b in repo.list_records("Booking") if b["lab_id"] == move["lab_id"]
           and to_dt(b["start_local"]).date() == day and b["booking_id"] != move["booking_id"]]
    requester_lab = repo.get_record("Lab", proposal["lab_id"])
    owner_booking = repo.get_record("Booking", move["booking_id"])
    duration_same = (to_dt(move["from"]["end"]) - to_dt(move["from"]["start"])) == (
        to_dt(move["to"]["end"]) - to_dt(move["to"]["start"]))
    return {"booking_id": move["booking_id"], "resource_id": move["resource_id"], "from": move["from"],
            "to": move["to"], "same_duration": duration_same, "same_day": to_dt(move["to"]["start"]).date() == day,
            "requested_by_lab": requester_lab["name"] if requester_lab else proposal["lab_id"],
            "booked_by": owner_booking["user_id"],
            "flexible": as_bool(owner_booking.get("flexible")),
            "person_conflicts": sorted(b["booking_id"] for b in own if b["user_id"] == owner_booking["user_id"]
                                       and overlaps(b["start_local"], b["end_local"], move["to"]["start"],
                                                    move["to"]["end"])),
            "your_other_bookings_that_day": [{"booking_id": b["booking_id"], "resource_id": b["resource_id"],
                                              "user_id": b["user_id"], "start": b["start_local"],
                                              "end": b["end_local"]} for b in own]}


def liaison_request_change(repo, actor_id, proposal_id, booking_id, message=None):
    """Send the owner of a displaced flexible booking a move request (in-app only, never email).
    Proposal only: the owner's booking does not change.

    Args:
        actor_id (str): the proposal's requester.
        proposal_id (str), booking_id (str): the booking to move (from contingent_moves).
        message (str, optional): short note shown to the owner.
    Returns:
        {"status": "ok", "approval_id", "notification_id", "owner_id", "impact": {...}}
    """
    proposal = repo.get_record("ReservationProposal", proposal_id)
    if proposal is None:
        return _err("NOT_FOUND", "Unknown proposal.")
    if proposal["requester_id"] != actor_id:
        return _deny(repo, actor_id, "liaison_request_change", "ReservationProposal", proposal_id)
    move = next((m for m in proposal["contingent_moves"] if m["booking_id"] == booking_id), None)
    record = next((a for a in approval_store.for_entity(repo, "ReservationProposal", proposal_id)
                   if a.get("booking_id") == booking_id), None)
    if move is None or record is None:
        return _err("NOT_FOUND", "That booking is not part of this proposal.")
    if record["status"] != "not_sent":
        return _ok(repo, approval_id=record["approval_id"], owner_id=record["approver_id"], replayed=True,
                   source_record_ids=[proposal_id, booking_id])
    impact = _owner_impact(repo, proposal, move)
    record = dict(record, status="pending", sent_at=repo.now(), impact=impact, message=message)
    repo.save_record("Approval", record)
    note = {"notification_id": repo.next_id("note"), "recipient_id": record["approver_id"],
            "kind": "owner_move_request", "approval_id": record["approval_id"], "proposal_id": proposal_id,
            "text": "%s requests moving your %s booking to %s-%s" % (
                impact["requested_by_lab"], move["resource_id"], move["to"]["start"][11:16], move["to"]["end"][11:16]),
            "created_at": repo.now(), "read": False, "channel": "in_app"}
    repo.save_record("Notification", note)
    audit.record(repo, actor_id, "liaison_request_change", "Approval", record["approval_id"],
                 request_id=proposal["request_id"], before={"status": "not_sent"}, after={"status": "pending"},
                 lab_ids=[proposal["lab_id"], move["lab_id"]], source_ids=[proposal_id, booking_id])
    return _ok(repo, approval_id=record["approval_id"], notification_id=note["notification_id"],
               owner_id=record["approver_id"], impact=impact, replayed=False,
               source_record_ids=[proposal_id, booking_id])


def liaison_get_change_request(repo, actor_id, approval_id):
    """Read an incoming move request as the owner (or core scheduler) sees it. Read only.
    Used by the Conflict Negotiator to recommend approve / reject / suggest another time.

    Args:
        actor_id (str): the owner named on the request, or a core scheduler.
        approval_id (str).
    Returns:
        {"status": "ok", "approval_id", "state", "impact": {...}, "message"} ; PERMISSION_DENIED otherwise.
    """
    record = repo.get_record("Approval", approval_id)
    actor = _actor(repo, actor_id)
    if record is None or record["slot_kind"] != "owner_move":
        return _err("NOT_FOUND", "Unknown move request.")
    if actor is None or (actor_id != record["approver_id"] and actor.get("role") != "core_scheduler"):
        return _deny(repo, actor_id, "liaison_get_change_request", "Approval", approval_id)
    return _ok(repo, approval_id=approval_id, state=record["status"], impact=record.get("impact"),
               message=record.get("message"), source_record_ids=[approval_id, record["booking_id"]])


# ---------------------------------------------------------------- approvals and commit

def _apply_entity_state(repo, record, actor_id):
    """After a decision, move the parent entity to the state its approvals imply."""
    kind, eid = record["entity_kind"], record["entity_id"]
    entity = repo.get_record(kind, eid)
    slots, decisions = approval_store.slots_and_decisions(approval_store.for_entity(repo, kind, eid))
    status = approval_status(slots, decisions)
    labs = [entity.get("lab_id")] if entity.get("lab_id") else entity.get("lab_ids", [])
    if kind == "ReservationProposal":
        target = reservation_state(entity, decisions)
        if target != entity["state"]:
            entity = _transition(repo, kind, entity, target, actor_id, "proposal_state", lab_ids=labs)
        plan = repo.get_record("ExperimentPlan", entity["plan_id"])
        if target == "rejected" and plan["state"] == "approval_pending":
            _transition(repo, "ExperimentPlan", plan, "needs_revision", actor_id, "plan_state", lab_ids=labs,
                        detail="OWNER_REJECTED")
        elif target == "authorized" and plan["state"] == "approval_pending":
            _transition(repo, "ExperimentPlan", plan, "ready_to_commit", actor_id, "plan_state", lab_ids=labs)
        return entity, ("replan" if target == "rejected" else "commit" if target == "authorized" else "await_approvals")
    if kind == "OrderProposal":
        if status["rejected"]:
            target = "rejected"
        elif "fund" in status["approved"]:
            target = "approved_request"
        elif "lab" in status["approved"]:
            target = "awaiting_fund_approval"
        else:
            target = entity["state"]
        if target != entity["state"]:
            entity = _transition(repo, kind, entity, target, actor_id, "order_state", lab_ids=labs)
        return entity, "none" if target in ("approved_request", "rejected") else "await_approvals"
    if kind == "DepartmentInsight":
        target = "dismissed" if status["rejected"] else "approved" if status["complete"] else entity["state"]
        if target != entity["state"]:
            entity = _transition(repo, kind, entity, target, actor_id, "insight_state", lab_ids=labs)
        return entity, "none" if target in ("approved", "dismissed") else "await_approvals"
    return entity, "none"


def approval_record(repo, actor_id, approval_id, decision, reason=None):
    """Record a human approve/reject decision on one Approval request. Writes only if authorized.

    Called by the UI when a person presses Approve/Reject; agents may recommend but never call
    this on someone's behalf.

    Args:
        actor_id (str): the person deciding.
        approval_id (str).
        decision (str): "approve" or "reject".
        reason (str, optional).
    Returns:
        {"status": "ok", "approval_id", "decision", "entity_kind", "entity_id", "entity_state", "next_step"}
        next_step: "commit" | "replan" | "await_approvals" | "none".
        Errors: NOT_FOUND, NOT_REQUESTED, UNAUTHORIZED_APPROVAL, APPROVAL_OUT_OF_ORDER, ALREADY_DECIDED.
    """
    if decision not in ("approve", "reject"):
        return _err("INVALID_DECISION", "decision must be approve or reject")
    record = repo.get_record("Approval", approval_id)
    actor = _actor(repo, actor_id)
    if record is None:
        return _err("NOT_FOUND", "Unknown approval request.")
    if actor is None:
        return _deny(repo, actor_id, "approval_record", "Approval", approval_id, code="UNAUTHORIZED_APPROVAL")
    records = approval_store.for_entity(repo, record["entity_kind"], record["entity_id"])
    slots, decisions = approval_store.slots_and_decisions(records)
    check = authorize_decision(slots, decisions, record["slot_id"], actor)
    if not check["authorized"]:
        if check["code"] == "UNAUTHORIZED_APPROVAL":
            return _deny(repo, actor_id, "approval_record", "Approval", approval_id, code="UNAUTHORIZED_APPROVAL")
        audit.record(repo, actor_id, "approval_record", "Approval", approval_id, status="refused", detail=check["code"])
        return _err(check["code"], "This decision can't be recorded yet.")
    if record["status"] != "pending":
        return _err("NOT_REQUESTED", "This request has not been sent to the approver yet.")
    before = {"status": record["status"]}
    record = dict(record, status="decided", decision=decision, decided_by=actor_id, decided_at=repo.now(), reason=reason)
    repo.save_record("Approval", record)
    audit.record(repo, actor_id, "approval_record", "Approval", approval_id, request_id=record.get("request_id"),
                 before=before, after={"status": "decided", "decision": decision},
                 lab_ids=[record.get("lab_id"), actor.get("lab_id")], source_ids=[record["entity_id"]], detail=reason)
    entity, next_step = _apply_entity_state(repo, record, actor_id)
    return _ok(repo, approval_id=approval_id, decision=decision, entity_kind=record["entity_kind"],
               entity_id=record["entity_id"], entity_state=entity["state"], next_step=next_step,
               source_record_ids=[approval_id, record["entity_id"]])


def booking_commit_approved(repo, actor_id, proposal_id, idempotency_key):
    """Commit an authorized proposal: re-validate, then write moved + new bookings atomically or
    compensate. The only tool that changes confirmed bookings.

    Args:
        actor_id (str): the proposal's requester (final confirmation already recorded).
        proposal_id (str).
        idempotency_key (str): e.g. "<request_id>:commit:<proposal_id>"; a retry returns the same receipt.
    Returns:
        {"status": "ok", "receipt": {...}, "changes": [writes], "replayed": bool}
        Errors: UNAUTHORIZED, MISSING_APPROVAL, OWNER_REJECTED, SLOT_STALE, PARTIAL_COMMIT_RECOVERY.
    """
    proposal = repo.get_record("ReservationProposal", proposal_id)
    if proposal is None:
        return _err("NOT_FOUND", "Unknown proposal.")
    prior = repo.get_record("CommitReceipt", idempotency_key)
    receipts = {idempotency_key: prior["receipt"]} if prior else {}
    records = approval_store.for_entity(repo, "ReservationProposal", proposal_id)
    _, decisions = approval_store.slots_and_decisions(records)
    bookings, rooms = _calendar(repo)
    plan_result = plan_commit(proposal, bookings + rooms, _resources(repo), decisions, actor_id, idempotency_key,
                              receipts, repo.list_records("MaintenanceWindow"), now=repo.now())
    labs = [proposal["lab_id"]] + [m["lab_id"] for m in proposal["contingent_moves"]]
    if plan_result["status"] == "error":
        code = plan_result["code"]
        if code == "UNAUTHORIZED":
            return _deny(repo, actor_id, "booking_commit_approved", "ReservationProposal", proposal_id, code=code)
        audit.record(repo, actor_id, "booking_commit_approved", "ReservationProposal", proposal_id,
                     request_id=proposal["request_id"], status="failed", detail=code, lab_ids=labs)
        if code == "SLOT_STALE" and proposal["state"] in HELD_STATES:
            _transition(repo, "ReservationProposal", proposal, "stale", actor_id, "proposal_state", lab_ids=labs)
            plan = repo.get_record("ExperimentPlan", proposal["plan_id"])
            if plan["state"] in ("approval_pending", "ready_to_commit"):
                _transition(repo, "ExperimentPlan", plan, "needs_revision", actor_id, "plan_state", lab_ids=labs,
                            detail=code)
        return _err(code, plan_result["detail"], **{k: v for k, v in plan_result.items()
                                                       if k in ("pending", "stale_ids", "rejected_by")})
    if plan_result["replayed"]:
        return _ok(repo, receipt=plan_result["receipt"], changes=[], replayed=True, source_record_ids=[proposal_id])
    applied = []
    try:
        for write in plan_result["writes"]:
            repo.apply_write(write)
            applied.append(write)
    except CommitWriteError as exc:
        undo = [c for c in plan_result["compensation"] if c["id"] in {w["id"] for w in applied}]
        for c in undo:
            repo.apply_write(c)
        _transition(repo, "ReservationProposal", proposal, "failed", actor_id, "proposal_state", lab_ids=labs,
                    detail="PARTIAL_COMMIT_RECOVERY")
        plan = repo.get_record("ExperimentPlan", proposal["plan_id"])
        _transition(repo, "ExperimentPlan", plan, "failed", actor_id, "plan_state", lab_ids=labs,
                    detail="PARTIAL_COMMIT_RECOVERY")
        audit.record(repo, actor_id, "booking_commit_compensated", "ReservationProposal", proposal_id,
                     request_id=proposal["request_id"], status="failed", before={"applied": applied},
                     after={"compensated": undo}, lab_ids=labs, detail=str(exc))
        return _err("PARTIAL_COMMIT_RECOVERY", "The commit failed part-way and every applied change was undone.",
                    compensated_ids=[c["id"] for c in undo])
    receipt = plan_result["receipt"]
    repo.save_record("CommitReceipt", {"idempotency_key": idempotency_key, "receipt": receipt})
    proposal = _transition(repo, "ReservationProposal", proposal, "committed", actor_id, "booking_commit_approved",
                           lab_ids=labs, source_ids=receipt["booking_ids"])
    plan = repo.get_record("ExperimentPlan", proposal["plan_id"])
    _transition(repo, "ExperimentPlan", plan, "committed", actor_id, "plan_state", lab_ids=labs)
    audit.record(repo, actor_id, "booking_commit", "ReservationProposal", proposal_id, request_id=proposal["request_id"],
                 before={"writes": [w["before"] for w in plan_result["writes"]]},
                 after={"writes": [w["after"] for w in plan_result["writes"]], "receipt_id": receipt["receipt_id"]},
                 lab_ids=labs, source_ids=receipt["booking_ids"])
    audit.record(repo, "system", "macro_signal", "ReservationProposal", proposal_id, request_id=proposal["request_id"],
                 after={"booking_ids": receipt["booking_ids"]}, lab_ids=labs,
                 detail="Stage 1 commit available to department snapshot")
    return _ok(repo, receipt=receipt, changes=plan_result["writes"], replayed=False,
               source_record_ids=[proposal_id] + receipt["booking_ids"])


# ---------------------------------------------------------------- department

def _require_admin(repo, actor_id, operation):
    actor = _actor(repo, actor_id)
    if actor is None or actor.get("role") not in ADMIN_ROLES:
        return _deny(repo, actor_id, operation, "Department", "dept_life_sciences_demo")
    return None


def _snapshot_id(repo):
    from .audit import digest
    bookings = sorted((b["booking_id"], str(b.get("version")), b["start_local"]) for b in repo.list_records("Booking"))
    orders = sorted((o["order_id"], o["state"], str(o["quantity"])) for o in repo.list_records("OrderProposal"))
    return "snap_%s" % digest([bookings, orders])


def dept_get_snapshot(repo, actor_id, week_start):
    """Permission-filtered department aggregates for one week. Department admins only. Read only.

    Args:
        actor_id (str): a department admin.
        week_start (str): Monday, e.g. "2026-11-02".
    Returns:
        {"status": "ok", "snapshot_id", "week_start", "utilization": [...], "open_proposals": {state: n},
         "open_orders": [{"sku_id", "lab_id", "quantity", "state"}], "restricted_signals_count": n}
        Funding details are never included; only a count of restricted planning signals.
    """
    denied = _require_admin(repo, actor_id, "dept_get_snapshot")
    if denied:
        return denied
    instruments = repo.list_records("Instrument")
    bookings = repo.list_records("Booking")
    maint = repo.list_records("MaintenanceWindow")
    util = [weekly_utilization(bookings, i, week_start, maint) for i in instruments]
    proposals = {}
    for p in repo.list_records("ReservationProposal"):
        proposals[p["state"]] = proposals.get(p["state"], 0) + 1
    orders = [{"order_id": o["order_id"], "sku_id": o["sku_id"], "lab_id": o["lab_id"],
               "quantity": as_num(o["quantity"]), "state": o["state"]}
              for o in repo.list_records("OrderProposal") if o["state"] not in ("rejected", "cancelled")]
    return _ok(repo, snapshot_id=_snapshot_id(repo), week_start=week_start, utilization=util,
               open_proposals=proposals, open_orders=orders,
               restricted_signals_count=len(repo.list_records("FundingHint")),
               source_record_ids=[i["instrument_id"] for i in instruments] + [o["order_id"] for o in orders])


def forecast_resource_demand(repo, actor_id, resource_id):
    """Baseline next-week demand forecast with backtest error; stores a ForecastRun. Admin only.

    Args:
        actor_id (str): a department admin.
        resource_id (str): instrument id.
    Returns:
        {"status": "ok", "forecast_run_id", "forecast": {model_kind, predicted_hours, low, high, mae,
         method_comparison, backtest, interval_label, ...}}
    """
    denied = _require_admin(repo, actor_id, "forecast_resource_demand")
    if denied:
        return denied
    demand = repo.list_records("WeeklyDemand")
    rows = sorted((r for r in demand if r["resource_id"] == resource_id), key=lambda r: r["week_start"])
    if len(rows) < 4:
        return _err("INSUFFICIENT_HISTORY", "At least 4 weeks of history are needed.")
    from datetime import timedelta
    next_week = (to_dt(rows[-1]["week_start"] + "T00:00:00-05:00").date() + timedelta(days=7)).isoformat()
    inst = repo.get_record("Instrument", resource_id)
    known = weekly_utilization(repo.list_records("Booking"), inst, next_week, repo.list_records("MaintenanceWindow"))
    result = forecast_resource(demand, resource_id, _policies(repo), known_booked_hours=known["booked_hours"])
    run = dict(result, forecast_run_id=repo.next_id("fc"), forecast_week=next_week, generated_at=repo.now(),
               known_booked_hours=known["booked_hours"])
    repo.save_record("ForecastRun", run)
    audit.record(repo, actor_id, "forecast_resource_demand", "ForecastRun", run["forecast_run_id"],
                 after={"predicted_hours": run["predicted_hours"], "mae": run["mae"]}, source_ids=[resource_id])
    return _ok(repo, forecast_run_id=run["forecast_run_id"], forecast=run,
               assumptions=["weighted baseline, not ML", "six weeks of synthetic history"],
               source_record_ids=[resource_id] + [r["demand_id"] for r in rows])


def _gaps(repo, week_start):
    return find_utilization_gaps(repo.list_records("Booking"), repo.list_records("Instrument"),
                                 repo.list_records("Person"), week_start, repo.list_records("MaintenanceWindow"),
                                 repo.list_records("WeeklyDemand"), _policies(repo))


def _pooled_insights(repo):
    skus = _index(repo.list_records("SupplySku"), "sku_id")
    result = find_shared_materials(repo.list_records("OrderProposal"), skus, repo.list_records("Lab"), _policies(repo))
    snap = _snapshot_id(repo)
    insights = [{
        "insight_id": "ins_%s" % pool["pool_id"], "kind": "pooled_order", "input_snapshot_id": snap,
        "candidate_ids": pool["order_ids"], "lab_ids": pool["lab_ids"], "estimate": pool["savings"],
        "units": "USD (potential, not realized)", "required_approvals": pool["required_approvals"],
        "assumptions": pool["assumptions"], "realized_savings_usd": None,
        "detail": {k: pool[k] for k in ("sku_id", "vendor_id", "ship_to", "quantities_by_lab")}}
        for pool in result["pools"]]
    return insights, result["exclusions"]


def _overload_insights(repo, week_start):
    snap = _snapshot_id(repo)
    return [{
        "insight_id": "ins_overload_%s_%s_%s" % (plan["source"], plan["target"], week_start.replace("-", "")),
        "kind": "overload_rebalance", "input_snapshot_id": snap, "week_start": week_start,
        "candidate_ids": [m["booking_id"] for m in plan["moves"]],
        "lab_ids": sorted({m["lab_id"] for m in plan["moves"]}), "estimate": plan,
        "units": "hours of congestion relieved (not money)",
        "required_approvals": plan["required_approvals"] + ["dept_admin"],
        "assumptions": ["same session times on the equivalent instrument", "owner approval required per booking"]}
        for plan in _gaps(repo, week_start)["overloads"]]


def _underuse_insights(repo, week_start):
    snap = _snapshot_id(repo)
    return [{
        "insight_id": "ins_underuse_%s_%s" % (u["resource_id"], week_start.replace("-", "")),
        "kind": "underuse", "input_snapshot_id": snap, "week_start": week_start,
        "candidate_ids": [u["resource_id"]], "lab_ids": [], "estimate": u, "units": "share of staffed hours",
        "required_approvals": ["dept_admin"], "assumptions": [u["caveat"]]}
        for u in sorted(_gaps(repo, week_start)["underused"], key=lambda u: (u["utilization"], u["resource_id"]))
        if u["persistent"]]


def _with_state(repo, insight):
    """Attach the workflow state: `detected` unless a person already took it further."""
    stored = repo.get_record("DepartmentInsight", insight["insight_id"])
    return dict(insight, state=stored["state"] if stored else "detected")


def insight_find_pooled_orders(repo, actor_id):
    """Detect cross-lab shared-purchase opportunities from current order proposals. Admin only. Read only.

    Args:
        actor_id (str): a department admin.
    Returns:
        {"status": "ok", "insights": [{insight_id, kind: "pooled_order", estimate: {potential_savings_usd,
         unpooled_total_usd, pooled_total_usd, volume_component_usd, shipping_component_usd, formula},
         units: "USD (potential, not realized)", required_approvals, assumptions, state}],
         "exclusions": [{sku_id, order_ids, reason}]}
    """
    denied = _require_admin(repo, actor_id, "insight_find_pooled_orders")
    if denied:
        return denied
    insights, exclusions = _pooled_insights(repo)
    return _ok(repo, insights=[_with_state(repo, i) for i in insights], exclusions=exclusions,
               snapshot_id=_snapshot_id(repo), source_record_ids=[c for i in insights for c in i["candidate_ids"]])


def insight_find_overloads(repo, actor_id, week_start):
    """Detect overloaded instruments and concrete, qualified, buffer-safe booking moves to an
    equivalent instrument. Admin only. Read only: moves nothing.

    Args:
        actor_id (str), week_start (str): Monday, e.g. "2026-11-02".
    Returns:
        {"status": "ok", "insights": [{insight_id, kind: "overload_rebalance", estimate: {movable_hours,
         before, after, total_hours_before, total_hours_after, moves, excluded}, units: "hours", state}]}
    """
    denied = _require_admin(repo, actor_id, "insight_find_overloads")
    if denied:
        return denied
    insights = _overload_insights(repo, week_start)
    return _ok(repo, insights=[_with_state(repo, i) for i in insights], snapshot_id=_snapshot_id(repo),
               source_record_ids=[c for i in insights for c in i["candidate_ids"]])


def insight_find_underuse(repo, actor_id, week_start):
    """Detect persistently underused instruments and matching overflow demand. Admin only. Read only.
    Advisory: never recommends selling or buying from one week of data. Ranked lowest utilization first.

    Args:
        actor_id (str), week_start (str): Monday, e.g. "2026-11-02".
    Returns:
        {"status": "ok", "insights": [{insight_id, kind: "underuse", estimate: {utilization, booked_hours,
         available_hours, history, low_weeks, overflow_sources, caveat}, units: "share of staffed hours", state}]}
    """
    denied = _require_admin(repo, actor_id, "insight_find_underuse")
    if denied:
        return denied
    insights = _underuse_insights(repo, week_start)
    return _ok(repo, insights=[_with_state(repo, i) for i in insights], snapshot_id=_snapshot_id(repo),
               source_record_ids=[c for i in insights for c in i["candidate_ids"]])


def insight_propose_action(repo, actor_id, insight_id, week_start=None):
    """Turn a currently detected insight into a proposed action awaiting approvals. Admin only.
    Proposal only: no order, booking or visibility change happens; impacted lab owners keep authority.
    The insight is recomputed from live data first, and its evidence is frozen on the stored record.

    Args:
        actor_id (str): a department admin.
        insight_id (str): from one of the insight_find_* tools.
        week_start (str, optional): the week used for overload/underuse insights.
    Returns:
        {"status": "ok", "insight_id", "state": "pending_approvals", "approvals": [...]}
        Errors: NOT_FOUND (not detected in current data), INVALID_TRANSITION (already proposed).
    """
    denied = _require_admin(repo, actor_id, "insight_propose_action")
    if denied:
        return denied
    if repo.get_record("DepartmentInsight", insight_id):
        return _err("INVALID_TRANSITION", "This insight was already proposed.",
                    state=repo.get_record("DepartmentInsight", insight_id)["state"])
    current = _pooled_insights(repo)[0]
    if week_start:
        current += _overload_insights(repo, week_start) + _underuse_insights(repo, week_start)
    insight = next((i for i in current if i["insight_id"] == insight_id), None)
    if insight is None:
        return _err("NOT_FOUND", "That insight is not detected in the current data. Run the finder again.")
    labs = insight.get("lab_ids", [])
    insight = dict(insight, state="detected", detected_at=repo.now(), proposed_by=actor_id)
    repo.save_record("DepartmentInsight", insight)
    audit.record(repo, actor_id, "insight_detected", "DepartmentInsight", insight_id,
                 after={"estimate": insight["estimate"], "units": insight["units"]},
                 source_ids=insight["candidate_ids"], lab_ids=labs)
    for target, op in (("reviewed", "insight_reviewed"), ("action_proposed", "insight_propose_action"),
                       ("pending_approvals", "insight_await_approvals")):
        insight = _transition(repo, "DepartmentInsight", insight, target, actor_id, op, lab_ids=labs)
    records = approval_store.open_requests(repo, "DepartmentInsight", insight_id, insight_slots(insight), actor_id)
    return _ok(repo, insight_id=insight_id, state=insight["state"], approvals=records,
               assumptions=["approving records consent only; nothing is purchased or moved automatically"],
               source_record_ids=[insight_id] + insight["candidate_ids"])


# ---------------------------------------------------------------- audit

def audit_get_activity(repo, actor_id, request_id=None, entity_id=None):
    """Audit events for a request or entity, scoped to what the actor may see. Read only.

    Department admins see everything; others see events for their own lab or that they took part in.

    Args:
        actor_id (str), request_id (str, optional), entity_id (str, optional).
    Returns:
        {"status": "ok", "events": [{audit_id, actor_id, operation, entity_kind, entity_id, before, after,
         status, created_at, ...}]} oldest first.
    """
    actor = _actor(repo, actor_id)
    if actor is None:
        return _err("UNKNOWN_ACTOR", "Unknown actor.")
    events = repo.list_records("AuditEvent")
    if request_id:
        events = [e for e in events if e["request_id"] == request_id]
    if entity_id:
        events = [e for e in events if e["entity_id"] == entity_id or entity_id in e["source_ids"]]
    if actor.get("role") not in ADMIN_ROLES:
        events = [e for e in events if e["actor_id"] == actor_id or actor["lab_id"] in e["lab_ids"]]
    events.sort(key=lambda e: (e["created_at"], e["audit_id"]))
    return _ok(repo, events=events, source_record_ids=[e["audit_id"] for e in events])
