"""The coordinator (replaces C3 APA): request -> Lab Agent -> held booking -> Conflict Negotiator ->
human approvals -> commit -> Department Optimizer.

Agents do language and judgment only: the Lab Agent parses and explains, the Negotiator advises
the owner, the Optimizer writes cards. Every state change is a deterministic tool call made by the
host when a person presses a button (or confirms in the CLI). Nothing here records an approval on
anyone's behalf.
"""
from labsync_tools import queries
from labsync_tools import tools as T

from .llm import LLMUnavailable
from .runner import last_call, last_result, run_agent

LAB_PLAN_TOOLS = ("catalog_find_resources", "resource_check_qualifications", "scheduler_find_slots",
                  "stock_get_availability", "supply_quote", "plan_create_draft", "audit_get_activity")
NEGOTIATOR_TOOLS = ("liaison_get_change_request", "resource_check_qualifications", "audit_get_activity")
OPTIMIZER_TOOLS = ("dept_get_snapshot", "forecast_resource_demand", "insight_find_pooled_orders",
                   "insight_find_overloads", "insight_find_underuse", "audit_get_activity")


def _llm_error(exc):
    return {"status": "error", "code": "LLM_UNAVAILABLE", "message": str(exc)}


def _public(run):
    return {k: v for k, v in run.items() if k != "tool_results"}


class Orchestrator:
    def __init__(self, repo, client):
        self.repo = repo
        self.client = client

    # ---------------------------------------------------------------- Stage 1
    def submit_request(self, actor_id, text):
        """Lab Agent parses the goal, saves the draft plan and searches options. Books nothing."""
        try:
            run = run_agent(self.client, "lab_agent", self.repo, actor_id, text, allowed_tools=LAB_PLAN_TOOLS)
        except LLMUnavailable as exc:
            return _llm_error(exc)
        draft = last_result(run, "plan_create_draft")
        return {"status": "ok", "run": _public(run), "agent_text": run["final_text"],
                "plan_id": draft["plan_id"] if draft else None,
                "parsed_goal": (last_call(run, "plan_create_draft") or {}).get("parsed_goal"),
                "needs_input": draft["needs_input"] if draft else None,
                "search": last_result(run, "scheduler_find_slots")}

    def search(self, actor_id, plan_id):
        return T.scheduler_find_slots(self.repo, actor_id, plan_id)

    def _request_id(self, plan_id=None, proposal_id=None):
        if proposal_id:
            proposal = self.repo.get_record("ReservationProposal", proposal_id)
            return proposal["request_id"] if proposal else proposal_id
        plan = self.repo.get_record("ExperimentPlan", plan_id)
        return plan["request_id"] if plan else plan_id

    def choose_option(self, actor_id, plan_id, option_id):
        """Hold the chosen option (proposal only). Retrying the same choice returns the same proposal."""
        key = "%s:propose:%s" % (self._request_id(plan_id=plan_id), option_id)
        return T.booking_propose(self.repo, actor_id, plan_id, option_id, key)

    def request_moves(self, actor_id, proposal_id, message=None):
        """'Ask the owner to move': send each owner move request, then let the Negotiator advise the owner."""
        proposal = self.repo.get_record("ReservationProposal", proposal_id)
        if proposal is None:
            return {"status": "error", "code": "NOT_FOUND", "message": "Unknown proposal."}
        sent = []
        for move in proposal["contingent_moves"]:
            result = T.liaison_request_change(self.repo, actor_id, proposal_id, move["booking_id"], message)
            if result["status"] == "ok" and not result.get("replayed"):
                result["recommendation"] = self.advise(result["approval_id"])
            sent.append(result)
        return {"status": "ok", "requests": sent}

    def advise(self, approval_id):
        """Run the Negotiator as the request's approver. Advice only; returns the run summary."""
        approval = self.repo.get_record("Approval", approval_id)
        if approval is None:
            return {"status": "error", "code": "NOT_FOUND"}
        try:
            run = run_agent(self.client, "conflict_negotiator", self.repo, approval["approver_id"],
                            "Review move request %s and recommend a response." % approval_id,
                            allowed_tools=NEGOTIATOR_TOOLS)
        except LLMUnavailable as exc:
            return _llm_error(exc)
        self.repo.save_record("AgentRun", dict(_public(run), subject_id=approval_id))
        return {"status": "ok" if run["output"] else "error", "run_id": run["run_id"], "output": run["output"],
                "text": run["final_text"], "errors": run["output_errors"]}

    def recommendation_for(self, approval_id):
        runs = [r for r in self.repo.list_records("AgentRun") if r.get("subject_id") == approval_id and r["output"]]
        return runs[-1]["output"] if runs else None

    def decide(self, actor_id, approval_id, decision, reason=None):
        """A person's Approve/Reject. The tool enforces who may decide and in what order."""
        return T.approval_record(self.repo, actor_id, approval_id, decision, reason)

    def commit(self, actor_id, proposal_id):
        key = "%s:commit:%s" % (self._request_id(proposal_id=proposal_id), proposal_id)
        return T.booking_commit_approved(self.repo, actor_id, proposal_id, key)

    def draft_orders(self, actor_id, plan_id):
        key = "%s:orders" % self._request_id(plan_id=plan_id)
        return T.supply_create_order_draft(self.repo, actor_id, plan_id, key)

    # ---------------------------------------------------------------- Stage 2
    def review_department(self, actor_id, week_start):
        try:
            run = run_agent(self.client, "department_optimizer", self.repo, actor_id,
                            "Review the department for the week of %s and return the insight cards." % week_start,
                            allowed_tools=OPTIMIZER_TOOLS, week_start=week_start)
        except LLMUnavailable as exc:
            return _llm_error(exc)
        return {"status": "ok" if run["output"] else "error", "run_id": run["run_id"], "output": run["output"],
                "text": run["final_text"], "errors": run["output_errors"],
                "tool_calls": [c["name"] for c in run["tool_calls"]]}

    def propose_insight(self, actor_id, insight_id, week_start=None):
        return T.insight_propose_action(self.repo, actor_id, insight_id, week_start)

    # ---------------------------------------------------------------- queries
    def queue(self, actor_id):
        return queries.list_approval_queue(self.repo, actor_id)

    def plan(self, actor_id, plan_id):
        return queries.get_plan(self.repo, actor_id, plan_id)

    def calendar(self, actor_id, resource_ids, day):
        return queries.get_calendar(self.repo, actor_id, resource_ids, day)

    def activity(self, actor_id, request_id=None, entity_id=None):
        return T.audit_get_activity(self.repo, actor_id, request_id=request_id, entity_id=entity_id)

    def reset(self, actor_id, token):
        return queries.reset_demo(self.repo, actor_id, token)
