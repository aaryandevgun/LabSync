# 09 — Deterministic scheduling, procurement pooling, forecasts, optimization

## A. Scheduling is a constraint problem, not an LLM opinion

### Inputs

`ExperimentPlan` steps have durations, windows, prerequisites, required capabilities, earliest start, latest finish, allowed facilities and requester eligibility. `Resource` has open hours, certifications, maintenance, time buffers, location and reservations. `Approval` has scope and immutable actor.

### Hard constraints

1. `start < end`, request within staffed open hours and before project deadline.
2. No overlap between any confirmed reservations after cleaning/turnaround buffer: for each confirmed occupied interval `[s, e)`, block `[s-bufferBefore, e+bufferAfter)` as policy defines. **Do not double-apply buffer if both sides already include it.**
3. All capabilities, training and supervision constraints satisfied (qualified operator may be required).
4. Dependencies: prep ends before imaging starts; supply delivered before prep; tasks can have fixed transition/setup margins.
5. Only a resource owner/core scheduler can authorize changes to a confirmed booking, per configured policy.
6. An order proposal does not equal vendor acceptance, receipt or lab stock.
7. Recheck all constraints at commit against current state/version.

### Soft objectives (rank feasible options, never defeat hard constraints)

A simple transparent weighted score:

`score = 50*(meetsPreferredWindow) - 2*(hoursLate) - 3*(roomSwitchCount) - 4*(requiresOwnerMove) - 1*(estimatedExtraInternalCostUnits)`

Coefficients are **demo heuristics**, not empirically learned benefits. UI shows top 3 options, explains penalties, permits user selection. Use deterministic tie-break `startTime`, then resource ID; do not let agent invent scoring.

### Suggested implementation

1. Enumerate 15-min start increments across requested window.
2. For each instrument candidate capability+qualification check, remove maintenance and occupancy+buffer segments.
3. For each slot, find prior room slot and supply ready date; check DAG ordering.
4. Generate an alternate only if all hard constraints satisfied; otherwise return infeasibility reason.
5. If `flexible` occupied booking candidate could be moved, create **contingent shift proposal** plus dependency approvals; do not pretend it is free.
6. Stable sort feasible candidates by utility score; return maximum 3 choices + explain exclusions.

### Commit algorithm (pseudocode)

```text
commit(proposalId, actor, idempotencyKey):
  if existing_receipt_for_key: return existing_receipt
  assert requester_authorized(actor)
  assert all_required_approvals_valid(proposalId)
  begin_transaction_or_safe_compensation_saga()
  current = read_versions_and_resource_intervals_for_update()
  if current.versions != proposal.expectedVersions: fail_and_replan()
  if !validate_no_overlaps(current.with_proposed_changes): fail_and_replan()
  write_changed_bookings_and_new_booking()
  write_audit_and_commit_receipt()
  commit_transaction()
  return receipt
```

If C3 platform version lacks atomic multi-record transaction facilities for these methods, use an explicitly designed safe compensation path and validate it on a forced failure. **Never** leave Chen moved while Moreno booking failed without recovery/consent.

## B. Agent-to-agent "negotiation" is structured consent

The agent is not an independent human delegate. Tool computes offers, `LabLiaisonAgent` supplies reasoned accept/reject suggestion; owner presses `Approve` or `Reject`. The coordinator interprets pending approvals and then requests final commit. Show this state machine visually. Maintain fairness priorities and avoid letting agent scripts override someone else's priority.

## C. Shared SKU pooling

Group `OrderProposal` items by `(sku, vendor, compatible storage+location, purchase window, ownership/authorization constraints)`. Check:
- Same exact SKU or formally authorized substitution; safety/storage and expiration rules compatible.
- Order statuses allow change; no restricted / incompatible source of funds.
- Per-lab approvals and proportional cost allocation documented.
- New vendor tier and shipping charges compared **after all costs**, no fictional savings.

Canonical math: separate orders `2×120 + 20 + 3×120 + 20 = $640`; pooled `5×105 + 20 = $545`; delta = **$95 potential**. Order allocation must not shift payment to a lab without authorization. Do not use cross-lab physical stock sharing without explicit transfer approval.

## D. Overload rebalance

For each pair of **capability-equivalent** resources within accepted geographic scope, compute available capacity and candidate flexible bookings. Use interval packing / greedy earliest-deadline-first with full qualification+buffers; for best quality small instance, use OR-Tools CP-SAT if available, otherwise transparent bounded search.

Objective: minimize blocked requests + total moved hours penalty + owner disruption while respecting hard constraints. Return `movableHours` with a list of concrete booking IDs and before/after times, not just abstract volume. Capacity comparison must conserve session hours: 37 + 8 = **45**, after proposed shift 29 + 16 = **45**. 8h is possible only if engine returns a valid reassignment. If engine returns 6, show 6; fixture tests can be tailored to guarantee a valid 8.

## E. Underuse and capacity strategy

- Utilization = confirmed session hours / available staffed hours. Explicitly **exclude offline/maintenance hours from denominator**, accounting consistently.
- Flag persistently low use if last 4+ weeks meet threshold and staffing/maintenance are normal. Default heuristic `<25%` for 4 out of 6 weeks (tunable), not a universal industry benchmark.
- Recommend discoverability, scheduling adjacent trained users, and matching alternative capacity first.
- Investment comparison must separate purchase capital, depreciation horizon, service contracts, staffed extension cost and scheduling constraints. A cheap instrument without trained operator is not a feasible "buy" answer.

## F. Demand forecasting with honest evaluation

### Feasible baseline with six weeks

Use historic `requestedHours` (latent demand, if available) and booked hours separately. Predict per resource week:

`EWMA_t = alpha * requestedHours_(t-1) + (1-alpha)*EWMA_(t-1)` with `alpha=0.35` as tunable initial setting.

Add bounded indicators for **already known requests**, maintenance and synthetic due-date pressure only if verified in input. For a demo, easiest dependable estimator is recent 3-week weighted average vs EWMA; pick lower holdout MAE by rolling-origin backtest. Don't leak future week into training. Forecast low/high can use backtest absolute errors quantiles; with tiny data label "illustrative range" and don't assert calibrated 95% interval.

### Evaluation

For historical weeks k=4..6, fit on weeks `1..k-1`, predict week k, calculate `MAE = mean(|prediction - actual|)`. Persist `inputSpan`, `testSpan`, `modelVersion`, `MAE` and prediction. Compare to "last week equals next week" baseline; if model doesn't improve, show baseline. Never fabricate MAE or call six weeks a robust foundation for sophisticated ML.

### Grant data

Use fictional `FundingHint` with deadline/ramp only, not actual UW grant records. Fund restrictions and purchasing policy are **human controlled**, never deduced from a model. A single grant deadline is one noisy signal, not evidence demand must spike.

## G. Ranking recommendations

Return one separate dimension as primary (potential USD, relieved hours, underuse percentage). Suggested importance ordering `actionability * confidence * normalized impact`, but do not show an unexplained weighted score to judges. Card copy instead explains which opportunities are executable and which require approvals. Include counterfactual assumptions and confidence reasons.
