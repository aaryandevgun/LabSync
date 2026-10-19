"""State machines, approval authorization and conditional commit (T-BOOK-001..005)."""
import copy

import pytest

from labsync_core.commit import apply_writes, plan_commit
from labsync_core.conflicts import detect_conflicts
from labsync_core.proposals import (approval_status, authorize_decision, can_transition, order_slots,
                                    reservation_slots, reservation_state)

T = "2026-11-03T%s:00-06:00"
KEY = "req_001:commit:prop_1"


def proposal():
    return {
        "proposal_id": "prop_1", "requester_id": "morgan", "lab_id": "lab_moreno",
        "creates": [
            {"booking_id": "bk_moreno_pending", "resource_id": "confocal_1", "start": T % "10:00", "end": T % "13:00",
             "user_id": "morgan", "lab_id": "lab_moreno"},
            {"booking_id": "bk_moreno_prep_pending", "resource_id": "prep_a", "start": T % "09:00",
             "end": T % "09:45", "user_id": "morgan", "lab_id": "lab_moreno", "entity": "RoomReservation"}],
        "contingent_moves": [{"booking_id": "bk_chen_confocal", "resource_id": "confocal_1", "owner_id": "chen_owner",
                              "lab_id": "lab_chen", "to": {"start": T % "13:30", "end": T % "15:30"}}],
        "expected_versions": {"bk_chen_confocal": 1},
    }


APPROVE_ALL = [{"slot_id": "owner:bk_chen_confocal", "actor_id": "chen_owner", "decision": "approve"},
               {"slot_id": "requester", "actor_id": "morgan", "decision": "approve"}]


@pytest.fixture
def world(seed):
    rows = copy.deepcopy(seed["bookings"]) + copy.deepcopy(seed["room_bookings"])
    resources = dict(seed["instruments_by_id"], **seed["rooms_by_id"])
    return rows, resources


def person(seed, pid):
    return seed["persons_by_id"][pid]


# ---------- state machines ----------

def test_reservation_cannot_skip_to_committed():
    assert not can_transition("ReservationProposal", "submitted", "committed")["ok"]
    assert can_transition("ReservationProposal", "authorized", "committed")["ok"]
    assert can_transition("ReservationProposal", "submitted", "requester_approval_pending")["ok"]


def test_orders_never_reach_vendor_states():
    machine_targets = {t for targets in [can_transition("OrderProposal", s, "x")["allowed"]
                                         for s in ["draft", "awaiting_lab_approval", "awaiting_fund_approval"]]
                       for t in targets}
    assert "submitted_to_vendor" not in machine_targets and "received" not in machine_targets
    assert can_transition("DepartmentInsight", "pending_approvals", "executed")["code"] == "INVALID_TRANSITION"


# ---------- approval authorization ----------

def test_book_002_patel_cannot_approve_chen_move(seed):
    slots = reservation_slots(proposal())
    result = authorize_decision(slots, [], "owner:bk_chen_confocal", person(seed, "patel_mgr"))
    assert result == {"authorized": False, "code": "UNAUTHORIZED_APPROVAL"}


def test_moreno_cannot_approve_chen_slot_and_chen_can(seed):
    slots = reservation_slots(proposal())
    assert authorize_decision(slots, [], "owner:bk_chen_confocal", person(seed, "morgan"))["authorized"] is False
    assert authorize_decision(slots, [], "owner:bk_chen_confocal", person(seed, "chen_owner"))["authorized"]


def test_core_scheduler_may_decide_owner_move_but_not_requester(seed):
    slots = reservation_slots(proposal())
    sched = person(seed, "core_sched")
    assert authorize_decision(slots, [], "owner:bk_chen_confocal", sched)["authorized"]
    assert authorize_decision(slots, APPROVE_ALL[:1], "requester", sched)["code"] == "UNAUTHORIZED_APPROVAL"


def test_requester_confirms_only_after_owner(seed):
    slots = reservation_slots(proposal())
    assert authorize_decision(slots, [], "requester", person(seed, "morgan"))["code"] == "APPROVAL_OUT_OF_ORDER"
    assert authorize_decision(slots, APPROVE_ALL[:1], "requester", person(seed, "morgan"))["authorized"]
    assert authorize_decision(slots, APPROVE_ALL, "requester", person(seed, "morgan"))["code"] == "ALREADY_DECIDED"


def test_reservation_state_follows_approvals():
    p = proposal()
    assert reservation_state(p, []) == "owner_approval_pending"
    assert reservation_state(p, APPROVE_ALL[:1]) == "requester_approval_pending"
    assert reservation_state(p, APPROVE_ALL) == "authorized"
    assert reservation_state(p, [dict(APPROVE_ALL[0], decision="reject")]) == "rejected"
    no_move = dict(p, contingent_moves=[])
    assert reservation_state(no_move, []) == "requester_approval_pending"


def test_order_needs_lab_and_fund_approval(seed):
    order = {"order_id": "po_moreno", "lab_id": "lab_moreno"}
    slots = order_slots(order, seed["labs"])
    assert [(s["kind"], s["approver_id"]) for s in slots] == [("lab_approval", "moreno_mgr"),
                                                             ("fund_approval", "moreno_mgr")]
    assert not approval_status(slots, [{"slot_id": "lab", "actor_id": "moreno_mgr", "decision": "approve"}])["complete"]
    assert authorize_decision(slots, [], "lab", person(seed, "morgan"))["code"] == "UNAUTHORIZED_APPROVAL"


# ---------- commit ----------

def test_commit_writes_exact_changes(world):
    rows, resources = world
    plan = plan_commit(proposal(), rows, resources, APPROVE_ALL, "morgan", KEY, now=T % "08:00")
    assert plan["status"] == "ok"
    assert [(w["op"], w["id"]) for w in plan["writes"]] == [
        ("update", "bk_chen_confocal"), ("create", "bk_moreno_pending"), ("create", "bk_moreno_prep_pending")]
    move = plan["writes"][0]
    assert move["before"]["start_local"] == T % "10:00" and move["after"]["start_local"] == T % "13:30"
    after = apply_writes(rows, plan["writes"])
    confocal = [r for r in after if r.get("resource_id") == "confocal_1"]
    for row in confocal:
        others = [o for o in confocal if o is not row]
        probe = [{"resource_id": "confocal_1", "start": row["start_local"], "end": row["end_local"]}]
        assert detect_conflicts(probe, others, resources) == [], row["booking_id"]
    assert sum(1 for r in after if r.get("booking_id") == "bk_moreno_pending") == 1


def test_book_001_rejection_blocks_commit(world):
    rows, resources = world
    rejected = [{"slot_id": "owner:bk_chen_confocal", "actor_id": "chen_owner", "decision": "reject"}]
    plan = plan_commit(proposal(), rows, resources, rejected, "morgan", KEY)
    assert plan["code"] == "OWNER_REJECTED" and plan["writes"] == []


def test_unapproved_and_wrong_actor_blocked(world):
    rows, resources = world
    assert plan_commit(proposal(), rows, resources, APPROVE_ALL[:1], "morgan", KEY)["code"] == "MISSING_APPROVAL"
    assert plan_commit(proposal(), rows, resources, APPROVE_ALL, "chen_owner", KEY)["code"] == "UNAUTHORIZED"


def test_book_003_competing_commits_one_wins(world):
    rows, resources = world
    first = plan_commit(proposal(), rows, resources, APPROVE_ALL, "morgan", KEY)
    rows = apply_writes(rows, first["writes"])
    rival = proposal()
    rival.update(proposal_id="prop_rival", requester_id="riley_rivera", contingent_moves=[], expected_versions={},
                 creates=[dict(rival["creates"][0], booking_id="bk_rival", user_id="riley_rivera")])
    rival_ok = [{"slot_id": "requester", "actor_id": "riley_rivera", "decision": "approve"}]
    second = plan_commit(rival, rows, resources, rival_ok, "riley_rivera", "rival:commit")
    assert second["status"] == "error" and second["code"] == "SLOT_STALE"


def test_stale_version_forces_replan(world):
    rows, resources = world
    for r in rows:
        if r.get("booking_id") == "bk_chen_confocal":
            r["version"] = "2"
    plan = plan_commit(proposal(), rows, resources, APPROVE_ALL, "morgan", KEY)
    assert plan["code"] == "SLOT_STALE" and plan["stale_ids"] == ["bk_chen_confocal"]


def test_book_004_retry_with_same_key_returns_same_receipt(world):
    rows, resources = world
    first = plan_commit(proposal(), rows, resources, APPROVE_ALL, "morgan", KEY)
    rows = apply_writes(rows, first["writes"])
    retry = plan_commit(proposal(), rows, resources, APPROVE_ALL, "morgan", KEY, receipts={KEY: first["receipt"]})
    assert retry["replayed"] and retry["receipt"] == first["receipt"] and retry["writes"] == []
    assert sum(1 for r in rows if r.get("booking_id") == "bk_moreno_pending") == 1


def test_book_005_partial_failure_is_fully_compensated(world):
    rows, resources = world
    plan = plan_commit(proposal(), rows, resources, APPROVE_ALL, "morgan", KEY)
    half = apply_writes(rows, plan["writes"][:1])  # Chen moved, Moreno not yet booked
    undo = [c for c in plan["compensation"] if c["id"] == "bk_chen_confocal"]
    restored = apply_writes(half, undo)
    chen = next(r for r in restored if r.get("booking_id") == "bk_chen_confocal")
    assert (chen["start_local"], chen["end_local"]) == (T % "10:00", T % "12:00")
    full_undo = apply_writes(apply_writes(rows, plan["writes"]), plan["compensation"])
    assert {r.get("booking_id") or r.get("reservation_id") for r in full_undo} == {
        r.get("booking_id") or r.get("reservation_id") for r in rows}


def test_apply_writes_rejects_version_mismatch(world):
    rows, resources = world
    plan = plan_commit(proposal(), rows, resources, APPROVE_ALL, "morgan", KEY)
    once = apply_writes(rows, plan["writes"])
    with pytest.raises(ValueError):
        apply_writes(once, plan["writes"][:1])


def test_insight_slots_need_each_lab_owner_and_admin():
    from labsync_core.proposals import insight_slots
    slots = insight_slots({"required_approvals": ["moreno_mgr", "patel_mgr", "dept_admin"]})
    assert [(s["kind"], s["approver_id"]) for s in slots] == [
        ("lab_owner", "moreno_mgr"), ("lab_owner", "patel_mgr"), ("admin", "dept_admin")]
