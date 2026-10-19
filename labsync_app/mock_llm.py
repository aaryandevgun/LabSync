"""Deterministic offline stand-in for the LLM, speaking the same message protocol as the live client.

It is a rule-based agent, not a model:
  * Lab Agent: uses the known answer for the few-shot and eval sentences, falls back to keyword
    rules (mock_parse) for other requests, and otherwise asks for the missing details. Then it
    calls the same tools a model would.
  * Conflict Negotiator: reads the change request and applies fixed rules to the tool's facts.
  * Department Optimizer: calls the snapshot and the three finders, then fills card templates
    with the tool's own numbers.
Scores from mock mode test the harness and the tools; they say nothing about a model's quality.
"""
import json
import os
import re

from labsync_core.values import to_dt

from . import mock_parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBMIT = "submit_output"


def _norm(text):
    return re.sub(r"\s+", " ", text.strip().lower())


def _known_parses():
    """{(normalized text, actor_id): answer} from the agent few-shots and the intake eval references."""
    known = {}
    with open(os.path.join(ROOT, "agents", "lab_agent", "few_shots.json"), encoding="utf-8") as fh:
        for shot in json.load(fh):
            known[(_norm(shot["input"]), shot["context"]["actor_id"])] = shot["output"]
    path = os.path.join(ROOT, "evals", "intake.jsonl")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                case = json.loads(line)
                known.setdefault((_norm(case["input"]), case["context"]["actor_id"]), case["reference"])
    return known


def _text(content):
    if isinstance(content, str):
        return content
    return " ".join(b.get("text", "") for b in content if b.get("type") == "text")


def _history(messages):
    """[(tool name, input, parsed result)] in call order."""
    calls, results = {}, {}
    order = []
    for m in messages:
        if isinstance(m["content"], str):
            continue
        for b in m["content"]:
            if b.get("type") == "tool_use":
                calls[b["id"]] = (b["name"], b["input"])
                order.append(b["id"])
            elif b.get("type") == "tool_result":
                try:
                    results[b["tool_use_id"]] = json.loads(b["content"])
                except (TypeError, ValueError):
                    results[b["tool_use_id"]] = {"status": "error", "message": b["content"]}
    return [(calls[i][0], calls[i][1], results.get(i)) for i in order]


def _pct(share):
    return "%g" % round(share * 100, 1)


def _hm(ts):
    return ts[11:16]


class MockClient:
    name = "mock"
    model = "mock-rules-v1"

    def __init__(self):
        self._known = _known_parses()
        self._n = 0

    # ---- protocol
    def complete(self, system, messages, tools, agent=None):
        history = _history(messages)
        user = _text(messages[0]["content"])
        handler = {"lab_agent": self._lab, "conflict_negotiator": self._negotiator,
                   "department_optimizer": self._optimizer}[agent]
        return handler(system, user, history)

    def _tool(self, name, arguments, text=None):
        self._n += 1
        content = ([{"type": "text", "text": text}] if text else []) + [
            {"type": "tool_use", "id": "mock_%d" % self._n, "name": name, "input": arguments}]
        return {"stop_reason": "tool_use", "content": content, "usage": {}, "model": self.model}

    def _say(self, text):
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": text}], "usage": {}, "model": self.model}

    # ---- Lab Agent
    def _lab(self, system, user, history):
        actor = re.search(r"Signed-in person: (\S+)", system).group(1)
        if not history:
            answer = self._known.get((_norm(user), actor))
            if answer is None:
                lab = re.search(r"Signed-in person: \S+ in lab (\S+?)\.?\s", system)
                now = re.search(r"Current time: (\S+?)\.?\s", system)
                if lab and now:
                    answer = mock_parse.parse(user, actor, lab.group(1), now.group(1))
            if answer is None:
                return self._say("I couldn't find an instrument or supply in that request. Name one (for example "
                                 "confocal, widefield, plate reader, centrifuge) with a day, time and duration.")
            if "response_kind" in answer:
                return self._say(answer.get("message", "What would you like to plan?"))
            return self._tool("plan_create_draft", {"parsed_goal": answer})
        name, _, result = history[-1]
        if name == "plan_create_draft":
            if result["status"] != "ok":
                return self._say("failed: the plan didn't pass validation (%s)." % "; ".join(result.get("errors", [])))
            if result["needs_input"]:
                return self._say("proposed (draft %s). I need: %s." % (result["plan_id"], ", ".join(result["needs_input"])))
            if result["scheduling_request"] is None:
                return self._say("proposed: draft %s saved with no instrument step. Supplies can be drafted as an order "
                                 "request when you're ready." % result["plan_id"])
            return self._tool("scheduler_find_slots", {"plan_id": result["plan_id"]})
        if name == "scheduler_find_slots":
            return self._say(self._options_text(history))
        return self._say("Done.")

    @staticmethod
    def _options_text(history):
        plan = next(r for n, _, r in history if n == "plan_create_draft")
        found = history[-1][2]
        if found["status"] != "ok":
            return "failed: %s" % found.get("message")
        lines = ["proposed: plan %s has %d option(s). Nothing is booked yet." % (plan["plan_id"], len(found["options"]))]
        for i, o in enumerate(found["options"], 1):
            move = ""
            if o["contingent_moves"]:
                m = o["contingent_moves"][0]
                move = "; needs %s to move %s to %s-%s" % (m["owner_id"], m["booking_id"], _hm(m["to"]["start"]),
                                                            _hm(m["to"]["end"]))
            prep = " after prep in %s %s-%s" % (o["prep"]["resource_id"], _hm(o["prep"]["start"]),
                                                 _hm(o["prep"]["end"])) if o["prep"] else ""
            lines.append("%d. %s %s %s %s-%s%s (score %g%s)" % (i, o["kind"], o["resource_id"], o["start"][:10],
                                                                _hm(o["start"]), _hm(o["end"]), prep, o["score"], move))
        for b in found["blocked_alternatives"]:
            lines.append("Blocked: %s (%s)" % (b["resource_id"], b["code"]))
        ready = found.get("supply_readiness")
        if ready:
            short = [i for i in ready["items"] if i["shortfall"]]
            if short:
                lines.append("Supplies to order: %s; last safe order date %s%s." % (
                    ", ".join("%s x%d" % (i["sku_id"], i["shortfall"]) for i in short), ready["last_safe_order_date"],
                    " (ORDER_TOO_LATE)" if ready.get("code") == "ORDER_TOO_LATE" else ""))
        return "\n".join(lines)

    # ---- Conflict Negotiator
    def _negotiator(self, system, user, history):
        if not history:
            match = re.search(r"\b(appr_\w+)", user)
            if not match:
                return self._say("Which move request should I review?")
            return self._tool("liaison_get_change_request", {"approval_id": match.group(1)})
        name, _, result = history[-1]
        if name == SUBMIT:
            return self._say("Recommendation ready for the owner to decide.")
        cr = next(r for n, _, r in history if n == "liaison_get_change_request")
        if cr["status"] != "ok":
            return self._say("You can't view this move request; it belongs to another lab or person.")
        if cr["state"] != "pending":
            return self._say("This request was already decided; there is nothing to recommend.")
        return self._tool(SUBMIT, recommend(cr))

    # ---- Department Optimizer
    def _optimizer(self, system, user, history):
        week = re.search(r"Week under review: (\d{4}-\d{2}-\d{2})", system).group(1)
        done = [n for n, _, _ in history]
        if history and history[-1][2] and history[-1][2].get("status") == "error" and history[-1][0] != SUBMIT:
            return self._say("Department insights are restricted to department admins; nothing was retrieved.")
        for name, args in (("dept_get_snapshot", {"week_start": week}), ("insight_find_pooled_orders", {}),
                           ("insight_find_overloads", {"week_start": week}),
                           ("insight_find_underuse", {"week_start": week})):
            if name not in done:
                return self._tool(name, args)
        if done[-1] == SUBMIT:
            return self._say("Three findings are ready for review; every value is a potential estimate.")
        results = {n: r for n, _, r in history}
        return self._tool(SUBMIT, build_cards(results, week))


def recommend(cr):
    """Fixed rules over the change request's facts (see conflict_negotiator/system_prompt.md)."""
    i = cr["impact"]
    rec, reasons, alternatives = "approve", [], []
    day_end = i["from"]["start"][:11] + "17:00:00" + i["from"]["start"][19:]
    if not i["flexible"]:
        rec = "reject"
        reasons = ["This session is not marked flexible, so it is not available to move.",
                   "Your booking stays as it is; the requester can pick another option."]
    elif i["person_conflicts"]:
        own = {b["booking_id"]: b for b in i["your_other_bookings_that_day"]}
        after = max(own[c]["end"] for c in i["person_conflicts"])
        length = to_dt(i["to"]["end"]) - to_dt(i["to"]["start"])
        reasons = ["The new time %s-%s overlaps your own session (%s)." % (
            _hm(i["to"]["start"]), _hm(i["to"]["end"]), ", ".join(i["person_conflicts"]))]
        if to_dt(day_end) - to_dt(after) >= length:
            rec = "suggest_other_time"
            alternatives = [{"earliestStart": after, "latestEnd": day_end,
                             "note": "Same day, after your session; unverified until re-searched"}]
            reasons.append("A slot after %s the same day would avoid it; the requester's scheduler must confirm it." % _hm(after))
        else:
            rec = "reject"
            reasons.append("No same-day window after your session is long enough.")
    elif not i["same_day"]:
        rec = "suggest_other_time"
        alternatives = [{"earliestStart": i["from"]["end"], "latestEnd": day_end,
                         "note": "Keep it on the original day; unverified until re-searched"}]
        reasons = ["The move pushes your session to another day.",
                   "Keeping it later the same day would preserve your schedule; the scheduler must confirm a slot."]
    else:
        reasons = ["You marked this session flexible.",
                   "It moves later the same day (%s-%s)%s." % (_hm(i["to"]["start"]), _hm(i["to"]["end"]),
                                                               " and keeps its length" if i["same_duration"] else ""),
                   "None of your own sessions overlap the new time."]
    return {"approvalId": cr["approval_id"], "bookingId": i["booking_id"], "recommendation": rec,
            "from": i["from"], "to": i["to"], "reasons": reasons,
            "ownerImpact": {"sameDay": i["same_day"], "sameDuration": i["same_duration"],
                            "personConflicts": i["person_conflicts"]},
            "alternatives": alternatives,
            "evidenceIds": [cr["approval_id"], i["booking_id"]] + list(i["person_conflicts"]),
            "dataTimestamp": cr["data_timestamp"], "decidedBy": "owner"}


def _lab_name(lab_id):
    return lab_id.replace("lab_", "").capitalize()


def _pooled_card(ins, exclusions):
    e, d = ins["estimate"], ins["detail"]
    qty = ", ".join("%s %d" % (_lab_name(l), q) for l, q in sorted(d["quantities_by_lab"].items()))
    return {
        "insightId": ins["insight_id"], "kind": "pooled_order",
        "headline": "Combine the %s orders for %s" % (" and ".join(_lab_name(l) for l in ins["lab_ids"]), d["sku_id"]),
        "evidenceSentence": "Open orders (%s) are for the same item from the same vendor, shipping to %s." % (qty, d["ship_to"]),
        "summary": ("Ordering %d together reaches the $%g volume price: %s. That is a potential $%g ($%g volume + $%g "
                    "shipping), not realized. Each lab keeps its own cost allocation; no grant money moves.") % (
            e["total_quantity"], e["pooled_unit_price_usd"], e["formula"], e["potential_savings_usd"],
            e["volume_component_usd"], e["shipping_component_usd"]),
        "impact": {"value": e["potential_savings_usd"], "unit": "USD", "status": "potential",
                   "label": "$%g potential savings (estimated)" % e["potential_savings_usd"]},
        "evidenceIds": [ins["insight_id"]] + ins["candidate_ids"], "assumptions": ins["assumptions"],
        "confidence": "high", "limitations": ["Prices are synthetic vendor tiers, not quotes.",
                                              "Each impacted lab manager and the department admin must agree."],
        "exclusions": [{"ids": x["order_ids"], "reason": "%s: %s" % (x["sku_id"], x["reason"])} for x in exclusions],
        "requiredApprovals": ins["required_approvals"],
        "nextStep": {"action": "propose_shared_order", "label": "Propose shared order"}, "advisory": False}


def _overload_card(ins):
    e = ins["estimate"]
    b, a = e["before"], e["after"]
    return {
        "insightId": ins["insight_id"], "kind": "overload_rebalance",
        "headline": "Move %g flexible hours from %s to %s" % (e["movable_hours"], e["source"], e["target"]),
        "evidenceSentence": "%s is booked %g hours (%s%% of staffed time) next week while %s has %g hours (%s%%)." % (
            e["source"], b["source_hours"], _pct(b["source_utilization"]), e["target"], b["target_hours"],
            _pct(b["target_utilization"])),
        "summary": ("The listed flexible sessions belong to people certified on %s and fit there with cleaning buffers. "
                    "After the move: %g h (%s%%) and %g h (%s%%); total workload stays %g h. Nothing moves until each "
                    "owner agrees.") % (e["target"], a["source_hours"], _pct(a["source_utilization"]), a["target_hours"],
                                        _pct(a["target_utilization"]), e["total_hours_after"]),
        "impact": {"value": e["movable_hours"], "unit": "hours", "status": "potential",
                   "label": "%g hours of potential congestion relief" % e["movable_hours"]},
        "evidenceIds": [ins["insight_id"]] + ins["candidate_ids"], "assumptions": ins["assumptions"],
        "confidence": "medium", "limitations": ["Each booking owner must consent; the admin can't approve for them.",
                                                "Hours, not money: this card has no dollar value."],
        "exclusions": [{"ids": [x["booking_id"]], "reason": x["reason"]} for x in e["excluded"]],
        "requiredApprovals": ins["required_approvals"],
        "nextStep": {"action": "review_transfer_plan", "label": "Review transfer plan"}, "advisory": False}


def _underuse_card(ins):
    e = ins["estimate"]
    summary = ""
    for src in e["overflow_sources"]:
        summary += "%s runs at %s%% with about %g unmet hours a week that %s could absorb for qualified users. " % (
            src["resource_id"], _pct(src["utilization"]), src["avg_unmet_hours_per_week"], e["resource_id"])
    summary += ("Publish the spare capacity first; compare borrowing, longer staffed hours or buying only if demand "
                "grows. Low use does not mean the instrument is obsolete.")
    return {
        "insightId": ins["insight_id"], "kind": "underuse",
        "headline": "%s is used %s%% of staffed hours" % (e["resource_id"], _pct(e["utilization"])),
        "evidenceSentence": "%g of %g staffed hours are booked next week; %d of %d observed weeks were low." % (
            e["booked_hours"], e["available_hours"], e["low_weeks"], e["weeks_observed"]),
        "summary": summary,
        "impact": {"value": round(e["utilization"] * 100, 1), "unit": "percent_of_staffed_hours", "status": "potential",
                   "label": "%s%% of staffed hours used (estimated)" % _pct(e["utilization"])},
        "evidenceIds": [ins["insight_id"], e["resource_id"]], "assumptions": ins["assumptions"],
        "confidence": "medium", "limitations": ["Advisory: based on synthetic history.", "No sale or purchase is implied."],
        "exclusions": [], "requiredApprovals": ins["required_approvals"],
        "nextStep": {"action": "publish_available_capacity", "label": "Publish available capacity"}, "advisory": True}


def build_cards(results, week):
    pooled = results["insight_find_pooled_orders"]
    over = results["insight_find_overloads"]["insights"]
    under = results["insight_find_underuse"]["insights"]
    cards, notes = [], ["All bookings, prices and forecasts are synthetic demo data."]
    if pooled["insights"]:
        cards.append(_pooled_card(pooled["insights"][0], pooled["exclusions"]))
    else:
        notes.insert(0, "No pooling opportunity: no two labs have compatible open orders for the same SKU.")
    if over:
        cards.append(_overload_card(over[0]))
    else:
        notes.insert(0, "No overloaded instrument with safely movable hours this week.")
    if under:
        cards.append(_underuse_card(under[0]))
    shown = {c["insightId"] for c in cards}
    also = []
    for ins in pooled["insights"] + over + under:
        if ins["insight_id"] not in shown:
            e = ins["estimate"]
            note = ("%s is also low (%s%%)." % (e["resource_id"], _pct(e["utilization"])) if ins["kind"] == "underuse"
                    else "Another %s finding; review it in the list." % ins["kind"])
            also.append({"insightId": ins["insight_id"], "note": note})
    snap = results["dept_get_snapshot"]
    return {"snapshotId": snap["snapshot_id"], "weekStart": week, "dataTimestamp": snap["data_timestamp"],
            "cards": cards, "alsoDetected": also, "notes": notes}
