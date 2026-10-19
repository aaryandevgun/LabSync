"""Capability and qualification checks for instruments and rooms."""
from .values import as_list


def capability_match(resource, required_capabilities):
    """Return the required capabilities the resource lacks (empty list = match)."""
    have = set(as_list(resource.get("capabilities")))
    return sorted(set(as_list(required_capabilities)) - have)


def check_qualifications(person, resource):
    """Can `person` operate `resource` unsupervised?

    Returns {"eligible": bool, "missing": [...], "code": None | "NOT_QUALIFIED"}.
    """
    have = set(as_list(person.get("qualifications")))
    missing = sorted(set(as_list(resource.get("required_qualifications"))) - have)
    return {
        "eligible": not missing,
        "missing": missing,
        "code": "NOT_QUALIFIED" if missing else None,
    }


def equivalent(resource_a, resource_b):
    """Capability-equivalent resources: same kind and same capability set."""
    return (resource_a.get("kind") == resource_b.get("kind")
            and set(as_list(resource_a.get("capabilities"))) == set(as_list(resource_b.get("capabilities"))))
