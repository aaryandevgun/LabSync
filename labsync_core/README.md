# labsync_core: pure business logic

These are plain functions over plain data: no C3 imports, no I/O and no LLM calls. Inputs are dicts. Rows read straight from `data_gen/out/*.csv` work as-is, because ISO timestamps, `;` lists and `"true"`/`"false"` are all accepted. Outputs are JSON-serializable. Every number, feasibility verdict and state change in LabSync comes from here; the agents only explain it.

```bash
python -m pytest -q tests                                # 97 tests
python -m coverage run --source=labsync_core -m pytest -q tests && python -m coverage report   # 98%
```

| Module | Main function | What it decides |
|---|---|---|
| `conflicts.py` | `detect_conflicts(proposed, existing, resources, maintenance)` | Overlap, buffer, maintenance and staffed-hours violations, each tagged with the blocking booking's owner and `flexible` flag |
| `slots.py` | `find_slots(request, instruments, persons, bookings, rooms, room_bookings, maintenance, policies)` | Up to 3 ranked options. Each is either `direct`, or `owner_move` (a contingent move of one flexible booking). Each comes with a prep-room slot and the approvals it needs. Unqualified alternatives are listed as `blocked_alternatives` |
| `swap_scoring.py` | `score_swap_options(options, policies)` | The docs/09 score: `50·preferred − 2·hoursLate − 3·roomSwitches − 4·ownerMove − 1·extraCost`. Weights come from Policy records. Ties break on start time, then resource id |
| `supplies.py` | `supply_readiness(...)`, `quote(...)`, `check_stock(...)` | Shortfall against the lab's *own* stock, a synthetic quote, the last safe order date and `ORDER_TOO_LATE` |
| `savings.py` | `pooled_savings(sku, quantities)` | Unpooled vs pooled cost, split into volume and shipping. Always `potential`, never realized |
| `materials.py` | `find_shared_materials(orders, skus, labs, policies)` | Poolable cross-lab orders, with the approvers each needs. Rejected groupings come with a reason: `STATE_LOCKED`, `DIFFERENT_SHIP_TO` or `OUTSIDE_WINDOW` |
| `utilization.py` | `find_utilization_gaps(...)`, `plan_transfer(...)` | Overloads, with concrete booking moves to an equivalent instrument. Underuse is flagged only when it persists across history weeks |
| `forecast.py` | `moving_average_forecast(...)`, `forecast_resource(...)` | Weighted moving average, EWMA and naive baselines. A rolling backtest with no future leakage picks the lowest-MAE method |
| `proposals.py` | `can_transition`, `authorize_decision`, `reservation_state` | The docs/10 state machines and who may approve what, and in which order |
| `commit.py` | `plan_commit(...)`, `apply_writes(...)` | Re-validates against the current calendar, checks versions and idempotency, and returns exact writes plus their compensation |

## How the hero scene flows through it

1. **Finding options.** `find_slots` steps through the search window in 15-minute increments on every confocal Morgan is qualified for.
   - Confocal-2 is skipped and reported as `NOT_QUALIFIED`.
   - Tue 10:00–13:00 on Confocal-1 is blocked only by Chen's *flexible* booking. That makes it an `owner_move` option, and `_find_move` puts Chen at the earliest half-hour mark that respects the 15-minute buffer: 13:30–15:30.
   - The latest prep room that ends 15 minutes before imaging is Prep A, 09:00–09:45.
   - Scores: owner-move 46, and the afternoon direct option −4.5.
2. **Approvals.** `reservation_slots` creates an owner slot for Chen and a confirmation slot for Morgan. `authorize_decision` enforces three rules:
   - only Chen (or the core scheduler) can decide Chen's slot
   - Morgan confirms only after Chen
   - anyone else gets `UNAUTHORIZED_APPROVAL`
3. **Commit.** `plan_commit` refuses to run without complete approvals. It re-checks Chen's booking version and re-runs `detect_conflicts` on the live calendar, then returns three writes: move Chen, create Moreno's imaging booking, create the prep reservation. It also returns the inverse writes. A retry with the same idempotency key returns the same receipt and writes nothing.
4. **Supplies.** `supply_readiness` shows that Moreno needs 2 anti-GFP and 1 coverslip box, with a last safe order date of Thu Oct 29.
5. **Department findings.** Run on the committed calendar:
   - `find_shared_materials` finds the Moreno + Patel anti-GFP pool ($640 → $545, $95 potential).
   - `find_utilization_gaps` finds Confocal-1 at 37/40h and moves two concrete 4h flexible bookings to Confocal-2 (29/40 and 16/40). It also flags Flow-Cytometer-2 at 10%, low in all 6 history weeks, as advisory.

## Assumptions added in this module

- Owner-move offers land on half-hour marks (`scheduling.move_step_minutes = 30`). This is what produces the docs' 13:30 slot rather than 13:15.
- Prep must end 15 minutes before imaging (`scheduling.prep_transition_minutes`), matching 09:45 → 10:00 in the docs.
- An instrument is overloaded at 85% or more (`utilization.overload_threshold`). A transfer stops before the target would become busier than the source.
- In the demo, the lab manager records the simulated fund approval, since the personas don't include a PI.
- A core scheduler may decide an owner-move slot (docs/00 role table), but never the requester's confirmation.
- One contingent move per option. Options blocked by two or more bookings are excluded (`BOOKED`).
