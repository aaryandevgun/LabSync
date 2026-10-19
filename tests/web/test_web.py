"""Web app: JSON API over real HTTP, static serving, and the browser smoke test (if Playwright is present)."""
import json
import os
import shutil
import subprocess
import threading
import urllib.error
import urllib.request

import pytest

from cli.demo import CANONICAL
from labsync_app.web.server import build, serve

TOKEN = "test-reset-token"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("LABSYNC_RESET_TOKEN", TOKEN)
    api = build(memory=True)
    httpd = serve(api, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % httpd.server_port, api
    httpd.shutdown()
    httpd.server_close()


def call(base, method, path, body=None, who="morgan", raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"X-LabSync-Persona": who, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read()), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read()), dict(exc.headers)


def plan_and_hold(base):
    _, r, _ = call(base, "POST", "/api/requests", {"text": CANONICAL})
    plan_id = r["plan_id"]
    _, plan, _ = call(base, "GET", "/api/plans/" + plan_id)
    option = plan["search"]["options"][0]
    _, held, _ = call(base, "POST", "/api/plans/%s/hold" % plan_id, {"option_id": option["option_id"]})
    return plan_id, held["proposal_id"]


def test_page_and_assets_are_served_with_security_headers(server):
    base, _ = server
    with urllib.request.urlopen(base + "/") as resp:
        html = resp.read().decode()
        assert "Local demo · C3 not connected" in html and "Synthetic campus data" in html
        assert "script-src 'self'" in resp.headers["Content-Security-Policy"]
    for asset in ("/static/app.js", "/static/app.css"):
        with urllib.request.urlopen(base + asset) as resp:
            assert resp.status == 200
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(base + "/static/../server.py")
    assert exc.value.code == 404


def test_session_labels_local_synthetic_mode(server):
    base, _ = server
    status, s, _ = call(base, "GET", "/api/session")
    assert status == 200
    assert s["c3_connected"] is False and s["synthetic"] is True and s["mode"] == "mock"
    assert s["persona"]["id"] == "morgan" and not s["is_admin"]
    assert {"morgan", "chen_owner", "dept_admin"} <= {p["id"] for p in s["personas"]}
    assert s["resource_names"]["flow_2"] == "Flow Cytometer 2" and s["resource_names"]["prep_a"] == "Prep Room A"
    status, err, _ = call(base, "GET", "/api/session", who="nobody")
    assert status == 400 and err["code"] == "UNKNOWN_PERSONA"


def test_full_loop_over_http(server):
    base, api = server
    status, r, _ = call(base, "POST", "/api/requests", {"text": CANONICAL})
    assert status == 200 and r["plan_id"] and "plan_create_draft" in r["tool_calls"]
    plan_id = r["plan_id"]
    _, plan, _ = call(base, "GET", "/api/plans/" + plan_id)
    assert plan["stage"] == "draft" and plan["commit_blockers"] == ["Hold an option first."]
    assert [o["kind"] for o in plan["search"]["options"]] == ["owner_move", "direct"]
    assert {r["id"] for r in plan["timeline"]["resources"]} >= {"confocal_1", "confocal_2", "prep_a"}
    chen_row = next(x for x in plan["timeline"]["rows"] if x["booking_id"] == "bk_chen_confocal")
    assert chen_row["user_id"] is None and chen_row["lab_id"] is None  # other lab: busy only

    option = plan["search"]["options"][0]
    _, held, _ = call(base, "POST", "/api/plans/%s/hold" % plan_id, {"option_id": option["option_id"]})
    prop = held["proposal_id"]
    status, early, _ = call(base, "POST", "/api/proposals/%s/commit" % prop)
    assert status == 409 and early["code"] == "MISSING_APPROVAL"

    status, sent, _ = call(base, "POST", "/api/proposals/%s/request-moves" % prop, {"message": "please"})
    assert status == 200 and "recommendation" not in sent["requests"][0]  # advice goes to the owner only
    _, inbox, _ = call(base, "GET", "/api/approvals", who="chen_owner")
    card = inbox["waiting_on_me"][0]
    assert card["recommendation"]["recommendation"] == "approve" and card["recommendation"]["decidedBy"] == "owner"
    assert card["impact"]["to"]["start"].endswith("13:30:00-06:00")

    status, _, _ = call(base, "POST", "/api/approvals/%s/decide" % card["approval_id"], {"decision": "approve"}, who="morgan")
    assert status == 403  # Morgan can't approve Chen's move
    status, d, _ = call(base, "POST", "/api/approvals/%s/decide" % card["approval_id"], {"decision": "approve"}, who="chen_owner")
    assert status == 200 and d["entity_state"] == "requester_approval_pending"

    _, plan, _ = call(base, "GET", "/api/plans/" + plan_id)
    mine = next(a for a in plan["approvals"] if a["slot_kind"] == "requester_confirm")
    assert mine["your_turn"]
    call(base, "POST", "/api/approvals/%s/decide" % mine["approval_id"], {"decision": "approve"})
    _, plan, _ = call(base, "GET", "/api/plans/" + plan_id)
    assert plan["stage"] == "ready" and plan["commit_blockers"] == []
    status, c, _ = call(base, "POST", "/api/proposals/%s/commit" % prop)
    assert status == 200 and "bk_chen_confocal" in c["receipt"]["booking_ids"]
    status, again, _ = call(base, "POST", "/api/proposals/%s/commit" % prop)
    assert status == 200 and again["replayed"]

    _, plan, _ = call(base, "GET", "/api/plans/" + plan_id)
    assert plan["stage"] == "confirmed" and plan["receipt"]["receipt_id"] == c["receipt"]["receipt_id"]
    _, orders, _ = call(base, "POST", "/api/plans/%s/orders" % plan_id)
    assert {o["state"] for o in orders["orders"]} == {"awaiting_lab_approval"}

    _, act, _ = call(base, "GET", "/api/activity?request_id=" + plan["plan"]["request_id"])
    labels = [e["label"] for e in act["events"]]
    assert "Bookings committed" in labels and "Approved" in labels
    assert [r["agent"] for r in act["runs"]] == ["lab_agent"]  # the owner's advice run stays with the owner

    status, denied, _ = call(base, "GET", "/api/department")
    assert status == 403 and denied["code"] == "PERMISSION_DENIED" and "snapshot" not in denied
    _, dept, _ = call(base, "GET", "/api/department", who="dept_admin")
    assert dept["review"] is None and dept["forecasts"] == {}
    _, review, _ = call(base, "POST", "/api/department/review", {}, who="dept_admin")
    assert [card["impact"]["value"] for card in review["output"]["cards"]] == [95, 8.0, 10.0]
    _, dept, _ = call(base, "GET", "/api/department", who="dept_admin")
    assert dept["review"]["output"] and set(dept["forecasts"]) == {"confocal_1", "confocal_2"}
    pool = dept["insights"]["ins_pool_anti_gfp_100_moreno_patel"]
    assert (pool["estimate"]["unpooled_total_usd"], pool["estimate"]["pooled_total_usd"]) == (640, 545)
    _, prop_ins, _ = call(base, "POST", "/api/insights/ins_pool_anti_gfp_100_moreno_patel/propose", {}, who="dept_admin")
    assert prop_ins["state"] == "pending_approvals"
    _, mgr, _ = call(base, "GET", "/api/approvals", who="moreno_mgr")
    assert any(c["entity_kind"] == "DepartmentInsight" for c in mgr["waiting_on_me"])
    assert any(c["entity_kind"] == "OrderProposal" and "not place an order" in c["note"] for c in mgr["waiting_on_me"])


def test_suggest_other_time_rejects_and_replans(server):
    base, api = server
    plan_id, prop = plan_and_hold(base)
    call(base, "POST", "/api/proposals/%s/request-moves" % prop, {})
    _, inbox, _ = call(base, "GET", "/api/approvals", who="chen_owner")
    approval = inbox["waiting_on_me"][0]["approval_id"]
    _, d, _ = call(base, "POST", "/api/approvals/%s/decide" % approval, {"suggested_time": "14:00-16:00"}, who="chen_owner")
    assert d["decision"] == "reject" and d["next_step"] == "replan"
    assert api.repo.get_record("Approval", approval)["reason"] == "Suggested another time: 14:00-16:00"
    chen = api.repo.get_record("Booking", "bk_chen_confocal")
    assert chen["start_local"] == "2026-11-03T10:00:00-06:00"  # nothing moved
    _, plan, _ = call(base, "GET", "/api/plans/" + plan_id)
    assert plan["stage"] == "needs_revision" and plan["proposal"]["state"] == "rejected"
    assert plan["search"]["options"]  # options come back for a new choice


def test_revise_plan_rechecks_with_new_duration(server):
    base, _ = server
    _, r, _ = call(base, "POST", "/api/requests", {"text": CANONICAL})
    status, rev, _ = call(base, "POST", "/api/plans/%s/revise" % r["plan_id"], {"edits": {"durations": {"image": 120}}})
    assert status == 200 and rev["plan_id"] != r["plan_id"] and rev["request_id"]
    _, plan, _ = call(base, "GET", "/api/plans/" + rev["plan_id"])
    assert plan["goal"]["steps"][1]["durationMinutes"] == 120
    assert all(o["end"] for o in plan["search"]["options"])
    status, bad, _ = call(base, "POST", "/api/plans/%s/revise" % r["plan_id"], {"edits": {"durations": {"image": -5}}})
    assert status == 409 and bad["code"] == "INVALID_PLAN"
    status, other, _ = call(base, "POST", "/api/plans/%s/revise" % r["plan_id"], {"edits": {}}, who="chen_owner")
    assert status == 403
    _, home, _ = call(base, "GET", "/api/home")
    assert [p["plan_id"] for p in home["plans"]] == [rev["plan_id"]]  # the revision replaces the draft


def test_other_lab_cannot_read_plan_and_bad_input_is_refused(server):
    base, _ = server
    plan_id, _ = plan_and_hold(base)
    status, err, _ = call(base, "GET", "/api/plans/" + plan_id, who="chen_owner")
    assert status == 403 and "plan" not in err
    status, err, _ = call(base, "POST", "/api/requests", raw=b"{not json")
    assert status == 400 and err["code"] == "BAD_JSON"
    status, err, _ = call(base, "POST", "/api/requests", {"text": "  "})
    assert status == 400 and err["code"] == "EMPTY_REQUEST"
    status, err, _ = call(base, "GET", "/api/nope")
    assert status == 404


def test_reset_needs_the_token(server):
    base, api = server
    plan_and_hold(base)
    status, err, _ = call(base, "POST", "/api/reset", {"token": "wrong"})
    assert status == 403 and err["code"] == "RESET_NOT_ALLOWED"
    assert api.repo.list_records("ReservationProposal")
    status, ok, _ = call(base, "POST", "/api/reset", {"token": TOKEN})
    assert status == 200 and not api.repo.list_records("ReservationProposal")


def test_llm_outage_returns_503_and_writes_nothing(server):
    base, api = server

    class Down:
        name, model = "live", "x"

        def complete(self, *a, **k):
            from labsync_app.llm import LLMUnavailable
            raise LLMUnavailable("down")
    api.o.client = Down()
    before = len(api.repo.list_records("ExperimentPlan"))
    status, err, _ = call(base, "POST", "/api/requests", {"text": CANONICAL})
    assert status == 503 and err["code"] == "LLM_UNAVAILABLE"
    assert len(api.repo.list_records("ExperimentPlan")) == before


def _playwright():
    node = shutil.which("node")
    if not node:
        return None, None
    root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()
    ok = subprocess.run([node, "-e", "require('playwright')"], env=dict(os.environ, NODE_PATH=root), capture_output=True)
    return (node, root) if ok.returncode == 0 else (None, None)


def test_browser_smoke(server, tmp_path):
    node, root = _playwright()
    if not node:
        pytest.skip("node + playwright not installed")
    base, _ = server
    env = dict(os.environ, NODE_PATH=root, LABSYNC_URL=base, LABSYNC_RESET_TOKEN=TOKEN)
    proc = subprocess.run([node, os.path.join(ROOT, "tests", "e2e", "smoke.cjs"), str(tmp_path)], env=env,
                          capture_output=True, text=True, timeout=240)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "passed" in proc.stdout


def test_typed_request_books_without_anyone_moving(server):
    base, _ = server
    _, r, _ = call(base, "POST", "/api/requests", {"text": "plate reader for 45 minutes Monday at 10"})
    _, plan, _ = call(base, "GET", "/api/plans/" + r["plan_id"])
    option = plan["search"]["options"][0]
    assert option["kind"] == "direct" and option["start"] == "2026-11-02T10:00:00-06:00"
    _, held, _ = call(base, "POST", "/api/plans/%s/hold" % r["plan_id"], {"option_id": option["option_id"]})
    _, plan, _ = call(base, "GET", "/api/plans/" + r["plan_id"])
    mine = next(a for a in plan["approvals"] if a["your_turn"])
    call(base, "POST", "/api/approvals/%s/decide" % mine["approval_id"], {"decision": "approve"})
    status, c, _ = call(base, "POST", "/api/proposals/%s/commit" % held["proposal_id"])
    assert status == 200 and c["receipt"]["booking_ids"] == ["bk_%s_img" % held["proposal_id"]]


def test_release_hold_frees_slots_and_withdraws_requests(server):
    base, api = server
    plan_id, prop = plan_and_hold(base)
    call(base, "POST", "/api/proposals/%s/request-moves" % prop, {})
    status, _, _ = call(base, "POST", "/api/proposals/%s/withdraw" % prop, {}, who="chen_owner")
    assert status == 403
    status, w, _ = call(base, "POST", "/api/proposals/%s/withdraw" % prop, {"reason": "not needed"})
    assert status == 200 and w["state"] == "cancelled" and len(w["withdrawn_approval_ids"]) == 2
    _, inbox, _ = call(base, "GET", "/api/approvals", who="chen_owner")
    assert inbox["waiting_on_me"] == []
    _, mine, _ = call(base, "GET", "/api/approvals")
    assert mine["requested_by_me"] == []
    _, plan, _ = call(base, "GET", "/api/plans/" + plan_id)
    assert plan["stage"] == "needs_revision" and plan["search"]["options"][0]["kind"] == "owner_move"
    assert not [r for r in plan["timeline"]["rows"] if r["status"] == "held"]
    status, again, _ = call(base, "POST", "/api/proposals/%s/withdraw" % prop, {})
    assert status == 409 and again["code"] == "INVALID_TRANSITION"
    assert api.repo.get_record("Booking", "bk_chen_confocal")["start_local"] == "2026-11-03T10:00:00-06:00"
