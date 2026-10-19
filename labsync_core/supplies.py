"""Stock checks, synthetic quotes and supply readiness against an experiment date.

Prices, tiers and lead times are synthetic assumptions; a quote is never a
purchase and readiness is an estimate (actual ETA is vendor-dependent).
"""
from datetime import datetime, time

from .conflicts import DEFAULT_TZ
from .values import add_business_days, as_num, business_days_before, to_date, to_dt


def check_stock(lab_id, items, stock):
    """Compare requested quantities with the lab's own stock (other labs' stock is never counted).

    Args: items [{"sku_id", "quantity"}]; stock rows {lab_id, sku_id, quantity}.
    Returns: [{"sku_id", "needed", "on_hand", "shortfall"}]
    """
    on_hand = {}
    for row in stock:
        if row["lab_id"] == lab_id:
            on_hand[row["sku_id"]] = on_hand.get(row["sku_id"], 0) + as_num(row["quantity"])
    return [{"sku_id": it["sku_id"], "needed": as_num(it["quantity"]), "on_hand": on_hand.get(it["sku_id"], 0),
             "shortfall": max(0, as_num(it["quantity"]) - on_hand.get(it["sku_id"], 0))} for it in items]


def unit_price(sku, quantity):
    """Tier price applies when one order's quantity reaches the tier minimum."""
    tier_min = as_num(sku.get("tier_min_qty"), None)
    if tier_min is not None and quantity >= tier_min:
        return as_num(sku["tier_price_usd"])
    return as_num(sku["base_price_usd"])


def quote(items, skus):
    """Synthetic quote: per-line price (with tier), one shipping charge per vendor.

    Args: items [{"sku_id", "quantity"}]; skus dict sku_id -> sku row.
    Returns: {"lines": [...], "shipping_by_vendor": {...}, "total_usd", "assumptions": [...]}
    """
    lines, shipping = [], {}
    for it in items:
        sku = skus[it["sku_id"]]
        qty = as_num(it["quantity"])
        price = unit_price(sku, qty)
        lines.append({"sku_id": it["sku_id"], "vendor_id": sku["vendor_id"], "quantity": qty,
                      "unit_price_usd": price, "subtotal_usd": price * qty,
                      "lead_business_days": as_num(sku["lead_business_days"])})
        shipping[sku["vendor_id"]] = max(shipping.get(sku["vendor_id"], 0), as_num(sku["shipping_per_order_usd"]))
    total = sum(l["subtotal_usd"] for l in lines) + sum(shipping.values())
    return {"lines": lines, "shipping_by_vendor": shipping, "total_usd": total, "status": "estimate",
            "assumptions": ["synthetic price assumptions", "one shipping charge per vendor order"]}


def _previous_business_day(day):
    return business_days_before(day, 1)


def supply_readiness(lab_id, items, skus, stock, order_date, needed_by, tz=DEFAULT_TZ):
    """Can the shortfall arrive before the experiment needs it?

    Delivery is assumed at close (17:00) of the order date + lead business days, and must
    land by close of the business day before `needed_by` (docs/05: order by Thu Oct 29
    for a Tue Nov 3 morning prep with a 2-day lead time).

    Returns: {"status": "in_stock" | "order_needed" | "too_late", "code": None | "ORDER_TOO_LATE",
              "items": [...], "last_safe_order_date", "ready_at" (ISO, when every item is on hand)}
    """
    needed_dt = to_dt(needed_by).astimezone(tz)
    deliver_by = _previous_business_day(needed_dt.date())
    order_day = to_date(order_date)
    shortfalls = [s for s in check_stock(lab_id, items, stock) if s["shortfall"] > 0]
    rows, cutoffs, deliveries = [], [], []
    for s in shortfalls:
        lead = int(as_num(skus[s["sku_id"]]["lead_business_days"]))
        cutoff = business_days_before(deliver_by, lead)
        delivery = add_business_days(order_day, lead)
        rows.append(dict(s, lead_business_days=lead, last_safe_order_date=cutoff.isoformat(),
                         estimated_delivery_date=delivery.isoformat(), on_time=delivery <= deliver_by))
        cutoffs.append(cutoff)
        deliveries.append(delivery)
    if not shortfalls:
        return {"status": "in_stock", "code": None, "items": [], "last_safe_order_date": None, "ready_at": None}
    ready_day = max(deliveries)
    ready_at = datetime.combine(ready_day, time(17, 0), tzinfo=tz)
    late = any(not r["on_time"] for r in rows)
    return {"status": "too_late" if late else "order_needed", "code": "ORDER_TOO_LATE" if late else None,
            "items": rows, "last_safe_order_date": min(cutoffs).isoformat(), "ready_at": ready_at.isoformat(),
            "assumptions": ["delivery at close of business on the estimated day", "actual ETA is vendor-dependent"]}


def ready_at_for_scheduling(readiness):
    """The `supplies_ready_at` value to pass to find_slots (None when stock covers the plan)."""
    return readiness.get("ready_at")

