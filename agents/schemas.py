"""Structured-output schemas for the three agents, plus grounding checks.

  * PARSED_GOAL_SCHEMA (Lab Agent request parsing) lives in labsync_tools.schemas and is
    re-exported here; `plan_create_draft` validates it before any write.
  * SWAP_PROPOSAL_SCHEMA: the Conflict Negotiator's recommendation on one move request.
  * RECOMMENDATION_CARD_SCHEMA / OPTIMIZER_OUTPUT_SCHEMA: the Department Optimizer's cards.

Schema validity is not enough: the grounding checks compare an agent output with the tool
result it was given, so a card can't carry a number or record id the tools never returned
(docs/02 gate: "genuinely reads tool-returned values ... not hallucinated KPIs").
"""
import json
import re

from labsync_core.values import to_dt
from labsync_tools.schemas import PARSED_GOAL_SCHEMA, validate_parsed_goal  # noqa: F401 (re-export)

from .jsonschema_lite import validate

_DT = {"type": "string", "format": "date-time", "description": "ISO 8601 with offset"}
_SLOT = {"type": "object", "additionalProperties": False, "required": ["start", "end"],
         "properties": {"start": _DT, "end": _DT}}
_IDS = {"type": "array", "items": {"type": "string", "minLength": 1}}

SWAP_PROPOSAL_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "SwapProposalRecommendation",
    "description": "The Conflict Negotiator's recommendation to a booking owner. The owner decides.",
    "type": "object", "additionalProperties": False,
    "required": ["approvalId", "bookingId", "recommendation", "from", "to", "reasons", "ownerImpact",
                 "alternatives", "evidenceIds", "dataTimestamp", "decidedBy"],
    "properties": {
        "approvalId": {"type": "string"},
        "bookingId": {"type": "string"},
        "recommendation": {"enum": ["approve", "reject", "suggest_other_time"]},
        "from": _SLOT,
        "to": _SLOT,
        "reasons": {"type": "array", "minItems": 1, "maxItems": 4, "items": {"type": "string", "maxLength": 200}},
        "ownerImpact": {
            "type": "object", "additionalProperties": False,
            "required": ["sameDay", "sameDuration", "personConflicts"],
            "properties": {"sameDay": {"type": "boolean"}, "sameDuration": {"type": "boolean"},
                           "personConflicts": _IDS}},
        "alternatives": {
            "type": "array", "maxItems": 3,
            "description": "Owner-side time windows to search instead; unverified until the scheduler re-checks them.",
            "items": {"type": "object", "additionalProperties": False, "required": ["earliestStart", "latestEnd", "note"],
                      "properties": {"earliestStart": _DT, "latestEnd": _DT, "note": {"type": "string", "maxLength": 160}}}},
        "evidenceIds": dict(_IDS, minItems=1),
        "dataTimestamp": _DT,
        "decidedBy": {"const": "owner", "description": "Always the human owner; the agent never decides."},
    },
}

KINDS = {
    # kind -> (impact unit, next-step action, estimate field holding the headline value, scale)
    "pooled_order": ("USD", "propose_shared_order", "potential_savings_usd", 1),
    "overload_rebalance": ("hours", "review_transfer_plan", "movable_hours", 1),
    "underuse": ("percent_of_staffed_hours", "publish_available_capacity", "utilization", 100),
}

RECOMMENDATION_CARD_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "RecommendationCard",
    "type": "object", "additionalProperties": False,
    "required": ["insightId", "kind", "headline", "evidenceSentence", "summary", "impact", "evidenceIds",
                 "assumptions", "confidence", "limitations", "exclusions", "requiredApprovals", "nextStep",
                 "advisory"],
    "properties": {
        "insightId": {"type": "string"},
        "kind": {"enum": list(KINDS)},
        "headline": {"type": "string", "maxLength": 90},
        "evidenceSentence": {"type": "string", "maxLength": 220},
        "summary": {"type": "string", "maxLength": 700},
        "impact": {
            "type": "object", "additionalProperties": False, "required": ["value", "unit", "status", "label"],
            "properties": {"value": {"type": "number"},
                           "unit": {"enum": sorted({k[0] for k in KINDS.values()})},
                           "status": {"const": "potential"},
                           "label": {"type": "string", "maxLength": 80}}},
        "evidenceIds": dict(_IDS, minItems=1),
        "assumptions": dict(_IDS, minItems=1),
        "confidence": {"enum": ["high", "medium", "low"]},
        "limitations": _IDS,
        "exclusions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["ids", "reason"],
            "properties": {"ids": _IDS, "reason": {"type": "string"}}}},
        "requiredApprovals": dict(_IDS, minItems=1),
        "nextStep": {"type": "object", "additionalProperties": False, "required": ["action", "label"],
                     "properties": {"action": {"enum": [k[1] for k in KINDS.values()]},
                                    "label": {"type": "string", "maxLength": 60}}},
        "advisory": {"type": "boolean"},
    },
}

OPTIMIZER_OUTPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "DepartmentOptimizerOutput",
    "type": "object", "additionalProperties": False,
    "required": ["snapshotId", "weekStart", "dataTimestamp", "cards", "alsoDetected", "notes"],
    "properties": {
        "snapshotId": {"type": "string"},
        "weekStart": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "dataTimestamp": _DT,
        "cards": {"type": "array", "maxItems": 3, "items": RECOMMENDATION_CARD_SCHEMA},
        "alsoDetected": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["insightId", "note"],
            "properties": {"insightId": {"type": "string"}, "note": {"type": "string", "maxLength": 200}}}},
        "notes": _IDS,
    },
}

SCHEMAS = {"ParsedGoal": PARSED_GOAL_SCHEMA, "SwapProposalRecommendation": SWAP_PROPOSAL_SCHEMA,
           "RecommendationCard": RECOMMENDATION_CARD_SCHEMA, "DepartmentOptimizerOutput": OPTIMIZER_OUTPUT_SCHEMA}


# ---------------------------------------------------------------- grounding

def check_swap(proposal, change_request):
    """Validate a negotiator output against the liaison_get_change_request result it was given.
    Returns a list of errors (empty = OK)."""
    errors = validate(proposal, SWAP_PROPOSAL_SCHEMA)
    if errors:
        return errors
    impact = change_request["impact"]
    if proposal["approvalId"] != change_request["approval_id"]:
        errors.append("approvalId does not match the request")
    if proposal["bookingId"] != impact["booking_id"]:
        errors.append("bookingId does not match the request")
    for key in ("from", "to"):
        if {k: to_dt(v) for k, v in proposal[key].items()} != {k: to_dt(v) for k, v in impact[key].items()}:
            errors.append("%s times differ from the request" % key)
    facts = {"sameDay": impact["same_day"], "sameDuration": impact["same_duration"],
             "personConflicts": sorted(impact["person_conflicts"])}
    if dict(proposal["ownerImpact"], personConflicts=sorted(proposal["ownerImpact"]["personConflicts"])) != facts:
        errors.append("ownerImpact differs from the tool result %s" % facts)
    if proposal["recommendation"] == "approve" and (impact["person_conflicts"] or not impact["flexible"]):
        errors.append("cannot recommend approval: the owner has an overlapping session or the booking is not flexible")
    if proposal["recommendation"] == "suggest_other_time" and not proposal["alternatives"]:
        errors.append("suggest_other_time needs at least one alternative window")
    if proposal["recommendation"] != "suggest_other_time" and proposal["alternatives"]:
        errors.append("alternatives are only allowed with suggest_other_time")
    allowed = {change_request["approval_id"], impact["booking_id"], impact["resource_id"]}
    allowed |= {b["booking_id"] for b in impact["your_other_bookings_that_day"]}
    stray = sorted(set(proposal["evidenceIds"]) - allowed)
    if stray:
        errors.append("evidenceIds not in the tool result: %s" % stray)
    return errors


def _numbers(text):
    return {float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def _allowed_numbers(insight):
    found = _numbers(json.dumps(insight))
    found |= {round(n * 100, 1) for n in found if 0 < n < 1}  # shares shown as percentages
    return found


def check_card(card, insight):
    """Validate one recommendation card against the insight dict an insight_find_* tool returned."""
    errors = validate(card, RECOMMENDATION_CARD_SCHEMA)
    if errors:
        return errors
    unit, action, field, scale = KINDS[insight["kind"]]
    if card["insightId"] != insight["insight_id"] or card["kind"] != insight["kind"]:
        errors.append("insightId/kind do not match the tool result")
        return errors
    if card["impact"]["unit"] != unit:
        errors.append("%s impact must be in %s (never mix dollars and hours)" % (insight["kind"], unit))
    if card["nextStep"]["action"] != action:
        errors.append("%s next step must be %s" % (insight["kind"], action))
    expected = round(float(insight["estimate"][field]) * scale, 1)
    if round(float(card["impact"]["value"]), 1) != expected:
        errors.append("impact value %s differs from the tool's %s" % (card["impact"]["value"], expected))
    allowed_ids = set(insight["candidate_ids"]) | {insight["insight_id"]}
    allowed_ids |= {i for e in insight.get("exclusions", []) for i in e.get("ids", e.get("order_ids", []))}
    stray = sorted(set(card["evidenceIds"]) - allowed_ids)
    if stray:
        errors.append("evidenceIds not in the tool result: %s" % stray)
    if set(card["requiredApprovals"]) != set(insight["required_approvals"]):
        errors.append("requiredApprovals differ from the tool result %s" % insight["required_approvals"])
    allowed = _allowed_numbers(insight)
    for key in ("headline", "evidenceSentence", "summary"):
        stray = sorted(n for n in _numbers(card[key]) if n not in allowed)
        if stray:
            errors.append("%s has numbers the tools did not return: %s" % (key, stray))
    for text in (card["headline"], card["evidenceSentence"], card["summary"], card["impact"]["label"]):
        claim = re.search(r"\b(realized|saved|guaranteed|completed)\b",
                          re.sub(r"\bnot (realized|guaranteed|completed)\b", "", text.lower()))
        if claim:
            errors.append("card claims a realized or guaranteed result (%r)" % claim.group(1))
    if insight["kind"] == "underuse" and not card["advisory"]:
        errors.append("underuse cards are advisory")
    return errors


def check_optimizer_output(output, insights):
    """Validate the optimizer's whole output. `insights` is every insight dict the finders returned."""
    errors = validate(output, OPTIMIZER_OUTPUT_SCHEMA)
    if errors:
        return errors
    by_id = {i["insight_id"]: i for i in insights}
    kinds = [c["kind"] for c in output["cards"]]
    if len(kinds) != len(set(kinds)):
        errors.append("at most one card per insight kind")
    for card in output["cards"]:
        insight = by_id.get(card["insightId"])
        if insight is None:
            errors.append("card %s is not a tool-returned insight" % card["insightId"])
            continue
        first = next(i for i in insights if i["kind"] == insight["kind"])
        if insight is not first:
            errors.append("card %s is not the top-ranked %s insight" % (card["insightId"], insight["kind"]))
        errors += ["%s: %s" % (card["insightId"], e) for e in check_card(card, insight)]
    shown = {c["insightId"] for c in output["cards"]}
    for extra in output["alsoDetected"]:
        if extra["insightId"] not in by_id:
            errors.append("alsoDetected %s is not a tool-returned insight" % extra["insightId"])
    missing = sorted(set(by_id) - shown - {e["insightId"] for e in output["alsoDetected"]})
    if missing:
        errors.append("insights neither shown nor listed in alsoDetected: %s" % missing)
    return errors
