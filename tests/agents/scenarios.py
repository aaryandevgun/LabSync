"""Reproduce the exact tool results the agent few-shots were written from."""
import copy

from labsync_tools import tools as T
from labsync_tools.memory_repo import InMemoryRepository

from tests.tools.helpers import CANONICAL_GOAL, propose_owner_move

WEEK = "2026-11-02"


def _department(repo):
    return {"snapshot": T.dept_get_snapshot(repo, "dept_admin", WEEK),
            "pooled": T.insight_find_pooled_orders(repo, "dept_admin"),
            "overloads": T.insight_find_overloads(repo, "dept_admin", WEEK),
            "underuse": T.insight_find_underuse(repo, "dept_admin", WEEK)}


def canonical_change_request():
    """Chen's view of the canonical move request, right after Morgan sends it."""
    repo = InMemoryRepository()
    _, prop = propose_owner_move(repo, copy.deepcopy(CANONICAL_GOAL))
    sent = T.liaison_request_change(repo, "morgan", prop["proposal_id"], "bk_chen_confocal")
    return T.liaison_get_change_request(repo, "chen_owner", sent["approval_id"])


def department_before_stage_1():
    return _department(InMemoryRepository())


def department_after_stage_1():
    """Canonical Stage 1 committed and Moreno's supply orders drafted, then the department tools."""
    repo = InMemoryRepository()
    plan_id, prop = propose_owner_move(repo, copy.deepcopy(CANONICAL_GOAL))
    T.liaison_request_change(repo, "morgan", prop["proposal_id"], "bk_chen_confocal")
    owner, confirm = prop["approvals"]
    T.approval_record(repo, "chen_owner", owner["approval_id"], "approve")
    T.approval_record(repo, "morgan", confirm["approval_id"], "approve")
    T.booking_commit_approved(repo, "morgan", prop["proposal_id"], "req:commit")
    T.supply_create_order_draft(repo, "morgan", plan_id, "req:orders")
    return _department(repo)


def department_denied():
    repo = InMemoryRepository()
    return {"snapshot": T.dept_get_snapshot(repo, "morgan", WEEK)}


def all_insights(dept):
    return [i for key in ("pooled", "overloads", "underuse") for i in dept[key]["insights"]]
