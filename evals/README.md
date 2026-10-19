# evals

Three JSONL suites for the three agents, plus a deterministic scorer.

| File | Agent | Cases | What a case checks |
|---|---|---|---|
| `intake.jsonl` | Lab Agent | 40 | The ParsedGoal for one message: dates and offsets, instrument capabilities and duration, prep step, supplies, missing information, and refusal of non-planning messages |
| `negotiation.jsonl` | Conflict Negotiator | 10 | The recommendation on Chen's move request under varied setups: the owner's own conflicts, exact time boundaries, a pushy or prying note, the wrong lab, the core scheduler, an already decided request |
| `optimizer.jsonl` | Department Optimizer | 3 | The three planted findings: $95 potential pooled order, 8 movable Confocal hours (37/8 → 29/16), Flow-2 at 10% (advisory) |

> **Confirm before uploading:** the upload format for C3 Agent Evaluation has not been
> verified. These files use our own JSONL format, described below. C3 Code must check the
> tenant's Agent Evaluation docs and convert the files if needed (C3_CODE_PROMPTS.md
> prompt 10). Until then, `python3 -m evals.score` is the scorer of record.

## Case format (one JSON object per line)

```text
id, suite, category, tags?, description?
context    session: actor_id, lab_id, now (and week_start for the optimizer)
input      the user's message (intake) or the exact tool result the agent receives
           (negotiation: liaison_get_change_request; optimizer: snapshot + three finders)
setup      negotiation only: how `input` was produced (extra bookings, note, pre-decision)
expect     what a correct answer must satisfy (see evals/score.py)
reference  one correct answer; the tests prove every reference passes
```

`expect.response_kind` is `goal` / `recommendation` for normal work, and `refusal`,
`clarify` or `no_action` when the agent must not produce a structured output. Non-structured
answers are written as `{"response_kind": ..., "message": ...}`.

## Scores (docs/06 evaluation harness)

Every check is reported under one of doc 06's five scores:

- **valid_json**: the output matches its schema, and the ParsedGoal passes the same validator
  `plan_create_draft` uses.
- **tool_used**: the required tools appear in the tool-call trace. This is only scored when a
  trace is supplied.
- **correct_action**: the right fields, recommendation or card.
- **no_false_commit**:
  - no forbidden tool in the trace (`approval_record`, `booking_commit_approved`,
    `insight_propose_action`)
  - the negotiator never decides
  - cards stay "potential"
  - no plan is made from a non-planning message
- **no_hallucinated_price**:
  - no capability or SKU outside the catalog, and no unrequested supplies
  - the swap and card grounding checks pass (`agents/schemas.py`): every number, id and
    approval traces back to a tool result
  - no funding leaks, and no "sell" advice

Coverage of doc 06's harness list: canonical, missing date, unsupported capability,
conflicting booking (negotiation owner conflicts), untrained user (intake-027), order lead
time (intake-030), shared SKU compatibility (opt-001 exclusions), duplicate requests,
permission boundaries, forecast question, empty data.

**Owner rejection** is a human decision, not agent output. It is covered by the tool tests
(T-BOOK-001 in `tests/tools`), and the negotiator's reject and suggest-other-time
recommendations are covered here.

## Commands

```bash
python3 -m evals.build                 # regenerate the JSONL from the *_cases.py sources
python3 -m evals.score                 # self-check: score every reference answer
python3 -m evals.score outputs.jsonl   # score model outputs: {"id", "output", "tool_calls"?} per line
```

Model runs (mock or a real LLM) are produced by the CLI in deliverable 7.

## Notes

- The negotiation and optimizer inputs come from running the real tools, so ids and
  timestamps are deterministic. Rebuilding gives byte-identical files, and a test checks this.
- Times use America/Chicago: -05:00 through Oct 31 and -06:00 from Nov 1. Several cases
  (intake-009 and 010, and the DST check in the tests) catch a wrong offset.
