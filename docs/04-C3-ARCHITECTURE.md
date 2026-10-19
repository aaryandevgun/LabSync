# 04 — C3-first system architecture and verification checklist

## Target architecture (C3 as system of record)

```text
                        LABSYNC UI (C3 uiComponentLibraryReact + custom React)
                              | Lab role / Admin role
                              v
                     C3 platform API / Type methods
                              |
       +----------------------+-------------------------+
       |                      |                         |
  C3 persistent Types   C3 Agent Workbench       C3 Agentic Workflows
  labs / resources /    Lab Planner Agent         plan -> validate ->
  bookings / orders /   Department Agent          request approvals ->
  approvals / audits    | tools                     conditional commit
       |               + C3 Action tools                  |
       |               + Python algorithm tools          |
       +----------- domain policy / validation <----------+
                              |
                   C3 Data Fusion / seed ingest
                              |
                 synthetic demo CSV/JSON or fixture Types

   Future / NOT live: approved iLab bridge, room booking, supplies ERP,
   consented grant-planning signals. Never assume live access or API rights.
```

### Highest-value C3 features to use

| Layer | C3 product/component | Hackathon role | Verification |
|---|---|---|---|
| Domain/data | **C3 Type System** persistable entities, relationships, methods | Single source of truth, access policies | Type upsert/fetch/read-after-write working |
| Data | **C3 Data Fusion** / seed data capability | Seed canonical demo fixtures, optionally recurring ingestion | Actual seeded records visible |
| AI | **genaiPlatform**, Agent Gallery/Workbench, Agent deployments | Lab Planner and Department Agent | Live agent run ID + trace |
| Tools | **C3 Action tools** wrapping Type methods; **native Python tools** if necessary | Deterministic queries, solver, forecasting | Tool outputs correct structured JSON |
| Orchestration | **C3 Agentic Workflows** / workflow canvas | Steps and human input for approval | Saved workflow logs and state |
| Forecast | **C3 ML pipeline/Model Ops** only as stretch | Forecast demand from history, compare against EWMA baseline | Valid model, actual holdout MAE |
| UI | **C3 UI Stack `uiComponentLibraryReact`** + custom React TSX | Enterprise forms/grid/charts, timeline, cards | Deployed UI calls C3 Type methods |
| Observability | C3 agent run traces, app audit records | Evidence to judges and debugging | Specific tool invocation/response inspected |
| Security | Platform roles / least-privilege access controls | Researcher vs admin, impacted lab approval | Unauthorized request rejected server-side |

**Do not claim prebuilt C3 Demand Forecasting / Inventory Optimization / Sourcing Optimization applications are installed or licensed.** They are product offerings, not automatically present in a hackathon tenant. Our own small logic runs on accessible C3 primitives.

## Access audit at project start (hard gate)

Claude must populate `BUILD-STATUS.md` with:

```text
Date:
C3 tenant URL/environment (no secrets):
Platform version (doc example 8.10; installed may differ):
Available packages: genaiPlatform?, uiComponentLibraryReact?, Data Fusion?, ML?
Roles: can create Type?, upsert data?, create tool?, create agent?, publish workflow?, deploy UI?
Commands/screens verifying read/write and agent/tool calls:
Available LLM provider configured? Must not invent credentials.
Fallback decision with reason:
```

**Smoke path:** create minimal test Type entity in a sandbox namespace, upsert 1 record, fetch it, create a tool that reads it, invoke from an agent or directly, exercise a UI read. Keep observable evidence such as a trace ID/log snippet. No fabricated screenshots or pretend success.

## Package proposal (adapt to actual tenant conventions)

- `labsyncDomain` — persistent Types and server-side policies; booking, approval and insights.
- `labsyncAgents` — C3 tools, agent definitions, workflow metadata.
- `labsyncAnalytics` — signal transformations and forecast logic.
- `labsyncUi` — C3 UI pages and custom TSX.
- `labsyncSeed` — idempotent demonstration data.

If fewer packages are faster, **one package with clear subfolders is fine**. C3 package names/structure must come from verified version of platform docs; don't invent package manifests before smoke test.

## Contract-first boundaries

### Domain Services (C3 Type methods)
- Availability and eligibility query / slot suggestions.
- Booking conflict checks and compare-and-swap commits.
- Supply stock, lead time, price tiers, fund approval routing.
- Department aggregate snapshot, forecast and insight proposals.
- Event/audit emission and reset-in-demo-mode only.

### Agent responsibilities
- Intent parsing and controlled plan enrichment.
- Recommend which **domain methods** to call.
- Explain constraints, tradeoffs and recommendations; no made-up numeric values.
- Yield to human when authorization needed.

### Why not build custom microservices first

When C3 Type methods and platform API meet the needed contract, no extra REST service or separate DB is necessary. It improves hackathon evidence: C3 isn't used as a superficial chat wrapper. A standalone React UI may use C3 REST APIs if C3 UI packaging is unavailable, but persistence/logic remain C3-native if possible.

## UI decision tree

1. **Tenant supports UI Stack & deployment:** use `uiComponentLibraryReact` grids, forms, charts; custom TSX for capacity heatmap, booking Gantt, workflow canvas and presentational cards. Use platform theme/density tokens.
2. **Can use C3 backend but cannot deploy native UI:** standalone React + Typescript frontend using verified C3 platform API/Auth via thin `C3Adapter`; use a safe same-origin dev proxy if applicable.
3. **C3 environment unavailable:** local mocked domain adapter + explicit topbar `C3 not connected · synthetic demo`. Preserve identical typed contracts; later port Type entities/actions. **Do not market local UI as running on C3.**

## iLab integration stance

UW publicly documents existing iLab scheduling/billing workflows and names participating cores. The proof-of-concept interface is:

```text
FacilitySystemAdapter:
  listResources(scope)
  listBookings(resourceId, window)
  createReservationRequest(request, idempotencyKey)
  getReservationStatus(externalRequestId)
```

These are **our adapter methods**, NOT asserted iLab API routes. Mock implementation is in-scope. Before live integration: verify iLab product API/license, institution's approval, scopes and privacy, scheduling ownership, conflicts, transaction semantics and reversibility. If no API, a user may manually complete a suggested booking in iLab and mark its status, but never label it an automated reservation.

## Permissions, audit, resilience

- Roles: student/researcher (lab scope), lab manager (lab scope), core scheduler (facility), department admin (aggregate view), system/demo admin (reset only).
- No direct editing other lab's commitments without resource owner approval.
- Model `readVersion`/expected version for booking commits to avoid race; fail/replan on stale state.
- Store tool input summary, input Type record IDs, approval actor, action type, changes, outcome and timestamp. Do not log unnecessary personally identifying data.
- Represent agent outcomes as suggestions until platform returns an actual commit receipt.
- A failed external adapter call is **not** a successful booking; show retry or manual handoff.

## Verified documentation anchors

- C3 architecture and packages: https://docs.c3.ai/docs/platform/8.10/topic/how-c3-applications-are-structured
- Agent/tool primitives: https://docs.c3.ai/docs/genaiPlatform/8.10/topic/genaiPlatform-dev-overview
- Agent/workflow UI: https://docs.c3.ai/docs/genAiSearch/8.10/topic/genai-dev-workflows-use-case
- C3 Types: https://docs.c3.ai/docs/platform/8.10/topic/type-inheritance
- C3 UI Stack and customization: https://docs.c3.ai/docs/uiInfrastructure/8.10/topic/ui-package-reference
- React and Type integration: https://docs.c3.ai/docs/uiComponentLibraryReact/8.10/topic/types-and-react
- External React/REST option: https://docs.c3.ai/docs/uiInfrastructure/8.10/topic/non-c3-ui-apps-served-by-server

**Reminder:** Names and docs here derive from publicly indexed C3 platform 8.10 docs, not from inspection of your tenant. Validate versions and permissions.
