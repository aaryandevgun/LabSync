"""Pooled-order savings arithmetic (docs/05, docs/09 C).

Canonical: separate 2x120+20 + 3x120+20 = 640; pooled 5x105+20 = 545; potential 95
(75 volume + 20 shipping). Always "potential": nothing here is a realized saving.
"""
from .supplies import unit_price
from .values import as_num


def separate_order_cost(sku, quantity):
    return unit_price(sku, quantity) * quantity + as_num(sku["shipping_per_order_usd"])


def pooled_savings(sku, quantities):
    """Compare separate orders against one pooled order for the same SKU and vendor.

    Args: sku row; quantities: list of per-order quantities.
    Returns: {"unpooled_total_usd", "pooled_total_usd", "potential_savings_usd",
              "volume_component_usd", "shipping_component_usd", "pooled_unit_price_usd",
              "total_quantity", "formula", "realized_savings_usd": None, "status": "potential"}
    """
    quantities = [as_num(q) for q in quantities]
    shipping = as_num(sku["shipping_per_order_usd"])
    total_qty = sum(quantities)
    pooled_unit = unit_price(sku, total_qty)
    unpooled = sum(separate_order_cost(sku, q) for q in quantities)
    pooled = pooled_unit * total_qty + shipping
    volume = sum((unit_price(sku, q) - pooled_unit) * q for q in quantities)
    shipping_saved = shipping * (len(quantities) - 1)
    parts = " + ".join("%sx%s+%s" % (q, unit_price(sku, q), shipping) for q in quantities)
    return {
        "unpooled_total_usd": unpooled, "pooled_total_usd": pooled,
        "potential_savings_usd": unpooled - pooled,
        "volume_component_usd": volume, "shipping_component_usd": shipping_saved,
        "pooled_unit_price_usd": pooled_unit, "total_quantity": total_qty,
        "formula": "separate %s = %s; pooled %sx%s+%s = %s; potential %s" % (
            parts, unpooled, total_qty, pooled_unit, shipping, pooled, unpooled - pooled),
        "realized_savings_usd": None, "status": "potential",
    }
