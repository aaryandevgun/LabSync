"""LLM client, agent runner, orchestrator, CLI demo and eval runner."""
import copy
import json

import pytest

from cli.__main__ import main as cli_main
from cli.demo import CANONICAL, Demo
from evals import run as eval_run
from labsync_app.llm import API_URL, AnthropicClient, LLMUnavailable, make_client
from labsync_app.mock_llm import SUBMIT
from labsync_app.orchestrator import Orchestrator
from labsync_app.runner import run_agent
from labsync_tools import tools as T
from labsync_tools.memory_repo import InMemoryRepository

from tests.tools.helpers import CANONICAL_GOAL, propose_owner_move


# ---------------------------------------------------------------- live client (fake transport)

def test_live_client_requires_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMUnavailable):
        make_client("live")


def test_live_client_sends_messages_api_request_and_parses_reply(monkeypatch):
    monkeypatch.setenv("LABSYNC_MODEL", "claude-test-model")
    seen = {}

    def transport(url, headers, body, timeout):
        seen.update(url=url, headers=headers, body=json.loads(body))
        return 200, json.dumps({"stop_reason": "tool_use", "model": "claude-test-model", "usage": {"input_tokens": 5},
                                "content": [{"type": "tool_use", "id": "t1", "name": "x", "input": {}}]}).encode()

    client = AnthropicClient(api_key="sk-test", transport=transport)
    out = client.complete("sys", [{"role": "user", "content": "hi"}], [{"name": "x", "input_schema": {}}])
    assert seen["url"] == API_URL and seen["headers"]["x-api-key"] == "sk-test"
    assert seen["headers"]["anthropic-version"] == "2023-06-01"
    assert seen["body"]["model"] == "claude-test-model" and seen["body"]["system"] == "sys"
    assert out["stop_reason"] == "tool_use" and out["content"][0]["name"] == "x"


def test_live_client_retries_overload_then_fails_cleanly(monkeypatch):
    monkeypatch.setattr("labsync_app.llm.time.sleep", lambda s: None)
    calls = []

    def transport(url, headers, body, timeout):
        calls.append(1)
        return 529, b'{"error": "overloaded"}'

    with pytest.raises(LLMUnavailable) as exc:
        AnthropicClient(api_key="k", transport=transport, retries=2).complete("s", [], [])
    assert len(calls) == 3 and "529" in str(exc.value)
    calls.clear()

    def bad_request(url, headers, body, timeout):
        calls.append(1)
        return 400, b'{"error": "bad"}'

    with pytest.raises(LLMUnavailable):
        AnthropicClient(api_key="k", transport=bad_request).complete("s", [], [])
    assert len(calls) == 1  # client errors are not retried


# ---------------------------------------------------------------- runner

class ScriptedClient:
    """Replays fixed responses, to drive the runner like a misbehaving model."""
    name, model = "scripted", "scripted"

    def __init__(self, steps):
        self.steps = list(steps)
        self.seen = []

    def complete(self, system, messages, tools, agent=None):
        self.seen.append(copy.deepcopy(messages))
        kind, payload = self.steps.pop(0)
        if kind == "say":
            return {"stop_reason": "end_turn", "content": [{"type": "text", "text": payload}]}
        name, args = payload
        return {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": "s%d" % len(self.seen),
                                                         "name": name, "input": args}]}


def _sent(repo):
    _, prop = propose_owner_move(repo, copy.deepcopy(CANONICAL_GOAL))
    return T.liaison_request_change(repo, "morgan", prop["proposal_id"], "bk_chen_confocal")


def test_runner_rejects_ungrounded_output_until_fixed():
    repo = InMemoryRepository()
    sent = _sent(repo)
    from labsync_app.mock_llm import recommend
    good = recommend(T.liaison_get_change_request(repo, "chen_owner", sent["approval_id"]))
    bad = dict(good, to={"start": "2026-11-03T09:00:00-06:00", "end": "2026-11-03T11:00:00-06:00"})
    client = ScriptedClient([("tool", ("liaison_get_change_request", {"approval_id": sent["approval_id"]})),
                             ("tool", (SUBMIT, bad)), ("tool", (SUBMIT, good)), ("say", "done")])
    run = run_agent(client, "conflict_negotiator", repo, "chen_owner", "Review %s" % sent["approval_id"])
    assert run["output"] == good and run["status"] == "completed"
    rejected = [c for c in run["tool_calls"] if c["name"] == SUBMIT and not c["result"]["accepted"]]
    assert len(rejected) == 1
    reply = client.seen[2][-1]["content"][0]
    assert reply["is_error"] and "to times differ" in reply["content"]
    assert repo.get_record("AgentRun", run["run_id"])["output"] == good


def test_runner_refuses_tools_outside_the_list_and_never_approves():
    repo = InMemoryRepository()
    sent = _sent(repo)
    client = ScriptedClient([("tool", ("approval_record", {"approval_id": sent["approval_id"], "decision": "approve"})),
                             ("say", "ok")])
    run = run_agent(client, "conflict_negotiator", repo, "chen_owner", "Review %s" % sent["approval_id"])
    assert run["tool_calls"][0]["result"]["code"] == "TOOL_NOT_ALLOWED"
    assert repo.get_record("Approval", sent["approval_id"])["status"] == "pending"


def test_runner_acts_as_the_signed_in_actor():
    repo = InMemoryRepository()
    sent = _sent(repo)
    client = ScriptedClient([("tool", ("liaison_get_change_request", {"approval_id": sent["approval_id"]})),
                             ("say", "can't see it")])
    run = run_agent(client, "conflict_negotiator", repo, "jordan_patel", "Review %s" % sent["approval_id"])
    assert run["tool_calls"][0]["result"]["code"] == "PERMISSION_DENIED"


def test_runner_stops_at_the_step_limit():
    repo = InMemoryRepository()
    client = ScriptedClient([("tool", ("dept_get_snapshot", {"week_start": "2026-11-02"}))] * 3)
    run = run_agent(client, "department_optimizer", repo, "dept_admin", "go", max_steps=3)
    assert run["status"] == "step_limit" and run["output"] is None


# ---------------------------------------------------------------- orchestrator and demo

@pytest.fixture
def orch():
    return Orchestrator(InMemoryRepository(), make_client("mock"))


def test_orchestrator_full_loop(orch):
    req = orch.submit_request("morgan", CANONICAL)
    assert req["status"] == "ok" and req["parsed_goal"]["labId"] == "lab_moreno"
    move = req["search"]["options"][0]
    assert move["kind"] == "owner_move"
    prop = orch.choose_option("morgan", req["plan_id"], move["option_id"])
    assert orch.choose_option("morgan", req["plan_id"], move["option_id"])["proposal_id"] == prop["proposal_id"]
    sent = orch.request_moves("morgan", prop["proposal_id"])["requests"][0]
    assert sent["recommendation"]["output"]["recommendation"] == "approve"
    assert orch.recommendation_for(sent["approval_id"])["approvalId"] == sent["approval_id"]
    assert orch.queue("chen_owner")["waiting_on_me"][0]["approval_id"] == sent["approval_id"]
    assert orch.commit("morgan", prop["proposal_id"])["code"] == "MISSING_APPROVAL"
    orch.decide("chen_owner", sent["approval_id"], "approve")
    confirm = prop["approvals"][-1]["approval_id"]
    orch.decide("morgan", confirm, "approve")
    commit = orch.commit("morgan", prop["proposal_id"])
    assert commit["status"] == "ok"
    assert orch.commit("morgan", prop["proposal_id"])["replayed"]
    orders = orch.draft_orders("morgan", req["plan_id"])["orders"]
    assert {o["state"] for o in orders} == {"awaiting_lab_approval"}
    dept = orch.review_department("dept_admin", "2026-11-02")
    assert [c["kind"] for c in dept["output"]["cards"]] == ["pooled_order", "overload_rebalance", "underuse"]
    insight = dept["output"]["cards"][0]["insightId"]
    assert orch.propose_insight("dept_admin", insight)["state"] == "pending_approvals"
    runs = orch.repo.list_records("AgentRun")
    assert {r["agent"] for r in runs} == {"lab_agent", "conflict_negotiator", "department_optimizer"}


def test_orchestrator_reports_llm_outage_without_writing():
    class Down:
        name = "live"

        def complete(self, *a, **k):
            raise LLMUnavailable("network down")

    o = Orchestrator(InMemoryRepository(), Down())
    assert o.submit_request("morgan", CANONICAL)["code"] == "LLM_UNAVAILABLE"
    assert o.repo.list_records("ExperimentPlan") == []


def test_demo_auto_runs_the_whole_story(orch):
    lines = []
    result = Demo(orch, out=lines.append, auto=True).run()
    text = "\n".join(lines)
    assert result["committed"] and "C3 not connected" in text
    assert "13:30-15:30  confirmed busy" in text and "10:00-13:00  confirmed morgan" in text
    assert "awaiting lab approval" in text and "$95 potential" in text


def test_demo_rejection_path_replans_without_moving_chen(orch):
    answers = iter(["1", "n", "y"])  # pick move, Chen rejects, the one direct option is held, Morgan confirms
    lines = []
    result = Demo(orch, out=lines.append, ask=lambda prompt: next(answers)).run()
    assert result["committed"]
    chen = orch.repo.get_record("Booking", "bk_chen_confocal")
    assert (chen["start_local"], chen["end_local"]) == ("2026-11-03T10:00:00-06:00", "2026-11-03T12:00:00-06:00")
    mine = orch.repo.get_record("Booking", "bk_%s_img" % result["proposal_id"])
    assert mine["start_local"] == "2026-11-03T12:15:00-06:00"


def test_cli_demo_and_reset_use_the_state_file(tmp_path, capsys):
    state = str(tmp_path / "s.json")
    assert cli_main(["demo", "--auto", "--state", state]) == 0
    from labsync_app.store import FileRepository
    assert FileRepository(state).get_record("Booking", "bk_chen_confocal")["start_local"].endswith("13:30:00-06:00")
    assert cli_main(["reset", "--state", state]) == 0
    assert FileRepository(state).get_record("Booking", "bk_chen_confocal")["start_local"].endswith("10:00:00-06:00")
    assert cli_main(["ask", "hi", "--memory"]) == 0
    assert "What would you like to plan" in capsys.readouterr().out


def test_mock_evals_pass_every_case():
    results = eval_run.run(make_client("mock"))
    assert len(results) == 53 and all(r["passed"] for _, _, _, r in results)
