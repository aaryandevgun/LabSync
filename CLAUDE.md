# Claude Code: project instructions (read before coding)

You are implementing **LabSync**, a C3-native research operations prototype for a hackathon. **Build in the exact order Stage 1 → Stage 2 → Stage 3.** Avoid prematurely building general frameworks, mock marketing pages, or integrations with actual UW systems.

## Mission and UX contract

- Product is **one operations platform with two roles**: Lab Workspace (researcher/lab manager) and Department Intelligence (administrator/core manager).
- Main workflow is **goal → dependency plan → validated options → human confirmation → persisted action → organizational signal**.
- The hero flow must work with keyboard and mouse, including empty/error states, without a presenter explaining away broken controls.
- Always show explicit states: `proposed`, `awaiting_approval`, `approved`, `committed`, `rejected`, `failed`; distinguish suggested vs actually executed.
- Never represent synthetic demo reservations, pricing, grant data, or forecasts as live institutional data.

## Mandatory working order

1. Read `README.md`, `docs/00-PRODUCT-STORY.md`, `docs/04-C3-ARCHITECTURE.md`, `docs/05-DATA-FIXTURES.md`, `docs/11-ACCEPTANCE-TESTS.md`, and `docs/14-C3-CLAUDE-CODE-SETUP.md`.
2. **C3 access audit:** inspect installed C3 tools, supplied workspace/cluster, package version, `genaiPlatform`, Type APIs, UI Stack, permissions, Agent/Tool Workbench, and ability to persist/fetch a test Type. Record real evidence in `BUILD-STATUS.md`. Do **not** claim integration without a successful call. If access is absent, use a swappable local adapter and say "C3 adapter not connected" in the app.
3. Implement **Stage 1** from `docs/01-PHASE-1-ASSISTANT.md` with vertical slices and tests; do not start Stage 2 until gate passes.
4. Implement **Stage 2** from `docs/02-PHASE-2-MACRO.md`, consuming the same source-of-truth bookings/orders.
5. Implement **Stage 3** from `docs/03-PHASE-3-DEMO.md`; polish UI and build repeatable replay/reset.
6. Run relevant tests after each change; update `BUILD-STATUS.md` and log blockers, actual commands and test results.

## Engineering rules

- Prefer C3 entity Types + type methods + C3 custom agent tools + C3 workflows + C3 UI Stack; if verified access/capability does not permit a part, use one precisely bounded adapter. **No second backend or database unless absolutely needed as a local fallback.**
- Reuse exact documented C3 APIs for the **actual platform version**. Docs in the references are for 8.10 and may differ from the hackathon tenant. Never invent tool method names or endpoints.
- LLMs interpret user goals, clarify missing inputs, summarize tradeoffs, and explain rationale; **deterministic code** checks permissions, budgets, constraints, booking overlap, calculations, and state transitions.
- Tools use validated structured arguments; tool operations have idempotency keys. Every approval/commit has an actor, timestamp, resource IDs, before/after and result. Make replay/reset deterministic.
- No direct spending, outgoing email, charge to grant, or modification to a different lab's confirmed bookings without explicit authorized action. A lab's agreement and admin approval are distinct when appropriate.
- Never promise iLab API functionality until tested/authorized. `MockILabAdapter` implements local calendar + proposed import/export; `RealILabAdapter` is a later integration task.
- No secrets, real participant names, or private grant records in repo/demos. Do not fetch real user data.
- Avoid unneeded features: no campus-wide rollout, external procurement checkout, email sending, AWS remote compute, grant submission, actual wet-lab safety recommendations, or full inventory ERP.

## Build process

- Start with a small domain model and canonical seeded fixtures in `docs/05-DATA-FIXTURES.md`.
- Implement the **highest-value end-to-end happy path before cosmetics**, but establish tokens/layout early to avoid ugly rework.
- Provide typed public contracts, unit tests, integration tests and Playwright or equivalent end-to-end smoke tests.
- After each stage report: implemented items, which C3 features were actually used and verified, commands/tests run, current known limitations, and whether stage gate passed.
- When a stage gate fails: fix it. Do not hand-wave or silently skip.

## C3 integration priority

1. Persistable data Types (labs, instruments, bookings, inventory/order proposals, approvals, insights, forecasts).
2. Type methods for query/validate/plan/approve/commit; C3-backed audit trail.
3. Agent Gallery/Workbench + Tool Workbench (C3 Action tools for domain methods; Python tools only where needed).
4. Agentic workflow for experimental plan and later insight review; human checkpoints.
5. Data Fusion ingestion of demo seed data and refresh; ML/Model Ops only if there is enough time and supported tenant access.
6. `uiComponentLibraryReact` for data grids/forms/charts with custom React components for sophisticated timelines, graphs and interactions. If native UI deployment is blocked, isolate React frontend behind a C3 Type-method/API adapter.

## Deliverable project tree to create (as build proceeds)

```text
labsync-c3-hackathon/
  CLAUDE.md  README.md  BUILD-STATUS.md
  docs/ ...
  [real C3 packages/source files, according to tenant package conventions]
  [frontend components/tests if not contained in C3 ui/]
  [seed data/tests]
```

The current bundle contains **implementation specifications, not source code**. Discover and use platform-appropriate file structure only after access audit.
