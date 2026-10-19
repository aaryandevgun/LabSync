"""evals/: the suites are current, complete, gradable, and the scorer catches wrong answers."""
import copy
import os

import pytest

from agents import specs
from evals import build, negotiation_cases
from evals.score import HERE, load, score_case
from labsync_core.values import violates_buffer
from labsync_tools import registry
from labsync_tools.memory_repo import InMemoryRepository

INTAKE, NEGOTIATION, OPTIMIZER = load("intake"), load("negotiation"), load("optimizer")
ALL = INTAKE + NEGOTIATION + OPTIMIZER


def by_id(cid):
    return copy.deepcopy(next(c for c in ALL if c["id"] == cid))


def test_jsonl_files_are_current():
    for name, text in build.rendered().items():
        with open(os.path.join(HERE, name), encoding="utf-8") as fh:
            assert fh.read() == text, "run python3 -m evals.build (%s is stale)" % name


def test_suite_sizes_and_unique_ids():
    assert len(INTAKE) >= 30 and len(NEGOTIATION) == 10 and len(OPTIMIZER) == 3
    ids = [c["id"] for c in ALL]
    assert len(ids) == len(set(ids))


def test_doc_06_harness_categories_are_covered():
    cats = {c["category"] for c in ALL}
    for needed in ("canonical", "missing_date", "unsupported_capability", "owner_conflict", "untrained_user",
                   "order_lead_time", "shared_purchasing", "duplicate", "permission_boundary",
                   "forecast_question", "empty_data"):
        assert needed in cats, needed
    assert sum(1 for c in INTAKE if c["category"] == "messy") >= 4


@pytest.mark.parametrize("case", ALL, ids=[c["id"] for c in ALL])
def test_reference_answers_pass(case):
    result = score_case(case, case["reference"])
    assert result["passed"], [c for c in result["checks"] if not c["passed"]]


@pytest.mark.parametrize("case", INTAKE, ids=[c["id"] for c in INTAKE])
def test_every_intake_case_checks_something(case):
    result = score_case(case, case["reference"])
    assert len(result["checks"]) >= 2


def test_inserted_eval_bookings_respect_the_calendar():
    repo = InMemoryRepository()
    instruments = {i["instrument_id"]: i for i in repo.list_records("Instrument")}
    for s in negotiation_cases.SCENARIOS:
        for row in s["setup"].get("insert_bookings", []):
            buf = int(instruments[row["resource_id"]]["buffer_minutes"])
            for b in repo.list_records("Booking"):
                if b["resource_id"] == row["resource_id"]:
                    assert not violates_buffer(row["start_local"], row["end_local"], b["start_local"], b["end_local"], buf), \
                        (s["id"], b["booking_id"])


def test_optimizer_input_matches_the_agent_few_shot():
    shot = next(s for s in specs.few_shots(registry.OPTIMIZER) if s["id"] == "opt-after-stage-1")
    assert OPTIMIZER[0]["input"] == shot["input"]


# ---------------------------------------------------------------- the scorer catches wrong answers

def failing(case, output, tool_calls=None):
    result = score_case(case, output, tool_calls)
    assert not result["passed"]
    return [c for c in result["checks"] if not c["passed"]]


def test_intake_wrong_dst_offset_fails():
    case = by_id("intake-001")
    out = case["reference"]
    out["desiredStart"] = "2026-11-03T09:00:00-05:00"  # CDT on a CST date is 08:00 local
    assert failing(case, out)[0]["score"] == "correct_action"


def test_intake_invented_capability_and_supply_fail():
    case = by_id("intake-019")
    out = case["reference"]
    out["steps"] = [{"stepId": "run", "kind": "instrument", "title": "EM", "durationMinutes": 180,
                     "requiredCapabilities": ["electron_microscopy"], "dependsOn": [], "source": "stated", "required": True}]
    scores = {c["score"] for c in failing(case, out)}
    assert "no_hallucinated_price" in scores
    case = by_id("intake-033")
    out = case["reference"]
    out["supplies"].append({"skuId": "PBS_1L", "quantity": 1, "source": "inferred"})
    assert any(c["score"] == "no_hallucinated_price" for c in failing(case, out))


def test_intake_plan_for_a_non_planning_message_fails():
    case = by_id("intake-037")
    goal = by_id("intake-001")["reference"]
    assert any(c["score"] == "no_false_commit" for c in failing(case, goal))


def test_intake_injection_trace_with_commit_fails():
    case = by_id("intake-036")
    failed = failing(case, case["reference"], ["plan_create_draft", "booking_commit_approved"])
    assert failed[0]["score"] == "no_false_commit"
    failed = failing(case, case["reference"], [])
    assert failed[0]["score"] == "tool_used"


def test_negotiation_approving_a_conflict_fails():
    case = by_id("neg-006")
    out = case["reference"]
    out.update(recommendation="approve", alternatives=[])
    scores = {c["score"] for c in failing(case, out)}
    assert {"correct_action", "no_hallucinated_price"} <= scores


def test_negotiation_leaking_funding_fails():
    case = by_id("neg-007")
    out = case["reference"]
    out["reasons"].append("Chen bills this to the R01 grant.")
    assert any("grant" in c["detail"] for c in failing(case, out))


def test_negotiation_recommending_on_a_denied_or_decided_request_fails():
    assert failing(by_id("neg-008"), by_id("neg-001")["reference"])
    assert failing(by_id("neg-010"), by_id("neg-001")["reference"])


def test_optimizer_wrong_or_realized_value_fails():
    case = by_id("opt-001")
    out = case["reference"]
    out["cards"][0]["impact"]["value"] = 100
    assert failing(case, out)
    case = by_id("opt-003")
    out = case["reference"]
    out["cards"][2]["summary"] += " We should sell it."
    assert any("sell" in c["detail"] for c in failing(case, out))
    case = by_id("opt-002")
    out = case["reference"]
    out["cards"] = [c for c in out["cards"] if c["kind"] != "overload_rebalance"]
    assert failing(case, out)
