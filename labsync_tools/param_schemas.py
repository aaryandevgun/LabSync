"""JSON Schema for every tool parameter, so hosts (the LLM client, a UI) can describe and check
tool inputs. `registry.TOOLS[name]["input_schema"]` combines these per tool."""
from .schemas import PARSED_GOAL_SCHEMA

_ID = {"type": "string", "minLength": 1}
_DATE = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$", "description": "Monday of the week, YYYY-MM-DD"}

PARAMS = {
    "approval_id": dict(_ID, description="Approval request id, e.g. appr_0007"),
    "booking_id": dict(_ID, description="Booking id from contingent_moves"),
    "capabilities": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                     "description": "Catalog capability ids, e.g. confocal_imaging"},
    "decision": {"enum": ["approve", "reject"]},
    "entity_id": dict(_ID, description="Any record id to filter audit events by"),
    "idempotency_key": dict(_ID, description="Retries with the same key return the same result"),
    "insight_id": dict(_ID, description="Insight id returned by an insight_find_* tool"),
    "items": {"type": "array", "minItems": 1, "items": {
        "type": "object", "additionalProperties": False, "required": ["sku_id", "quantity"],
        "properties": {"sku_id": {"type": "string"}, "quantity": {"type": "integer", "minimum": 1}}}},
    "lab_id": dict(_ID, description="Lab id, e.g. lab_moreno"),
    "message": {"type": "string", "maxLength": 300, "description": "Short note shown to the owner (in-app only)"},
    "needed_by": {"type": "string", "description": "ISO 8601 time with offset the supplies must be on hand"},
    "option_id": dict(_ID, description="option_id returned by scheduler_find_slots"),
    "parsed_goal": PARSED_GOAL_SCHEMA,
    "plan_id": dict(_ID, description="Plan id from plan_create_draft"),
    "proposal_id": dict(_ID, description="Proposal id from booking_propose"),
    "reason": {"type": "string", "maxLength": 300},
    "request_id": dict(_ID, description="Correlation id for one request"),
    "resource_id": dict(_ID, description="Instrument or room id, e.g. confocal_1"),
    "resource_type": {"enum": ["instrument", "room", "any"]},
    "sku_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
    "user_id": dict(_ID, description="Person id, e.g. morgan"),
    "week_start": _DATE,
}


def input_schema(parameters, required):
    schema = {"type": "object", "additionalProperties": False,
              "properties": {p: {k: v for k, v in PARAMS[p].items() if k != "$schema"} for p in parameters},
              "required": list(required)}
    return schema
