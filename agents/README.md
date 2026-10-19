# agents

Definitions for the three LabSync agents, as plain text and JSON. C3 Code configures them in
Agent Workbench (C3_CODE_PROMPTS.md prompt 5); the CLI (deliverable 7) loads them with
`agents.specs.load`.

| Agent (our name) | docs/06 role | Output (schema) | Tools |
|---|---|---|---|
| `lab_agent` | LabPlannerAgent | `ParsedGoal` (request parsing) | catalog, qualifications, scheduler, stock, quote, plan draft, order draft, propose, request change, commit, audit |
| `conflict_negotiator` | LabLiaisonAgent | `SwapProposalRecommendation` | change request (read), qualifications, audit. Read-only. |
| `department_optimizer` | DepartmentEfficiencyAgent | `DepartmentOptimizerOutput` (up to 3 `RecommendationCard`s) | snapshot, forecast, three insight finders, propose action, audit |

Each agent folder has:
- `system_prompt.md`: starts with the docs/06 system instruction word for word, then adds
  LabSync specifics. `{{ACTOR_ID}}`, `{{LAB_ID}}`, `{{NOW}}`, `{{WEEK_START}}`, `{{CAPABILITIES}}`
  and `{{SKUS}}` are filled when the agent is loaded. The catalog lists come from the live
  repository, so they can't drift from the data.
- `tools.json`: the agent's tools with effect, parameters and docstring. This file is
  generated; run `python3 -m agents.export`.
- `few_shots.json`: 3–5 examples, each with `context` (session), `input` (user text or tool
  result) and `output` (structured output).

`schemas/*.json` holds the four output schemas, also generated. `schemas.py` is the source.

## How outputs are checked

1. **Schema:** `jsonschema_lite.validate` (stdlib) checks every output against its schema.
2. **Grounding:** a valid shape isn't enough, so outputs are also compared with the tool
   result they were written from.
   - `check_swap`: ids, times and owner-impact facts must equal the tool's. "approve" is
     refused when the owner has an overlapping session or the booking isn't flexible.
     Alternatives are only allowed with `suggest_other_time`.
   - `check_card` / `check_optimizer_output`:
     - Impact value, unit and next step must follow the kind table. Dollars and hours never mix.
     - Evidence ids and required approvals must come from the insight.
     - Every number in the headline, evidence sentence and summary must appear in the tool
       result.
     - No "saved", "realized" or "guaranteed" claims.
     - Underuse cards are advisory.
     - One card per kind, using the top-ranked insight. Every other insight is listed in
       `alsoDetected`.
3. **Writes:** `plan_create_draft` re-validates the ParsedGoal before writing anything
   (T-AGENT-002).

## Few-shots are real

- The canonical negotiator example and the two department examples use exact tool results
  from `tests/agents/scenarios.py`, and the tests fail if the tools ever return something
  different.
- The other negotiator examples are hypothetical variants and say so. A test checks that
  their facts are consistent with how the tool computes them.
- Every Lab Agent example is accepted by `plan_create_draft`. The canonical one yields the
  docs' 10:00–13:00 owner-move option.

## Decisions to know about

- **Which underuse card.** Doc 02 wants exactly three cards. The underuse finder returns
  every persistently low instrument (Flow-2, Confocal-2, sequencer), ranked lowest first, so
  the card is Flow-2. The others appear in `alsoDetected`.
- **No approval tool.** Agents never get `approval_record`. People decide in the UI, and the
  negotiator's output is a recommendation only (`decidedBy: "owner"`).
- **Alternative windows.** These are the owner's preferred windows for a new search, labelled
  unverified. The negotiator has no scheduler access.
