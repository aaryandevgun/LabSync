"""Load an agent definition: system prompt (with session values filled in), tool list,
output schema and few-shot examples. Used by the CLI and by `agents.export`.

    spec = load("lab_agent", repo, actor_id="morgan")
    spec["system_prompt"], spec["tools"], spec["output_schema"], spec["few_shots"]
"""
import json
import os

from labsync_core.values import as_list
from labsync_tools import registry

from .schemas import OPTIMIZER_OUTPUT_SCHEMA, PARSED_GOAL_SCHEMA, SWAP_PROPOSAL_SCHEMA

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WEEK = "2026-11-02"

AGENTS = {
    registry.LAB: {"title": "LabSync Lab Agent (docs/06 LabPlannerAgent)", "output_schema": PARSED_GOAL_SCHEMA,
                   "output_name": "ParsedGoal"},
    registry.NEGOTIATOR: {"title": "LabSync Conflict Negotiator (docs/06 LabLiaisonAgent)",
                          "output_schema": SWAP_PROPOSAL_SCHEMA, "output_name": "SwapProposalRecommendation"},
    registry.OPTIMIZER: {"title": "LabSync Department Optimizer (docs/06 DepartmentEfficiencyAgent)",
                         "output_schema": OPTIMIZER_OUTPUT_SCHEMA, "output_name": "DepartmentOptimizerOutput"},
}


def _read(agent, name):
    with open(os.path.join(HERE, agent, name), encoding="utf-8") as fh:
        return fh.read()


def tool_specs(agent):
    """The agent's tools as {name, effect, description, input_schema}; host-injected args omitted."""
    return [{k: registry.TOOLS[n][k] for k in ("name", "effect", "description", "input_schema")}
            for n in registry.tools_for(agent)]


def catalog_vocabulary(repo):
    caps = set()
    for r in repo.list_records("Instrument") + repo.list_records("Room"):
        caps |= set(as_list(r["capabilities"]))
    skus = ["%s (%s)" % (s["sku_id"], s["name"]) for s in sorted(repo.list_records("SupplySku"), key=lambda s: s["sku_id"])]
    return ", ".join(sorted(caps)), ", ".join(skus)


def render_prompt(agent, repo, actor_id, now=None, week_start=DEFAULT_WEEK):
    actor = repo.get_record("Person", actor_id) or {}
    caps, skus = catalog_vocabulary(repo)
    values = {"ACTOR_ID": actor_id, "LAB_ID": actor.get("lab_id") or "(none)", "NOW": now or repo.now(),
              "WEEK_START": week_start, "CAPABILITIES": caps, "SKUS": skus}
    text = _read(agent, "system_prompt.md")
    for key, value in values.items():
        text = text.replace("{{%s}}" % key, value)
    return text


def few_shots(agent):
    return json.loads(_read(agent, "few_shots.json"))


def load(agent, repo, actor_id, now=None, week_start=DEFAULT_WEEK):
    if agent not in AGENTS:
        raise KeyError("unknown agent %s" % agent)
    meta = AGENTS[agent]
    return {"name": agent, "title": meta["title"], "system_prompt": render_prompt(agent, repo, actor_id, now, week_start),
            "tools": tool_specs(agent), "output_name": meta["output_name"], "output_schema": meta["output_schema"],
            "few_shots": few_shots(agent)}
