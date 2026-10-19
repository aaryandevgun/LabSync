# 02 — PHASE 2: Department Efficiency Agent (build SECOND)

## Stage outcome

A department administrator opens **Department Intelligence**, sees three ranked, evidence-backed opportunities with material impact and clear tradeoffs, and can submit or approve a **simulated recommendation**. This view is powered by the **same bookings/supplies/orders** used by Phase 1.

## Do not build an isolated second demo

No static chart disconnected from reservations. Stage 1 `BookingCommit`, `OrderProposal` and `AuditEvent` are upstream inputs to Stage 2. The macro agent runs on a shared, permission-filtered organizational graph. It must not expose one lab's confidential grant details to another lab; the department may see aggregate signals only where authorized.

## Exactly three insight classes

### M2.1 — Coordinate shared purchasing
- Detect two or more pending orders for identical, compatible, non-expired SKU within a configurable pooling window (e.g., 7 days), vendor, storage condition and shipping location.
- **Seeded insight:** Moreno wants 2 packs anti-GFP; Patel wants 3. Base $120/pack + $20 shipping per lab; pooled vendor price $105/pack for 5 or more, combined shipping $20. **Potential: $95**, decomposed $75 volume + $20 shipping. If split across grant sources, book one consolidated vendor order **only after separate cost allocation/PI approvals** and compatible purchasing policy; otherwise surface shared-order proposal only.
- Show formula on click. Mark `estimated`, `not realized`, and `synthetic price assumptions`.
- Action: `Propose shared order` → owner approval from both labs → admin check → approved simulated purchase proposal; **never purchase live**.

### M2.2 — Reduce overload with compatible capacity
- For following demo week, Confocal-1 demand = 37 booked hours out of 40 viable hours, Confocal-2 demand = 8/40. Suggested shift 8 of Confocal-1's flexible, compatible hours to Confocal-2; resulting 29/40 (72.5%) and 16/40 (40%). Compare pre/post and preserve 45 total workload hours.
- Check qualifications, instrument equivalence and optics/capabilities, buffers, calendar conflicts, owners, operator availability and deadlines. If impossible, show zero safely movable hours and a reason.
- Action: `Review transfer plan` → list impacted bookings with owner approvals required; **not batch-edit without approval**.
- Value: hours of potential congestion relieved, NOT guaranteed money saved.

### M2.3 — Reveal idle/underused capacity + buy/borrow/extend
- Flow-Cytometer-2 uses 4/40 available hours (10%); don't infer equipment is obsolete. Offer discoverability to qualified users and matched overflow demand from Flow-Cytometer-1; compare short-term **borrow/share**, **extend staffed hours**, **buy** with a transparent scenario table.
- Demand assumptions come from fixture planning signals; do not calculate ROI with invented market prices and present as actual.
- Action: `Publish available capacity` → admin approves visibility; procurement recommendation remains advisory.
- Show underuse trend across 4-6 seeded weeks, not only one week, to minimize false claims.

## Forecasting (minimum viable, defensible)

**Baseline**: use 6 weeks of synthetic historical booked/demand hours, day-of-week profile, recent trend/EWMA, known future bookings, maintenance outages and optional artificial grant-deadline pressure. Output next-week `predictedHours`, `low`, `high`, available capacity and a baseline MAE from backtest. Do not call this advanced ML if it is a rules/weighted-average baseline.

**Stretch**: use a C3 ML pipeline/model if the tenant supports training/serving and sufficient data exist. Show side-by-side baseline vs ML and report MAE on holdout; never replace reliable baseline merely to mention AI.

**Signal separation**: actual bookings ≠ new requests ≠ forecasts; show visually separate lines/legend and confidence badges. A synthetic grant record is a coarse planning signal, never proof a lab has a legal budget allocation.

## Macro agent tool workflow

1. `get_department_snapshot()` returns permission-filtered structured stats and data timestamp.
2. `forecast_capacity(week)` calculates baseline, uncertainty and heldout error.
3. `find_order_pooling()`, `find_transfer_candidates()`, `find_underutilized_assets()` compute **deterministic proposals** and detailed feasibility exclusions.
4. `rank_insights()` orders by evidence/confidence/impact (never adds dollars to hours in one KPI).
5. Natural-language agent **explains** findings and their conditions using validated numeric outputs.
6. Admin opens card → evaluates scenario → requests/approves a non-destructive proposal; impacted lab owners retain authority.
7. Audit trail links recommendation to input version and later disposition (`identified`, `proposed`, `approved`, `executed`, `dismissed`). Only show **realized savings** on supported execution evidence.

## Macro UI

- `/intelligence`: header with department, week, filters and last refresh; 3 KPI summaries (capacity, open proposals, potential savings — units and assumptions clear), ranked insight cards, 2-asset compare, demand forecast.
- `/intelligence/insights/:id`: explanation, evidence, math drawer, before/after, affected labs (permission-limited), constraints, owner approvals and `Propose action`.
- `/intelligence/forecast`: instrument heatmap with observed vs expected vs capacity and confidence.
- `/intelligence/scenarios`: illustrative buy/borrow/extend comparison with editable assumptions and no procurement button.

## Build tasks in order

1. M2.0 materialize cross-lab read models from Stage 1 records; enforce aggregate permissions.
2. M2.1 implement three deterministic detectors and fixture-based tests.
3. M2.2 implement forecast and compare test/metrics; store `ForecastRun` versioned results.
4. M2.3 build C3 macro agent + C3 tools to synthesize recommendations with source IDs and disclaimers.
5. M2.4 implement dashboard, detail cards and permissioned approval workflow.
6. M2.5 verify Stage 1 booking/order mutation updates department metrics, rerun regressions, ensure demo reset.

## Stage exit gate

- [ ] All three insight types are computed from stored synthetic data, not typed into UI.
- [ ] Shared order mathematics reproduces **$95 potential**, not realized.
- [ ] Load shift conserves workload hours and respects approved owners.
- [ ] 6-week forecast generated with uncertainty and measured error; dashboard labels estimates.
- [ ] Insight actions leave proposals, approvals and audit history; no autonomous spending.
- [ ] Stage 1 booking or proposed supply request changes Stage 2 snapshot after refresh/recompute.
- [ ] Macro agent genuinely reads tool-returned values and citations/record IDs, not hallucinated KPIs.
