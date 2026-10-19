# LabSync — C3 AI Hackathon Build Pack

**Positioning:** *One request for the researcher. One intelligence layer for the department.*

An **AI lab operations copilot** helps a grad student/lab manager plan an experiment, assemble dependencies, reserve shared equipment and rooms, and draft supplies requests. A **department efficiency agent** sees safe, permissioned patterns across labs to recommend shared purchasing, better equipment allocation, and capacity decisions. They are **two views of the same system**, not two unrelated apps.

**Scope:** a fictional life-sciences department in one building; four labs, ten instruments, four rooms, and an eight-SKU consumables catalog. **Demo data is synthetic**; UW–Madison is real-world inspiration, not a connected data source. iLab integration is **proposed**, not asserted to exist or to expose a particular API.

## The 1 → 2 → 3 build sequence (mandatory)

| Stage | Build | Proof it works | Stop/go gate |
|---|---|---|---|
| **1. Lab Assistant** | Research goal → plan → constraints → slot/room/supplies → proposal → approval → synthetic reservation | Demo user completes one coordinated experiment, handling a conflict and buffers | End-to-end test green, visible bookings, persisted approvals |
| **2. Macro Efficiency** | Ingest stage-1 events; demand forecasting, collaborative purchase, overload/underuse recommendations, scenario comparison | Admin sees three evidence-backed insights and proposes/approves action | Reproducible arithmetic, no overbooking, permissions respected |
| **3. Demo & pitch** | Connected polished UI, 3-minute live walkthrough, deck outline, reset/replay | One coherent story traverses Lab Assistant → Department View | Offline backup, timed rehearsal, source/claim QA |

## Open in Claude Code

1. Unzip or copy the `labsync-c3-hackathon/` folder into your desired project root. Preserve `CLAUDE.md` at the root.
2. Open Claude Code in that directory.
3. Use this prompt: **"Read CLAUDE.md and README.md. Implement Phase 1 only, in small testable increments. First perform the C3 access/capability audit and document the selected runtime; then build and verify the Lab Assistant. Do not start Phase 2 until Phase 1 acceptance criteria pass."**
4. When Phase 1 is approved, ask Claude: **"Implement Phase 2 according to docs/02-PHASE-2-MACRO.md; rerun Phase 1 regressions."**
5. When Phase 2 is approved, ask Claude: **"Implement Phase 3 from docs/03-PHASE-3-DEMO.md and docs/07-UI-UX.md; rehearse and test reset."**

## Reading order

1. `CLAUDE.md` — implementation contract and handoff process
2. `docs/00-PRODUCT-STORY.md` — users, use cases, narrative boundaries
3. `docs/04-C3-ARCHITECTURE.md` — platform-first decisions and access audit
4. `docs/05-DATA-FIXTURES.md` — canonical dataset and numeric truth
5. `docs/07-UI-UX.md` — page-by-page interface spec
6. `docs/01-PHASE-1-ASSISTANT.md` → `docs/02-PHASE-2-MACRO.md` → `docs/03-PHASE-3-DEMO.md`
7. Supporting docs: agents/tools, algorithms, workflows, QA, pitch, sources, and `docs/14-C3-CLAUDE-CODE-SETUP.md` for connecting Claude Code to actual C3

## A deliberate boundary

**C3 first, not C3-branded theater.** Use real C3 Type entities/methods, C3 agents/tools/workflows, C3-native data/UI services, and C3 tracing wherever the team has actual access. Don't hardcode non-existent C3 method signatures. A fallback prototype must be labeled as local simulation and keep the same typed domain contracts for migration. Use grants as an **optional forecasting signal** (fictional award/deadline metadata); do not pretend to read private UW grants or infer permissible uses of grant funds.

## Run it (standalone, no C3)

The team chose to build LabSync as a standalone Python app (stdlib only, Python 3.9+); see `docs/PLAN.md` section 6. It runs locally on synthetic data and is labelled "Local demo · C3 not connected".

```sh
python3 -m labsync_app.web --fresh  # web app at http://127.0.0.1:8000 (prints the demo reset token)
python3 -m cli demo                 # the full story, pausing for each person's Approve
python3 -m cli demo --auto          # same, pressing Approve automatically
python3 -m cli ask "I need to image GFP-tagged cells Tuesday morning: three hours on a confocal, a prep room beforehand, and enough anti-GFP antibody and coverslips. I need the results by Wednesday." --as morgan
python3 -m cli reset                # put the saved state back to the seed data
python3 -m evals.run --mock         # score the eval suites (mock agents check the harness, not a model)
python3 -m pytest tests -q
```

State is saved to `var/labsync_state.json` (`--memory` keeps it in memory only). By default the agents run on a deterministic offline mock, which only understands the sample requests from the few-shots and evals. To use Claude, set `ANTHROPIC_API_KEY` and add `--live`. The model defaults to `claude-sonnet-5-5`; you can change it with `LABSYNC_MODEL`. The web app has three screens from `docs/07-UI-UX.md` (My Lab, Approvals, Department) and a simulated-identity switcher. The 3-minute walkthrough is in `docs/DEMO-SCRIPT.md`. In either mode, the agents only parse, advise and write. Every booking, order and recommendation still goes through an Approval made by a person.

## Top-line definition of done

A judge can watch a researcher request an experiment, see an agent identify a conflict and propose a safe resolution, approve the bookings, then switch to the **same dataset** in the department view and see a cross-lab savings opportunity with a defensible calculation. At least one action is persisted, visible after refresh, and auditable. If C3 access is available, the backend/tool calls visibly execute on C3.

See `docs/12-SOURCES-AND-ASSUMPTIONS.md` for authoritative references, caveats, and pitch claims.
