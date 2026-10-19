"""Prove the generated CSVs contain every planted demo pattern from docs/05.

These tests read the CSVs back from disk (as C3 Code's loader will) rather than
inspecting generator internals.
"""
import csv
import filecmp
import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta

import pytest

from data_gen.generate import DEFAULT_OUT, generate

DEMO_WEEK = "2026-11-02"
POOLABLE_STATES = {"draft", "awaiting_lab_approval", "awaiting_fund_approval"}


# ---------- helpers ----------

def _read(out, name):
    with open(os.path.join(out, name), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _dt(text):
    return datetime.fromisoformat(text)


def _overlaps(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end


def _buffer_ok(intervals, buffer_minutes):
    """Half-open intervals on one resource keep `buffer_minutes` between them."""
    gap = timedelta(minutes=buffer_minutes)
    ordered = sorted(intervals)
    return all(prev[1] + gap <= cur[0] for prev, cur in zip(ordered, ordered[1:]))


def _hours(rows):
    return sum(float(r["session_hours"]) for r in rows)


def _business_days_before(day, n):
    while n:
        day -= timedelta(days=1)
        if day.weekday() < 5:
            n -= 1
    return day


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    path = tmp_path_factory.mktemp("gen")
    generate(str(path))
    return str(path)


@pytest.fixture(scope="module")
def data(out):
    names = ["ilab_style_instrument_bookings", "room_schedule_export", "purchasing_export",
             "weekly_instrument_demand", "labs", "persons", "instruments", "rooms", "supply_skus",
             "stock", "maintenance_windows", "funding_hints", "policies", "vendors"]
    d = {n: _read(out, n + ".csv") for n in names}
    d["bookings"] = d.pop("ilab_style_instrument_bookings")
    d["rooms_res"] = d.pop("room_schedule_export")
    d["orders"] = d.pop("purchasing_export")
    d["persons_by_id"] = {p["person_id"]: p for p in d["persons"]}
    d["inst_by_id"] = {i["instrument_id"]: i for i in d["instruments"]}
    with open(os.path.join(out, "scenario.json"), encoding="utf-8") as fh:
        d["scenario"] = json.load(fh)
    return d


def _demo(data, resource_id):
    return [b for b in data["bookings"] if b["resource_id"] == resource_id and b["week_start"] == DEMO_WEEK]


def _apply_phase1_commit(rows):
    """Chen moves to 13:30-15:30 (same duration); Moreno adds 10:00-13:00 on Confocal-1."""
    moved = []
    for b in rows:
        b = dict(b)
        if b["booking_id"] == "bk_chen_confocal":
            b.update(start_local="2026-11-03T13:30:00-06:00", end_local="2026-11-03T15:30:00-06:00")
        moved.append(b)
    moved.append({"booking_id": "bk_moreno_pending", "resource_id": "confocal_1", "user_id": "morgan",
                  "start_local": "2026-11-03T10:00:00-06:00", "end_local": "2026-11-03T13:00:00-06:00",
                  "session_hours": "3", "flexible": "false", "week_start": DEMO_WEEK})
    return moved


def _intervals(rows):
    return [(_dt(r["start_local"]), _dt(r["end_local"])) for r in rows]


# ---------- determinism and integrity ----------

def test_generation_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    files = generate(str(a))
    generate(str(b))
    match, mismatch, errors = filecmp.cmpfiles(str(a), str(b), files, shallow=False)
    assert mismatch == [] and errors == []


def test_committed_csvs_are_up_to_date(out):
    files = sorted(os.listdir(out))
    match, mismatch, errors = filecmp.cmpfiles(out, DEFAULT_OUT, files, shallow=False)
    assert mismatch == [] and errors == [], "run `python -m data_gen.generate` and commit data_gen/out"


def test_ids_unique_and_references_resolve(data):
    for table, key in [("bookings", "booking_id"), ("rooms_res", "reservation_id"), ("orders", "order_id"),
                       ("persons", "person_id"), ("instruments", "instrument_id"), ("supply_skus", "sku_id")]:
        ids = [r[key] for r in data[table]]
        assert len(ids) == len(set(ids)), table
    labs = {l["lab_id"] for l in data["labs"]}
    rooms = {r["room_id"] for r in data["rooms"]}
    skus = {s["sku_id"]: s for s in data["supply_skus"]}
    vendors = {v["vendor_id"] for v in data["vendors"]}
    for b in data["bookings"]:
        assert b["resource_id"] in data["inst_by_id"] and b["lab_id"] in labs
        assert b["user_id"] in data["persons_by_id"]
    for r in data["rooms_res"]:
        assert r["room_id"] in rooms and r["lab_id"] in labs
    for o in data["orders"]:
        assert o["lab_id"] in labs and o["sku_id"] in skus and o["vendor_id"] == skus[o["sku_id"]]["vendor_id"]
    assert {s["vendor_id"] for s in skus.values()} <= vendors


def test_every_row_is_marked_synthetic(data):
    for table in ("bookings", "rooms_res", "orders", "weekly_instrument_demand", "stock", "funding_hints", "policies"):
        assert all(r["provenance"] == "synthetic:imaging_tuesday_v1" for r in data[table]), table
    assert data["scenario"]["synthetic"] is True


def test_timestamps_carry_correct_chicago_offsets(data):
    for b in data["bookings"]:
        start = _dt(b["start_local"])
        expected = "-06:00" if start.date() >= date(2026, 11, 1) else "-05:00"
        assert b["start_local"].endswith(expected), b["booking_id"]
        utc = datetime.strptime(b["start_utc"], "%Y-%m-%dT%H:%M:%SZ")
        assert utc == start.replace(tzinfo=None) - start.utcoffset()


# ---------- calendar validity ----------

def test_no_overlaps_and_buffers_respected(data):
    by_res = defaultdict(list)
    for b in data["bookings"]:
        by_res[b["resource_id"]].append((_dt(b["start_local"]), _dt(b["end_local"])))
    for res, intervals in by_res.items():
        assert _buffer_ok(intervals, int(data["inst_by_id"][res]["buffer_minutes"])), res
    room_buffer = {r["room_id"]: int(r["buffer_minutes"]) for r in data["rooms"]}
    by_room = defaultdict(list)
    for r in data["rooms_res"]:
        by_room[r["room_id"]].append((_dt(r["start_local"]), _dt(r["end_local"])))
    for room, intervals in by_room.items():
        assert _buffer_ok(intervals, room_buffer[room]), room


def test_sessions_inside_staffed_weekday_hours(data):
    for row in data["bookings"] + data["rooms_res"]:
        start, end = _dt(row["start_local"]), _dt(row["end_local"])
        assert start.weekday() < 5 and start.date() == end.date()
        assert start.hour >= 9 and (end.hour, end.minute) <= (17, 0) and start < end


def test_maintenance_window_on_non_confocal_and_unbooked(data):
    assert len(data["maintenance_windows"]) >= 1
    for mw in data["maintenance_windows"]:
        assert not mw["resource_id"].startswith("confocal")
        start = datetime.strptime(mw["start_local"], "%Y-%m-%d %H:%M")
        end = datetime.strptime(mw["end_local"], "%Y-%m-%d %H:%M")
        for b in data["bookings"]:
            if b["resource_id"] == mw["resource_id"]:
                s, e = _dt(b["start_local"]).replace(tzinfo=None), _dt(b["end_local"]).replace(tzinfo=None)
                assert not _overlaps(s, e, start, end), b["booking_id"]


# ---------- Phase 1 scene: the Tuesday confocal conflict ----------

def test_chen_booking_is_confirmed_flexible_on_confocal_1(data):
    chen = [b for b in data["bookings"] if b["booking_id"] == "bk_chen_confocal"]
    assert len(chen) == 1
    b = chen[0]
    assert (b["resource_id"], b["user_id"], b["lab_id"]) == ("confocal_1", "chen_owner", "lab_chen")
    assert (b["start_local"], b["end_local"]) == ("2026-11-03T10:00:00-06:00", "2026-11-03T12:00:00-06:00")
    assert b["status"] == "confirmed" and b["flexible"] == "true"


def test_moreno_request_conflicts_and_fits_only_after_chen_moves(data):
    c1 = _demo(data, "confocal_1")
    moreno = (_dt("2026-11-03T10:00:00-06:00"), _dt("2026-11-03T13:00:00-06:00"))
    # Proposed bookings from the flow are not seeded.
    ids = {b["booking_id"] for b in data["bookings"]}
    assert not ids & {"bk_moreno_pending", "bk_moreno_prep_pending", "bk_chen_shift_pending"}
    assert not _buffer_ok(_intervals(c1) + [moreno], 15)
    # Chen's new slot is free before the commit, and the full post-commit calendar is valid.
    others = [b for b in c1 if b["booking_id"] != "bk_chen_confocal"]
    chen_new = (_dt("2026-11-03T13:30:00-06:00"), _dt("2026-11-03T15:30:00-06:00"))
    assert _buffer_ok(_intervals(others) + [chen_new], 15)
    assert _buffer_ok(_intervals(_apply_phase1_commit(c1)), 15)


def test_prep_a_free_before_imaging_and_prep_b_taken(data):
    prep = (_dt("2026-11-03T09:00:00-06:00"), _dt("2026-11-03T09:45:00-06:00"))
    prep_a = [r for r in data["rooms_res"] if r["room_id"] == "prep_a"]
    assert _buffer_ok(_intervals(prep_a) + [prep], 10)
    prep_b = [r for r in data["rooms_res"] if r["room_id"] == "prep_b"]
    assert any(_overlaps(*prep, *iv) for iv in _intervals(prep_b))
    assert prep[1] + timedelta(minutes=15) <= _dt("2026-11-03T10:00:00-06:00")


def test_morgan_certified_for_confocal_1_not_confocal_2(data):
    quals = data["persons_by_id"]["morgan"]["qualifications"].split(";")
    assert "confocal_cert" in quals and "confocal_2_cert" not in quals
    assert data["inst_by_id"]["confocal_1"]["required_qualifications"] == "confocal_cert"
    assert data["inst_by_id"]["confocal_2"]["required_qualifications"] == "confocal_2_cert"


def test_moreno_has_no_antibody_or_coverslips_in_stock(data):
    stock = {(s["lab_id"], s["sku_id"]): int(s["quantity"]) for s in data["stock"]}
    assert stock[("lab_moreno", "ANTI_GFP_100")] == 0
    assert stock[("lab_moreno", "COVERSLIP_24")] == 0


def test_last_safe_order_date_is_thursday_oct_29(data):
    skus = {s["sku_id"]: s for s in data["supply_skus"]}
    need_by = date(2026, 11, 2)  # delivered by Mon Nov 2 close, before Tue morning prep
    for sku in ("ANTI_GFP_100", "COVERSLIP_24"):
        cutoff = _business_days_before(need_by, int(skus[sku]["lead_business_days"]))
        assert cutoff == date(2026, 10, 29)
    assert _dt(data["scenario"]["scenario_now_local"]).date() <= date(2026, 10, 29)


# ---------- Phase 2: the three planted department findings ----------

def test_confocal_hours_34_then_37_and_8_of_40(data):
    c1, c2 = _demo(data, "confocal_1"), _demo(data, "confocal_2")
    assert _hours(c1) == 34
    post = _apply_phase1_commit(c1)
    assert _hours(post) == 37 and _hours(post) / 40 == 0.925
    assert _hours(c2) == 8 and _hours(c2) / 40 == 0.20
    assert all(int(data["inst_by_id"][i]["staffed_hours_per_week"]) == 40 for i in ("confocal_1", "confocal_2"))


def test_exactly_8_flexible_hours_can_move_to_confocal_2(data):
    post = _apply_phase1_commit(_demo(data, "confocal_1"))
    c2 = _intervals(_demo(data, "confocal_2"))
    movable = []
    for b in post:
        quals = data["persons_by_id"][b["user_id"]]["qualifications"].split(";")
        if b["flexible"] != "true" or "confocal_2_cert" not in quals:
            continue
        if _buffer_ok(c2 + [iv for iv in _intervals(movable)] + _intervals([b]), 15):
            movable.append(b)
    moved = _hours(movable)
    assert moved == 8
    c1_after, c2_after = _hours(post) - moved, _hours(_demo(data, "confocal_2")) + moved
    assert (c1_after, c2_after) == (29, 16)
    assert c1_after / 40 == 0.725 and c2_after / 40 == 0.40
    assert c1_after + c2_after == 45


def _pool_groups(orders, window_days=7):
    groups = defaultdict(list)
    for o in orders:
        if o["state"] in POOLABLE_STATES:
            groups[(o["sku_id"], o["vendor_id"], o["ship_to"])].append(o)
    pools = []
    for rows in groups.values():
        created = sorted(_dt(r["created_local"]) for r in rows)
        if len({r["lab_id"] for r in rows}) >= 2 and created[-1] - created[0] <= timedelta(days=window_days):
            pools.append(rows)
    return pools


def _moreno_draft_order():
    return {"order_id": "po_moreno_antigfp", "lab_id": "lab_moreno", "sku_id": "ANTI_GFP_100",
            "vendor_id": "vendor_bioreagent", "quantity": "2", "state": "draft",
            "created_local": "2026-10-28T10:05:00-05:00", "ship_to": "north_bio_receiving"}


def test_no_pooling_opportunity_until_moreno_drafts_order(data):
    assert _pool_groups(data["orders"]) == []
    pools = _pool_groups(data["orders"] + [_moreno_draft_order()])
    assert len(pools) == 1
    assert sorted(o["lab_id"] for o in pools[0]) == ["lab_moreno", "lab_patel"]


def test_pooled_antigfp_savings_are_95(data):
    sku = next(s for s in data["supply_skus"] if s["sku_id"] == "ANTI_GFP_100")
    base, tier_min, tier = int(sku["base_price_usd"]), int(sku["tier_min_qty"]), int(sku["tier_price_usd"])
    ship = int(sku["shipping_per_order_usd"])
    pool = _pool_groups(data["orders"] + [_moreno_draft_order()])[0]
    qtys = [int(o["quantity"]) for o in pool]
    assert sorted(qtys) == [2, 3]
    unpooled = sum(q * base + ship for q in qtys)
    total = sum(qtys)
    assert total >= tier_min
    pooled = total * tier + ship
    assert (unpooled, pooled, unpooled - pooled) == (640, 545, 95)
    assert total * (base - tier) == 75 and (len(qtys) - 1) * ship == 20


def test_pooling_decoys_are_blocked(data):
    tips = [o for o in data["orders"] if o["sku_id"] == "TIPS_200"]
    assert len({o["lab_id"] for o in tips}) == 2 and len({o["ship_to"] for o in tips}) == 2
    dapi = [o for o in data["orders"] if o["sku_id"] == "DAPI_1ML"]
    assert len({o["lab_id"] for o in dapi}) == 2
    assert any(o["state"] not in POOLABLE_STATES for o in dapi)


def test_flow_2_underused_10_percent_and_persistently_low(data):
    flow2 = _demo(data, "flow_2")
    assert _hours(flow2) == 4 and _hours(flow2) / 40 == 0.10
    hist = [r for r in data["weekly_instrument_demand"] if r["resource_id"] == "flow_2"]
    booked = [float(r["booked_hours"]) for r in sorted(hist, key=lambda r: r["week_start"])]
    assert booked == [6, 5, 7, 4, 6, 5]
    assert sum(1 for h in booked if h / 40 < 0.25) >= 4
    # Busy sibling provides overflow demand to match against.
    flow1 = [r for r in data["weekly_instrument_demand"] if r["resource_id"] == "flow_1"]
    assert all(float(r["requested_hours"]) > float(r["booked_hours"]) for r in flow1)


# ---------- forecast input ----------

def test_history_series_match_spec_and_booking_rows(data):
    expected = {"confocal_1": [24, 29, 31, 28, 33, 34], "confocal_2": [7, 10, 8, 9, 6, 8]}
    demand = defaultdict(dict)
    for r in data["weekly_instrument_demand"]:
        demand[r["resource_id"]][r["week_start"]] = r
    weeks = data["scenario"]["history_week_starts"]
    assert len(weeks) == 6 and weeks[-1] == "2026-10-26"
    for res, rows in demand.items():
        assert sorted(rows) == weeks
        for week, r in rows.items():
            from_rows = _hours([b for b in data["bookings"] if b["resource_id"] == res and b["week_start"] == week])
            assert float(r["booked_hours"]) == from_rows
            assert float(r["requested_hours"]) >= float(r["booked_hours"])
    for res, series in expected.items():
        assert [float(demand[res][w]["booked_hours"]) for w in weeks] == series


def test_funding_hint_is_restricted_planning_signal(data):
    assert len(data["funding_hints"]) == 1
    hint = data["funding_hints"][0]
    assert hint["restricted_flag"] == "true" and "Synthetic" in hint["note"]


def test_policy_records_hold_doc_09_weights(data):
    pol = {p["key"]: float(p["value"]) for p in data["policies"]}
    assert pol["score.weight.meets_preferred_window"] == 50
    assert pol["score.weight.hours_late"] == -2
    assert pol["score.weight.room_switch_count"] == -3
    assert pol["score.weight.requires_owner_move"] == -4
    assert pol["score.weight.extra_internal_cost_units"] == -1
    assert pol["pooling.window_days"] == 7
