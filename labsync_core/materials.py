"""find_shared_materials: detect poolable orders for the same SKU across labs (docs/02 M2.1, docs/09 C).

A pool needs: the same SKU and vendor (so storage/handling match), orders still
in an editable state, the same ship-to location, at least two labs, all inside
the pooling window, and a positive saving after all costs. Every rejected
grouping is reported with a reason so the admin can see what was excluded.
"""
from datetime import timedelta

from . import policy
from .savings import pooled_savings
from .values import to_dt

POOLABLE_STATES = {"draft", "awaiting_lab_approval", "awaiting_fund_approval"}


def find_shared_materials(orders, skus, labs, policies=None):
    """Find pooled-order opportunities.

    Args:
        orders: order rows {order_id, lab_id, sku_id, vendor_id, quantity, state, created_local, ship_to}.
        skus: dict sku_id -> sku row. labs: lab rows (manager_id used for approvals).
        policies: Policy rows / map (`pooling.window_days`).
    Returns: {"pools": [...], "exclusions": [{"sku_id", "order_ids", "reason"}]}
        Each pool: pool_id, sku_id, vendor_id, ship_to, order_ids, lab_ids, quantities_by_lab,
        savings (see savings.pooled_savings), required_approvals, state "detected", assumptions.
    """
    window = timedelta(days=float(policy.get(policy.policy_map(policies) if not isinstance(policies, dict)
                                             else policies, "pooling.window_days")))
    managers = {lab["lab_id"]: lab["manager_id"] for lab in labs}
    by_sku = {}
    for order in orders:
        by_sku.setdefault((order["sku_id"], order["vendor_id"]), []).append(order)
    pools, exclusions = [], []
    for (sku_id, vendor_id), group in sorted(by_sku.items()):
        if len({o["lab_id"] for o in group}) < 2:
            continue
        locked = [o for o in group if o["state"] not in POOLABLE_STATES]
        if locked:
            exclusions.append({"sku_id": sku_id, "order_ids": sorted(o["order_id"] for o in locked),
                               "reason": "STATE_LOCKED"})
        open_orders = [o for o in group if o["state"] in POOLABLE_STATES]
        by_dest = {}
        for o in open_orders:
            by_dest.setdefault(o["ship_to"], []).append(o)
        if len(by_dest) > 1 and all(len({o["lab_id"] for o in rows}) < 2 for rows in by_dest.values()):
            exclusions.append({"sku_id": sku_id, "order_ids": sorted(o["order_id"] for o in open_orders),
                               "reason": "DIFFERENT_SHIP_TO"})
        for ship_to, rows in sorted(by_dest.items()):
            if len({o["lab_id"] for o in rows}) < 2:
                continue
            anchor = max(to_dt(o["created_local"]) for o in rows)
            in_window = [o for o in rows if anchor - to_dt(o["created_local"]) <= window]
            stale = [o for o in rows if o not in in_window]
            if stale:
                exclusions.append({"sku_id": sku_id, "order_ids": sorted(o["order_id"] for o in stale),
                                   "reason": "OUTSIDE_WINDOW"})
            if len({o["lab_id"] for o in in_window}) < 2:
                continue
            in_window.sort(key=lambda o: o["order_id"])
            savings = pooled_savings(skus[sku_id], [o["quantity"] for o in in_window])
            if savings["potential_savings_usd"] <= 0:
                exclusions.append({"sku_id": sku_id, "order_ids": [o["order_id"] for o in in_window],
                                   "reason": "NO_SAVINGS"})
                continue
            lab_ids = sorted({o["lab_id"] for o in in_window})
            qty_by_lab = {}
            for o in in_window:
                qty_by_lab[o["lab_id"]] = qty_by_lab.get(o["lab_id"], 0) + int(float(o["quantity"]))
            pools.append({
                "pool_id": "pool_%s_%s" % (sku_id.lower(), "_".join(l.replace("lab_", "") for l in lab_ids)),
                "sku_id": sku_id, "vendor_id": vendor_id, "ship_to": ship_to,
                "order_ids": [o["order_id"] for o in in_window], "lab_ids": lab_ids,
                "quantities_by_lab": qty_by_lab, "savings": savings,
                "required_approvals": [managers[l] for l in lab_ids] + ["dept_admin"],
                "state": "detected",
                "assumptions": ["synthetic vendor tier", "single pooled shipping destination",
                                "separate cost allocation per lab; no grant money moves",
                                "finance policy approval required"],
            })
    return {"pools": pools, "exclusions": exclusions}
