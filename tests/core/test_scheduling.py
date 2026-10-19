"""detect_conflicts, find_slots and score_swap_options against the seeded calendar."""
import copy


from labsync_core.conflicts import detect_conflicts
from labsync_core.slots import find_slots
from labsync_core.swap_scoring import score_option, score_swap_options

T = "2026-11-03T%s:00-06:00"


def canonical_request(**overrides):
    req = {
        "requester_id": "morgan", "lab_id": "lab_moreno",
        "required_capabilities": ["gfp_imaging", "confocal_imaging"], "duration_minutes": 180,
        "search_start": T % "09:00", "search_end": "2026-11-04T18:00:00-06:00",
        "preferred_start": T % "09:00", "preferred_end": T % "13:00",
        "deadline": "2026-11-04T18:00:00-06:00",
        "prep": {"room_capabilities": ["wet_prep"], "duration_minutes": 45},
    }
    req.update(overrides)
    return req


def run(seed, request, bookings=None, policies=None):
    return find_slots(request, seed["instruments"], seed["persons"],
                      seed["bookings"] if bookings is None else bookings, seed["rooms"], seed["room_bookings"],
                      seed["maintenance_windows"], seed["policies"] if policies is None else policies)


def _moved_chen(seed):
    rows = copy.deepcopy(seed["bookings"])
    for b in rows:
        if b["booking_id"] == "bk_chen_confocal":
            b["start_local"], b["end_local"] = T % "13:30", T % "15:30"
    return rows


# ---------- detect_conflicts ----------

def test_sched_001_direct_booking_overlaps_chen(seed):
    issues = detect_conflicts([{"resource_id": "confocal_1", "start": T % "10:00", "end": T % "13:00"}],
                              seed["bookings"], seed["instruments_by_id"])
    assert [(c["type"], c["booking_id"], c["owner_id"], c["flexible"]) for c in issues] == [
        ("overlap", "bk_chen_confocal", "chen_owner", True)]


def test_sched_002_fits_after_chen_moves(seed):
    issues = detect_conflicts([{"resource_id": "confocal_1", "start": T % "10:00", "end": T % "13:00"}],
                              _moved_chen(seed), seed["instruments_by_id"])
    assert issues == []


def test_sched_003_follow_up_inside_buffer_is_flagged(seed):
    proposed = [{"resource_id": "confocal_1", "start": T % "10:00", "end": T % "13:00", "ref": "moreno"},
                {"resource_id": "confocal_1", "start": T % "13:10", "end": T % "15:10", "ref": "chen"}]
    issues = detect_conflicts(proposed, seed["bookings"], seed["instruments_by_id"],
                              ignore_booking_ids=["bk_chen_confocal"])
    assert {(c["ref"], c["type"]) for c in issues} == {("moreno", "buffer"), ("chen", "buffer")}


def test_sched_005_prep_then_imaging_is_valid(seed):
    resources = dict(seed["instruments_by_id"], **seed["rooms_by_id"])
    proposed = [{"resource_id": "prep_a", "start": T % "09:00", "end": T % "09:45"},
                {"resource_id": "confocal_1", "start": T % "10:00", "end": T % "13:00"}]
    assert detect_conflicts(proposed, _moved_chen(seed) + seed["room_bookings"], resources) == []


def test_room_turnover_enforced(seed):
    # Patel holds prep_a 10:30-12:00; a 10:25 end leaves only 5 of the 10 turnover minutes.
    issues = detect_conflicts([{"resource_id": "prep_a", "start": T % "09:40", "end": T % "10:25"}],
                              seed["room_bookings"], seed["rooms_by_id"])
    assert [c["type"] for c in issues] == ["buffer"]


def test_maintenance_hours_and_weekends_are_hard_conflicts(seed):
    inst = seed["instruments_by_id"]
    mw = detect_conflicts([{"resource_id": "plate_reader_1", "start": "2026-11-05T10:00:00-06:00",
                            "end": "2026-11-05T11:00:00-06:00"}], [], inst, seed["maintenance_windows"])
    assert [c["type"] for c in mw] == ["maintenance"]
    late = detect_conflicts([{"resource_id": "confocal_1", "start": T % "16:00", "end": T % "17:30"}], [], inst)
    sat = detect_conflicts([{"resource_id": "confocal_1", "start": "2026-11-07T10:00:00-06:00",
                             "end": "2026-11-07T11:00:00-06:00"}], [], inst)
    assert [c["type"] for c in late] == ["outside_hours"] and [c["type"] for c in sat] == ["outside_hours"]


def test_held_rows_block_and_cancelled_rows_do_not(seed):
    held = {"booking_id": "hold_1", "resource_id": "confocal_2", "start_local": T % "09:00", "end_local": T % "10:00",
            "status": "held", "user_id": "riley_rivera", "flexible": "false"}
    probe = [{"resource_id": "confocal_2", "start": T % "09:30", "end": T % "10:30"}]
    assert detect_conflicts(probe, [held], seed["instruments_by_id"])[0]["booking_id"] == "hold_1"
    assert detect_conflicts(probe, [dict(held, status="cancelled")], seed["instruments_by_id"]) == []


# ---------- find_slots ----------

def test_canonical_request_proposes_chen_move_first(seed):
    out = run(seed, canonical_request())
    assert out["status"] == "ok"
    best = out["options"][0]
    assert (best["kind"], best["resource_id"], best["start"], best["end"]) == (
        "owner_move", "confocal_1", T % "10:00", T % "13:00")
    assert best["hard_constraint_status"] == "conditional"
    assert best["contingent_moves"] == [{
        "booking_id": "bk_chen_confocal", "owner_id": "chen_owner", "lab_id": "lab_chen", "resource_id": "confocal_1",
        "from": {"start": T % "10:00", "end": T % "12:00"}, "to": {"start": T % "13:30", "end": T % "15:30"}}]
    assert best["approvals_required"] == ["chen_owner", "morgan"]
    assert best["prep"] == {"resource_id": "prep_a", "start": T % "09:00", "end": T % "09:45"}
    assert best["score"] == 46


def test_canonical_request_offers_direct_afternoon_alternative(seed):
    options = run(seed, canonical_request())["options"]
    assert len(options) <= 3
    direct = [o for o in options if o["kind"] == "direct"]
    assert direct and (direct[0]["start"], direct[0]["end"]) == (T % "12:15", T % "15:15")
    assert direct[0]["approvals_required"] == ["morgan"] and direct[0]["score"] < options[0]["score"]


def test_sched_004_confocal_2_blocked_not_bookable_for_morgan(seed):
    out = run(seed, canonical_request())
    assert all(o["resource_id"] != "confocal_2" for o in out["options"])
    assert out["blocked_alternatives"] == [{
        "resource_id": "confocal_2", "code": "NOT_QUALIFIED", "missing": ["confocal_2_cert"],
        "detail": "Requires confocal_2_cert; eligible only after qualification or with a qualified operator"}]


def test_qualified_user_does_get_confocal_2(seed):
    out = run(seed, canonical_request(requester_id="riley_rivera", lab_id="lab_rivera"))
    assert any(o["resource_id"] == "confocal_2" and o["kind"] == "direct" for o in out["options"])


def test_find_slots_is_deterministic(seed):
    assert run(seed, canonical_request()) == run(seed, canonical_request())


def test_options_never_violate_hard_constraints(seed):
    resources = dict(seed["instruments_by_id"], **seed["rooms_by_id"])
    for option in run(seed, canonical_request())["options"]:
        moved = [m["booking_id"] for m in option["contingent_moves"]]
        proposed = [{"resource_id": option["resource_id"], "start": option["start"], "end": option["end"]},
                    dict(option["prep"])]
        proposed += [{"resource_id": m["resource_id"], "start": m["to"]["start"], "end": m["to"]["end"]}
                     for m in option["contingent_moves"]]
        assert detect_conflicts(proposed, seed["bookings"] + seed["room_bookings"], resources,
                                seed["maintenance_windows"], ignore_booking_ids=moved) == []


def test_sched_006_supplies_arriving_too_late_block_tuesday(seed):
    out = run(seed, canonical_request(supplies_ready_at="2026-11-03T12:00:00-06:00"))
    assert out["exclusion_counts"].get("ORDER_TOO_LATE", 0) > 0
    for option in out["options"]:
        assert option["prep"]["start"] >= "2026-11-03T12:00:00-06:00"
    tuesday_morning = [o for o in out["options"] if o["start"] < T % "12:00"]
    assert tuesday_morning == []


def test_no_viable_slot_reports_status(seed):
    out = run(seed, canonical_request(duration_minutes=9 * 60))
    assert out["status"] == "no_viable_slot" and out["options"] == []


def test_unsupported_capability_returns_no_options(seed):
    out = run(seed, canonical_request(required_capabilities=["super_resolution_imaging"]))
    assert out["status"] == "no_viable_slot" and out["exclusion_counts"]["CAPABILITY_MISMATCH"] == 10


def test_non_flexible_blocker_is_never_moved(seed):
    rows = copy.deepcopy(seed["bookings"])
    for b in rows:
        if b["booking_id"] == "bk_chen_confocal":
            b["flexible"] = "false"
    out = run(seed, canonical_request(), bookings=rows)
    assert all(not o["contingent_moves"] for o in out["options"])


def test_policy_weights_change_ranking(seed):
    heavy = [dict(p) for p in seed["policies"]]
    for p in heavy:
        if p["key"] == "score.weight.requires_owner_move":
            p["value"] = "-100"
    out = run(seed, canonical_request(), policies=heavy)
    assert out["options"][0]["kind"] == "direct"


# ---------- score_swap_options ----------

def test_score_breakdown_matches_formula():
    result = score_option({"meets_preferred_window": True, "hours_late": 0, "requires_owner_move": True})
    assert result["score"] == 46
    assert {b["feature"]: b["points"] for b in result["breakdown"]}["requires_owner_move"] == -4
    assert score_option({"hours_late": 2.25})["score"] == -4.5


def test_ties_break_by_start_then_resource():
    opts = [{"resource_id": "b", "start": T % "10:00", "features": {}},
            {"resource_id": "a", "start": T % "10:00", "features": {}},
            {"resource_id": "a", "start": T % "09:00", "features": {}}]
    ranked = score_swap_options(opts)
    assert [(o["start"], o["resource_id"]) for o in ranked] == [(T % "09:00", "a"), (T % "10:00", "a"),
                                                                (T % "10:00", "b")]


def test_unknown_resource_is_reported(seed):
    issues = detect_conflicts([{"resource_id": "laser_9", "start": T % "10:00", "end": T % "11:00"}], [],
                              seed["instruments_by_id"])
    assert issues == [{"type": "unknown_resource", "ref": 0, "resource_id": "laser_9"}]


def test_maintenance_window_excludes_plate_reader_slots(seed):
    req = canonical_request(requester_id="jordan_patel", lab_id="lab_patel",
                            required_capabilities=["fluorescence_plate_read"], duration_minutes=60,
                            search_start="2026-11-05T09:00:00-06:00", search_end="2026-11-05T17:00:00-06:00",
                            preferred_start=None, preferred_end=None, deadline=None, prep=None)
    out = run(seed, req)
    assert out["exclusion_counts"].get("MAINTENANCE_OR_HOURS", 0) > 0
    assert all(o["start"] >= "2026-11-05T13:00:00-06:00" for o in out["options"])
