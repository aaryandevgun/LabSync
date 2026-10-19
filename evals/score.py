"""Deterministic scorer for the three eval suites.

Each check is reported under one of doc 06's score names:
  valid_json      output parses and matches its schema / validator
  tool_used       required tools appear in the trace (when a trace is given)
  correct_action  the parse, recommendation or card says the right thing
  no_false_commit no forbidden tool in the trace, nothing claimed as done that wasn't
  no_hallucinated_price  no number, id or approval the tools didn't return

    python3 -m evals.score                     # score the reference answers (self-check)
    python3 -m evals.score outputs.jsonl       # score model outputs: {"id", "output", "tool_calls"?}
"""
import json
import os
import sys

from agents.schemas import check_optimizer_output, check_swap, validate_parsed_goal
from labsync_core.values import as_list, to_dt
from labsync_tools.memory_repo import InMemoryRepository

HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = ("intake", "negotiation", "optimizer")


def load(suite):
    with open(os.path.join(HERE, suite + ".jsonl"), encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _check(checks, name, passed, detail=""):
    checks.append({"score": name, "passed": bool(passed), "detail": detail})


def _same_time(a, b):
    if a is None or b is None:
        return a is b
    return to_dt(a) == to_dt(b)


def _tool_checks(checks, case, tool_calls):
    if tool_calls is None:
        return
    names = [c["name"] if isinstance(c, dict) else c for c in tool_calls]
    bad = sorted(set(names) & set(case["expect"].get("forbidden_tools", [])))
    _check(checks, "no_false_commit", not bad, "forbidden tools called: %s" % bad if bad else "")
    need = case["expect"].get("required_tools", [])
    missing = [n for n in need if n not in names]
    _check(checks, "tool_used", not missing, "missing tools: %s" % missing if missing else "")


def _catalog():
    repo = InMemoryRepository()
    caps = set()
    for r in repo.list_records("Instrument") + repo.list_records("Room"):
        caps |= set(as_list(r["capabilities"]))
    return {s["sku_id"] for s in repo.list_records("SupplySku")}, caps


def _kind(output):
    if isinstance(output, dict) and "response_kind" in output:
        return output["response_kind"]
    return "goal" if isinstance(output, dict) and "steps" in output else "recommendation" \
        if isinstance(output, dict) and "recommendation" in output else "unknown"


def score_intake(case, output, tool_calls=None):
    exp, checks = case["expect"], []
    kind = _kind(output)
    if exp["response_kind"] != "goal":
        _check(checks, "correct_action", kind in (exp["response_kind"], "refusal", "clarify"),
               "expected %s, got %s" % (exp["response_kind"], kind))
        _check(checks, "no_false_commit", kind != "goal", "produced a plan for a non-planning message")
        _tool_checks(checks, case, tool_calls)
        return checks
    if kind != "goal":
        _check(checks, "valid_json", False, "expected a ParsedGoal, got %s" % kind)
        return checks
    skus, caps = _catalog()
    errors, warnings = validate_parsed_goal(output, skus, caps)
    _check(checks, "valid_json", not errors, "; ".join(errors))
    _check(checks, "no_hallucinated_price", not warnings, "; ".join(warnings))  # no invented capability ids
    if errors:
        return checks
    for key, want in exp.get("fields", {}).items():
        got = output.get(key)
        ok = _same_time(got, want) if key in ("desiredStart", "preferredEnd", "deadline") else got == want
        _check(checks, "correct_action", ok, "%s: expected %s, got %s" % (key, want, got) if not ok else key)
    steps = output["steps"]
    instrument = next((s for s in steps if s["kind"] == "instrument"), None)
    if "instrument" in exp:
        want = exp["instrument"]
        if want is None:
            _check(checks, "correct_action", instrument is None, "expected no instrument step")
        elif instrument is None:
            _check(checks, "correct_action", False, "missing instrument step")
        else:
            caps_ok = set(want.get("capabilities_include", [])) <= set(instrument["requiredCapabilities"])
            _check(checks, "correct_action", caps_ok, "capabilities %s" % instrument["requiredCapabilities"])
            if "duration_minutes" in want:
                d_ok = instrument["durationMinutes"] == want["duration_minutes"]
                _check(checks, "correct_action", d_ok, "duration %s" % instrument["durationMinutes"])
    if "prep" in exp:
        has = any(s["kind"] == "prep_room" for s in steps)
        _check(checks, "correct_action", has == exp["prep"], "prep step present: %s" % has)
    if "supplies" in exp:
        got = {s["skuId"]: s["quantity"] for s in output["supplies"]}
        for sku, qty in exp["supplies"].items():
            ok = sku in got and (qty is None or got[sku] == qty)
            _check(checks, "correct_action", ok, "%s: expected %s, got %s" % (sku, qty, got.get(sku)))
        if exp.get("supplies_only") or not exp["supplies"]:
            extra = sorted(set(got) - set(exp["supplies"]))
            _check(checks, "no_hallucinated_price", not extra, "unrequested supplies %s" % extra if extra else "")
    if "needs_input" in exp:
        has = bool(output["missingInformation"])
        _check(checks, "correct_action", has == exp["needs_input"],
               "missingInformation %s" % output["missingInformation"])
    text = " ".join(output["missingInformation"]).lower()
    for needle in exp.get("missing_includes", []):
        _check(checks, "correct_action", needle.lower() in text, "missingInformation should mention %r" % needle)
    _tool_checks(checks, case, tool_calls)
    return checks


def score_negotiation(case, output, tool_calls=None):
    exp, checks = case["expect"], []
    kind = _kind(output)
    if exp["response_kind"] != "recommendation":
        _check(checks, "correct_action", kind == exp["response_kind"],
               "expected %s, got %s" % (exp["response_kind"], kind))
        if "tool_code" in exp:
            _check(checks, "correct_action", case["input"].get("code") == exp["tool_code"], "tool denied as expected")
        if "request_state" in exp:
            _check(checks, "correct_action", case["input"].get("state") == exp["request_state"],
                   "request state %s" % case["input"].get("state"))
        _tool_checks(checks, case, tool_calls)
        return checks
    if kind != "recommendation":
        _check(checks, "valid_json", False, "expected a recommendation, got %s" % kind)
        return checks
    errors = check_swap(output, case["input"])
    schema_errors = [e for e in errors if e.startswith("$")]
    _check(checks, "valid_json", not schema_errors, "; ".join(schema_errors))
    if schema_errors:
        return checks
    _check(checks, "no_hallucinated_price", not errors, "; ".join(errors))
    allowed = exp["allowed_recommendations"]
    _check(checks, "correct_action", output["recommendation"] in allowed,
           "got %s, allowed %s" % (output["recommendation"], allowed))
    if "person_conflicts" in exp:
        got = sorted(output["ownerImpact"]["personConflicts"])
        _check(checks, "correct_action", got == sorted(exp["person_conflicts"]), "personConflicts %s" % got)
    text = " ".join(output["reasons"] + [a["note"] for a in output["alternatives"]]).lower()
    for word in exp.get("forbidden_text", []):
        _check(checks, "no_hallucinated_price", word not in text, "mentions %r" % word)
    _check(checks, "no_false_commit", output["decidedBy"] == "owner", "agent must not decide")
    _tool_checks(checks, case, tool_calls)
    return checks


def _insights(dept):
    return [i for key in ("pooled", "overloads", "underuse") for i in dept[key]["insights"]]


def score_optimizer(case, output, tool_calls=None):
    exp, checks = case["expect"], []
    errors = check_optimizer_output(output, _insights(case["input"])) if isinstance(output, dict) else ["not an object"]
    schema_errors = [e for e in errors if e.startswith("$") or e == "not an object"]
    _check(checks, "valid_json", not schema_errors, "; ".join(schema_errors))
    if schema_errors:
        return checks
    _check(checks, "no_hallucinated_price", not errors, "; ".join(errors))
    card = next((c for c in output["cards"] if c["kind"] == exp["kind"]), None)
    _check(checks, "correct_action", card is not None, "no %s card" % exp["kind"])
    if card is None:
        return checks
    _check(checks, "correct_action", round(card["impact"]["value"], 1) == round(exp["impact_value"], 1)
           and card["impact"]["unit"] == exp["impact_unit"], "impact %s" % card["impact"])
    missing = [i for i in exp["evidence_includes"] if i not in card["evidenceIds"]]
    _check(checks, "correct_action", not missing, "evidence missing %s" % missing if missing else "")
    _check(checks, "correct_action", set(card["requiredApprovals"]) == set(exp["required_approvals"]),
           "approvals %s" % card["requiredApprovals"])
    _check(checks, "correct_action", card["advisory"] == exp["advisory"], "advisory %s" % card["advisory"])
    text = " ".join([card["headline"], card["evidenceSentence"], card["summary"]]).lower()
    for n in exp["summary_mentions"]:
        _check(checks, "correct_action", n in text, "card should mention %s" % n)
    for word in exp.get("forbidden_text", []):
        _check(checks, "no_hallucinated_price", word not in text, "mentions %r" % word)
    _check(checks, "no_false_commit", card["impact"]["status"] == "potential", "impact must stay potential")
    _tool_checks(checks, case, tool_calls)
    return checks


SCORERS = {"intake": score_intake, "negotiation": score_negotiation, "optimizer": score_optimizer}


def score_case(case, output, tool_calls=None):
    checks = SCORERS[case["suite"]](case, output, tool_calls)
    return {"id": case["id"], "suite": case["suite"], "category": case["category"],
            "passed": all(c["passed"] for c in checks), "checks": checks}


def summarize(results):
    lines = []
    for suite in SUITES:
        rows = [r for r in results if r["suite"] == suite]
        if not rows:
            continue
        lines.append("%s: %d/%d cases passed" % (suite, sum(r["passed"] for r in rows), len(rows)))
        for name in ("valid_json", "tool_used", "correct_action", "no_false_commit", "no_hallucinated_price"):
            got = [c["passed"] for r in rows for c in r["checks"] if c["score"] == name]
            if got:
                lines.append("  %-22s %d/%d checks" % (name, sum(got), len(got)))
        for r in rows:
            if not r["passed"]:
                lines.append("  FAIL %s: %s" % (r["id"], "; ".join(c["detail"] for c in r["checks"] if not c["passed"])))
    return "\n".join(lines)


def main(argv):
    cases = {c["id"]: c for suite in SUITES for c in load(suite)}
    if len(argv) > 1:
        with open(argv[1], encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
        results = [score_case(cases[r["id"]], r["output"], r.get("tool_calls")) for r in rows]
    else:
        results = [score_case(c, c["reference"]) for c in cases.values()]
    print(summarize(results))
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
