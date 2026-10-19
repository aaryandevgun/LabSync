# 08 — Milestone board, sequencing, priorities, team split

## Dependency plan (must follow Stage 1 → 2 → 3)

```text
C3 access audit
    -> Domain Types + fixtures
      -> availability rules + booking conflict tests
        -> goal parser + plan UI
          -> owner approval + conditional commit
            -> supplies request + receipt + Stage 1 smoke
              -> cross-lab aggregate snapshot
                -> 3 detectors + forecast
                  -> macro agent + approval trail
                    -> department UI + Stage 2 smoke
                      -> end-to-end demo mode + polish
                        -> pitch screenshots + 3 timed rehearsals
```

## Practical backlog (story points = rough relative effort, NOT time promise)

| Priority | ID | Deliverable | Dependencies | Acceptance |
|---|---|---|---|---|
| P0 | `C3-0` | Platform access/version audit | none | Verified Type read/write and tools capability documented |
| P0 | `DATA-1` | Seed 4 labs/10 instruments/4 rooms/8 SKUs, roles | C3-0 | All fixture IDs and constraints queryable |
| P0 | `CORE-1` | Availability/qualifications/buffers | DATA-1 | Solver tests pass |
| P0 | `AGENT-1` | Goal-to-plan structured extraction | DATA-1 | Canonical prompt parse deterministic required fields |
| P0 | `UI-1` | Workspace/plan/calendar and request editing | CORE-1, AGENT-1 | Researcher can inspect feasible options |
| P0 | `CORE-2` | Approval state + commit + idempotency/audit | CORE-1 | Owner approves; receipt persisted |
| P0 | `UI-2` | Approvals inbox/supply order draft/receipt | CORE-2 | End-to-end Phase 1 demo |
| P0 | `GATE-1` | Phase 1 regression suite | UI-2 | All checkboxes pass |
| P0 | `MACRO-1` | Department aggregate read model | GATE-1 | Derived from Phase 1 store |
| P0 | `MACRO-2` | Purchasing/overload/underuse detectors | MACRO-1 | 3 testable outputs including $95 |
| P1 | `MACRO-3` | Baseline capacity forecast | MACRO-1 | Evaluation error calculated on holdout |
| P0 | `AGENT-2` | Department agent and evidence/approval tools | MACRO-2 | Agent explains true tool result |
| P0 | `UI-3` | Insight dashboard/detail | AGENT-2 | Actionable evidence cards |
| P0 | `GATE-2` | Cross-screen mutation test | UI-3 | Stage 1 write changes macro |
| P0 | `DEMO-1` | Role switch + seeded reset + script | GATE-2 | Runs cleanly three times |
| P0 | `DEMO-2` | Polished navigation, responsive, screenshots | DEMO-1 | Judge-readable at 1440×900 |
| P0 | `PITCH-1` | Six-slide narrative, rehearsal and FAQ | DEMO-2 | Under 3 min, no unverified claims |
| P2 | `ML-1` | Native C3 trained forecast | MACRO-3 | Demonstrably better holdout MAE |
| P2 | `OPTION-1` | Buy/borrow/extend interactive simulator | MACRO-2 | Recomputes valid cost sensitivity |
| P2 | `ILAB-1` | Real iLab integration discovery | credentials + permission | Not required, no unsupported claims |

## Team ownership pattern (adapt to team size)

- **Backend/C3 owner:** tenant setup, persisted Types, domain methods, approvals and audit, seed/reset.
- **AI/orchestration owner:** C3 Lab Planner/Department Agents, tools, output contracts, evaluation prompts, workflows.
- **UI owner:** shared shell, plan studio, timeline, insight dashboard, responsive/states, screenshot polish.
- **Story/QA owner:** synthetic dataset truth, negative tests, role-play, deck, demo reset and stage gates.

If three people: merge Story/QA with agent owner. **Constrain parallel work to interfaces** so UI agent mocks don't diverge from backend schemas.

## Integration checkpoints

### Gate A: End of Stage 1
- Run full path from a fresh seed, prove no false booking.
- Collect screenshot: typed prompt → conflict → owner authorization → commit receipt.
- Only after gate A start department model, not a static dashboard.

### Gate B: End of Stage 2
- Recompute shared SKU detector after Stage 1 supply draft.
- Confirm same `lab_moreno`, `ANTI_GFP_100` and `confocal_1` IDs across UIs.
- Audit shows macro insight source snapshot; screen does not mislabel estimated values.

### Gate C: End of Stage 3
- Demo sandbox seeded and reset command passes; presenter never navigates to dev console in live flow.
- At least one visible C3 tool-run trace if tenant is connected; fallback explicitly described otherwise.

## Scope cuts in descending order

1. Cut animated 3D building / campus map; unrelated to one-building scope.
2. Cut mobile-specific interactive drag/drop (keep functional stacked cards).
3. Cut native ML training before cuts to baseline validity (no value without backtest).
4. Cut multi-lab agent deployments if one lab-scoped liaison tool suffices.
5. Cut scenario explorer if it threatens working 3-card dashboard.
6. Cut real iLab API, email and procurement connections before cutting verified C3 persistence and approvals.

**Never cut:** real booking conflict logic, owner approval, one coherent dataset, observable C3 tool use (if available), and credible measured/synthetic distinction.
