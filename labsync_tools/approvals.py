"""Approval request records: the human approval queue behind every proposed change.

Each proposed change (reservation, supply order, insight action) gets one Approval
record per required decision, in the order decisions must happen. Authorization
rules live in labsync_core.proposals; this module only stores and reads them.
"""


def open_requests(repo, entity_kind, entity_id, slots, requested_by, request_id=None, held_slot_kinds=()):
    """Create one Approval record per slot. Slots whose kind is in `held_slot_kinds` start as
    `not_sent` (e.g. an owner move before "Ask Chen to move" is pressed); the rest are `pending`."""
    created = []
    for order, slot in enumerate(slots):
        record = {
            "approval_id": repo.next_id("appr"), "entity_kind": entity_kind, "entity_id": entity_id,
            "request_id": request_id, "slot_id": slot["slot_id"], "slot_kind": slot["kind"],
            "slot_order": order, "approver_id": slot["approver_id"], "lab_id": slot.get("lab_id"),
            "booking_id": slot.get("booking_id"), "requested_by": requested_by,
            "status": "not_sent" if slot["kind"] in held_slot_kinds else "pending",
            "decision": None, "decided_by": None, "decided_at": None, "reason": None,
            "created_at": repo.now(),
        }
        created.append(repo.save_record("Approval", record))
    return created


def for_entity(repo, entity_kind, entity_id):
    rows = [a for a in repo.list_records("Approval") if a["entity_kind"] == entity_kind and a["entity_id"] == entity_id]
    return sorted(rows, key=lambda a: a["slot_order"])


def slots_and_decisions(records):
    """Turn Approval records into labsync_core.proposals slots + decisions."""
    slots = [{"slot_id": a["slot_id"], "kind": a["slot_kind"], "approver_id": a["approver_id"],
              "lab_id": a.get("lab_id"), "booking_id": a.get("booking_id")} for a in records]
    decisions = [{"slot_id": a["slot_id"], "actor_id": a["decided_by"], "decision": a["decision"]}
                 for a in records if a["decision"]]
    return slots, decisions
