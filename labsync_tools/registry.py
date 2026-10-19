"""Tool registry: every agent tool from docs/06 with its allowed effect and the agents that get it.

C3 Code registers these in the Tool Workbench (C3_CODE_PROMPTS.md prompt 4); the CLI uses the
same list. A tool's docstring is its description for the agent. `repo` and `actor_id` are
injected by the host from the signed-in session; the agent never supplies who it is acting for.

Agent names: the three agents Aaryan chose map onto docs/06 as
  lab_agent           = LabPlannerAgent
  conflict_negotiator = LabLiaisonAgent (lab-scoped; recommends, the owner decides)
  department_optimizer = DepartmentEfficiencyAgent
`approval_record` is UI-only: a person presses Approve/Reject; no agent is given it.
"""
import inspect

from . import tools
from .jsonschema_lite import validate
from .param_schemas import input_schema

LAB = "lab_agent"
NEGOTIATOR = "conflict_negotiator"
OPTIMIZER = "department_optimizer"

# (name, effect from docs/06, agents)
TOOL_TABLE = [
    ("catalog_find_resources", "read_only", [LAB]),
    ("resource_check_qualifications", "read_only", [LAB, NEGOTIATOR]),
    ("scheduler_find_slots", "read_only", [LAB]),
    ("stock_get_availability", "read_only", [LAB]),
    ("supply_quote", "read_only", [LAB]),
    ("plan_create_draft", "internal_draft_write", [LAB]),
    ("supply_create_order_draft", "proposal_only", [LAB]),
    ("booking_propose", "proposal_only", [LAB]),
    ("liaison_request_change", "proposal_only", [LAB]),
    ("liaison_get_change_request", "read_only", [NEGOTIATOR]),
    ("approval_record", "write_if_authorized", []),
    ("booking_commit_approved", "conditional_booking_write", [LAB]),
    ("dept_get_snapshot", "aggregated_read_only", [OPTIMIZER]),
    ("forecast_resource_demand", "forecast_write_read", [OPTIMIZER]),
    ("insight_find_pooled_orders", "read_only", [OPTIMIZER]),
    ("insight_find_overloads", "read_only", [OPTIMIZER]),
    ("insight_find_underuse", "read_only", [OPTIMIZER]),
    ("insight_propose_action", "proposal_only", [OPTIMIZER]),
    ("audit_get_activity", "read_scoped", [LAB, NEGOTIATOR, OPTIMIZER]),
]

# Not in docs/06's table; added because docs/01 names SupplyRequest.createDraft and the
# negotiator needs to read the request it is judging.
EXTRA_TOOLS = {"supply_create_order_draft", "liaison_get_change_request"}


HOST_ARGS = ("repo", "actor_id")


def _params(fn):
    return [p for p in inspect.signature(fn).parameters if p not in HOST_ARGS]


def _required(fn):
    return [n for n, p in inspect.signature(fn).parameters.items()
            if n not in HOST_ARGS and p.default is inspect.Parameter.empty]


TOOLS = {name: {"name": name, "function": getattr(tools, name), "effect": effect, "agents": agents,
                "parameters": _params(getattr(tools, name)),
                "required": _required(getattr(tools, name)), "description": inspect.getdoc(getattr(tools, name))}
         for name, effect, agents in TOOL_TABLE}
for _tool in TOOLS.values():
    _tool["input_schema"] = input_schema(_tool["parameters"], _tool["required"])


def tools_for(agent):
    """Tool names an agent may call, in registry order."""
    return [name for name, _, agents in TOOL_TABLE if agent in agents]


def call(repo, name, arguments, actor_id, agent=None):
    """Dispatch an agent's tool call as `actor_id` (the signed-in person, from the host).
    Refuses tools outside the agent's list, unknown or missing arguments, and any attempt by the
    agent to pass its own actor_id."""
    if name not in TOOLS:
        return {"status": "error", "code": "UNKNOWN_TOOL", "message": "No tool named %s." % name}
    if agent is not None and agent not in TOOLS[name]["agents"]:
        return {"status": "error", "code": "TOOL_NOT_ALLOWED", "message": "%s may not call %s." % (agent, name)}
    unknown = sorted(set(arguments) - set(TOOLS[name]["parameters"]))
    missing = [p for p in TOOLS[name]["required"] if p not in arguments]
    if unknown or missing:
        return {"status": "error", "code": "INVALID_ARGUMENTS",
                "message": "Unknown arguments: %s; missing: %s" % (unknown, missing)}
    # Type-check arguments; parsed_goal is left to plan_create_draft, which audits rejected plans.
    shallow = dict(TOOLS[name]["input_schema"], properties={
        k: v for k, v in TOOLS[name]["input_schema"]["properties"].items() if k != "parsed_goal"})
    errors = validate({k: v for k, v in arguments.items() if k != "parsed_goal"},
                      dict(shallow, required=[r for r in shallow["required"] if r != "parsed_goal"]))
    if errors:
        return {"status": "error", "code": "INVALID_ARGUMENTS", "message": "; ".join(errors)}
    return TOOLS[name]["function"](repo, actor_id=actor_id, **arguments)
