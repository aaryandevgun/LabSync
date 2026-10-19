# LabSync: build plan for approval (revised for the Claude / C3 Code split)

Written after reading every file in `labmesh-c3-hackathon/docs/` (00 to 14), plus the root `CLAUDE.md` and `README.md`. No code has been written yet. This version replaces the first plan and follows your edited prompt.

## Decisions (Aaryan, Oct 19)

- Three agents: Lab Agent, Conflict Negotiator (the docs' LabLiaisonAgent role) and Department Optimizer.
- Everything else follows the docs. Where the prompt and docs differ, the docs win.
- Name: LabSync everywhere. The docs, CLAUDE.md and README were renamed from LabMesh on Oct 19.
- Still open: where the code lives, and a go-ahead to start deliverable 1.

## 1. What we're building

This is one platform with two views of the same synthetic data. It covers a fictional department in one building: 4 labs, 10 instruments, 4 rooms and 8 SKUs, fixed to the week of Nov 2–6, 2026, in `America/Chicago` time.

- **Lab side (the hero scene).** Morgan in the Moreno lab types one goal: GFP imaging Tuesday morning, 3h on a confocal, a prep room beforehand, anti-GFP and coverslips, results by Wednesday.
  - The Lab Agent parses it into an editable plan: prep room, then confocal, then supplies ready, then deadline.
  - Deterministic code finds slots under hard constraints: half-open intervals, a 15-minute confocal buffer, 10-minute room turnover, certifications, maintenance and lead time.
  - It hits Chen's flexible confirmed booking on Confocal-1 (10:00–12:00) and proposes moving Chen to 13:30–15:30. Confocal-2 shows as blocked because Morgan lacks `confocal_2_cert`.
  - Chen approves, Morgan confirms, and a versioned, idempotent commit writes the bookings plus audit events.
  - The supply order stays `awaiting_fund_approval` and is never purchased.
- **Department side.** Exactly three findings, computed from the same records:
  1. A pooled anti-GFP order: $640 becomes $545, a **$95 potential** saving ($75 volume plus $20 shipping).
  2. Confocal overload: 37/40h on Confocal-1 vs 8/40h on Confocal-2. Moving 8 concrete hours gives 29/40 and 16/40, so the total stays at 45h.
  3. Flow-Cytometer-2 underused at 4/40h (10%), low across 6 weeks, so the finding is advisory only.

  It also includes a backtested baseline forecast. Every action is a proposal that needs approvals. Nothing is shown as realized savings.
- **Rules that apply everywhere.**
  - LLMs only parse requests, explain swaps and write cards.
  - Every number, feasibility check and state change comes from pure Python.
  - Nothing is ever presented as live UW, iLab or grant data.
  - Nothing is described as running on C3 until C3 Code verifies it.

## 2. Proposed repo structure

```text
labsync/
  README.md  pyproject.toml            (pytest is the only dev dependency)
  docs/                                (the spec, unchanged)
  data_gen/
    generate.py                        deterministic, fixed seed -> out/*.csv
    columns.py                         column definitions per export
    out/  bookings_ilab_style.csv  rooms_schedule.csv  purchasing.csv
          + reference CSVs (see Q6)
    tests/test_planted_patterns.py     every seed assertion in doc 05
  labsync_core/                        pure functions, stdlib only, no I/O
    models.py        dataclasses for the doc-05 entities
    intervals.py     tz-aware half-open intervals, buffer expansion
    eligibility.py   capabilities, certifications, maintenance
    slots.py         find_slots (15-min steps, DAG ordering, top 3 + exclusions)
    conflicts.py     detect_conflicts
    swap_scoring.py  score_swap_options (weights from Policy records)
    proposals.py     ReservationProposal / Order / Insight state machines, authz
    commit.py        version check, idempotency, compensation plan
    supplies.py      stock, price tiers, lead time, last safe order date
    materials.py     find_shared_materials
    utilization.py   find_utilization_gaps (overload rebalance + underuse)
    forecast.py      moving_average_forecast, EWMA, naive, rolling backtest + MAE
    savings.py       pooled order arithmetic
    tests/
  labsync_tools/
    repository.py    Repository protocol (what C3 Code implements on Types)
    memory_repo.py   in-memory implementation, loads data_gen CSVs
    tools.py         the 17 tools from doc 06, one function each, JSON in/out
    approvals.py, audit.py   approval requests + AuditEvent on every state change
    tests/
  agents/
    lab_agent/  conflict_negotiator/  department_optimizer/
      system_prompt.md  tools.json  schemas/*.json  few_shot.jsonl
  evals/
    intake.jsonl (30+)  negotiation.jsonl (10)  optimizer.jsonl (3)
    README.md (C3 Agent Evaluation upload format: to be confirmed)
    run_local.py     scores against the CLI in mock or live mode
  c3_handoff/
    TYPES_SPEC.md  UI_SPEC.md  C3_CODE_PROMPTS.md
  cli/
    main.py          request -> held booking -> conflict -> swap -> approvals -> findings
    llm.py           LLMClient interface, real client (API key from env), mock client
```

## 3. Things in the division of labor that look wrong

1. **"Demand forecasting with C3's domain algorithm."** Doc 04 says not to assume C3's prebuilt Demand Forecasting app is installed or licensed. Docs 02 and 09 make a backtested baseline the primary method and C3 ML a stretch goal that must beat it on holdout MAE. *Suggestion: `moving_average_forecast` (plus EWMA vs naive, lowest MAE wins) is the primary. C3 Code's prompt 7 first checks whether a C3 forecasting algorithm is even available, and only shows it side by side if it beats the baseline.*
2. **No step owns the C3 access audit.** The docs make it the hard first step (BUILD-STATUS.md, a smoke test of one Type upsert/fetch, one tool and one agent run). *Suggestion: add it as prompt 0 for C3 Code.*
3. **Nobody owns demo reset and replay** (doc 03 requires one-click reset that works 3 times in a row). *Suggestion: I build `reset` in the in-memory repository and the CLI. C3 Code gets a reset step in prompt 2 (load CSVs) that restores the same seed.*
4. **Atomic commit is split across both sides.** The rules for the conditional commit (version compare, idempotency key, compensation if half fails) are pure logic and belong to me. Whether C3 can write several records atomically is a platform question. *Suggestion: `labsync_core.commit` returns a write plan plus compensation steps, and prompt 3 asks C3 Code to execute it atomically or run the compensation and prove it on a forced failure (test T-BOOK-005).*
5. **Audit is on both sides.** You list "audit trail configuration" under C3 Code, but my tools must also write AuditEvent records. *Suggestion: AuditEvent stays an app-level record that my tools create (it's in the data model), and C3 Code adds platform-level logging and tracing on top. They don't replace each other.*
6. **Browser end-to-end tests** (doc 11, Playwright) aren't owned by anyone now that C3 Code builds the UI. *Suggestion: C3 Code covers them in prompt 8. My CLI covers the same journey headless.*
7. **Pitch deck and demo script (doc 03)** aren't in either list. I'm treating them as out of scope unless you want them.

## 4. Open questions

Each has my recommended default, and I'll go with it unless you say otherwise.

**Conflicts with the docs**

1. **Name.** Resolved: LabSync everywhere, and the docs have been renamed.
2. **Three agents vs two.** Doc 06 deploys 2 agents (Lab Planner, Department) plus lab-scoped liaison *behaviour*, and warns against multiplying agents for the count. You want three: Lab Agent, Conflict Negotiator, Department Optimizer. *Default: three, with Conflict Negotiator = doc 06's LabLiaisonAgent. It recommends approve/reject/revise and explains the swap, the owner decides, and it is scoped by `labId`.*
3. **Policy records.** There is no Policy entity in doc 05, and doc 09 fixes the swap score weights as demo heuristics. *Default: add a small `Policy` record that holds exactly those weights plus the buffer and turnover values, with no new behaviour. It goes in TYPES_SPEC.md flagged as an addition to doc 05.*
4. **"Held booking."** The docs have no hold. A ReservationProposal has no side effects until commit. *Default: "held" = a submitted ReservationProposal whose slot blocks other proposals but creates no confirmed Booking and doesn't count toward utilization.*
5. **Three screens vs nine.** Doc 07 specifies 9 screens, and your prompt says three. *Default: My Lab = `/workspace` + `/plans/:id` (with an embedded calendar strip and audit timeline). Approvals = `/approvals`. Department = `/intelligence` + the insight detail drawer. Forecast and scenarios (marked stretch) are deferred, and calendar and activity are folded in.*
6. **CSV shapes.** You asked for iLab-, room- and purchasing-style exports. The docs say iLab's real export or API format is unverified, and many entities don't fit those three files (instruments, certifications, SKUs and price tiers, stock, maintenance, funding hints, 6-week history). *Default: three export-style CSVs with clearly invented, labelled column names, plus reference CSVs for the rest. I won't claim they match real iLab exports.*

**Gaps in the spec I'll fill with defaults**

7. **Staffed hours.** The docs give 40h/week but no daily window. *Default: Mon–Fri 09:00–17:00. I hand-checked that the 34h → 37h Confocal-1 target fits with buffers.*
8. **Missing fixture values.** These are unspecified:
   - prices and lead times for 7 of the 8 SKUs
   - stock levels (Moreno's anti-GFP must be 0 for test T-SCHED-006)
   - `prep_b` turnover and room hours
   - which instrument gets the maintenance window
   - which lab gets the FundingHint
   - who holds `confocal_2_cert` (the 8 movable hours need it)

   *Default: plausible synthetic values, all listed in the data_gen README.*
9. **Forecast history.** *Default: 6 history weeks end Oct 30, and the demo week (Nov 2–6) is week 7.*
10. **Pooling depends on the lab flow.** Patel's 3-pack order is seeded. The pooling finding only appears after Moreno's draft order exists. *Default: optimizer evals and the CLI run the Moreno flow first, as test T-MACRO-004 implies.*

**Logistics**

11. **LLM provider for the CLI.** *Default: Anthropic Claude via `ANTHROPIC_API_KEY`, behind a small `LLMClient` interface so another provider can be swapped in. Mock mode is used by all tests.* Are you sure you don't want it to match whatever LLM your C3 tenant uses?
12. **Python version.** The C3 Python runtime version is unknown. *Default: Python 3.9-compatible syntax and stdlib only, so the tools register without dependency trouble. C3 Code confirms this in prompt 4.*
13. **Where the code lives.** No GitHub repo is attached to this project, only your `labmesh-c3-hackathon` folder. *Default: send me a GitHub repo name and I'll push small commits there. Otherwise I'll work in the device folder.*

## 5. C3 items I'll leave to C3 Code (named in the handoff prompts, not guessed)

Type syntax and references, Data Integration Canvas loading, how Python tools are registered and whether they can see the repository, structured-output enforcement in Agent Workbench, whether APA can pause for an asynchronous approval and resume, multi-record atomicity, user groups for the demo personas, UI framework components, trace IDs for the UI, and the Agent Evaluation upload format. Each one becomes a "verify first" step in C3_CODE_PROMPTS.md.

## 6. Revision: standalone app, no C3 (Aaryan, Oct 19)

Aaryan chose to build everything without C3, so there is no C3 Code handoff. Deliverables 1–5 are
unchanged. Deliverables 6 and 7 are replaced:

**Deliverable 6: engine and CLI (`labsync_app/engine`, `cli/`)**
- The orchestrator replaces APA. It is one Python coordinator for request → Lab Agent → held booking
  → Conflict Negotiator → approvals → commit → Department Optimizer. People decide at every approval.
- A pluggable LLM client: Claude API, with the key read from the `ANTHROPIC_API_KEY` env var and the
  model from `LABSYNC_MODEL`. It also has a deterministic mock mode for offline tests and demos.
- The agent loop calls tools only through `labsync_tools.registry`, and every structured output passes
  the `agents/` schema and grounding checks.
- Durable local storage: the in-memory repository is saved to a JSON file, so state survives a restart,
  and reset restores the seed.
- An eval runner sends the three suites through mock or live agents and scores them with `evals/score.py`.
- The CLI runs the full loop in a terminal (the old deliverable 7).

**Deliverable 7: web app (`labsync_app/web`)**
- A local server built on Python's stdlib HTTP server, with a JSON API over the tools and queries.
- One page with three screens from docs/07: My Lab (request → plan → options → propose), Approvals
  (Chen's card with Approve / Reject / Suggest another time) and Department (three insight cards and
  the forecast).
- A persona switcher, demo reset, and a "Local demo · C3 not connected" badge (CLAUDE.md fallback).
- Plain HTML/CSS/JS with no build step and no runtime downloads, so it works offline.
- Playwright smoke test of the canonical flow, plus a demo script.

**Dropped:** `c3_handoff/`, and C3 features with no local equivalent: the C3 ML forecasting stretch
(the baseline forecast stays), Agent Evaluation upload, and C3 deployment.
