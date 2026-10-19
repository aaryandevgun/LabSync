"""The ParsedGoal schema (docs/01 P1.1) and its deterministic validator.

The Lab Agent's request-parsing output must match PARSED_GOAL_SCHEMA. Field names
follow docs/01 exactly (camelCase). `validate_parsed_goal` is what actually guards
writes: an LLM output that fails it never becomes a plan (T-AGENT-002).
"""
from labsync_core.values import to_dt

STEP_KINDS = ("prep_room", "instrument", "analysis")
SOURCES = ("stated", "inferred")

PARSED_GOAL_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ParsedGoal",
    "type": "object",
    "additionalProperties": False,
    "required": ["labId", "requesterId", "goalSummary", "desiredStart", "preferredEnd", "deadline", "steps",
                 "requiredCapabilities", "supplies", "missingInformation", "confidence"],
    "properties": {
        "labId": {"type": "string"},
        "requesterId": {"type": "string"},
        "goalSummary": {"type": "string", "maxLength": 200},
        "desiredStart": {"type": ["string", "null"], "format": "date-time",
                         "description": "Start of the preferred window, ISO 8601 with offset"},
        "preferredEnd": {"type": ["string", "null"], "format": "date-time",
                         "description": "End of the preferred window"},
        "deadline": {"type": ["string", "null"], "format": "date-time",
                     "description": "Latest acceptable end of the instrument session"},
        "steps": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["stepId", "kind", "title", "durationMinutes", "requiredCapabilities", "dependsOn",
                         "source", "required"],
            "properties": {
                "stepId": {"type": "string"},
                "kind": {"enum": list(STEP_KINDS)},
                "title": {"type": "string"},
                "durationMinutes": {"type": "integer", "minimum": 15, "maximum": 480, "multipleOf": 15},
                "requiredCapabilities": {"type": "array", "items": {"type": "string"}},
                "dependsOn": {"type": "array", "items": {"type": "string"}},
                "source": {"enum": list(SOURCES)},
                "required": {"type": "boolean"},
            }}},
        "requiredCapabilities": {"type": "array", "items": {"type": "string"}},
        "supplies": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["skuId", "quantity", "source"],
            "properties": {"skuId": {"type": "string"}, "quantity": {"type": "integer", "minimum": 1},
                           "source": {"enum": list(SOURCES)}}}},
        "missingInformation": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}


def _is_iso(value):
    try:
        to_dt(value)
        return True
    except (TypeError, ValueError):
        return False


def validate_parsed_goal(goal, known_skus=(), known_capabilities=()):
    """Validate a ParsedGoal dict. Returns (errors, warnings); any error means: do not write.

    Unknown SKUs are errors (no invented products). Unknown capabilities are warnings: the
    plan can be saved, and find_slots will report that nothing supports them.
    """
    errors, warnings = [], []
    if not isinstance(goal, dict):
        return ["goal must be an object"], []
    props = PARSED_GOAL_SCHEMA["properties"]
    for key in PARSED_GOAL_SCHEMA["required"]:
        if key not in goal:
            errors.append("missing field: %s" % key)
    for key in goal:
        if key not in props:
            errors.append("unexpected field: %s" % key)
    if errors:
        return errors, warnings
    for key in ("labId", "requesterId", "goalSummary"):
        if not isinstance(goal[key], str) or not goal[key]:
            errors.append("%s must be a non-empty string" % key)
    for key in ("desiredStart", "preferredEnd", "deadline"):
        if goal[key] is not None and not _is_iso(goal[key]):
            errors.append("%s must be ISO 8601 with a timezone offset" % key)
    conf = goal["confidence"]
    if not isinstance(conf, (int, float)) or isinstance(conf, bool) or not 0 <= conf <= 1:
        errors.append("confidence must be a number between 0 and 1")
    for key in ("requiredCapabilities", "missingInformation"):
        if not isinstance(goal[key], list) or not all(isinstance(x, str) for x in goal[key]):
            errors.append("%s must be a list of strings" % key)
    steps = goal["steps"] if isinstance(goal["steps"], list) else []
    if not isinstance(goal["steps"], list):
        errors.append("steps must be a list")
    step_ids = set()
    step_props = props["steps"]["items"]["properties"]
    for i, step in enumerate(steps):
        where = "steps[%d]" % i
        if not isinstance(step, dict):
            errors.append("%s must be an object" % where)
            continue
        missing = [k for k in props["steps"]["items"]["required"] if k not in step]
        extra = [k for k in step if k not in step_props]
        if missing or extra:
            errors.append("%s fields: missing %s, unexpected %s" % (where, missing, extra))
            continue
        if step["kind"] not in STEP_KINDS:
            errors.append("%s.kind must be one of %s" % (where, STEP_KINDS))
        if step["source"] not in SOURCES:
            errors.append("%s.source must be stated or inferred" % where)
        dur = step["durationMinutes"]
        if not isinstance(dur, int) or isinstance(dur, bool) or not 15 <= dur <= 480 or dur % 15:
            errors.append("%s.durationMinutes must be a multiple of 15 between 15 and 480" % where)
        if not isinstance(step["required"], bool):
            errors.append("%s.required must be true or false" % where)
        if step["stepId"] in step_ids:
            errors.append("%s.stepId duplicated" % where)
        step_ids.add(step["stepId"])
    for i, step in enumerate(steps):
        if isinstance(step, dict) and isinstance(step.get("dependsOn"), list):
            for dep in step["dependsOn"]:
                if dep not in step_ids:
                    errors.append("steps[%d].dependsOn references unknown step %s" % (i, dep))
    instrument_steps = [s for s in steps if isinstance(s, dict) and s.get("kind") == "instrument"]
    if len(instrument_steps) > 1:
        errors.append("only one instrument step per plan is supported")
    if instrument_steps and goal["desiredStart"] is None and "desiredStart" not in goal["missingInformation"]:
        errors.append("desiredStart is null but not listed in missingInformation")
    if not isinstance(goal["supplies"], list):
        errors.append("supplies must be a list")
    else:
        for i, item in enumerate(goal["supplies"]):
            if not isinstance(item, dict) or set(item) != {"skuId", "quantity", "source"}:
                errors.append("supplies[%d] must have exactly skuId, quantity, source" % i)
                continue
            if known_skus and item["skuId"] not in known_skus:
                errors.append("supplies[%d].skuId %s is not in the catalog" % (i, item["skuId"]))
            if not isinstance(item["quantity"], int) or isinstance(item["quantity"], bool) or item["quantity"] < 1:
                errors.append("supplies[%d].quantity must be a positive integer" % i)
            if item["source"] not in SOURCES:
                errors.append("supplies[%d].source must be stated or inferred" % i)
    if known_capabilities:
        wanted = set(goal["requiredCapabilities"]) if isinstance(goal["requiredCapabilities"], list) else set()
        for s in steps:
            if isinstance(s, dict) and isinstance(s.get("requiredCapabilities"), list):
                wanted |= set(s["requiredCapabilities"])
        unknown = sorted(wanted - set(known_capabilities))
        if unknown:
            warnings.append("no resource in the catalog offers: %s" % ", ".join(unknown))
    return errors, warnings
