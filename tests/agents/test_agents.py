"""agents/: prompts, tool lists, schemas, few-shots and grounding checks."""
import copy
import os

import pytest

from agents import export, specs
from agents.jsonschema_lite import validate
from agents.schemas import (PARSED_GOAL_SCHEMA, check_card, check_optimizer_output, check_swap,
                            validate_parsed_goal)
from labsync_core.values import overlaps
from labsync_tools import registry
from labsync_tools import tools as T
from labsync_tools.memory_repo import InMemoryRepository

from . import scenarios as S

DOC_06_FIRST_LINES = {
    registry.LAB: "You are LabSync Lab Planner, a research-operations assistant for a participating",
    registry.NEGOTIATOR: "You assist only your assigned lab. Evaluate incoming proposed schedule moves",
    registry.OPTIMIZER: "You are LabSync Department Intelligence. Identify exactly three insight types:",
}


@pytest.fixture(scope="module")
def after():
    return S.department_after_stage_1()


@pytest.mark.parametrize("agent,actor", [(registry.LAB, "morgan"), (registry.NEGOTIATOR, "chen_owner"),
                                         (registry.OPTIMIZER, "dept_admin")])
def test_agents_load_with_docs_06_instructions_and_filled_placeholders(agent, actor):
    spec = specs.load(agent, InMemoryRepository(), actor)
    assert spec["system_prompt"].startswith(DOC_06_FIRST_LINES[agent])
    assert "{{" not in spec["system_prompt"]
    assert 3 <= len(spec["few_shots"]) <= 5
    assert [t["name"] for t in spec["tools"]] == registry.tools_for(agent)
    assert all("actor_id" not in t["parameters"] for t in spec["tools"])


def test_lab_prompt_lists_the_live_catalog():
    prompt = specs.load(registry.LAB, InMemoryRepository(), "morgan")["system_prompt"]
    for token in ("confocal_imaging", "wet_prep", "flow_analysis", "ANTI_GFP_100", "COVERSLIP_24"):
        assert token in prompt


def test_tool_lists_keep_agents_inside_their_lane():
    negotiator = {t["name"]: t["effect"] for t in specs.tool_specs(registry.NEGOTIATOR)}
    assert set(negotiator.values()) <= {"read_only", "read_scoped"}
    optimizer = set(registry.tools_for(registry.OPTIMIZER))
    assert not optimizer & {"booking_propose", "booking_commit_approved", "liaison_request_change"}
    for agent in specs.AGENTS:
        assert "approval_record" not in registry.tools_for(agent)


def test_exported_json_files_are_current():
    for rel, text in export.rendered().items():
        with open(os.path.join(specs.HERE, rel), encoding="utf-8") as fh:
            assert fh.read() == text, "run python3 -m agents.export (%s is stale)" % rel


# ---------------------------------------------------------------- Lab Agent

LAB_SHOTS = specs.few_shots(registry.LAB)


@pytest.mark.parametrize("shot", LAB_SHOTS, ids=[s["id"] for s in LAB_SHOTS])
def test_lab_few_shots_are_valid_parsed_goals_that_the_tool_accepts(shot):
    repo = InMemoryRepository()
    goal = shot["output"]
    assert validate(goal, PARSED_GOAL_SCHEMA) == []
    skus = {s["sku_id"] for s in repo.list_records("SupplySku")}
    caps = set(specs.catalog_vocabulary(repo)[0].split(", "))
    errors, warnings = validate_parsed_goal(goal, skus, caps)
    assert (errors, warnings) == ([], [])
    assert (goal["labId"], goal["requesterId"]) == (shot["context"]["lab_id"], shot["context"]["actor_id"])
    result = T.plan_create_draft(repo, shot["context"]["actor_id"], goal)
    assert result["status"] == "ok", result


def test_canonical_lab_few_shot_finds_the_docs_options():
    repo = InMemoryRepository()
    goal = next(s for s in LAB_SHOTS if s["id"] == "lab-canonical")["output"]
    plan_id = T.plan_create_draft(repo, "morgan", goal)["plan_id"]
    found = T.scheduler_find_slots(repo, "morgan", plan_id)
    best = found["options"][0]
    assert (best["kind"], best["start"], best["end"]) == ("owner_move", "2026-11-03T10:00:00-06:00",
                                                          "2026-11-03T13:00:00-06:00")
    assert best["prep"]["resource_id"] == "prep_a"


def test_missing_date_few_shot_asks_instead_of_searching():
    repo = InMemoryRepository()
    goal = next(s for s in LAB_SHOTS if s["id"] == "lab-missing-date")["output"]
    plan = T.plan_create_draft(repo, "morgan", goal)
    assert plan["needs_input"] == ["desiredStart"]
    assert T.scheduler_find_slots(repo, "morgan", plan["plan_id"])["code"] == "MISSING_INFORMATION"


# ---------------------------------------------------------------- Conflict Negotiator

NEG_SHOTS = specs.few_shots(registry.NEGOTIATOR)


def test_canonical_negotiator_input_is_the_real_tool_result():
    shot = next(s for s in NEG_SHOTS if s["id"] == "neg-canonical-approve")
    assert shot["input"] == S.canonical_change_request()


@pytest.mark.parametrize("shot", NEG_SHOTS, ids=[s["id"] for s in NEG_SHOTS])
def test_negotiator_few_shots_pass_grounding(shot):
    impact = shot["input"]["impact"]
    # Hypothetical inputs must still be internally consistent with how the tool computes facts.
    own = [b for b in impact["your_other_bookings_that_day"] if b["user_id"] == impact["booked_by"]
           and overlaps(b["start"], b["end"], impact["to"]["start"], impact["to"]["end"])]
    assert sorted(b["booking_id"] for b in own) == sorted(impact["person_conflicts"])
    assert check_swap(shot["output"], shot["input"]) == []


def test_negotiator_covers_each_recommendation():
    assert {s["output"]["recommendation"] for s in NEG_SHOTS} == {"approve", "reject", "suggest_other_time"}


@pytest.mark.parametrize("mutate,needle", [
    (lambda p: p.update(recommendation="approve", alternatives=[]), "cannot recommend approval"),
    (lambda p: p["to"].update(start="2026-11-03T13:00:00-06:00"), "to times differ"),
    (lambda p: p["ownerImpact"].update(personConflicts=[]), "ownerImpact differs"),
    (lambda p: p["evidenceIds"].append("bk_moreno_secret"), "evidenceIds not in the tool result"),
    (lambda p: p.update(alternatives=[]), "needs at least one alternative"),
    (lambda p: p.update(decidedBy="agent"), "must be 'owner'"),
])
def test_swap_grounding_rejects_bad_outputs(mutate, needle):
    shot = copy.deepcopy(next(s for s in NEG_SHOTS if s["id"] == "neg-person-conflict"))
    mutate(shot["output"])
    assert any(needle in e for e in check_swap(shot["output"], shot["input"]))


# ---------------------------------------------------------------- Department Optimizer

OPT_SHOTS = specs.few_shots(registry.OPTIMIZER)


def test_optimizer_inputs_are_the_real_tool_results(after):
    by_id = {s["id"]: s for s in OPT_SHOTS}
    assert by_id["opt-after-stage-1"]["input"] == after
    assert by_id["opt-before-stage-1"]["input"] == S.department_before_stage_1()
    assert by_id["opt-permission-denied"]["input"] == S.department_denied()


@pytest.mark.parametrize("shot", OPT_SHOTS, ids=[s["id"] for s in OPT_SHOTS])
def test_optimizer_few_shots_pass_grounding(shot):
    insights = S.all_insights(shot["input"]) if "pooled" in shot["input"] else []
    assert check_optimizer_output(shot["output"], insights) == []


def test_after_stage_1_output_shows_the_three_planted_findings():
    out = next(s for s in OPT_SHOTS if s["id"] == "opt-after-stage-1")["output"]
    impacts = {c["kind"]: (c["impact"]["value"], c["impact"]["unit"]) for c in out["cards"]}
    assert impacts == {"pooled_order": (95, "USD"), "overload_rebalance": (8.0, "hours"),
                       "underuse": (10.0, "percent_of_staffed_hours")}
    assert out["cards"][2]["evidenceIds"][-1] == "flow_2"


def test_forecast_quoted_in_the_overload_card_matches_the_tool():
    from tests.tools.helpers import CANONICAL_GOAL, authorize_owner_move
    repo = InMemoryRepository()
    _, proposal_id = authorize_owner_move(repo, copy.deepcopy(CANONICAL_GOAL))
    T.booking_commit_approved(repo, "morgan", proposal_id, "k")
    fc = T.forecast_resource_demand(repo, "dept_admin", "confocal_1")["forecast"]
    card = next(s for s in OPT_SHOTS if s["id"] == "opt-after-stage-1")["output"]["cards"][1]
    quoted = "%g h (%g-%g), MAE %.1f" % (fc["predicted_hours"], fc["low"], fc["high"], fc["mae"])
    assert any(quoted in line for line in card["limitations"]), quoted


def _card(kind):
    out = next(s for s in OPT_SHOTS if s["id"] == "opt-after-stage-1")["output"]
    return copy.deepcopy(next(c for c in out["cards"] if c["kind"] == kind))


def _insight(after, kind):
    return next(i for i in S.all_insights(after) if i["kind"] == kind)


@pytest.mark.parametrize("kind,mutate,needle", [
    ("pooled_order", lambda c: c["impact"].update(value=120), "differs from the tool"),
    ("pooled_order", lambda c: c.update(summary=c["summary"] + " Annual impact $1,140."), "numbers the tools did not return"),
    ("pooled_order", lambda c: c["impact"].update(unit="hours"), "never mix dollars and hours"),
    ("pooled_order", lambda c: c.update(headline="We saved $95 on antibody"), "realized or guaranteed"),
    ("pooled_order", lambda c: c["requiredApprovals"].remove("patel_mgr"), "requiredApprovals differ"),
    ("overload_rebalance", lambda c: c["evidenceIds"].append("bk_chen_confocal"), "evidenceIds not in the tool result"),
    ("overload_rebalance", lambda c: c["nextStep"].update(action="propose_shared_order"), "next step must be"),
    ("underuse", lambda c: c.update(advisory=False), "advisory"),
])
def test_card_grounding_rejects_hallucinations(after, kind, mutate, needle):
    card = _card(kind)
    mutate(card)
    assert any(needle in e for e in check_card(card, _insight(after, kind)))


def test_output_must_use_top_ranked_insight_and_list_the_rest(after):
    out = copy.deepcopy(next(s for s in OPT_SHOTS if s["id"] == "opt-after-stage-1")["output"])
    insights = S.all_insights(after)
    dropped = copy.deepcopy(out)
    dropped["alsoDetected"] = dropped["alsoDetected"][:1]
    assert any("neither shown nor listed" in e for e in check_optimizer_output(dropped, insights))
    swapped = copy.deepcopy(out)
    swapped["cards"][2]["insightId"] = "ins_underuse_confocal_2_20261102"
    assert any("not the top-ranked" in e for e in check_optimizer_output(swapped, insights))
    invented = copy.deepcopy(out)
    invented["cards"][0]["insightId"] = "ins_made_up"
    assert any("not a tool-returned insight" in e for e in check_optimizer_output(invented, insights))


# ---------------------------------------------------------------- schema validator

def test_jsonschema_lite_basics():
    schema = {"type": "object", "additionalProperties": False, "required": ["a"],
              "properties": {"a": {"type": "integer", "minimum": 1, "multipleOf": 15},
                             "b": {"type": ["string", "null"], "maxLength": 3},
                             "c": {"type": "array", "minItems": 1, "items": {"enum": ["x", "y"]}}}}
    assert validate({"a": 30, "b": None, "c": ["x"]}, schema) == []
    errors = validate({"a": 20, "b": "long", "c": [], "d": 1}, schema)
    assert len(errors) == 4
    assert validate({"a": True}, schema) == ["$.a: expected integer"]
