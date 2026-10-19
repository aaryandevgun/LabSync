"""JSON API for the web app: thin view-models over the orchestrator, tools and queries.

Every write goes through the same orchestrator methods the CLI uses, so the tools still enforce who
may do what. The persona header is a simulated identity for the local demo (labelled in the UI);
it picks the actor, and the tools check that actor's permissions exactly as they would a real login.
Reads that the tools restrict (department data, other labs' details) are passed through as the
tools return them, errors included.
"""
import re
import threading

from labsync_tools import queries
from labsync_tools import tools as T

DEMO_WEEK = "2026-11-02"
DEFAULT_PERSONA = "morgan"
CONFOCALS = ("confocal_1", "confocal_2")
HISTORY_RESOURCES = ("confocal_1", "confocal_2", "flow_1", "flow_2")
HELD = ("draft", "submitted", "owner_approval_pending", "requester_approval_pending", "authorized")


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _hm(ts):
    return ts[11:16] if ts else None


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _http_status(result):
    """Map a tool error code to an HTTP status. The JSON body always carries the code."""
    if result.get("status") != "error":
        return 200
    code = result.get("code", "")
    if code in ("PERMISSION_DENIED", "UNAUTHORIZED", "UNAUTHORIZED_APPROVAL", "RESET_NOT_ALLOWED"):
        return 403
    if code in ("NOT_FOUND", "UNKNOWN_ACTOR"):
        return 404
    if code == "LLM_UNAVAILABLE":
        return 503
    return 409


class WebAPI:
    def __init__(self, orchestrator, mode="mock"):
        self.o = orchestrator
        self.repo = orchestrator.repo
        self.mode = mode
        self.lock = threading.RLock()
        self.routes = [
            ("GET", r"/api/session", self.session),
            ("GET", r"/api/home", self.home),
            ("POST", r"/api/requests", self.submit_request),
            ("GET", r"/api/plans/(?P<plan_id>[\w-]+)", self.plan),
            ("POST", r"/api/plans/(?P<plan_id>[\w-]+)/revise", self.revise_plan),
            ("POST", r"/api/plans/(?P<plan_id>[\w-]+)/hold", self.hold),
            ("POST", r"/api/plans/(?P<plan_id>[\w-]+)/orders", self.draft_orders),
            ("POST", r"/api/proposals/(?P<proposal_id>[\w-]+)/request-moves", self.request_moves),
            ("POST", r"/api/proposals/(?P<proposal_id>[\w-]+)/commit", self.commit),
            ("GET", r"/api/approvals", self.approvals),
            ("POST", r"/api/approvals/(?P<approval_id>[\w-]+)/decide", self.decide),
            ("GET", r"/api/calendar", self.calendar),
            ("GET", r"/api/department", self.department),
            ("POST", r"/api/department/review", self.review_department),
            ("POST", r"/api/insights/(?P<insight_id>[\w-]+)/propose", self.propose_insight),
            ("GET", r"/api/activity", self.activity),
            ("POST", r"/api/reset", self.reset),
        ]

    # ------------------------------------------------------------ dispatch
    def handle(self, method, path, query=None, body=None, persona=None):
        """Returns (http_status, payload). Never raises for expected errors."""
        query, body = query or {}, body or {}
        for verb, pattern, fn in self.routes:
            match = re.fullmatch(pattern, path)
            if match and verb == method:
                try:
                    with self.lock:
                        actor = self._persona(persona)
                        result = fn(actor, query=query, body=body, **match.groupdict())
                except ApiError as exc:
                    return exc.status, {"status": "error", "code": exc.code, "message": exc.message}
                return _http_status(result), result
        return 404, {"status": "error", "code": "NO_ROUTE", "message": "No such endpoint."}

    def _persona(self, persona):
        actor = persona or DEFAULT_PERSONA
        if self.repo.get_record("Person", actor) is None:
            raise ApiError(400, "UNKNOWN_PERSONA", "Unknown demo persona.")
        return actor

    # ------------------------------------------------------------ names
    def _person(self, person_id):
        p = self.repo.get_record("Person", person_id) or {}
        return (p.get("display_name") or person_id or "").replace(" (synthetic)", "")

    def _resource_name(self, resource_id):
        r = self.repo.get_record("Instrument", resource_id) or self.repo.get_record("Room", resource_id)
        return r["name"] if r else resource_id

    def _lab_name(self, lab_id):
        lab = self.repo.get_record("Lab", lab_id)
        return lab["name"] if lab else lab_id

    def _sku_name(self, sku_id):
        sku = self.repo.get_record("SupplySku", sku_id)
        return sku["name"] if sku else sku_id

    # ------------------------------------------------------------ session / home
    def session(self, actor, **_):
        dept = self.repo.list_records("Department")[0]
        people = []
        for p in self.repo.list_records("Person"):
            people.append({"id": p["person_id"], "name": self._person(p["person_id"]), "role": p["role"],
                           "lab_id": p["lab_id"] or None, "lab_name": self._lab_name(p["lab_id"]) if p["lab_id"] else None})
        me = next(p for p in people if p["id"] == actor)
        waiting = queries.list_approval_queue(self.repo, actor)["waiting_on_me"]
        return {"status": "ok", "persona": me, "personas": people, "is_admin": me["role"] in T.ADMIN_ROLES,
                "mode": getattr(self.o.client, "name", self.mode), "model": getattr(self.o.client, "model", None),
                "c3_connected": False, "synthetic": True, "now": self.repo.now(), "demo_week": DEMO_WEEK,
                "department": dept["name"], "building": dept["building_name"], "waiting_count": len(waiting),
                "resource_names": {r.get("instrument_id") or r["room_id"]: r["name"]
                                   for r in self.repo.list_records("Instrument") + self.repo.list_records("Room")}}

    def _plan_summary(self, plan):
        proposals = [p for p in self.repo.list_records("ReservationProposal") if p["plan_id"] == plan["plan_id"]]
        latest = proposals[-1] if proposals else None
        return {"plan_id": plan["plan_id"], "request_id": plan["request_id"], "state": plan["state"],
                "stage": _stage(plan, latest), "goal": plan["goal"]["goalSummary"],
                "day": (plan["goal"].get("desiredStart") or "")[:10] or None, "created_at": plan["created_at"],
                "proposal_state": latest["state"] if latest else None}

    def home(self, actor, **_):
        me = self.repo.get_record("Person", actor)
        plans = [p for p in self.repo.list_records("ExperimentPlan") if p["lab_id"] == me["lab_id"]] if me["lab_id"] else []
        latest = {}
        for p in plans:  # a revised plan replaces the earlier draft for the same request
            latest[p["request_id"]] = p
        rows = sorted((self._plan_summary(p) for p in latest.values()), key=lambda r: r["created_at"], reverse=True)
        notes = queries.list_notifications(self.repo, actor)["notifications"]
        waiting = queries.list_approval_queue(self.repo, actor)["waiting_on_me"]
        return {"status": "ok", "lab_name": self._lab_name(me["lab_id"]) if me["lab_id"] else None,
                "plans": rows, "notifications": notes[:5], "waiting": [self._approval_card(c, actor) for c in waiting]}

    # ------------------------------------------------------------ Stage 1
    def submit_request(self, actor, body, **_):
        text = (body.get("text") or "").strip()
        if not text:
            raise ApiError(400, "EMPTY_REQUEST", "Describe what you are trying to run.")
        result = self.o.submit_request(actor, text)
        if result["status"] != "ok":
            return result
        steps = [c["name"] for c in result["run"]["tool_calls"]]
        return {"status": "ok", "plan_id": result["plan_id"], "agent_text": result["agent_text"],
                "needs_input": result["needs_input"], "run_id": result["run"]["run_id"], "tool_calls": steps}

    def _check_plan(self, actor, plan_id):
        result = queries.get_plan(self.repo, actor, plan_id)
        if result["status"] != "ok":
            raise ApiError(_http_status(result), result["code"], result["message"])
        return result

    def plan(self, actor, plan_id, **_):
        got = self._check_plan(actor, plan_id)
        plan, proposals = got["plan"], got["proposals"]
        latest = proposals[-1] if proposals else None
        goal = plan["goal"]
        search = None
        if plan["scheduling_request"] and plan["state"] in ("draft", "options_ready", "needs_revision"):
            search = T.scheduler_find_slots(self.repo, actor, plan_id)
        quote = None
        items = [{"sku_id": s["skuId"], "quantity": s["quantity"]} for s in goal["supplies"]]
        if items:
            quote = T.supply_quote(self.repo, actor, items, goal.get("desiredStart"))
        day = (goal.get("desiredStart") or "")[:10] or None
        resources = self._timeline_resources(search, latest)
        rows = queries.get_calendar(self.repo, actor, resources, day)["rows"] if day and resources else []
        approvals = sorted(latest["approvals"], key=lambda a: a.get("slot_order", 0)) if latest else []
        earlier_ok = True
        for a in approvals:
            record = self.repo.get_record("Approval", a["approval_id"])
            a["slot_order"] = record["slot_order"]
            a["approver_name"] = self._person(a["approver_id"])
            a["reason"] = record.get("reason")
            a["your_turn"] = a["status"] == "pending" and earlier_ok and a["approver_id"] == actor
            earlier_ok = earlier_ok and a["status"] == "decided" and a["decision"] == "approve"
        return {"status": "ok", "plan": plan, "stage": _stage(plan, latest), "goal": goal,
                "requester_name": self._person(plan["requester_id"]), "lab_name": self._lab_name(plan["lab_id"]),
                "search": search, "proposal": latest,
                "previous_proposals": [{"proposal_id": p["proposal_id"], "state": p["state"]} for p in proposals[:-1]],
                "approvals": approvals, "orders": got["orders"], "quote": quote,
                "timeline": {"day": day, "resources": [self._resource_info(r) for r in resources], "rows": rows,
                             "maintenance": [m for m in self.repo.list_records("MaintenanceWindow")
                                             if m["resource_id"] in resources and m["start_local"][:10] == day]},
                "receipt": self._receipt(latest), "commit_blockers": _commit_blockers(latest, approvals),
                "is_requester": plan["requester_id"] == actor}

    def _timeline_resources(self, search, proposal):
        ids = []
        if search and search.get("status") == "ok":
            for opt in search["options"]:
                ids += [opt["resource_id"]] + ([opt["prep"]["resource_id"]] if opt.get("prep") else [])
            ids += [b["resource_id"] for b in search.get("blocked_alternatives", [])]
        if proposal:
            ids += [h["resource_id"] for h in proposal.get("creates", [])]
        if not ids:
            ids = list(CONFOCALS)
        seen = []
        for r in ids:
            if r not in seen:
                seen.append(r)
        return sorted(seen, key=lambda r: (self.repo.get_record("Room", r) is not None, r))

    def _resource_info(self, resource_id):
        inst = self.repo.get_record("Instrument", resource_id)
        r = inst or self.repo.get_record("Room", resource_id) or {}
        return {"id": resource_id, "name": r.get("name", resource_id), "type": "instrument" if inst else "room",
                "buffer_minutes": int(_num(r.get("buffer_minutes"))), "open": r.get("open_local", "09:00"),
                "close": r.get("close_local", "17:00"),
                "required_qualifications": [q for q in (r.get("required_qualifications") or "").split(";") if q]}

    def _receipt(self, proposal):
        if not proposal or proposal["state"] != "committed":
            return None
        for r in self.repo.list_records("CommitReceipt"):
            if r["receipt"]["proposal_id"] == proposal["proposal_id"]:
                return r["receipt"]
        return None

    def revise_plan(self, actor, plan_id, body, **_):
        self._check_plan(actor, plan_id)
        return self.o.revise_plan(actor, plan_id, body.get("edits") or {})

    def hold(self, actor, plan_id, body, **_):
        self._check_plan(actor, plan_id)
        if not body.get("option_id"):
            raise ApiError(400, "MISSING_OPTION", "Choose an option to hold.")
        return self.o.choose_option(actor, plan_id, body["option_id"])

    def draft_orders(self, actor, plan_id, **_):
        self._check_plan(actor, plan_id)
        return self.o.draft_orders(actor, plan_id)

    def request_moves(self, actor, proposal_id, body, **_):
        proposal = self.repo.get_record("ReservationProposal", proposal_id)
        if proposal is None:
            raise ApiError(404, "NOT_FOUND", "Unknown proposal.")
        if proposal["requester_id"] != actor:
            raise ApiError(403, "PERMISSION_DENIED", "Only the requester can ask an owner to move.")
        result = self.o.request_moves(actor, proposal_id, body.get("message"))
        for r in result.get("requests", []):
            r.pop("recommendation", None)  # the advice is for the owner, shown in their inbox
        return result

    def commit(self, actor, proposal_id, **_):
        return self.o.commit(actor, proposal_id)

    # ------------------------------------------------------------ approvals
    def _approval_card(self, card, actor):
        card = dict(card)
        record = self.repo.get_record("Approval", card["approval_id"])
        card["requested_by"] = record["requested_by"]
        card["requested_by_name"] = self._person(record["requested_by"])
        card["approver_name"] = self._person(card["approver_id"])
        card["reason"] = record.get("reason")
        card["decided_by_name"] = self._person(record["decided_by"]) if record.get("decided_by") else None
        kind = card["entity_kind"]
        if kind == "ReservationProposal":
            proposal = self.repo.get_record("ReservationProposal", card["entity_id"])
            card["resource_name"] = self._resource_name((card.get("impact") or {}).get("resource_id")
                                                        or (proposal["creates"][0]["resource_id"] if proposal.get("creates") else ""))
            card["plan_id"] = proposal["plan_id"]
            card["requester_lab"] = self._lab_name(proposal["lab_id"])
            if card["slot_kind"] == "owner_move":
                card["title"] = "%s requests moving your %s slot" % (self._person(record["requested_by"]),
                                                                   card["resource_name"])
                if actor == card["approver_id"]:
                    card["recommendation"] = self.o.recommendation_for(card["approval_id"])
            else:
                card["title"] = "Confirm your final schedule"
                card["held"] = proposal.get("creates", [])
        elif kind == "OrderProposal":
            order = self.repo.get_record("OrderProposal", card["entity_id"])
            card["title"] = "Proposed supply purchase: %s x%s" % (self._sku_name(order["sku_id"]), order["quantity"])
            card["order"] = {k: order.get(k) for k in ("order_id", "sku_id", "quantity", "unit_price_usd",
                                                       "shipping_usd", "need_by_date", "lab_id", "state")}
            card["order"]["estimated_total_usd"] = _num(order["quantity"]) * _num(order["unit_price_usd"]) + _num(order["shipping_usd"])
            card["order"]["sku_name"] = self._sku_name(order["sku_id"])
            card["note"] = "Request only: approving does not place an order, charge a grant or send anything."
        elif kind == "DepartmentInsight":
            insight = self.repo.get_record("DepartmentInsight", card["entity_id"])
            card["title"] = _insight_title(insight)
            card["insight"] = {"insight_id": insight["insight_id"], "kind": insight["kind"],
                               "estimate": insight["estimate"], "units": insight["units"],
                               "assumptions": insight["assumptions"]}
            card["note"] = "Approving records your consent only; nothing is purchased or moved automatically."
        return card

    def approvals(self, actor, **_):
        q = queries.list_approval_queue(self.repo, actor)
        return {"status": "ok", "data_timestamp": q["data_timestamp"],
                "waiting_on_me": [self._approval_card(c, actor) for c in q["waiting_on_me"]],
                "requested_by_me": [self._approval_card(c, actor) for c in q["requested_by_me"]],
                "history": [self._approval_card(c, actor) for c in reversed(q["history"])]}

    def decide(self, actor, approval_id, body, **_):
        decision = body.get("decision")
        reason = (body.get("reason") or "").strip() or None
        if body.get("suggested_time"):  # "Suggest a different time" = reject with the owner's proposal
            decision = "reject"
            reason = "Suggested another time: %s%s" % (body["suggested_time"], (". " + reason) if reason else "")
        return self.o.decide(actor, approval_id, decision, reason)

    # ------------------------------------------------------------ calendar
    def calendar(self, actor, query, **_):
        day = query.get("day") or "2026-11-03"
        ids = [r for r in (query.get("resources") or "").split(",") if r] or list(CONFOCALS)
        result = queries.get_calendar(self.repo, actor, ids, day)
        if result["status"] == "ok":
            result["resources"] = [self._resource_info(r) for r in ids]
        return result

    # ------------------------------------------------------------ Stage 2
    def department(self, actor, query, **_):
        week = query.get("week") or DEMO_WEEK
        snapshot = T.dept_get_snapshot(self.repo, actor, week)
        if snapshot["status"] != "ok":
            return snapshot
        pooled = T.insight_find_pooled_orders(self.repo, actor)
        overloads = T.insight_find_overloads(self.repo, actor, week)
        underuse = T.insight_find_underuse(self.repo, actor, week)
        detected = {i["insight_id"]: i for r in (pooled, overloads, underuse) for i in r["insights"]}
        for stored in self.repo.list_records("DepartmentInsight"):
            if stored["insight_id"] in detected:
                detected[stored["insight_id"]]["state"] = stored["state"]
        for insight in detected.values():
            approvals = [a for a in self.repo.list_records("Approval") if a["entity_id"] == insight["insight_id"]]
            insight["approvals"] = [{"approver_id": a["approver_id"], "approver_name": self._person(a["approver_id"]),
                                     "status": a["status"], "decision": a["decision"], "decided_at": a["decided_at"]}
                                    for a in sorted(approvals, key=lambda a: a["slot_order"])]
        runs = [r for r in self.repo.list_records("AgentRun") if r["agent"] == "department_optimizer"]
        review = None
        if runs:
            run = runs[-1]
            review = {"run_id": run["run_id"], "output": run["output"], "text": run["final_text"],
                      "errors": run["output_errors"], "finished_at": run.get("finished_at"), "mode": run.get("mode"),
                      "model": run.get("model"), "tool_calls": [c["name"] for c in run["tool_calls"]]}
        forecasts = {}
        for f in self.repo.list_records("ForecastRun"):
            if f["resource_id"] in CONFOCALS:
                forecasts[f["resource_id"]] = f
        history = {}
        for row in self.repo.list_records("WeeklyDemand"):
            if row["resource_id"] in HISTORY_RESOURCES:
                history.setdefault(row["resource_id"], []).append(
                    {"week_start": row["week_start"], "requested_hours": _num(row["requested_hours"]),
                     "booked_hours": _num(row["booked_hours"]), "staffed_hours": _num(row["staffed_hours"])})
        for rows in history.values():
            rows.sort(key=lambda r: r["week_start"])
        names = {u["resource_id"]: self._resource_name(u["resource_id"]) for u in snapshot["utilization"]}
        return {"status": "ok", "week": week, "snapshot": snapshot, "names": names, "insights": detected,
                "exclusions": pooled.get("exclusions", []), "review": review, "forecasts": forecasts,
                "history": history, "lab_names": {l["lab_id"]: l["name"] for l in self.repo.list_records("Lab")},
                "people": {p["person_id"]: self._person(p["person_id"]) for p in self.repo.list_records("Person")}}

    def review_department(self, actor, body, **_):
        week = body.get("week") or DEMO_WEEK
        result = self.o.review_department(actor, week)
        if result.get("code") in ("PERMISSION_DENIED", "LLM_UNAVAILABLE"):
            return result
        if result["status"] == "ok":
            for resource in CONFOCALS:
                T.forecast_resource_demand(self.repo, actor, resource)
        return result

    def propose_insight(self, actor, insight_id, body, **_):
        return self.o.propose_insight(actor, insight_id, body.get("week") or DEMO_WEEK)

    # ------------------------------------------------------------ activity
    def activity(self, actor, query, **_):
        request_id, entity_id = query.get("request_id"), query.get("entity_id")
        if not request_id and not entity_id:
            raise ApiError(400, "MISSING_SUBJECT", "Pass request_id or entity_id.")
        result = self.o.activity(actor, request_id=request_id, entity_id=entity_id)
        if result["status"] != "ok":
            return result
        events = result["events"]
        for e in events:
            e["actor_name"] = self._person(e["actor_id"]) if e["actor_id"] != "system" else "LabSync"
            e["label"] = _event_label(e)
        result["runs"] = self._runs_for(actor, request_id, events)
        return result

    def _runs_for(self, actor, request_id, events):
        """Agent runs behind a request: tool names, ids and timestamps; never hidden reasoning."""
        entity_ids = {e["entity_id"] for e in events}
        approval_ids = {a["approval_id"] for a in self.repo.list_records("Approval")
                        if request_id and a.get("request_id") == request_id}
        runs = []
        for run in self.repo.list_records("AgentRun"):
            related = run.get("subject_id") in approval_ids or any(
                (c.get("result") or {}).get("plan_id") in entity_ids for c in run["tool_calls"])
            if not related:
                continue
            if run["agent"] == "conflict_negotiator" and run["actor_id"] != actor:
                person = self.repo.get_record("Person", actor)
                if person.get("role") not in T.ADMIN_ROLES:
                    continue  # the owner's advice stays with the owner
            runs.append({"run_id": run["run_id"], "agent": run["agent"], "actor_id": run["actor_id"],
                         "mode": run.get("mode"), "model": run.get("model"), "status": run["status"],
                         "started_at": run["started_at"], "finished_at": run.get("finished_at"),
                         "tool_calls": [{"name": c["name"], "result": c["result"]} for c in run["tool_calls"]]})
        return runs

    # ------------------------------------------------------------ demo controls
    def reset(self, actor, body, **_):
        return self.o.reset(actor, body.get("token"))


def _stage(plan, proposal):
    """Draft -> Pending approvals -> Ready -> Confirmed (docs/07 plan header)."""
    if plan["state"] == "committed":
        return "confirmed"
    if plan["state"] in ("failed",):
        return "failed"
    if plan["state"] == "needs_revision":
        return "needs_revision"
    if proposal and proposal["state"] == "authorized":
        return "ready"
    if proposal and proposal["state"] in HELD:
        return "pending_approvals"
    return "draft"


def _commit_blockers(proposal, approvals):
    if proposal is None:
        return ["Hold an option first."]
    if proposal["state"] == "committed":
        return []
    if proposal["state"] in ("rejected", "stale", "failed"):
        return ["This proposal is %s; choose another option." % proposal["state"]]
    out = []
    for a in approvals:
        if a["status"] == "decided" and a["decision"] == "approve":
            continue
        if a["status"] == "not_sent":
            out.append("%s hasn't been asked yet." % a["approver_name"])
        elif a["status"] == "pending":
            out.append("Waiting on %s." % a["approver_name"])
        elif a["decision"] == "reject":
            out.append("%s rejected." % a["approver_name"])
    return out


def _insight_title(insight):
    est = insight["estimate"]
    if insight["kind"] == "pooled_order":
        return "Shared order: %s across %d labs (potential $%s)" % (
            insight["detail"]["sku_id"], len(insight["lab_ids"]), est["potential_savings_usd"])
    if insight["kind"] == "overload_rebalance":
        return "Move %s flexible hours from %s to %s" % (est["movable_hours"], est["source"], est["target"])
    return "Publish spare capacity on %s (%d%% used)" % (est["resource_id"], round(est["utilization"] * 100))


EVENT_LABELS = {
    "plan_create_draft": "Plan generated", "booking_propose": "Option chosen and proposal drafted",
    "booking_hold": "Slots held (not booked)", "liaison_request_change": "Change requested from the owner",
    "booking_commit": "Bookings committed", "booking_commit_approved": "Commit approved",
    "supply_create_order_draft": "Supply request drafted", "macro_signal": "Shared with the department view",
    "insight_detected": "Insight recorded", "insight_reviewed": "Insight reviewed",
    "insight_propose_action": "Action proposed", "insight_await_approvals": "Waiting for approvals",
    "forecast_resource_demand": "Forecast computed", "reset_demo": "Demo reset",
    "booking_commit_compensated": "Commit undone after a failure",
}
STATE_WORDS = {
    "owner_approval_pending": "waiting for the owner", "requester_approval_pending": "waiting for the requester",
    "authorized": "ready to commit", "approval_pending": "waiting for approvals", "ready_to_commit": "ready to commit",
    "needs_revision": "needs a new option", "options_ready": "option chosen", "awaiting_lab_approval": "awaiting lab approval",
    "awaiting_fund_approval": "awaiting fund authorization", "approved_request": "approved request (not ordered)",
    "pending_approvals": "waiting for approvals",
}


def _event_label(e):
    op, after = e["operation"], e.get("after") or {}
    if op == "approval_record":
        label = "Approved" if after.get("decision") == "approve" else "Rejected"
    elif "state" in after and op not in EVENT_LABELS:
        label = "%s now %s" % (e["entity_kind"].replace("ReservationProposal", "Proposal").replace(
            "ExperimentPlan", "Plan").replace("OrderProposal", "Order").replace("DepartmentInsight", "Insight"),
            STATE_WORDS.get(after["state"], after["state"].replace("_", " ")))
    else:
        label = EVENT_LABELS.get(op, op.replace("_", " ").capitalize())
    if e["status"] != "ok":
        label += " (%s)" % e["status"]
    return label
