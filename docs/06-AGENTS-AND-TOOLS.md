# 06 — Multi-agent topology, prompts, tools, and safe delegation

## Intentional agent design: one coordinated system

**Agents** (C3 Agent Gallery/Workbench when available):

1. **`LabPlannerAgent` (user-facing):** converts goal to editable plan, discovers dependencies, calls tools for available options and requests approvals. It owns no funds and can't bypass booking policy.
2. **`LabLiaisonAgent` (one per participating lab or logical lab-scoped instance):** handles incoming negotiated shift proposal for its lab. For hackathon, one configurable C3 agent with `labId`-scoped tools is simpler than 4 different deployments. The **owner must approve** an agent's recommended response.
3. **`DepartmentEfficiencyAgent` (admin-facing):** consumes aggregate records and deterministic detectors, describes saving/congestion/capacity insights, ranks proposals and requests admin sign-off.
4. **`Coordinator` workflow (not a free-form autonomous LLM boss):** C3 workflow state machine coordinating planner, policy checks, lab-liaison approval and commit. C3 Workflow templates and actual availability should decide precise implementation.

**Demo count:** 2 core deployed agents (Lab Planner, Department) and simulated lab-scoped liaison behavior; **do not artificially multiply autonomous agents** merely for a high count. If time/access allow, deploy named lab scoped agents with traceable separate runs.

## Recommended tool registry (typed JSON, implemented in C3)

| Tool | Input / output | Allowed effect |
|---|---|---|
| `catalog_find_resources` | capability+window → instruments/rooms | Read only |
| `resource_check_qualifications` | userId, resourceId → eligible/reasons | Read only |
| `scheduler_find_slots` | task graph/window → options/conflicts/buffers | Read only |
| `stock_get_availability` | labId, skuIds → stock/dates | Read only |
| `supply_quote` | skuIds, qty → cost/leadTime with assumptions | Read only |
| `plan_create_draft` | validated plan JSON → draftId | Internal draft write |
| `booking_propose` | proposed timeline → proposalId | Proposal only |
| `liaison_request_change` | bookingId, alternatives → owner inbox | Proposal only |
| `approval_record` | proposalId, actorId, decision → status | Write if authorized |
| `booking_commit_approved` | proposalId, versions, key → receipt or conflict | Conditional booking write |
| `dept_get_snapshot` | week, scope → versioned aggregates | Aggregated read only |
| `forecast_resource_demand` | resource/week → forecast/runId/error | Forecast write/read |
| `insight_find_pooled_orders` | window → candidates/calculation | Read only |
| `insight_find_overloads` | week → feasible shift plans | Read only |
| `insight_find_underuse` | week → underuse + matching needs | Read only |
| `insight_propose_action` | insightId, actorId → proposal | Proposal only |
| `audit_get_activity` | requestId → event list | Read scoped |

Use C3 Action tools for Type-backed actions and native Python tool for a complex planner/optimization routine if C3 Action implementation would be unnecessarily difficult. Agent output carries **tool result IDs and data timestamps**.

## System instructions (adapt to verified C3 Workbench configuration)

### LabPlannerAgent

```text
You are LabSync Lab Planner, a research-operations assistant for a participating
life-sciences lab. Convert the researcher's goal into an editable logistics
plan; distinguish explicitly stated constraints from inferred suggestions.
Use only permitted tools to query rooms, instruments, bookings, supply stock,
lead time, qualifications, and owners. Never assume a slot is free or a user
is qualified. Domain tool output determines feasibility, money, lead times,
and final action status. Show alternatives and why they rank. Never commit
purchases, outgoing communications, or other lab's booking changes directly.
Request explicit authorized human approval, including owner approval for moves.
When a tool returns an error/stale version, explain and replan. Never claim
completed booking until a committed receipt is returned.
Respond in structured plan form + brief plain-language explanation, with IDs.
```

### LabLiaisonAgent

```text
You assist only your assigned lab. Evaluate incoming proposed schedule moves
against the lab's owned bookings, deadlines, qualifications and change cost.
Return approve/reject/revise AS A RECOMMENDATION with reason and alternatives.
The human authorized owner alone finalizes the decision. Do not expose
non-permitted details from other labs. Do not auto-revoke confirmed bookings.
```

### DepartmentEfficiencyAgent

```text
You are LabSync Department Intelligence. Identify exactly three insight types:
shared compatible supply orders, overload redistribution, and underuse/capacity.
Only use permission-filtered records and deterministic calculations returned
by tools. For each insight return: summary, evidence IDs, assumptions,
quantified potential impact + unit, confidence/limitations, exclusions,
required approvals, and a proposed next step. Never assert realized savings
or completed transfer without confirmed execution evidence. Never expose one
lab's private funding details to another lab; don't combine dollars and hours
into an arbitrary aggregate savings number. If unable to verify feasibility,
mark insight advisory and ask the admin to inspect constraints.
```

## Tool result format (sketch)

```json
{
  "status": "ok",
  "snapshotId": "snapshot_2026_11_03_demo_v1",
  "sourceRecordIds": ["bk_chen_confocal", "confocal_1"],
  "proposals": [{"id": "proposal_swap_1", "feasible": true,
    "requiresApprovals": ["chen_owner", "morgan"]}],
  "assumptions": ["15-minute instrument buffer"],
  "warnings": []
}
```

All JSON shown here is a **domain contract sketch**, not the C3 API payload schema.

## Negotiation state machine

```text
conflict detected
  -> recommendation issued
  -> proposed change created (no bookings mutated)
  -> impacted owner approves OR rejects
      -> if rejected: alternate slots/replan
      -> if approved: requester confirms
          -> revalidate versions and constraints
              -> conditional commit or return conflict/replan
                  -> audit and refresh both UIs
```

For multiple changes, obtain **all required approvals** and commit a coordinated transaction/compensating saga suitable for actual platform semantics. In case atomic multi-entity operation is not supported, never leave an unapproved partial move. Test recovery.

## Evaluation harness

Create at least 12 prompts/tests spanning canonical request, missing date, unsupported microscope capability, conflicting booking, untrained user, owner rejection, order lead time, shared SKU compatibility, duplicate requests, permission boundaries, forecast questions, and empty data. Score: valid JSON, tool used, correct feasible actions, no false commit, no hallucinated price. Use C3 Agent Evaluation if available; otherwise local deterministic tests.
