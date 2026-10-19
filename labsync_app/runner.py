"""Run one agent turn: the tool-use loop between an LLM client and the LabSync tools.

* Tools are called only through `labsync_tools.registry.call`, as the signed-in actor, and only
  tools on the agent's list (optionally narrowed with `allowed_tools`).
* The Negotiator and the Optimizer finish by calling `submit_output` with their structured
  output. The runner checks it against the schema and the tool results it was based on
  (agents/schemas.py). A failed check goes back to the model as an error to fix; only an
  output that passes is accepted.
* Every run is stored as an AgentRun record (the activity panel in docs/07).
"""
import json

from agents import specs
from agents.schemas import check_optimizer_output, check_swap
from labsync_tools import registry

from .mock_llm import SUBMIT

MAX_STEPS = 12
STRUCTURED = {registry.NEGOTIATOR, registry.OPTIMIZER}


def _examples(agent, shots):
    lines = ["", "## Examples (synthetic data)"]
    for shot in shots:
        lines.append("### %s" % shot["description"])
        if agent == registry.LAB:
            lines.append("User: %s" % shot["input"])
        elif agent == registry.NEGOTIATOR:
            lines.append("liaison_get_change_request result: %s" % json.dumps(shot["input"], sort_keys=True))
        lines.append("Output: %s" % json.dumps(shot["output"], sort_keys=True))
    return "\n".join(lines)


def _submit_tool(spec):
    schema = {k: v for k, v in spec["output_schema"].items() if k not in ("$schema", "title")}
    return {"name": SUBMIT, "description": "Submit your final %s. It is checked against the tool results you "
                                           "used; fix any errors it returns and submit again." % spec["output_name"],
            "input_schema": schema}


def _check(agent, output, results):
    if agent == registry.NEGOTIATOR:
        cr = next((r for n, r in reversed(results) if n == "liaison_get_change_request" and r.get("status") == "ok"), None)
        if cr is None:
            return ["call liaison_get_change_request before submitting"]
        return check_swap(output, cr)
    found = {n: r for n, r in results if r.get("status") == "ok"}
    missing = [n for n in ("insight_find_pooled_orders", "insight_find_overloads", "insight_find_underuse") if n not in found]
    if missing:
        return ["call %s before submitting" % ", ".join(missing)]
    insights = [i for n in ("insight_find_pooled_orders", "insight_find_overloads", "insight_find_underuse")
                for i in found[n]["insights"]]
    return check_optimizer_output(output, insights)


def _summary(result):
    keys = ("status", "code", "plan_id", "proposal_id", "approval_id", "state", "entity_state", "next_step")
    return {k: result[k] for k in keys if k in result}


def run_agent(client, agent, repo, actor_id, user_message, allowed_tools=None, week_start=specs.DEFAULT_WEEK,
              max_steps=MAX_STEPS, save=True):
    """Returns the AgentRun dict plus `tool_results` (full results, not stored)."""
    spec = specs.load(agent, repo, actor_id, week_start=week_start)
    names = [t["name"] for t in spec["tools"] if allowed_tools is None or t["name"] in allowed_tools]
    tools = [{"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
             for t in spec["tools"] if t["name"] in names]
    if agent in STRUCTURED:
        tools.append(_submit_tool(spec))
    system = spec["system_prompt"] + "\n" + _examples(agent, spec["few_shots"])
    messages = [{"role": "user", "content": user_message}]
    run = {"run_id": repo.next_id("run"), "agent": agent, "actor_id": actor_id, "input": user_message,
           "model": getattr(client, "model", None), "mode": getattr(client, "name", None), "started_at": repo.now(),
           "tool_calls": [], "output": None, "output_errors": [], "final_text": None, "status": "running", "usage": []}
    results = []
    for _ in range(max_steps):
        response = client.complete(system, messages, tools, agent=agent)
        run["usage"].append(response.get("usage", {}))
        messages.append({"role": "assistant", "content": response["content"]})
        uses = [b for b in response["content"] if b.get("type") == "tool_use"]
        if not uses:
            run["final_text"] = " ".join(b.get("text", "") for b in response["content"] if b.get("type") == "text")
            run["status"] = "completed"
            break
        replies = []
        for use in uses:
            name, args = use["name"], use.get("input") or {}
            if name == SUBMIT and agent in STRUCTURED:
                errors = _check(agent, args, results)
                run["tool_calls"].append({"name": name, "arguments": args, "result": {"accepted": not errors}})
                if errors:
                    run["output_errors"] = errors
                    content, is_error = json.dumps({"status": "error", "code": "OUTPUT_REJECTED", "errors": errors}), True
                else:
                    run["output"], run["output_errors"] = args, []
                    content, is_error = json.dumps({"status": "ok", "accepted": True}), False
            elif name not in names:
                result = {"status": "error", "code": "TOOL_NOT_ALLOWED", "message": "%s is not available here." % name}
                run["tool_calls"].append({"name": name, "arguments": args, "result": _summary(result)})
                content, is_error = json.dumps(result), True
            else:
                result = registry.call(repo, name, args, actor_id, agent=agent)
                results.append((name, result))
                run["tool_calls"].append({"name": name, "arguments": args, "result": _summary(result)})
                content, is_error = json.dumps(result, default=str), result.get("status") == "error"
            replies.append({"type": "tool_result", "tool_use_id": use["id"], "content": content, "is_error": is_error})
        messages.append({"role": "user", "content": replies})
    else:
        run["status"] = "step_limit"
    run["finished_at"] = repo.now()
    if save:
        repo.save_record("AgentRun", run)
    return dict(run, tool_results=results)


def last_result(run, tool_name, ok_only=True):
    for name, result in reversed(run["tool_results"]):
        if name == tool_name and (not ok_only or result.get("status") == "ok"):
            return result
    return None


def last_call(run, tool_name, ok_only=True):
    """Arguments of the last call to `tool_name` (that succeeded, by default)."""
    for call in reversed(run["tool_calls"]):
        if call["name"] == tool_name and (not ok_only or call["result"].get("status") == "ok"):
            return call["arguments"]
    return None
