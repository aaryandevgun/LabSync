"""Stage 1 through the tools: request -> held booking -> owner move -> approvals -> commit (docs/11)."""
import json

from labsync_tools import queries as Q
from labsync_tools import tools as T
from labsync_tools.memory_repo import InMemoryRepository

from .helpers import authorize_owner_move, ok, option, propose_owner_move


def bookings(repo):
    return {b["booking_id"]: b for b in repo.list_records("Booking")}


def test_canonical_search_matches_the_docs(repo, goal):
    plan_id = ok(T.plan_create_draft(repo, "morgan", goal))["plan_id"]
    found = ok(T.scheduler_find_slots(repo, "morgan", plan_id))
    move = option(found, "owner_move")
    assert (move["resource_id"], move["start"], move["end"]) == (
        "confocal_1", "2026-11-03T10:00:00-06:00", "2026-11-03T13:00:00-06:00")
    assert move["prep"] == {"resource_id": "prep_a", "start": "2026-11-03T09:00:00-06:00",
                            "end": "2026-11-03T09:45:00-06:00"}
    assert move["contingent_moves"][0]["booking_id"] == "bk_chen_confocal"
    assert move["contingent_moves"][0]["to"] == {"start": "2026-11-03T13:30:00-06:00", "end": "2026-11-03T15:30:00-06:00"}
    assert [b["resource_id"] for b in found["blocked_alternatives"]] == ["confocal_2"]  # T-SCHED-004
    assert found["supply_readiness"]["last_safe_order_date"] == "2026-10-29"
    assert "bk_chen_confocal" in found["source_record_ids"]


def test_search_is_read_only(repo, goal):
    plan_id = ok(T.plan_create_draft(repo, "morgan", goal))["plan_id"]
    before = (repo.list_records("ExperimentPlan"), repo.list_records("AuditEvent"), repo.list_records("Booking"))
    ok(T.scheduler_find_slots(repo, "morgan", plan_id))
    assert (repo.list_records("ExperimentPlan"), repo.list_records("AuditEvent"), repo.list_records("Booking")) == before


def test_full_flow_commits_exact_times_and_moves_chen(repo, goal):
    seed = bookings(repo)
    plan_id, proposal_id = authorize_owner_move(repo, goal)
    assert bookings(repo) == seed  # approvals alone change no booking
    commit = ok(T.booking_commit_approved(repo, "morgan", proposal_id, "req:commit:1"))
    after = bookings(repo)
    chen = after["bk_chen_confocal"]
    assert (chen["start_local"], chen["end_local"]) == ("2026-11-03T13:30:00-06:00", "2026-11-03T15:30:00-06:00")
    mine = after["bk_%s_img" % proposal_id]
    assert (mine["resource_id"], mine["start_local"], mine["end_local"], mine["user_id"]) == (
        "confocal_1", "2026-11-03T10:00:00-06:00", "2026-11-03T13:00:00-06:00", "morgan")
    room = repo.get_record("RoomReservation", "rr_%s_prep" % proposal_id)
    assert (room["room_id"], room["start_local"], room["end_local"]) == (
        "prep_a", "2026-11-03T09:00:00-06:00", "2026-11-03T09:45:00-06:00")
    assert set(commit["receipt"]["booking_ids"]) == {"bk_chen_confocal", mine["booking_id"], room["reservation_id"]}
    assert repo.get_record("ExperimentPlan", plan_id)["state"] == "committed"
    assert repo.get_record("ReservationProposal", proposal_id)["state"] == "committed"
    # Calendar after: no overlap or hidden 15-minute buffer violation on Confocal-1 that day.
    day = sorted((b["start_local"], b["end_local"]) for b in after.values()
                 if b["resource_id"] == "confocal_1" and b["start_local"].startswith("2026-11-03"))
    from labsync_core.values import to_dt
    for (s1, e1), (s2, e2) in zip(day, day[1:]):
        assert (to_dt(s2) - to_dt(e1)).total_seconds() >= 15 * 60


def test_proposals_change_no_confirmed_booking(repo, goal):
    seed = bookings(repo)
    _, prop = propose_owner_move(repo, goal)
    ok(T.liaison_request_change(repo, "morgan", prop["proposal_id"], "bk_chen_confocal"))
    assert bookings(repo) == seed
    assert prop["state"] == "owner_approval_pending"


def test_commit_without_approvals_is_refused(repo, goal):
    seed = bookings(repo)
    _, prop = propose_owner_move(repo, goal)
    result = T.booking_commit_approved(repo, "morgan", prop["proposal_id"], "k")
    assert result["status"] == "error" and result["code"] == "MISSING_APPROVAL"
    assert bookings(repo) == seed
    fails = [e for e in repo.list_records("AuditEvent") if e["operation"] == "booking_commit_approved"]
    assert fails and fails[-1]["status"] == "failed"


def test_owner_move_request_hidden_until_sent_and_ordered(repo, goal):
    _, prop = propose_owner_move(repo, goal)
    owner, confirm = prop["approvals"]
    assert ok(Q.list_approval_queue(repo, "chen_owner"))["waiting_on_me"] == []
    assert ok(Q.list_approval_queue(repo, "morgan"))["waiting_on_me"] == []  # not Morgan's turn yet
    early = T.approval_record(repo, "morgan", confirm["approval_id"], "approve")
    assert early["code"] == "APPROVAL_OUT_OF_ORDER"
    unsent = T.approval_record(repo, "chen_owner", owner["approval_id"], "approve")
    assert unsent["code"] == "NOT_REQUESTED"
    sent = ok(T.liaison_request_change(repo, "morgan", prop["proposal_id"], "bk_chen_confocal", "Can you shift?"))
    inbox = ok(Q.list_approval_queue(repo, "chen_owner"))["waiting_on_me"]
    assert [c["approval_id"] for c in inbox] == [owner["approval_id"]]
    assert inbox[0]["impact"]["to"]["start"] == "2026-11-03T13:30:00-06:00"
    assert ok(Q.list_notifications(repo, "chen_owner"))["notifications"][0]["channel"] == "in_app"
    assert sent["owner_id"] == "chen_owner"
    assert (sent["impact"]["booked_by"], sent["impact"]["flexible"]) == ("chen_owner", True)
    assert sent["impact"]["person_conflicts"] == []  # Sam's 10:30-14:00 plate read is not Chen's own session
    # Impact shown to Chen lists only Chen's own lab bookings.
    labs = {repo.get_record("Booking", b["booking_id"])["lab_id"] for b in sent["impact"]["your_other_bookings_that_day"]}
    assert labs <= {"lab_chen"}


def test_owner_rejection_keeps_chen_and_allows_replan(repo, goal):
    """T-BOOK-001: original Chen booking remains, Moreno not committed; replan with the direct option."""
    seed = bookings(repo)
    plan_id, prop = propose_owner_move(repo, goal)
    owner, _ = prop["approvals"]
    ok(T.liaison_request_change(repo, "morgan", prop["proposal_id"], "bk_chen_confocal"))
    rej = ok(T.approval_record(repo, "chen_owner", owner["approval_id"], "reject", "Need the morning slot"))
    assert (rej["entity_state"], rej["next_step"]) == ("rejected", "replan")
    assert repo.get_record("ExperimentPlan", plan_id)["state"] == "needs_revision"
    assert T.booking_commit_approved(repo, "morgan", prop["proposal_id"], "k")["status"] == "error"
    assert bookings(repo) == seed
    found = ok(T.scheduler_find_slots(repo, "morgan", plan_id))
    direct = option(found, "direct")
    second = ok(T.booking_propose(repo, "morgan", plan_id, direct["option_id"], "prop-key-2"))
    assert second["state"] == "requester_approval_pending"  # no owner step, but confirmation still required
    assert [a["slot_kind"] for a in second["approvals"]] == ["requester_confirm"]
    ok(T.approval_record(repo, "morgan", second["approvals"][0]["approval_id"], "approve"))
    ok(T.booking_commit_approved(repo, "morgan", second["proposal_id"], "k2"))
    assert bookings(repo)["bk_chen_confocal"] == seed["bk_chen_confocal"]


def test_wrong_lab_cannot_approve_chen_move(repo, goal):
    """T-BOOK-002: a Patel actor attempting Chen's owner approval is denied and audited; nothing changes."""
    _, prop = propose_owner_move(repo, goal)
    owner, _ = prop["approvals"]
    ok(T.liaison_request_change(repo, "morgan", prop["proposal_id"], "bk_chen_confocal"))
    before = (repo.get_record("Approval", owner["approval_id"]), repo.get_record("ReservationProposal", prop["proposal_id"]))
    result = T.approval_record(repo, "jordan_patel", owner["approval_id"], "approve")
    assert result == {"status": "error", "code": "UNAUTHORIZED_APPROVAL", "message": "You are not authorized for this action."}
    assert (repo.get_record("Approval", owner["approval_id"]),
            repo.get_record("ReservationProposal", prop["proposal_id"])) == before
    denied = [e for e in repo.list_records("AuditEvent") if e["status"] == "denied"]
    assert denied[-1]["actor_id"] == "jordan_patel" and denied[-1]["entity_id"] == owner["approval_id"]
    assert T.liaison_get_change_request(repo, "jordan_patel", owner["approval_id"])["code"] == "PERMISSION_DENIED"


def test_held_slot_blocks_a_competing_proposal(repo, goal):
    """T-BOOK-003 at proposal time: a second request can't hold the same time on the same instrument."""
    propose_owner_move(repo, goal)
    rival = dict(goal, labId="lab_patel", requesterId="jordan_patel", supplies=[])
    plan_id = ok(T.plan_create_draft(repo, "jordan_patel", rival))["plan_id"]
    found = ok(T.scheduler_find_slots(repo, "jordan_patel", plan_id))
    from labsync_core.values import to_dt
    for o in found["options"]:
        if o["resource_id"] == "confocal_1":
            assert to_dt(o["end"]) <= to_dt("2026-11-03T10:00:00-06:00") or \
                to_dt(o["start"]) >= to_dt("2026-11-03T13:15:00-06:00")


def test_competing_commit_goes_stale(repo, goal):
    """T-BOOK-003 at commit time: a booking that appears after approval makes the commit stale."""
    plan_id, proposal_id = authorize_owner_move(repo, goal)
    repo.save_record("Booking", {"booking_id": "bk_intruder", "resource_id": "confocal_1", "user_id": "riley_rivera",
                                 "lab_id": "lab_rivera", "start_local": "2026-11-03T11:00:00-06:00",
                                 "end_local": "2026-11-03T12:00:00-06:00", "status": "confirmed",
                                 "flexible": "false", "version": "1"})
    result = T.booking_commit_approved(repo, "morgan", proposal_id, "k")
    assert result["code"] == "SLOT_STALE"
    assert repo.get_record("ReservationProposal", proposal_id)["state"] == "stale"
    assert repo.get_record("ExperimentPlan", plan_id)["state"] == "needs_revision"
    assert repo.get_record("Booking", "bk_%s_img" % proposal_id) is None


def test_commit_retry_returns_same_receipt(repo, goal):
    """T-BOOK-004: same key -> same receipt, exactly one new booking."""
    _, proposal_id = authorize_owner_move(repo, goal)
    first = ok(T.booking_commit_approved(repo, "morgan", proposal_id, "same-key"))
    count = len(repo.list_records("Booking"))
    again = ok(T.booking_commit_approved(repo, "morgan", proposal_id, "same-key"))
    assert again["replayed"] and again["receipt"] == first["receipt"]
    assert len(repo.list_records("Booking")) == count
    assert sum(1 for b in repo.list_records("Booking") if b["booking_id"].startswith("bk_prop")) == 1


def test_propose_retry_returns_same_proposal(repo, goal):
    plan_id, prop = propose_owner_move(repo, goal, key="dup")
    again = ok(T.booking_propose(repo, "morgan", plan_id, "anything", "dup"))
    assert again["replayed"] and again["proposal_id"] == prop["proposal_id"]
    assert len(repo.list_records("ReservationProposal")) == 1


def test_partial_commit_is_compensated(repo, goal):
    """T-BOOK-005: a failure part-way leaves no partial final state."""
    seed_bookings, seed_rooms = bookings(repo), repo.list_records("RoomReservation")
    plan_id, proposal_id = authorize_owner_move(repo, goal)
    repo.fail_on_write = repo._writes + 1  # first write (Chen's move) succeeds, the second fails
    result = T.booking_commit_approved(repo, "morgan", proposal_id, "k")
    assert result["code"] == "PARTIAL_COMMIT_RECOVERY" and result["compensated_ids"] == ["bk_chen_confocal"]
    assert bookings(repo) == seed_bookings
    assert repo.list_records("RoomReservation") == seed_rooms
    assert repo.get_record("ReservationProposal", proposal_id)["state"] == "failed"
    assert repo.get_record("ExperimentPlan", plan_id)["state"] == "failed"
    assert any(e["operation"] == "booking_commit_compensated" for e in repo.list_records("AuditEvent"))


def test_only_the_requester_can_commit(repo, goal):
    _, proposal_id = authorize_owner_move(repo, goal)
    result = T.booking_commit_approved(repo, "chen_owner", proposal_id, "k")
    assert result["code"] == "UNAUTHORIZED"
    assert repo.get_record("ReservationProposal", proposal_id)["state"] == "authorized"


def test_every_state_change_is_audited(repo, goal):
    _, proposal_id = authorize_owner_move(repo, goal)
    ok(T.booking_commit_approved(repo, "morgan", proposal_id, "k"))
    ok(T.supply_create_order_draft(repo, "morgan", repo.list_records("ExperimentPlan")[0]["plan_id"], "o"))
    events = repo.list_records("AuditEvent")
    for kind, id_field in (("ExperimentPlan", "plan_id"), ("ReservationProposal", "proposal_id"),
                           ("OrderProposal", "order_id")):
        for rec in repo.list_records(kind):
            if rec.get("provenance") == "seed" or kind == "OrderProposal" and rec.get("plan_id") is None:
                continue
            states = [e["after"]["state"] for e in events if e["entity_id"] == rec[id_field]
                      and e["after"] and "state" in e["after"]]
            assert states and states[-1] == rec["state"], (kind, rec[id_field], states)
    decided = [a for a in repo.list_records("Approval") if a["status"] == "decided"]
    for a in decided:
        assert any(e["entity_id"] == a["approval_id"] and e["operation"] == "approval_record" for e in events)
    commit = next(e for e in events if e["operation"] == "booking_commit")
    assert commit["before"] and commit["after"] and commit["actor_id"] == "morgan" and commit["created_at"]


def test_plan_view_and_calendar_scope(repo, goal):
    plan_id, prop = propose_owner_move(repo, goal)
    view = ok(Q.get_plan(repo, "morgan", plan_id))
    assert view["proposals"][0]["proposal_id"] == prop["proposal_id"]
    assert Q.get_plan(repo, "jordan_patel", plan_id)["code"] == "PERMISSION_DENIED"
    cal = ok(Q.get_calendar(repo, "jordan_patel", ["confocal_1"], "2026-11-03"))["rows"]
    held = [r for r in cal if r["status"] == "held"]
    assert held and all(r["lab_id"] is None and r["user_id"] is None for r in held)


def test_results_are_json_serializable(repo, goal):
    plan_id, prop = propose_owner_move(repo, goal)
    for result in (prop, T.scheduler_find_slots(repo, "morgan", plan_id),
                   T.audit_get_activity(repo, "morgan", request_id=prop.get("request_id"))):
        json.dumps(result)


def test_fresh_repositories_are_deterministic(goal):
    a, b = InMemoryRepository(), InMemoryRepository()
    for r in (a, b):
        authorize_owner_move(r, goal)
    assert a.list_records("AuditEvent") == b.list_records("AuditEvent")


def test_move_request_flags_the_owners_own_overlapping_session(repo, goal):
    repo.save_record("Booking", {"booking_id": "bk_chen_seq", "resource_id": "microscope_wide_1", "user_id": "chen_owner",
                                 "lab_id": "lab_chen", "start_local": "2026-11-03T14:30:00-06:00",
                                 "end_local": "2026-11-03T16:00:00-06:00", "status": "confirmed",
                                 "flexible": False, "version": 1})
    _, prop = propose_owner_move(repo, goal)
    sent = ok(T.liaison_request_change(repo, "morgan", prop["proposal_id"], "bk_chen_confocal"))
    assert sent["impact"]["person_conflicts"] == ["bk_chen_seq"]
