"""A small JSON Schema validator (stdlib only) for the subset the agent schemas use.

Supported keywords: type (incl. lists and "null"), enum, const, required, properties,
additionalProperties (false only), items, minItems, maxItems, minLength, maxLength,
minimum, maximum, multipleOf, pattern. `format` and `description` are ignored here;
date-time values are checked by the deterministic validators that guard writes.
C3 Code can hand the same schemas to the platform's own structured-output feature.
"""
import re

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def validate(value, schema, path="$"):
    """Return a list of error strings; empty means valid."""
    errors = []
    types = schema.get("type")
    if types is not None:
        types = types if isinstance(types, list) else [types]
        if not any(_TYPES[t](value) for t in types):
            return ["%s: expected %s" % (path, " or ".join(types))]
    if "const" in schema and value != schema["const"]:
        errors.append("%s: must be %r" % (path, schema["const"]))
    if "enum" in schema and value not in schema["enum"]:
        errors.append("%s: must be one of %s" % (path, schema["enum"]))
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append("%s: missing %s" % (path, key))
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errors.append("%s: unexpected %s" % (path, key))
        for key, sub in props.items():
            if key in value:
                errors += validate(value[key], sub, "%s.%s" % (path, key))
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append("%s: at least %d items" % (path, schema["minItems"]))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append("%s: at most %d items" % (path, schema["maxItems"]))
        if "items" in schema:
            for i, item in enumerate(value):
                errors += validate(item, schema["items"], "%s[%d]" % (path, i))
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append("%s: too short" % path)
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append("%s: longer than %d" % (path, schema["maxLength"]))
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append("%s: does not match %s" % (path, schema["pattern"]))
    if _TYPES["number"](value):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append("%s: below %s" % (path, schema["minimum"]))
        if "maximum" in schema and value > schema["maximum"]:
            errors.append("%s: above %s" % (path, schema["maximum"]))
        if "multipleOf" in schema and value % schema["multipleOf"]:
            errors.append("%s: not a multiple of %s" % (path, schema["multipleOf"]))
    return errors
