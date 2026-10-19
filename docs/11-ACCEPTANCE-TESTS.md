# 11 — Test specification, stage gates, demo acceptance

## Verification hierarchy

1. **Unit:** interval logic, buffers, eligibility, price tiers, forecast math, status transitions.
2. **Integration:** persisted C3 Type read/write, agent tool wrappers, materialized department aggregate, audit evidence.
3. **E2E:** canonical workflow via browser, role switched to Chen, approvals, commit, macro update and reset.
4. **Security/reliability:** unauthorized approvals, stale version, retries, reload, invalid LLM JSON, offline fallback labels.

All assertions run against same `imaging_tuesday_v1` fixture. Record actual tool logs/failed cases; tests are not checkboxes filled by guesswork.

## Key unit tests (explicit)

| ID | Given | Then |
|---|---|---|
| `T-SCHED-001` | Chen confirmed 10:00–12:00 Confocal-1 | Moreno 10:00–13:00 direct booking fails overlap |
| `T-SCHED-002` | Chen tentatively moves to 13:30–15:30 with owner approval | Moreno 10:00–13:00 can fit with 15m cleaning buffer |
| `T-SCHED-003` | Confocal-1 10:00–13:00 and proposed follow-up 13:10 | Fails 15m buffer |
| `T-SCHED-004` | Moreno has no Confocal-2 certificate | Confocal-2 isn't directly bookable by Moreno |
| `T-SCHED-005` | Prep A 09:00–09:45, imaging 10:00–13:00 | Dependency and room turnover valid |
| `T-SCHED-006` | Missing anti-GFP, vendor ETA after morning Tue | Plan flagged as unready; no false promise |
| `T-BOOK-001` | Owner rejects move | Original Chen booking remains, Moreno not committed |
| `T-BOOK-002` | Actor from Patel attempts Chen owner approval | Denied + audit, no state change |
| `T-BOOK-003` | Two competing commits same resource and time | At most one success; other returns stale/conflict |
| `T-BOOK-004` | Commit retried with same key | Returns same receipt, exactly one new booking |
| `T-BOOK-005` | Commit fails halfway | No unapproved partial final state; compensation verified |
| `T-SUPPLY-001` | 2 + 3 packs at $120, pooled threshold 5 at $105 | $640 separate, $545 pooled, **$95 potential** |
| `T-SUPPLY-002` | Handling/vendor/ownership incompatible | Pooling opportunity blocked or downgraded |
| `T-SUPPLY-003` | No lab/fund approval | Proposed supply order cannot become completed purchase |
| `T-MACRO-001` | Confocal-1 37h and Confocal-2 8h (both 40h) | 92.5% and 20% utilization |
| `T-MACRO-002` | Exactly eight fully feasible flexible hours to move | After = 29h and 16h; total stays 45h |
| `T-MACRO-003` | Flow-2 uses 4h of 40h | 10% utilization, advisory opportunity only |
| `T-MACRO-004` | Fresh Moreno booking and supply proposal | Department snapshot counts/insight source IDs change after recompute |
| `T-FORE-001` | 6 weeks synthetic input | No future leakage; MAE computed over actual holdout weeks |
| `T-SEC-001` | Lab user requests another lab's restricted funding | No sensitive data leak (incl error payload) |
| `T-AGENT-001` | Canonical request | Valid typed fields, correct tool calls, no fake commit |
| `T-AGENT-002` | Agent returns malformed/untrusted fields | Validation rejects or safely requests edit; no write |
| `T-RESET-001` | 2 completed demo runs and reset | Snapshot returns exact canonical seed, no stale residual approvals |

## Phase 1 user journey acceptance

1. Reset `imaging_tuesday_v1`.
2. Enter canonical goal; generated plan shows real editable dependencies and resources.
3. Conflict displays Chen 10:00–12:00 and disabled direct-book path.
4. Researcher submits owner shift request; role switch to Chen. Chen approves from inbox.
5. Moreno approves final schedule; booking receipt appears; calendar refresh shows exact times, no overlap or hidden 15m buffer violation.
6. Supply draft explicitly says **awaiting fund authorization**; never reads "ordered".
7. Agent technical panel shows verified C3 agent and method call IDs if connected.

## Phase 2 user journey acceptance

1. Department admin accesses overview; sees **three insight types** with grounded metrics.
2. Open pooled order: before $640, after $545, savings potential $95, required approvals enumerated.
3. Open overload: 37/40 vs 8/40, drilldown lists **concrete** candidate move IDs, feasibility, after 29/40 and 16/40 if 8h valid.
4. Open idle: flow2 4/40, long-term trend and comparison, no one-week purchase conclusion.
5. Modify Phase 1 source request and recompute: macro snapshot/data version changes; no detached canned response.
6. Changing role from admin to researcher hides lab confidential financial details and denies restricted API calls.

## Phase 3 show-ready acceptance

1. Replay 3 times from seed in ≤3 minutes **of scripted interaction** (measured by your own rehearsal, not asserted ahead of time).
2. UI at 1440×900 shows legible timeline and macro evidence; mobile 375×812 no overflow or button clipping.
3. Five C3 proof artifacts where available: Type record screenshot, agent tool binding, agent run, workflow approval trace, UI-to-Type action.
4. A disconnected tenant causes honest `C3 not connected` fallback, not faux platform success.
5. Pitch copy names all synthetic assumptions and uses "potential" consistently.
6. Scripted backup screenshots/video are ready; screenshots show the **actual app**, not speculative renders.

## Simple automated report format

```text
RUN: 2026-xx-xx / stage: 1|2|3 / git sha:
Environment: C3 tenant version or Local Demo
Unit: N passed / M failed
Integration: N passed / M failed
Browser E2E: N passed / M failed
Data assertions: N passed / M failed
Known deviations:
Evidence paths:
Stage gate result: PASS | FAIL
```

## Bug triage

P0: any unauthorized commit, misleading "purchased" status, double booking, source-less KPI, false C3 claim, corrupt state. P1: broken primary navigation, macro data stale, role switch fails, incorrect forecast units, unreadable demo at 1440. P2: animation polish, optional scenario filters, mobile heatmap refinements. Don't trade P0 correctness for cosmetic features.
