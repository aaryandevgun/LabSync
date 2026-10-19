"""Supplies, department insights, permissions, agent-output validation, registry and reset."""
import copy
import json

import pytest

from labsync_tools import queries as Q
from labsync_tools import registry
from labsync_tools import tools as T
from labsync_tools.memory_repo import InMemoryRepository

from .helpers import authorize_owner_move, ok

WEEK = "2026-11-02"


def test_order_draft_only_covers_shortfall_and_is_idempotent(repo, goal):
    plan_id = ok(T.plan_create_draft(repo, "morgan", goal))["plan_id"]
    first = ok(T.supply_create_order_draft(repo, "morgan", plan_id, "order-key"))
    assert [(o["sku_id"], o["quantity"], o["state"]) for o in first["orders"]] == [
        ("ANTI_GFP_100", 2, "awaiting_lab_approval"), ("COVERSLIP_24", 1, "awaiting_lab_approval")]
    again = ok(T.supply_create_order_draft(repo, "morgan", plan_id, "order-key"))
    assert again["replayed"] and len([o for o in repo.list_records("OrderProposal") if o.get("plan_id")]) == 2


def test_order_never_becomes_a_purchase(repo, goal):
    """T-SUPPLY-003: no lab/fund approval -> no completed purchase; with both -> approved_request only."""
    plan_id = ok(T.plan_create_draft(repo, "morgan", goal))["plan_id"]
    order = ok(T.supply_create_order_draft(repo, "morgan", plan_id, "o"))["orders"][0]
    lab, fund = [a for a in repo.list_records("Approval") if a["entity_id"] == order["order_id"]]
    assert T.approval_record(repo, "morgan", lab["approval_id"], "approve")["code"] == "UNAUTHORIZED_APPROVAL"
    assert T.approval_record(repo, "moreno_mgr", fund["approval_id"], "approve")["code"] == "APPROVAL_OUT_OF_ORDER"
    step = ok(T.approval_record(repo, "moreno_mgr", lab["approval_id"], "approve"))
    assert step["entity_state"] == "awaiting_fund_approval"
    done = ok(T.approval_record(repo, "moreno_mgr", fund["approval_id"], "approve"))
    assert (done["entity_state"], done["next_step"]) == ("approved_request", "none")
    states = {o["state"] for o in repo.list_records("OrderProposal")}
    assert not states & {"ordered", "submitted_to_vendor", "received", "purchased"}


def test_quote_reports_late_order(repo):
    """T-SCHED-006 via tools: needed Tuesday morning but quoted after the last safe date -> no false promise."""
    late = InMemoryRepository(now="2026-11-02T10:00:00-06:00")
    q = ok(T.supply_quote(late, "morgan", [{"sku_id": "ANTI_GFP_100", "quantity": 2}], "2026-11-03T09:00:00-06:00"))
    assert q["readiness"]["code"] == "ORDER_TOO_LATE"
    assert q["readiness"]["ready_at"] > "2026-11-03T09:00:00-06:00"  # earliest arrival is after the need time
    on_time = ok(T.supply_quote(repo, "morgan", [{"sku_id": "ANTI_GFP_100", "quantity": 2}], "2026-11-03T09:00:00-06:00"))
    assert on_time["readiness"]["last_safe_order_date"] == "2026-10-29"
    assert on_time["quote"]["status"] == "estimate"


def test_department_snapshot_and_insights_change_after_stage_1(repo, goal):
    """T-MACRO-004: a fresh Moreno booking + supply proposal changes the snapshot and the insight sources."""
    before = ok(T.dept_get_snapshot(repo, "dept_admin", WEEK))
    assert ok(T.insight_find_pooled_orders(repo, "dept_admin"))["insights"] == []
    plan_id, proposal_id = authorize_owner_move(repo, goal)
    ok(T.booking_commit_approved(repo, "morgan", proposal_id, "k"))
    orders = ok(T.supply_create_order_draft(repo, "morgan", plan_id, "o"))["orders"]
    after = ok(T.dept_get_snapshot(repo, "dept_admin", WEEK))
    assert after["snapshot_id"] != before["snapshot_id"]
    util = {u["resource_id"]: u["booked_hours"] for u in after["utilization"]}
    assert (util["confocal_1"], util["confocal_2"], util["flow_2"]) == (37.0, 8.0, 4.0)
    pools = ok(T.insight_find_pooled_orders(repo, "dept_admin"))
    pool = pools["insights"][0]
    antigfp = next(o["order_id"] for o in orders if o["sku_id"] == "ANTI_GFP_100")
    assert antigfp in pool["candidate_ids"] and "po_patel_antigfp" in pool["candidate_ids"]
    assert (pool["estimate"]["unpooled_total_usd"], pool["estimate"]["pooled_total_usd"],
            pool["estimate"]["potential_savings_usd"]) == (640, 545, 95)
    assert pool["state"] == "detected" and pool["realized_savings_usd"] is None
    reasons = {e["reason"] for e in pools["exclusions"]}
    assert reasons >= {"STATE_LOCKED", "DIFFERENT_SHIP_TO"}


def test_overload_and_underuse_insights(repo, goal):
    _, proposal_id = authorize_owner_move(repo, goal)
    ok(T.booking_commit_approved(repo, "morgan", proposal_id, "k"))
    over = ok(T.insight_find_overloads(repo, "dept_admin", WEEK))["insights"]
    est = over[0]["estimate"]
    assert (over[0]["estimate"]["source"], over[0]["estimate"]["target"]) == ("confocal_1", "confocal_2")
    assert est["movable_hours"] == 8.0
    assert (est["after"]["source_hours"], est["after"]["target_hours"]) == (29.0, 16.0)
    assert over[0]["candidate_ids"] and over[0]["units"].startswith("hours")
    ranked = ok(T.insight_find_underuse(repo, "dept_admin", WEEK))["insights"]
    assert ranked[0]["candidate_ids"] == ["flow_2"]  # lowest utilization first
    under = {i["candidate_ids"][0]: i for i in ranked}
    flow2 = under["flow_2"]["estimate"]
    assert flow2["utilization"] == 0.1 and len(flow2["history"]) == 6
    assert "USD" not in under["flow_2"]["units"]


def test_finders_are_read_only(repo):
    before = {k: repo.list_records(k) for k in ("DepartmentInsight", "AuditEvent", "Booking", "OrderProposal")}
    ok(T.insight_find_pooled_orders(repo, "dept_admin"))
    ok(T.insight_find_overloads(repo, "dept_admin", WEEK))
    ok(T.insight_find_underuse(repo, "dept_admin", WEEK))
    ok(T.dept_get_snapshot(repo, "dept_admin", WEEK))
    assert {k: repo.list_records(k) for k in before} == before


def test_insight_proposal_needs_owner_and_admin_approval_and_changes_nothing(repo, goal):
    plan_id = ok(T.plan_create_draft(repo, "morgan", goal))["plan_id"]
    ok(T.supply_create_order_draft(repo, "morgan", plan_id, "o"))
    orders_before = repo.list_records("OrderProposal")
    insight_id = ok(T.insight_find_pooled_orders(repo, "dept_admin"))["insights"][0]["insight_id"]
    prop = ok(T.insight_propose_action(repo, "dept_admin", insight_id))
    assert prop["state"] == "pending_approvals"
    assert [a["approver_id"] for a in prop["approvals"]] == ["moreno_mgr", "patel_mgr", "dept_admin"]
    assert T.insight_propose_action(repo, "dept_admin", insight_id)["code"] == "INVALID_TRANSITION"
    for a in prop["approvals"]:
        last = ok(T.approval_record(repo, a["approver_id"], a["approval_id"], "approve"))
    assert last["entity_state"] == "approved"
    assert repo.list_records("OrderProposal") == orders_before  # consent recorded, nothing purchased or merged
    listed = ok(T.insight_find_pooled_orders(repo, "dept_admin"))["insights"][0]
    assert listed["state"] == "approved"


def test_propose_unknown_or_vanished_insight(repo):
    assert T.insight_propose_action(repo, "dept_admin", "ins_made_up")["code"] == "NOT_FOUND"
    under = ok(T.insight_find_underuse(repo, "dept_admin", WEEK))["insights"][0]["insight_id"]
    assert T.insight_propose_action(repo, "dept_admin", under)["code"] == "NOT_FOUND"  # week needed
    assert ok(T.insight_propose_action(repo, "dept_admin", under, week_start=WEEK))["state"] == "pending_approvals"


def test_forecast_is_admin_only_and_stored(repo):
    assert T.forecast_resource_demand(repo, "morgan", "confocal_1")["code"] == "PERMISSION_DENIED"
    fc = ok(T.forecast_resource_demand(repo, "dept_admin", "confocal_1"))
    assert fc["forecast"]["forecast_week"] == WEEK and fc["forecast"]["mae"] is not None
    assert repo.get_record("ForecastRun", fc["forecast_run_id"])["predicted_hours"] == fc["forecast"]["predicted_hours"]


@pytest.mark.parametrize("call", [
    lambda r: T.stock_get_availability(r, "morgan", "lab_patel", ["ANTI_GFP_100"]),
    lambda r: T.dept_get_snapshot(r, "morgan", WEEK),
    lambda r: T.insight_find_pooled_orders(r, "jordan_patel"),
    lambda r: T.insight_find_underuse(r, "chen_owner", WEEK),
    lambda r: T.forecast_resource_demand(r, "sam_chen", "confocal_1"),
])
def test_no_restricted_data_leaks_to_lab_users(repo, call):
    """T-SEC-001: a lab user asking for another lab's or department data gets a bare denial."""
    result = call(repo)
    assert result == {"status": "error", "code": "PERMISSION_DENIED", "message": "You are not authorized for this action."}
    assert repo.list_records("AuditEvent")[-1]["status"] == "denied"


def test_funding_details_never_leave_the_tools(repo):
    hints = repo.list_records("FundingHint")
    secret_values = {str(v) for h in hints for k, v in h.items() if k not in ("lab_id", "funding_hint_id") and v}
    snap = json.dumps(ok(T.dept_get_snapshot(repo, "dept_admin", WEEK)))
    pools = json.dumps(ok(T.insight_find_pooled_orders(repo, "dept_admin")))
    for value in secret_values:
        if len(value) > 3:
            assert value not in snap and value not in pools


def test_audit_activity_is_scoped(repo, goal):
    plan_id, proposal_id = authorize_owner_move(repo, goal)
    request_id = repo.get_record("ExperimentPlan", plan_id)["request_id"]
    mine = ok(T.audit_get_activity(repo, "morgan", request_id=request_id))["events"]
    admin = ok(T.audit_get_activity(repo, "dept_admin", request_id=request_id))["events"]
    patel = ok(T.audit_get_activity(repo, "jordan_patel", request_id=request_id))["events"]
    assert mine and len(admin) >= len(mine) and patel == []


@pytest.mark.parametrize("mutate,needle", [
    (lambda g: g.update(extra="x"), "unexpected field: extra"),
    (lambda g: g["supplies"].append({"skuId": "MADE_UP", "quantity": 1, "source": "inferred"}), "not in the catalog"),
    (lambda g: g["steps"][1].update(durationMinutes=170), "multiple of 15"),
    (lambda g: g.update(confidence="high"), "confidence"),
    (lambda g: g.update(desiredStart="next tuesday"), "ISO 8601"),
    (lambda g: g.update(labId="lab_chen"), "signed-in actor"),
    (lambda g: g["steps"][1].update(dependsOn=["ghost"]), "unknown step"),
])
def test_malformed_agent_output_is_rejected_without_a_write(repo, goal, mutate, needle):
    """T-AGENT-002: invalid or untrusted fields -> INVALID_PLAN, no ExperimentPlan saved."""
    mutate(goal)
    result = T.plan_create_draft(repo, "morgan", goal)
    assert result["code"] == "INVALID_PLAN" and any(needle in e for e in result["errors"])
    assert repo.list_records("ExperimentPlan") == []


def test_missing_information_blocks_search(repo, goal):
    goal.update(desiredStart=None, missingInformation=["desiredStart"])
    plan = ok(T.plan_create_draft(repo, "morgan", goal))
    assert plan["needs_input"] == ["desiredStart"] and plan["scheduling_request"] is None
    assert T.scheduler_find_slots(repo, "morgan", plan["plan_id"])["code"] == "MISSING_INFORMATION"


def test_unknown_capability_is_a_warning(repo, goal):
    goal["steps"][1]["requiredCapabilities"].append("cryo_em")
    plan = ok(T.plan_create_draft(repo, "morgan", goal))
    assert any("cryo_em" in w for w in plan["warnings"])
    found = ok(T.scheduler_find_slots(repo, "morgan", plan["plan_id"]))
    assert found["options"] == []


def test_registry_covers_docs_06_and_enforces_agent_lists(repo, goal):
    docs_06 = {"catalog_find_resources", "resource_check_qualifications", "scheduler_find_slots",
               "stock_get_availability", "supply_quote", "plan_create_draft", "booking_propose",
               "liaison_request_change", "approval_record", "booking_commit_approved", "dept_get_snapshot",
               "forecast_resource_demand", "insight_find_pooled_orders", "insight_find_overloads",
               "insight_find_underuse", "insight_propose_action", "audit_get_activity"}
    assert set(registry.TOOLS) == docs_06 | registry.EXTRA_TOOLS
    assert all(t["description"] for t in registry.TOOLS.values())
    assert not any("approval_record" in registry.tools_for(a) for a in
                   (registry.LAB, registry.NEGOTIATOR, registry.OPTIMIZER))
    assert "booking_commit_approved" not in registry.tools_for(registry.OPTIMIZER)
    refused = registry.call(repo, "approval_record", {"approval_id": "x", "decision": "approve"}, "morgan",
                            agent=registry.LAB)
    assert refused["code"] == "TOOL_NOT_ALLOWED"
    spoof = registry.call(repo, "plan_create_draft", {"actor_id": "chen_owner", "parsed_goal": goal}, "morgan",
                          agent=registry.LAB)
    assert spoof["code"] == "INVALID_ARGUMENTS"
    missing = registry.call(repo, "plan_create_draft", {}, "morgan", agent=registry.LAB)
    assert missing["code"] == "INVALID_ARGUMENTS"
    typed = registry.call(repo, "dept_get_snapshot", {"week_start": "next week"}, "dept_admin",
                          agent=registry.OPTIMIZER)
    assert typed["code"] == "INVALID_ARGUMENTS"
    good = registry.call(repo, "plan_create_draft", {"parsed_goal": goal}, "morgan", agent=registry.LAB)
    assert good["status"] == "ok"


def test_reset_restores_the_exact_seed(repo, goal, monkeypatch):
    """T-RESET-001: two completed demo runs with a reset after each -> exact seed, no residual approvals."""
    fresh = InMemoryRepository()
    assert Q.reset_demo(repo, "morgan", "guess")["code"] == "RESET_NOT_ALLOWED"  # token unset: always refused
    monkeypatch.setenv("LABSYNC_RESET_TOKEN", "demo-secret")
    assert Q.reset_demo(repo, "morgan", "wrong")["code"] == "RESET_NOT_ALLOWED"
    for i in range(2):
        plan_id, proposal_id = authorize_owner_move(repo, copy.deepcopy(goal))
        ok(T.booking_commit_approved(repo, "morgan", proposal_id, "k%d" % i))
        ok(T.supply_create_order_draft(repo, "morgan", plan_id, "o%d" % i))
        ok(Q.reset_demo(repo, "morgan", "demo-secret"))
        for kind in ("Booking", "RoomReservation", "OrderProposal", "Stock", "ExperimentPlan", "ReservationProposal",
                     "Approval", "DepartmentInsight", "Notification", "CommitReceipt", "ForecastRun"):
            assert repo.list_records(kind) == fresh.list_records(kind), kind
        assert ok(T.dept_get_snapshot(repo, "dept_admin", WEEK))["snapshot_id"] == \
            ok(T.dept_get_snapshot(fresh, "dept_admin", WEEK))["snapshot_id"]
