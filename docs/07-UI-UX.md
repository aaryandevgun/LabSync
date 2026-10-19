# 07 — Detailed UI / interaction specification (professional, useful, distinctive)

## Design thesis

**LabSync is a polished operations cockpit, not another chat app and not a sci-fi dashboard.** Research decisions, scheduling and approvals are the primary objects. AI chat is the command entry point; evidence, timeline and interactive plans are the interface. Keep the two views within **one information architecture and one visual language**.

**Product signature:** zoom from a single experiment's workflow graph to the department's capacity network. The app should feel calm, fast and capable: thin grid lines, elegant instrument timelines, small live-status indicators, meaningful motion, clear numbers, and an unmistakable audit trail. Avoid animated particles, generic glowing robot icons, giant chat bubbles and dashboard clutter.

## Visual language

- Style: premium research/enterprise SaaS, closer to Linear + Vercel data polish than a consumer chatbot.
- Base: very light warm gray (`#F7F9FB`) main canvas, white (`#FFFFFF`) elevated panels, ink (`#0F172A`) primary text, slate (`#64748B`) secondary; dense/dark admin alternatives permitted **without switching visual system**.
- Brand ink/indigo (`#3555E8`) for primary action; deep teal (`#087E76`) for successful validated actions; amber (`#B7791F`) for proposals needing attention; red (`#C2414A`) only for hard violations; soft violet for forecast, not random gradients.
- Typography: `Inter` or system sans for UI; tabular numerals for metrics; headings medium/semibold. Prefer actual font available; do not add external font fetch as reliability dependency.
- Grid: 8px rhythm; radii 10/14/18; 1px slate borders, low-elevation cards, predictable spacing. Constrained content 1360-1480px; left nav 220-240px.
- Icons: Lucide 18-20px; icon+label for significant actions; never icon-only for destructive actions.
- Chart colors: Confocal-1 indigo, Confocal-2 teal, warning amber, forecast dashed violet, capacity dotted slate, grouped order savings teal; use legend + pattern/dash so not color-only.
- Motion: 150-220ms subtle transitions; respect `prefers-reduced-motion`; no animated confetti or looping background.
- Density: large narrative focus in Lab Workspace, denser analytics on Department view; both share same app chrome, tokens, tables, panels.

## Global information architecture

```text
LabSync  [department/bldg dropdown] [Synthetic sandbox] [C3 connected / not connected]
+------------------------------------------------------------------------+
| Sidebar  | Page topbar: breadcrumbs / date / role / last refreshed       |
|          +-------------------------------------------------------------|
| LAB       | Workspace                                                    |
| - Home    | My Experiments                                               |
| - Calendar| Approvals / Requests                                         |
| - Orders  |                                                              |
| DEPARTMENT| Department Intelligence                                      |
| - Insights| Demand Forecasts                                             |
| - Capacity| Scenarios                                                   |
|          |                                                              |
| BOTTOM    | Activity / Audit                                             |
| - Persona | Settings (demo-only)                                         |
+------------------------------------------------------------------------+
```

**Navigation:** top-level **Lab** and **Department** items clearly mark role switch but not different products. If researcher lacks admin role, do not show underlying restricted data. In demo mode, use clearly labeled simulated persona switcher in sidebar footer.

### Screen 1: `/workspace` — researcher home / experiment composer

- Above fold: eyebrow `YOUR LAB · MORENO CELL BIOLOGY`; headline **"What are you trying to run?"**, subline **"Tell LabSync your goal. We'll assemble the logistics for review."**
- Hero action: large but controlled text input, 2–3 lines, not an entire chat transcript. Placeholder: `Example: Image GFP-tagged cells Tuesday morning...`.
- Prompts as 3 compact chips, not silly cards: `Schedule imaging experiment`, `Find a microscope`, `Reorder supplies`.
- Below: `Upcoming experiments` 2-3 rows (date / goal / step progress / approval state), and `Needs attention` right rail.
- Primary CTA `Generate plan` disabled until input nonempty; show deterministic agent parse loading sequence with practical status (`Matching equipment`, `Checking rooms`, `Verifying supplies`). Do not render invented progress/tool claims; statuses advance on actual completed stages.
- Optional small UI graphic of plan nodes after first successful parse; do not force users to chat endlessly.

### Screen 2: `/plans/:id` — experiment plan studio (PRIMARY HERO SCREEN)

Desktop 3-column composition, approximately 20%/48%/32%:

```text
[Plan header: GFP cell imaging · Tue Nov 3 · Moreno · DRAFT] [Share plan] [Commit after approval]
+------------------+--------------------------------------+--------------------------+
| 1. TASKS         | 2. SCHEDULE & OPTIONS                | 3. APPROVALS / COSTS     |
|                  |                                      |                          |
| [Prep] 9-9:45    | 09  10  11  12  13  14  15         | NEEDS 2 APPROVALS        |
|    |             | Confocal1 [CHEN BOOKED]    ...       | • Chen move [Request]    |
| [Image] 10-13    |          [MOR. PROPOSED]           | • Moreno [Approve]       |
|    |             | Confocal2 [available - certification]|                         |
| [Analyze]       | Prep A   [proposed]                 | SUPPLIES                 |
|                  |                                      | Anti-GFP ×2 / Coverslips |
| constraints      | [Ask Chen to move]  [Other options] | Estimated / needs PI      |
+------------------+--------------------------------------+--------------------------+
```

**Must work:** step nodes are editable (duration, priority, dependency, whether required). Validations recalculate, not merely redraw. Show conflict visually with striping and explanatory text. Clicking conflict opens detail `Owned by Chen · confirmed 10–12 · flexible (request permission)`; on blocked alternative show `Confocal-2 requires certification`. Booked and proposed timeline segments visually distinct with tooltip+labels. Header tracks `Draft → Pending approvals → Ready → Confirmed` with explicit, not ambiguous, transitions.

**Right rail:** quote breakdown (not dollar savings), supply readiness, approval recipients, clear disabled CTA reasons, list of pending/received/denied decisions. `Commit plan` only enabled when all necessary approvals and validation pass. User sees short confirmation modal listing exact writes to be performed.

**Feedback after commit:** in-place receipt, green small banner, booking IDs, calendar links, `View audit trail`; not a fake success animation before server acknowledgement.

### Screen 3: `/calendar` — shared instrument scheduling

- Week switcher (Nov 2–6) and search/filter `Equipment / Rooms / All`, location, capability.
- Left sticky resource names; top hour grid; confirmed solid blocks, proposal outlined blocks, owner-shift awaiting approval hatched amber, maintenance gray.
- `Turnaround buffers` toggle ON by default with tinted narrow segments to visually explain 15-min cleaning rule.
- Click resource → detail drawer (capabilities, qualifications, available slots, ownership, fair access rules) and `Use in current plan` action.
- Allow keyboard list alternative to drag/drop; drag and drop may remain nonessential. Never silently alter confirmed reservation.

### Screen 4: `/approvals` — actual human handoff

- Tabbed `Waiting on me`, `Requested by me`, `History`.
- Card: `Moreno requests moving your Confocal-1 slot` with before/after time mini-visual, rationale, impact to Chen, `Approve`, `Reject`, `Suggest different time`.
- Confirmation modal: “Approving permits the proposed move **only if constraints still validate**.”
- Once approved, card status updates and both parties' activity logs reflect actor/time. If requester later fails commit, show reason.
- Purchases separate from booking: `Proposed supply purchase — awaiting fund authorization` with no live checkout.

### Screen 5: `/intelligence` — department overview (SECOND HERO SCREEN)

- Top header: `Department Intelligence` and smaller `Life Sciences · North Bio Building · Synthetic scenario`, date filter, `Last computed 11:32 AM CST` from actual run.
- Top three stat blocks **do not merge incompatible units**: `Potential purchasing savings $95`, `Confocal-1 utilization 92.5%`, `Open cross-lab recommendations 3`; small metadata text marks estimates.
- Hero row 60/40: **Capacity imbalance chart** with Confocal-1 vs Confocal-2 utilization bars and optional next-week forecast; to right **Top opportunity** with transparent dollars + conditional approvals.
- Insight list below: exactly 3 cards: 1 shared anti-GFP orders, 2 confocal overload, 3 underused flow cytometer. Each card has: type icon, action-oriented headline, 1-sentence supporting evidence, **primary quantified value + unit**, confidence/assumptions note, `Review recommendation`.
- Bottom: `Demand and capacity` 6-week observed/history and forecast; lab activity pulse with aggregate counts only. Don't add unnecessary map or global heatmap when one building suffices.
- Optional small evidence pane: source record count, last agent run, trace link; good for judges who ask about C3.

### Screen 6: `/intelligence/insights/:id` — decision case

- Header: `Combine 5 anti-GFP packs across 2 labs` / `Estimated potential: $95` / proposed status.
- Left 2/3: timeline of evidence, side-by-side before/after arithmetic (unpooled $640 vs pooled $545) and detailed affected SKUs/constraints. For overload, show 37→29 and 8→16 hours; before/after groups and pending owner approvals.
- Right 1/3: **Why this matters**, confidence/evidence IDs, explicit assumptions (`same vendor`, `same storage requirements`, `authorization needed`), required approvers, `Propose shared order` CTA.
- `How calculated` accordion includes exact math and source timestamp. Avoid charts without clear labels.
- Approval clicks create review request state; no automatic order payment, no procurement receipts generated.

### Screen 7: `/intelligence/forecast` — demand and supply

- Chart: historical booked (solid), incoming requests (thin dotted), forecast (dashed), credible low/high shaded interval, available staffed hours horizontal line.
- Heatmap: rows instruments, columns weekdays; cells `% staffed capacity`; hover shows confirmed bookings, projected demand, downtime and staffing. Color thresholds need label not just color.
- Show `Forecast method: weighted baseline v1`; `Backtest MAE: [computed]`, last trained/run date; don't fabricate backtest numbers.
- Allow scenario comparison for +4 staffed hours, redirect to scenarios screen; no manual annotation mistaken for forecast.

### Screen 8: `/intelligence/scenarios` — investment decision explorer

**Illustrative, not a financial recommendation**. Row of 3 options: `Borrow / share capacity`, `Extend staffed hours`, `Purchase another instrument`. Inputs: extra demand hours/week, cost per staffed hour, internal recharge cost/hour, capital price, annual maintenance, available compatible hours, staff requirements, expected horizon. Default assumptions visibly synthetic; each option outputs cost, wait-time benefit, constraints, feasibility badge and break-even sensitivity if calculable. Disable infeasible options and explain why.

This screen is **stretch**; if time-limited, a read-only detail panel inside the underuse card is better than a broken calculator.

### Screen 9: `/activity/:id` — observability without dumping chain-of-thought

- User-facing activity timeline: `Plan generated → Slots checked → Conflict found → Change requested → Chen approved → Moreno approved → Bookings committed`.
- Technical toggle `Tool execution` shows actual tool names, timestamps, data sources, JSON summary, platform run/trace identifiers **if verified**. Do **not** expose raw private model reasoning. Make the causality legible; source proof should match transaction.

## Interaction patterns and edge states

| State | UI behavior |
|---|---|
| Loading | Skeleton for actual API operations; current plan stays visible |
| Empty | Friendly exact next action e.g. "No experiment yet — describe one above" |
| No viable slot | Constraint explanation + closest valid alternates / adjust duration |
| Agent ambiguity | Editable choices and highlighted missing facts; never silently guess |
| Conflict | Red/amber striped segment plus explicit owner / impacted reservation |
| Approval pending | Button disabled with reason, recipient + expected next action |
| Approved | Show who and when; do not auto-commit if requester confirmation missing |
| Failed commit | State unchanged or compensated; stale version; `Recheck plan` CTA |
| C3 unavailable | Persistent subtle topbar status `Local demo · C3 not connected` |
| Synthetic mode | Always visible `Synthetic campus data` chip/badge near global header |
| Permission denied | No leaked metadata; plain explanation + return to authorized space |

## Responsive requirements

- Desktop ≥1280: sidebar + full 3-column plan; charts and evidence side-by-side.
- Tablet 768–1279: sidebar collapses to icons; plan 2 columns with approvals as right drawer; summary not hidden.
- Mobile <768: tabbed `Plan | Schedule | Approvals`, stacked insight cards, chart horizontal scroll or small-screen alternate table; sticky review/approve footer; buttons ≥44px target.
- Must render correctly at 1440×900 and 375×812; no clipped modal or unreadable axis.

## Accessibility & product quality

WCAG-AA-inspired text contrast, semantic keyboard controls and focus order, descriptive aria-labels for status, status announcements for approvals, meaningful text for chart patterns and keyboard-accessible table equivalents. Avoid hover-only critical tooltips. No `disabled` CTA without nearby reason. Apply role enforcement server-side even though pages may hide actions client-side.

## UI component inventory (first-to-build)

- `AppShell`, `RoleSwitcher`, `EnvironmentStatus`, `PageHeader`, `MetricCard`
- `GoalComposer`, `ExperimentStepGraph`, `ExperimentStepEditor`, `DependencySummary`
- `ResourceTimeline`, `ConflictPopover`, `SlotOptionCard`, `QualificationCheck`
- `ApprovalQueue`, `ApprovalDetail`, `CommitConfirmation`, `ActivityTimeline`
- `InsightCard`, `InsightEvidenceDrawer`, `SavingsBreakdown`, `CapacityComparison`
- `DemandForecastChart`, `ResourceHeatmap`, `ScenarioComparison` (stretch)

**Every button in screenshots needs a real meaningful state transition.** No decorative CTA. Use C3-native components for standard grids/forms/charts when verified; use custom React for timeline / dependency graph only where native widgets lack the desired UX.

## Design QA screenshots to capture

1. Home composer before input.
2. Plan with conflict and approvals.
3. Calendar with 15-minute turnaround visualized.
4. Chen approves move.
5. Confirmed plan receipt + audit.
6. Department homepage with 3 insight cards and relevant chart.
7. Pooled order evidence showing $640 → $545.
8. 1440×900 desktop and 375×812 mobile representative screens.
