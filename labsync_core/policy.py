"""Read Policy records (key/value rows) with documented defaults.

Defaults are the docs/09 demo heuristics, so code behaves identically when no
Policy rows are supplied.
"""
from .values import as_num

DEFAULTS = {
    "score.weight.meets_preferred_window": 50,
    "score.weight.hours_late": -2,
    "score.weight.room_switch_count": -3,
    "score.weight.requires_owner_move": -4,
    "score.weight.extra_internal_cost_units": -1,
    "scheduling.slot_step_minutes": 15,
    "scheduling.move_step_minutes": 30,
    "scheduling.max_options": 3,
    "scheduling.prep_transition_minutes": 15,
    "pooling.window_days": 7,
    "utilization.overload_threshold": 0.85,
    "underuse.utilization_threshold": 0.25,
    "underuse.min_low_weeks_of_6": 4,
    "forecast.ewma_alpha": 0.35,
}


def policy_map(policies=None):
    """Merge Policy rows (`{"key": ..., "value": ...}`) over the defaults."""
    merged = dict(DEFAULTS)
    for row in policies or []:
        merged[row["key"]] = as_num(row["value"])
    return merged


def get(policies, key):
    """Look up one key from Policy rows or an already-merged policy map."""
    if isinstance(policies, dict):
        return policies.get(key, DEFAULTS[key])
    return policy_map(policies)[key]
