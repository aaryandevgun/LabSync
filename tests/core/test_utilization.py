"""find_utilization_gaps: T-MACRO-001..003 against the post-Phase-1 calendar."""
import copy

from labsync_core.utilization import find_utilization_gaps, plan_transfer, weekly_utilization

WEEK = "2026-11-02"


def post_commit(seed):
    rows = copy.deepcopy(seed["bookings"])
    for b in rows:
        if b["booking_id"] == "bk_chen_confocal":
            b["start_local"], b["end_local"] = "2026-11-03T13:30:00-06:00", "2026-11-03T15:30:00-06:00"
    rows.append({"booking_id": "bk_moreno_pending", "resource_id": "confocal_1", "lab_id": "lab_moreno",
                 "user_id": "morgan", "start_local": "2026-11-03T10:00:00-06:00",
                 "end_local": "2026-11-03T13:00:00-06:00", "status": "confirmed", "flexible": "false"})
    return rows


def gaps(seed, bookings):
    return find_utilization_gaps(bookings, seed["instruments"], seed["persons"], WEEK, seed["maintenance_windows"],
                                 seed["demand"], seed["policies"])


def test_macro_001_confocal_utilization(seed):
    util = {u["resource_id"]: u for u in gaps(seed, post_commit(seed))["utilization"]}
    assert (util["confocal_1"]["booked_hours"], util["confocal_1"]["utilization"]) == (37, 0.925)
    assert (util["confocal_2"]["booked_hours"], util["confocal_2"]["utilization"]) == (8, 0.2)


def test_pre_commit_confocal_1_is_34_hours(seed):
    u = weekly_utilization(seed["bookings"], seed["instruments_by_id"]["confocal_1"], WEEK)
    assert u["booked_hours"] == 34


def test_macro_002_eight_hours_move_with_concrete_bookings(seed):
    plans = gaps(seed, post_commit(seed))["overloads"]
    plan = next(p for p in plans if (p["source"], p["target"]) == ("confocal_1", "confocal_2"))
    assert plan["movable_hours"] == 8
    assert [(m["booking_id"], m["owner_id"]) for m in plan["moves"]] == [
        ("bk_confocal_1_20261104_0900", "riley_rivera"), ("bk_confocal_1_20261105_0900", "sam_chen")]
    assert (plan["after"]["source_hours"], plan["after"]["target_hours"]) == (29, 16)
    assert (plan["after"]["source_utilization"], plan["after"]["target_utilization"]) == (0.725, 0.4)
    assert plan["total_hours_before"] == plan["total_hours_after"] == 45
    assert plan["required_approvals"] == ["riley_rivera", "sam_chen"]
    # Chen's moved booking is flexible but Chen lacks confocal_2_cert.
    assert {"booking_id": "bk_chen_confocal", "reason": "NOT_QUALIFIED", "missing": ["confocal_2_cert"]} in plan["excluded"]


def test_zero_movable_hours_reports_reason(seed):
    rows = post_commit(seed)
    for b in rows:
        b["flexible"] = "false"
    plan = plan_transfer(seed["instruments_by_id"]["confocal_1"], seed["instruments_by_id"]["confocal_2"], rows,
                         seed["persons"], WEEK)
    assert plan["movable_hours"] == 0 and plan["moves"] == [] and plan["reason"]
    assert plan["after"] == plan["before"]


def test_transfer_respects_target_calendar(seed):
    rows = post_commit(seed)
    rows.append({"booking_id": "blocker", "resource_id": "confocal_2", "lab_id": "lab_chen", "user_id": "sam_chen",
                 "start_local": "2026-11-04T10:00:00-06:00", "end_local": "2026-11-04T11:00:00-06:00",
                 "status": "confirmed", "flexible": "false"})
    plan = plan_transfer(seed["instruments_by_id"]["confocal_1"], seed["instruments_by_id"]["confocal_2"], rows,
                         seed["persons"], WEEK)
    assert plan["movable_hours"] == 4
    assert {"booking_id": "bk_confocal_1_20261104_0900", "reason": "TARGET_CONFLICT"} in plan["excluded"]


def test_macro_003_flow_2_underused_persistently_and_advisory(seed):
    under = {u["resource_id"]: u for u in gaps(seed, post_commit(seed))["underused"]}
    flow2 = under["flow_2"]
    assert (flow2["booked_hours"], flow2["utilization"]) == (4, 0.1)
    assert flow2["persistent"] and flow2["low_weeks"] == 6 and flow2["status"] == "advisory"
    assert [s["resource_id"] for s in flow2["overflow_sources"]] == ["flow_1"]
    assert "obsolete" in flow2["caveat"]


def test_single_low_week_is_not_persistent(seed):
    out = find_utilization_gaps(post_commit(seed), seed["instruments"], seed["persons"], WEEK,
                                seed["maintenance_windows"], [], seed["policies"])
    flow2 = next(u for u in out["underused"] if u["resource_id"] == "flow_2")
    assert not flow2["persistent"] and flow2["status"] == "insufficient_trend"


def test_maintenance_hours_leave_the_denominator(seed):
    u = weekly_utilization(seed["bookings"], seed["instruments_by_id"]["plate_reader_1"], WEEK,
                           seed["maintenance_windows"])
    assert u["maintenance_hours"] == 4 and u["available_hours"] == 36
    assert u["utilization"] == round(u["booked_hours"] / 36, 4)


def test_transfer_stops_before_inverting_the_imbalance(seed):
    rows = post_commit(seed)
    # Pad Confocal-2's free afternoons (no overlaps) so the second 4h move would flip the imbalance.
    pads = [("2026-11-02", "12:15"), ("2026-11-03", "15:15"), ("2026-11-04", "13:15"), ("2026-11-06", "12:15")]
    for i, (day, start) in enumerate(pads):
        rows.append({"booking_id": "pad_%d" % i, "resource_id": "confocal_2", "lab_id": "lab_chen",
                     "user_id": "sam_chen", "start_local": "%sT%s:00-06:00" % (day, start),
                     "end_local": day + "T17:00:00-06:00", "status": "confirmed", "flexible": "false"})
    plan = plan_transfer(seed["instruments_by_id"]["confocal_1"], seed["instruments_by_id"]["confocal_2"], rows,
                         seed["persons"], WEEK)
    assert any(e["reason"] == "WOULD_INVERT_IMBALANCE" for e in plan["excluded"])
    assert plan["movable_hours"] == 4
    assert plan["after"]["source_hours"] >= plan["after"]["target_hours"]
