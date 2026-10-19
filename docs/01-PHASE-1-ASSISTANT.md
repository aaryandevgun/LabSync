# 01 — PHASE 1: Lab Assistant planner (build FIRST)

## Stage outcome

A real, functioning **research goal → editable experiment plan → calendar constraints → approval → committed synthetic booking** journey backed by C3 Type methods and agent tools where access allows. Room, instrument and supply tasks are all covered at minimum demo depth.

## User-facing workflow

1. **Open Lab Workspace** for Moreno Cell Biology. Empty screen includes one sample prompt button.
2. Enter canonical demo request from `00-PRODUCT-STORY.md`.
3. The C3 Lab Planner Agent translates natural language to validated structured plan draft. **Never infer unstated biology protocol as fact**: mark equipment/prep/supplies as suggestions for confirmation.
4. Show a four-step execution graph: `Sample prep (room) → Image (confocal) → Supplies ready → Deadline` (with real temporal edges; supplies should arrive before prep). List estimated durations, missing quantities, and source of suggestion.
5. `Find options` calls deterministic availability engine: checks equipment compatibility, user certifications, room occupancy, prep buffer, maintenance, hours, existing reservations and grant/fund constraints for purchases.
6. Conflict row: Chen holds Confocal-1 Tue Nov 3 10:00–12:00; Chen's existing booking is flexible and can be shifted by its owner. Show explicit choices: ask Chen to move; use compatible Confocal-2 if trained; select different slot. **Only ask Chen if no unilateral authority.**
7. `Request swap` creates a pending negotiation, sends **simulated in-app notification** to Chen (no email). Chen can approve or reject. Reject path returns user to alternatives.
8. On Chen approval and Moreno final confirmation, commit atomic conditional mutations: Chen moved to 13:30–15:30; Moreno Confocal-1 booking 10:00–13:00; room 09:00–09:45 (with resource buffers). Supply purchase remains **proposed / needs fund approval**, unless simulated manager approval explicitly recorded.
9. Show an outcome receipt and calendar update; refreshing preserves committed state. Macro input event emitted for Stage 2.

## Implementation tasks (ordered vertical slices)

### P1.0 — Bootstrap and verifiable C3 foundation
- Audit tenant, package version, platform permissions, persistence, genaiPlatform dependency, agent/tool creation permissions, UI runtime. Record in BUILD-STATUS.md.
- Define minimal Type data for lab, user/certifications, room, instrument, supply SKU/stock, booking, experiment plan, approval, audit event.
- Import deterministic canonical fixture snapshot; add seed reset idempotency guard.
- Implement read methods, simple list/availability view, contract tests.
- Exit: booking fixtures render from **actual persisted store** if C3 available.

### P1.1 — Working assistant and editable plan
- Implement `parse_goal` tool returning JSON with: `labId`, `requesterId`, `desiredStart`, `deadline`, `steps[]`, `requiredCapabilities[]`, `supplies[]`, `missingInformation[]`, `confidence`.
- Validate typed output, handle ambiguous time by exposing editable time input. Uncertain recommendations are displayed as suggestions.
- Agent response narrates options but **domain method** calculates all slots and conflicts.
- Exit: typing the canonical prompt yields same reproducible plan fields and validates on second run.

### P1.2 — Constraint solver and alternatives
- 15-min booking buffer on Confocal-1/2; 10-min room turnaround; preferred 09:00–13:00 request; Chen shift candidate 13:30–15:30.
- Time intervals are half-open `[start,end)`; check overlap after adding buffer; see `09-ALGORITHMS.md`.
- Alternative Confocal-2 must be capability-compatible and user-certified. If training differs, mark blocked until certified, **not** bookable.
- Room must precede imaging; reserve supply ready before experiment.
- Exit: conflict recognized, illegal overlap blocked, at least one viable authorized recommendation.

### P1.3 — Approval and actual write
- Persist `Proposal` / `Approval` transitions; actor/role check on server, not UI only.
- Implement conditional version compare in commit to avoid concurrent bookings; failed commit returns replan.
- Idempotent commit `requestId + stage + actionId` prevents duplicates on retries.
- Confirm exact changed resources and time slots, show audit history, and refresh to prove persistence.
- Exit: Chen approver (not Moreno) approves Chen change; Moreno approves own proposed booking; unapproved modification blocked.

### P1.4 — Supplies + supporting interface
- Reagent SKU and coverslip requests, current stock check, synthetic vendor price tiers and lead time; compute deadline feasibility.
- Make order `draft` / `awaiting_fund_approval` only. No checkout, procurement or payment in MVP.
- Lab calendar with before/after view, clear conflict and approval chips; role switch for demo.
- Exit: experiment dependencies, calendar and order summary are all visible and consistent.

## Minimum backend method contracts (pseudo-contract, NOT assumed C3 API syntax)

```text
LabPlan.createDraft(input: GoalRequest) -> PlanDraft
ResourceQuery.findCandidates(input: PlanDraft) -> CandidateOption[]
BookingPolicy.validate(input: ProposedSchedule) -> ValidationReport
BookingProposal.create(input: ProposedSchedule, key: string) -> BookingProposal
ApprovalDecision.record(input: {proposalId, actorId, decision, reason}) -> Approval
BookingCommit.commitApproved(input: {proposalId, expectedVersions, key}) -> CommitReceipt
SupplyRequest.createDraft(input: {labId, items, fundHint?}) -> OrderProposal
AuditQuery.listByRequest(requestId) -> AuditEvent[]
```

Attach **C3 Action tools** around tested Type methods. Exact methods, Type declarations and REST invocation are created according to verified tenant docs in Phase P1.0. A proposed domain interface is not proof that these are built-in C3 methods.

## Screen-by-screen Phase 1

- `/workspace` — conversational entry / suggested goals / active experiment list.
- `/plans/:id` — plan graph left, options calendar center, approval sidebar right.
- `/calendar` — resource rows and week grid; existing vs proposed vs blocked states.
- `/approvals` — Chen swap request and manager procurement approval queue.
- `/activity/:id` — timeline of agent steps/tool results + human decisions + commit receipt.

See exact layouts and visual tokens in `07-UI-UX.md`.

## Must-test negative paths

- Two users try to book the same slot → one commit wins, other replans.
- Chen rejects shift → no changes; alternate presented.
- Reagent can't arrive before experiment → visible blocker, plan editable.
- User lacks Confocal-2 certification → not offered as immediately bookable.
- Missing funds/PI approval → supply remains request only.
- Refresh / network retry → no duplicate bookings.
- Unauthorized lab member attempts to approve another lab's move → denied and audited.

## Exit gate: DO NOT start Phase 2 until all true

- [ ] Goal parsed into coherent editable experiment plan with visible source and uncertainty.
- [ ] 3 task domains (instrument, room, supplies) participate in one plan.
- [ ] Conflict, 15-min buffer, alternative and owner approval behave correctly.
- [ ] Conditional commit + idempotency + rollback/failure recovery tested.
- [ ] Synthetic booking persists through refresh; receipt/audit trails inspectable.
- [ ] At least one real C3 Type read/write and real C3 agent/tool execution verified if access exists; otherwise fallback status clearly indicated.
- [ ] Clean UI, keyboard access, responsive layout and seeded reset.
