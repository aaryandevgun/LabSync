"""Shared data and flow helpers for tool tests."""
import copy

from labsync_tools import tools as T

CANONICAL_GOAL = {
    "labId": "lab_moreno", "requesterId": "morgan",
    "goalSummary": "Confocal GFP imaging of fixed cells next Tuesday morning",
    "desiredStart": "2026-11-03T09:00:00-06:00", "preferredEnd": "2026-11-03T13:00:00-06:00",
    "deadline": "2026-11-04T18:00:00-06:00",
    "steps": [
        {"stepId": "prep", "kind": "prep_room", "title": "Sample prep", "durationMinutes": 45,
         "requiredCapabilities": ["wet_prep"], "dependsOn": [], "source": "inferred", "required": True},
        {"stepId": "image", "kind": "instrument", "title": "Confocal imaging", "durationMinutes": 180,
         "requiredCapabilities": ["confocal_imaging", "gfp_imaging"], "dependsOn": ["prep"], "source": "stated",
         "required": True},
    ],
    "requiredCapabilities": [],
    "supplies": [{"skuId": "ANTI_GFP_100", "quantity": 2, "source": "stated"},
                 {"skuId": "COVERSLIP_24", "quantity": 1, "source": "inferred"}],
    "missingInformation": [], "confidence": 0.9,
}


def ok(result):
    assert result["status"] == "ok", result
    return result


def option(result, kind):
    return next(o for o in result["options"] if o["kind"] == kind)


def propose_owner_move(repo, goal, key="prop-key"):
    """Draft -> search -> hold the owner-move option. Returns (plan_id, proposal result)."""
    plan_id = ok(T.plan_create_draft(repo, "morgan", goal))["plan_id"]
    found = ok(T.scheduler_find_slots(repo, "morgan", plan_id))
    prop = ok(T.booking_propose(repo, "morgan", plan_id, option(found, "owner_move")["option_id"], key))
    return plan_id, prop


def authorize_owner_move(repo, goal):
    """Full approval path: hold, ask Chen, Chen approves, Morgan confirms. Returns (plan_id, proposal_id)."""
    plan_id, prop = propose_owner_move(repo, goal)
    owner, confirm = prop["approvals"]
    ok(T.liaison_request_change(repo, "morgan", prop["proposal_id"], "bk_chen_confocal"))
    ok(T.approval_record(repo, "chen_owner", owner["approval_id"], "approve"))
    ok(T.approval_record(repo, "morgan", confirm["approval_id"], "approve"))
    return plan_id, prop["proposal_id"]
