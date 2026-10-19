# labsync_tools

The agent tools from docs/06, as plain Python functions over `labsync_core`. JSON in, JSON out.
C3 Code registers them in the Tool Workbench and writes a C3-backed repository; this package never
touches C3 itself.

## Files

| File | What it is |
|---|---|
| `repository.py` | The `Repository` interface (now, next_id, list/get/save record, apply_write, reset_to_seed) and the id field per record kind. |
| `memory_repo.py` | `InMemoryRepository`: loads `data_gen/out`, deterministic clock (1 s per call from 2026-10-28 10:00 CDT) and ids, `fail_on_write` for fault tests. |
| `tools.py` | One function per agent tool. Every tool takes `repo`, then `actor_id`, then its arguments. |
| `queries.py` | UI/CLI reads that are not agent tools: approval queue, calendar, plan detail, notifications, and the token-guarded `reset_demo`. |
| `registry.py` | Tool table: effect (from docs/06), which agent gets each tool, parameters, docstring description, and a `call()` dispatcher. |
| `schemas.py` | The ParsedGoal JSON schema (docs/01 field names) and its deterministic validator. |
| `approvals.py`, `audit.py` | Approval request records and AuditEvent records. |

## Rules the code enforces

- Reads write nothing (scheduler, stock, quote, snapshot and the three insight finders). Denied attempts are the one exception: they write a `denied` AuditEvent.
- Every state change goes through `_transition`, which checks the docs/10 state machine and writes an AuditEvent with before/after.
- Proposals open Approval records in the order decisions must happen. An owner-move approval starts as `not_sent` and stays hidden from the owner until `liaison_request_change`.
- `booking_commit_approved` is the only path that changes confirmed bookings. It re-runs the commit checks against the live calendar, applies writes in order, and on a failed write undoes every applied write.
- Orders stop at `approved_request`. Insights stop at `approved`, which records consent and changes no order or booking.
- `actor_id` comes from the host's signed-in session. `registry.call` refuses an agent-supplied `actor_id`, tools outside the agent's list, and unknown or missing arguments. No agent gets `approval_record`; people decide in the UI.
- Department tools require the `department_admin` role. Denials return only `{status, code, message}`. Funding hints are reduced to a count.

## Decisions to know about

- **Agent names.** The three agents map to docs/06 as lab_agent = LabPlannerAgent, conflict_negotiator = LabLiaisonAgent and department_optimizer = DepartmentEfficiencyAgent.
- **Two extra tools.** `supply_create_order_draft` comes from docs/01's `SupplyRequest.createDraft`. `liaison_get_change_request` lets the negotiator read the request it judges.
- **Held slots.** An open proposal in submitted, owner_approval_pending, requester_approval_pending or authorized blocks its slots and the owner-move target for other searches.
- **Deterministic option ids.** `booking_propose` re-runs the scheduler and accepts the option only if the current calendar still offers it. Otherwise it returns `SLOT_STALE`, so the search tool stays read-only.
- **Insight records.** Insights are stored only when an admin proposes one (`insight_propose_action`). The finders keep doc 06's "read only".
- **Assumptions.** Order approvals: the lab manager signs both the lab and the simulated fund slot, because there is no PI persona in the fixtures. Every lab ships to `north_bio_receiving`.

## Tests

`python3 -m pytest tests/tools` has 45 tests. They cover the canonical flow, T-BOOK-001…005, T-SUPPLY-003, T-SCHED-006, T-MACRO-004, T-SEC-001, T-AGENT-002, T-RESET-001, read-only checks, audit coverage and the registry.
