"""score_swap_options: transparent weighted ranking of feasible options (docs/09 A).

score = 50*meetsPreferredWindow - 2*hoursLate - 3*roomSwitchCount
        - 4*requiresOwnerMove - 1*extraInternalCostUnits

Weights come from Policy records; they are demo heuristics, not learned values.
Ranking never overrides hard constraints: only already-feasible options go in.
"""
from . import policy

FEATURES = [
    ("meets_preferred_window", "score.weight.meets_preferred_window"),
    ("hours_late", "score.weight.hours_late"),
    ("room_switch_count", "score.weight.room_switch_count"),
    ("requires_owner_move", "score.weight.requires_owner_move"),
    ("extra_internal_cost_units", "score.weight.extra_internal_cost_units"),
]


def score_option(features, policies=None):
    """Score one option. Returns {"score": float, "breakdown": [{feature, value, weight, points}]}."""
    weights = policy.policy_map(policies) if not isinstance(policies, dict) else policies
    breakdown = []
    total = 0.0
    for feature, key in FEATURES:
        value = features.get(feature, 0)
        value = float(value) if not isinstance(value, bool) else (1.0 if value else 0.0)
        weight = float(policy.get(weights, key))
        points = weight * value
        total += points
        breakdown.append({"feature": feature, "value": value, "weight": weight, "points": points})
    return {"score": round(total, 4), "breakdown": breakdown}


def score_swap_options(options, policies=None):
    """Score and rank options.

    Args:
        options: dicts each with "features" (see FEATURES), "start" (ISO) and "resource_id".
        policies: Policy rows or a merged policy map.
    Returns: new list sorted by score desc, then start, then resource_id (deterministic
        tie-break), each option copied with "score" and "score_breakdown" added.
    """
    scored = []
    for option in options:
        result = score_option(option.get("features", {}), policies)
        scored.append(dict(option, score=result["score"], score_breakdown=result["breakdown"]))
    return sorted(scored, key=lambda o: (-o["score"], o["start"], o["resource_id"]))
