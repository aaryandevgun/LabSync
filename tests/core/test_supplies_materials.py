"""Supplies, pooled-order savings and find_shared_materials (T-SUPPLY-*)."""
from labsync_core.materials import find_shared_materials
from labsync_core.savings import pooled_savings
from labsync_core.supplies import check_stock, quote, supply_readiness

MORENO_ITEMS = [{"sku_id": "ANTI_GFP_100", "quantity": 2}, {"sku_id": "COVERSLIP_24", "quantity": 1}]
MORENO_DRAFT = {"order_id": "po_moreno_antigfp", "lab_id": "lab_moreno", "sku_id": "ANTI_GFP_100",
                "vendor_id": "vendor_bioreagent", "quantity": 2, "state": "draft",
                "created_local": "2026-10-28T10:05:00-05:00", "ship_to": "north_bio_receiving"}


def test_stock_only_counts_own_lab(seed):
    rows = check_stock("lab_moreno", MORENO_ITEMS, seed["stock"])
    assert [(r["sku_id"], r["on_hand"], r["shortfall"]) for r in rows] == [
        ("ANTI_GFP_100", 0, 2), ("COVERSLIP_24", 0, 1)]  # Chen's 3 coverslips are not Moreno's


def test_quote_is_estimate_with_one_shipping_per_vendor(seed):
    q = quote(MORENO_ITEMS, seed["skus_by_id"])
    assert q["status"] == "estimate" and q["total_usd"] == 2 * 120 + 20 + 18 + 12
    assert q["shipping_by_vendor"] == {"vendor_bioreagent": 20, "vendor_glassco": 12}


def test_readiness_cutoff_thursday_oct_29(seed):
    r = supply_readiness("lab_moreno", MORENO_ITEMS, seed["skus_by_id"], seed["stock"], "2026-10-28",
                         "2026-11-03T09:00:00-06:00")
    assert r["status"] == "order_needed" and r["code"] is None
    assert r["last_safe_order_date"] == "2026-10-29"
    assert r["ready_at"] == "2026-10-30T17:00:00-05:00"


def test_sched_006_order_after_cutoff_is_too_late(seed):
    r = supply_readiness("lab_moreno", MORENO_ITEMS, seed["skus_by_id"], seed["stock"], "2026-10-30",
                         "2026-11-03T09:00:00-06:00")
    assert r["status"] == "too_late" and r["code"] == "ORDER_TOO_LATE"
    assert r["ready_at"] == "2026-11-03T17:00:00-06:00"


def test_in_stock_needs_no_order(seed):
    r = supply_readiness("lab_moreno", [{"sku_id": "PBS_1L", "quantity": 2}], seed["skus_by_id"], seed["stock"],
                         "2026-10-28", "2026-11-03T09:00:00-06:00")
    assert r["status"] == "in_stock" and r["ready_at"] is None


def test_supply_001_pooled_math_is_95(seed):
    s = pooled_savings(seed["skus_by_id"]["ANTI_GFP_100"], [2, 3])
    assert (s["unpooled_total_usd"], s["pooled_total_usd"], s["potential_savings_usd"]) == (640, 545, 95)
    assert (s["volume_component_usd"], s["shipping_component_usd"]) == (75, 20)
    assert s["status"] == "potential" and s["realized_savings_usd"] is None
    assert "640" in s["formula"] and "545" in s["formula"]


def test_below_tier_pool_still_saves_shipping_only(seed):
    s = pooled_savings(seed["skus_by_id"]["ANTI_GFP_100"], [1, 2])
    assert (s["volume_component_usd"], s["shipping_component_usd"], s["potential_savings_usd"]) == (0, 20, 20)


def test_no_pool_before_moreno_drafts(seed):
    out = find_shared_materials(seed["orders"], seed["skus_by_id"], seed["labs"], seed["policies"])
    assert out["pools"] == []


def test_moreno_draft_creates_exactly_the_planted_pool(seed):
    out = find_shared_materials(seed["orders"] + [MORENO_DRAFT], seed["skus_by_id"], seed["labs"], seed["policies"])
    assert len(out["pools"]) == 1
    pool = out["pools"][0]
    assert pool["sku_id"] == "ANTI_GFP_100" and pool["lab_ids"] == ["lab_moreno", "lab_patel"]
    assert pool["quantities_by_lab"] == {"lab_moreno": 2, "lab_patel": 3}
    assert pool["savings"]["potential_savings_usd"] == 95
    assert pool["required_approvals"] == ["moreno_mgr", "patel_mgr", "dept_admin"]
    assert pool["state"] == "detected"


def test_supply_002_incompatible_pools_are_excluded_with_reasons(seed):
    out = find_shared_materials(seed["orders"] + [MORENO_DRAFT], seed["skus_by_id"], seed["labs"], seed["policies"])
    reasons = {(e["sku_id"], e["reason"]) for e in out["exclusions"]}
    assert ("TIPS_200", "DIFFERENT_SHIP_TO") in reasons
    assert ("DAPI_1ML", "STATE_LOCKED") in reasons


def test_window_policy_excludes_old_orders(seed):
    old = dict(MORENO_DRAFT, created_local="2026-10-10T10:00:00-05:00")
    out = find_shared_materials(seed["orders"] + [old], seed["skus_by_id"], seed["labs"], seed["policies"])
    assert out["pools"] == []
    assert ("ANTI_GFP_100", "OUTSIDE_WINDOW") in {(e["sku_id"], e["reason"]) for e in out["exclusions"]}
