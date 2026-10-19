"""Optimizer eval cases: the three planted department findings (docs/02, docs/11 T-MACRO-*).

All three grade the same Department Optimizer run. Its input is the real tool results after the
canonical Stage 1 commit plus Moreno's supply drafts. Each case checks one card.
"""
import copy

from agents import specs
from labsync_tools import registry
from labsync_tools import tools as T
from labsync_tools.memory_repo import InMemoryRepository

from .negotiation_cases import GOAL

WEEK = "2026-11-02"


def department_after_stage_1():
    repo = stage_1_repo()
    return {"snapshot": T.dept_get_snapshot(repo, "dept_admin", WEEK),
            "pooled": T.insight_find_pooled_orders(repo, "dept_admin"),
            "overloads": T.insight_find_overloads(repo, "dept_admin", WEEK),
            "underuse": T.insight_find_underuse(repo, "dept_admin", WEEK)}


def stage_1_repo():
    """The repository after the canonical Stage 1 commit and Moreno's supply drafts."""
    repo = InMemoryRepository()
    plan_id = T.plan_create_draft(repo, "morgan", copy.deepcopy(GOAL))["plan_id"]
    found = T.scheduler_find_slots(repo, "morgan", plan_id)
    option = next(o for o in found["options"] if o["kind"] == "owner_move")
    prop = T.booking_propose(repo, "morgan", plan_id, option["option_id"], "eval:stage1")
    T.liaison_request_change(repo, "morgan", prop["proposal_id"], "bk_chen_confocal")
    owner, confirm = prop["approvals"]
    T.approval_record(repo, "chen_owner", owner["approval_id"], "approve")
    T.approval_record(repo, "morgan", confirm["approval_id"], "approve")
    T.booking_commit_approved(repo, "morgan", prop["proposal_id"], "eval:commit")
    T.supply_create_order_draft(repo, "morgan", plan_id, "eval:orders")
    return repo


FINDINGS = [
    {"id": "opt-001", "category": "shared_purchasing", "kind": "pooled_order",
     "description": "Moreno 2 + Patel 3 anti-GFP packs: $640 separate, $545 pooled, $95 potential.",
     "expect": {"impact_value": 95, "impact_unit": "USD", "evidence_includes": ["po_patel_antigfp"],
                "required_approvals": ["moreno_mgr", "patel_mgr", "dept_admin"],
                "summary_mentions": ["640", "545", "95"], "advisory": False}},
    {"id": "opt-002", "category": "overload_rebalance", "kind": "overload_rebalance",
     "description": "Confocal-1 37h vs Confocal-2 8h; 8 movable hours give 29h and 16h, total 45h.",
     "expect": {"impact_value": 8.0, "impact_unit": "hours",
                "evidence_includes": ["bk_confocal_1_20261104_0900", "bk_confocal_1_20261105_0900"],
                "required_approvals": ["riley_rivera", "sam_chen", "dept_admin"],
                "summary_mentions": ["29", "16", "45"], "advisory": False}},
    {"id": "opt-003", "category": "underuse", "kind": "underuse",
     "description": "Flow-2 at 4/40 hours (10%), persistently low; advisory only, no purchase conclusion.",
     "expect": {"impact_value": 10.0, "impact_unit": "percent_of_staffed_hours", "evidence_includes": ["flow_2"],
                "required_approvals": ["dept_admin"], "summary_mentions": [], "advisory": True,
                "forbidden_text": ["sell", "obsolete instrument", "should buy"]}},
]


def cases():
    dept = department_after_stage_1()
    shot = next(s for s in specs.few_shots(registry.OPTIMIZER) if s["id"] == "opt-after-stage-1")
    out = []
    for f in FINDINGS:
        card = next(c for c in shot["output"]["cards"] if c["kind"] == f["kind"])
        out.append({"id": f["id"], "suite": "optimizer", "category": f["category"], "description": f["description"],
                    "context": {"actor_id": "dept_admin", "now": "2026-10-28T10:00:00-05:00", "week_start": WEEK},
                    "input": dept,
                    "expect": dict(f["expect"], kind=f["kind"],
                                   required_tools=["dept_get_snapshot", "insight_find_pooled_orders",
                                                   "insight_find_overloads", "insight_find_underuse"],
                                   forbidden_tools=["approval_record", "insight_propose_action",
                                                    "booking_commit_approved"]),
                    "reference": shot["output"], "reference_card_id": card["insightId"]})
    return out
