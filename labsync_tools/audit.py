"""AuditEvent records: one per state change, approval decision or denied attempt."""
import hashlib
import json


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


def record(repo, actor_id, operation, entity_kind, entity_id, request_id=None, source_ids=(), before=None,
           after=None, status="ok", lab_ids=(), detail=None):
    """Write an AuditEvent (docs/05: id, actorId, requestId, operation, sourceIds, payloadDigest, status,
    createdAt) plus before/after and result so every approval/commit is traceable (CLAUDE.md)."""
    event = {
        "audit_id": repo.next_id("audit"), "actor_id": actor_id, "request_id": request_id,
        "operation": operation, "entity_kind": entity_kind, "entity_id": entity_id,
        "source_ids": sorted(set(source_ids)), "before": before, "after": after,
        "payload_digest": digest({"before": before, "after": after}), "status": status,
        "lab_ids": sorted(set(l for l in lab_ids if l)), "detail": detail, "created_at": repo.now(),
    }
    return repo.save_record("AuditEvent", event)
