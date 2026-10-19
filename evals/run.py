"""Run the eval suites through the agents and score them.

    python3 -m evals.run --mock            # offline: tests the harness and tools, not a model
    python3 -m evals.run --live            # Claude API (ANTHROPIC_API_KEY, LABSYNC_MODEL)
    python3 -m evals.run --live --suite intake --limit 5

Outputs go to evals/results/<suite-set>-<mode>.jsonl ({"id", "output", "tool_calls"}), which
`python3 -m evals.score <file>` can re-score.
"""
import argparse
import json
import os
import sys

from labsync_app.llm import LLMUnavailable, make_client
from labsync_app.orchestrator import LAB_PLAN_TOOLS, NEGOTIATOR_TOOLS, OPTIMIZER_TOOLS
from labsync_app.runner import last_call, last_result, run_agent
from labsync_tools.memory_repo import InMemoryRepository

from . import negotiation_cases, optimizer_cases
from .score import HERE, SUITES, load, score_case, summarize


def _names(run):
    return [c["name"] for c in run["tool_calls"]]


def run_intake(client, case):
    ctx = case["context"]
    repo = InMemoryRepository(now=ctx["now"])
    run = run_agent(client, "lab_agent", repo, ctx["actor_id"], case["input"], allowed_tools=LAB_PLAN_TOOLS,
                    save=False)
    goal = (last_call(run, "plan_create_draft") or {}).get("parsed_goal")
    if goal is None:
        attempted = last_call(run, "plan_create_draft", ok_only=False)
        goal = attempted["parsed_goal"] if attempted else None
    output = goal if goal is not None else {"response_kind": "clarify", "message": run["final_text"]}
    return output, _names(run)


def run_negotiation(client, case):
    scenario = next(s for s in negotiation_cases.SCENARIOS if s["id"] == case["id"])
    repo, approval_id = negotiation_cases.build_repo(scenario)
    run = run_agent(client, "conflict_negotiator", repo, scenario["actor_id"],
                    "Review move request %s and recommend a response." % approval_id,
                    allowed_tools=NEGOTIATOR_TOOLS, save=False)
    if run["output"] is not None:
        return run["output"], _names(run)
    seen = last_result(run, "liaison_get_change_request", ok_only=False)
    if seen is None:
        return {"response_kind": "none", "message": run["final_text"]}, _names(run)
    if seen.get("status") == "error":
        return {"response_kind": "refusal", "message": run["final_text"]}, _names(run)
    if seen.get("state") != "pending":
        return {"response_kind": "no_action", "message": run["final_text"]}, _names(run)
    return {"response_kind": "none", "message": run["final_text"], "errors": run["output_errors"]}, _names(run)


def run_optimizer(client, cases):
    """One optimizer run, graded by each of the three finding cases."""
    repo = optimizer_cases.stage_1_repo()
    run = run_agent(client, "department_optimizer", repo, "dept_admin",
                    "Review the department for the week of %s and return the insight cards." % optimizer_cases.WEEK,
                    allowed_tools=OPTIMIZER_TOOLS, week_start=optimizer_cases.WEEK, save=False)
    output = run["output"] or {"response_kind": "none", "message": run["final_text"], "errors": run["output_errors"]}
    return {c["id"]: (output, _names(run)) for c in cases}


def run(client, suites=SUITES, limit=None):
    rows = []
    for suite in suites:
        cases = load(suite)[:limit] if limit else load(suite)
        if suite == "optimizer":
            outputs = run_optimizer(client, cases)
            rows += [(c, outputs[c["id"]]) for c in cases]
            continue
        runner = run_intake if suite == "intake" else run_negotiation
        rows += [(c, runner(client, c)) for c in cases]
    return [(case, output, calls, score_case(case, output, calls)) for case, (output, calls) in rows]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true", help="offline rule-based agents (default)")
    mode.add_argument("--live", action="store_true", help="Claude API")
    parser.add_argument("--suite", choices=SUITES, action="append")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    name = "live" if args.live else "mock"
    try:
        client = make_client(name)
    except LLMUnavailable as exc:
        print("Can't run live evals: %s" % exc)
        return 2
    suites = tuple(args.suite or SUITES)
    results = run(client, suites, args.limit)
    out_dir = os.path.join(HERE, "results")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "%s-%s.jsonl" % ("-".join(suites), name))
    with open(path, "w", encoding="utf-8") as fh:
        for case, output, calls, _ in results:
            fh.write(json.dumps({"id": case["id"], "output": output, "tool_calls": calls}, sort_keys=True) + "\n")
    print("mode: %s (%s)" % (name, getattr(client, "model", "")))
    if name == "mock":
        print("note: mock agents are rule-based; these scores check the harness, not a model")
    print(summarize([r for _, _, _, r in results]))
    print("outputs: %s" % os.path.relpath(path))
    return 0 if all(r["passed"] for _, _, _, r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
