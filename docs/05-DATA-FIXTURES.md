# 05 — Canonical typed data model, fixtures, and arithmetic truth

## Principles

- Every cross-screen KPI must derive from canonical fixture events, not independent hardcoded display values.
- All IDs are fictional. No person, campus core, budget, or grant record is meant to be live UW data.
- Fixed time zone: `America/Chicago`; store time as ISO 8601 with offset or UTC and render in local time. On Nov 3, 2026 Central is CST (UTC-06:00). Avoid naïve local/UTC mixes.
- Seed state has immutable `scenarioId=imaging_tuesday_v1`; `resetDemo` restores it in demo sandbox only.

## Reference entities (suggested C3 entity Types, not concrete DSL syntax)

| Entity | Key fields | Notes |
|---|---|---|
| `Department` | id, name, buildingId | `dept_life_sciences_demo` |
| `Lab` | id, name, departmentId, managerId | Four fictional participating labs |
| `Person` | id, labId, role, resourceQualifications[] | Synthetic personas; avoid real individuals |
| `Instrument` | id, kind, capabilities[], location, bookableHours, requiredQualifications[], bufferMinutes, status | Instrument type compatibility matters |
| `Room` | id, kind, capacity, capabilities[], bufferMinutes, openHours | Prep before microscope |
| `Booking` | id, resourceId, labId, ownerId, startUtc, endUtc, status, flexible, version, provenance | Half-open interval, status confirmed/tentative |
| `ExperimentPlan` | id, labId, requestText, constraints, steps[], status | LLM draft is editable |
| `ReservationProposal` | id, planId, before[], after[], approvalsRequired[], state, expectedVersions, idempotencyKey | No side effects until committed |
| `Approval` | id, proposalId, actorId, role, decision, createdAt | Server authorizes transition |
| `SupplySku` | id, vendorId, unit, basePrice, priceTiers[], handlingRequirements, leadBusinessDays | Illustrative price rules |
| `Stock` | id, labId, skuId, quantity, expiryDate, ownershipSource | A lab's stock is not auto-shareable |
| `OrderProposal` | id, skuItems[], labId, fundingSourceHint?, approvals, state, dueDate | Never live procurement |
| `DepartmentInsight` | id, kind, inputSnapshotId, candidateIds[], estimate, units, assumptions[], state | Versioned rationale |
| `ForecastRun` | id, modelKind, inputWindow, predictedHours, interval, mae, generatedAt | Baseline or C3 ML |
| `AuditEvent` | id, actorId, requestId, operation, sourceIds[], payloadDigest, status, createdAt | Traceable changes |
| `FundingHint` | id, labId, category, milestoneDate, restrictedFlag | Synthetic planning context only; NEVER authorization |

## Labs and demo personas

| Lab ID | Name | Persona | Need |
|---|---|---|---|
| `lab_moreno` | Moreno Cell Biology | `morgan` researcher; `moreno_mgr` manager | Run GFP imaging |
| `lab_chen` | Chen Imaging | `chen_owner` researcher | Existing 2h confocal booking; can approve move |
| `lab_patel` | Patel Neurobiology | `patel_mgr` manager | Same anti-GFP SKU order |
| `lab_rivera` | Rivera Genetics | `rivera_mgr` manager | Other instruments; forecast demand |

Other: `core_sched` equipment scheduler, `dept_admin` department admin. All synthetic demo identities, role switcher must be labeled accordingly.

## 10 instruments, 4 rooms

| ID | Instrument | Relevant constraints |
|---|---|---|
| `confocal_1` | Confocal Microscope 1 | GFP imaging, 15-min cleanup, user needs `confocal_cert` |
| `confocal_2` | Confocal Microscope 2 | compatible GFP imaging, 15-min cleanup, `confocal_2_cert` required |
| `flow_1` | Flow Cytometer 1 | flow analysis, 20-min cleaning |
| `flow_2` | Flow Cytometer 2 | compatible flow analysis, 20-min cleaning |
| `pcr_1` | Thermal Cycler 1 | PCR |
| `pcr_2` | Thermal Cycler 2 | PCR |
| `centrifuge_1` | High-speed Centrifuge | high g-force |
| `plate_reader_1` | Plate Reader | fluorescence |
| `sequencer_1` | Benchtop Sequencer | sequencing |
| `microscope_wide_1` | Widefield Fluorescence Microscope | lower-cost alternative, not identical to confocal |

Rooms: `prep_a` (wet prep, 10-min turnover), `prep_b` (wet prep), `analysis_room` (dry analysis), `consult_room` (meetings). Instrument availability has separate maintenance/qualification records.

### Request-critical bookings (Tuesday Nov 3, 2026)

| Booking ID | Initial booking | Date and local time | State |
|---|---|---|---|
| `bk_chen_confocal` | Chen on `confocal_1` | Nov 3, **10:00–12:00** | confirmed, flexible **only with owner approval** |
| `bk_moreno_pending` | Moreno proposed `confocal_1` | Nov 3, **10:00–13:00** | not present as confirmed in seed |
| `bk_moreno_prep_pending` | Moreno proposed `prep_a` | Nov 3, **09:00–09:45** | proposed, no confirmed conflict |
| `bk_chen_shift_pending` | Chen on `confocal_1` | Nov 3, **13:30–15:30** | proposed, owner approval required |

Confocal turnaround 15 minutes makes 10:00–13:00 and 13:30–15:30 compatible. There is no automatic override. `morgan` has `confocal_cert` but NOT `confocal_2_cert`, so alternate Confocal-2 must display **eligible only after qualification / using qualified operator**, not one-click bookable.

Create additional compatible synthetic confirmed bookings/maintenance windows such that **after Phase 1 commit**, week Nov 2–6 confirmed session hours on `confocal_1` total exactly **37h** (including 3h Moreno), and on `confocal_2` exactly **8h**, with 40 staffed hours each and **at least eight feasible flexible hours on Confocal-1 that can migrate to Confocal-2**. Add supporting bookings across **Mon–Fri**, not fake raw sums; validation tests should compute totals. Ensure no overlap including buffers, and cap realistic schedules at 40 staffed hours (calendar space for cleaning). Avoid overlap with Nov 3 booked slots and choose shift candidates that actually fit Confocal-2.

**Fixture-generation assertion:** total pre-commit Confocal-1 session hours = **34h**; after Chen's move (same duration) and Moreno's 3h booking = **37h**. This requires carefully chosen pre-seeded sessions and adequate gaps. If the `37/40` data cannot be realized with buffers given time/qualifications, **adjust the demo numbers in ALL docs** rather than simulating an impossible state.

## Supplies: eight synthetic SKUs

| SKU | Name | Demo role |
|---|---|---|
| `ANTI_GFP_100` | Anti-GFP antibody pack | 2 Moreno + 3 Patel, pooling candidate |
| `COVERSLIP_24` | Coverslip box | Moreno request |
| `PBS_1L` | PBS buffer 1L | Other lab stock |
| `TIPS_200` | Pipette tips | Shared common consumable |
| `TUBES_15` | 15ml tubes | Shared common consumable |
| `DAPI_1ML` | DAPI stain | Handling check required |
| `DNA_KIT` | DNA isolation kit | Rivera demand |
| `PCR_PLATES` | PCR plate box | PCR demand |

**Pricing for `ANTI_GFP_100`:** $120 per pack normally; >=5 packs pooled at $105 each (same vendor). Shipping $20 per separate order or $20 once pooled. $95 **potential** savings = `(2+3)*(120-105) + (2-1)*20 = 75+20`. For a pooled order, cost allocation follows each lab's actual items and permitted accounting rules; nothing posts to a grant automatically.

**Supply readiness:** the assistant requests `ANTI_GFP_100` and `COVERSLIP_24` before Nov 3 morning. Seed lead time 2 business days; the app must display **last safe ordering cutoff Thu Oct 29** (delivery assumed by Mon Nov 2 close) and treat actual ETA as vendor-dependent. If demo is performed after this cutoff, label the story a **sandbox replay of the Nov 2026 planning week**, not a live order. Dates are fictional scenario dates and may be historically later/earlier relative to demo day.

## Six-week synthetic forecast input

Build six historical Mon–Fri week rows per instrument with `requestedHours` and `bookedHours` separated. Suggested sample booked-hour series (per week) to use ONLY where calendar fixtures agree; adjust week stats from generated events:

- Confocal-1 prior weeks: `[24, 29, 31, 28, 33, 34]` (session hours); demo week after commit 37h.
- Confocal-2 prior weeks: `[7, 10, 8, 9, 6, 8]`; demo week 8h.
- Flow-Cytometer-2 demo week: **4/40 = 10%**; prior 6 weeks `[6, 5, 7, 4, 6, 5]` to show persistently low use.
- Add `MaintenanceWindow` for one non-confocal instrument so planner handles blocked hours.
- `FundingHint` artificial upcoming end-of-award deadline for one lab; use only as a permitted demand-feature if enabled, with visibility restricted and clear synthetic label.

Define whether a given chart depicts `observed`, `confirmed future`, `requested`, or `forecast`; do not combine these into one unlabeled line.

## Derivation checks / nonnegotiable seed assertions

```text
initial_confocal1_hours_demo_week == 34
post_commit_confocal1_hours_demo_week == 37
post_commit_confocal2_hours_demo_week == 8
confocal1_capacity == confocal2_capacity == 40
confocal1_util_post == 37 / 40 == 0.925
confocal2_util_post == 8 / 40 == 0.20
pooled_packs == 2 + 3 == 5
unpooled_total == 5*120 + 2*20 == 640
pooled_total == 5*105 + 1*20 == 545
estimated_potential_savings == 95
flow2_util_demo_week == 4 / 40 == 0.10
shift_if_feasible == 8
confocal1_after_shift == 29 / 40 == 0.725
confocal2_after_shift == 16 / 40 == 0.40
```

All hours are **session hours**; separately enforce buffer/maintenance windows in actual schedule. If shifts prove infeasible due to buffers, qualifications, or staff, show an accurate lower feasible amount rather than pretending 8h can move.
