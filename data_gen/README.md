# data_gen: synthetic `imaging_tuesday_v1` dataset

```bash
python -m data_gen.generate          # writes data_gen/out/
python -m pytest tests/data_gen -q   # proves the planted patterns exist
```

Everything is synthetic. Output is byte-for-byte deterministic: fixed seed `20261103`, and the hand-placed demo-week sessions live in `schedule.py`. A test fails if `data_gen/out/` is stale, so regenerate and commit after any change.

## Files in `out/`

| File | Shape | Rows |
|---|---|---|
| `ilab_style_instrument_bookings.csv` | iLab-*style* booking export (6 history weeks + demo week Nov 2–6) | 438 |
| `room_schedule_export.csv` | room-scheduling export (demo week) | 21 |
| `purchasing_export.csv` | purchasing / requisition export (seeded orders only) | 7 |
| `weekly_instrument_demand.csv` | requested vs booked hours per instrument, 6 history weeks | 60 |
| `labs`, `persons`, `instruments`, `rooms`, `vendors`, `supply_skus`, `stock`, `maintenance_windows`, `funding_hints`, `policies`, `departments` | reference tables | small |
| `scenario.json` | scenario id, clock, weeks, canonical request | |

The export column names are our own. Real iLab export and API formats have not been verified (docs/04, docs/12). Lists are `;`-joined, booleans are `true`/`false`, and times appear twice: as ISO 8601 with the Chicago offset and as UTC `Z`.

## Planted patterns (asserted in `tests/data_gen/test_planted_patterns.py`)

- `bk_chen_confocal`: Chen on Confocal-1, Tue Nov 3, 10:00–12:00, confirmed and flexible.
  - Moreno's 10:00–13:00 overlaps it.
  - Chen's 13:30–15:30 slot is free.
  - After the move, all 15-min buffers still hold.
- Prep A is free Tue 09:00–09:45 with 10-min turnover. Prep B is taken then.
- Morgan has `confocal_cert` but not `confocal_2_cert`.
- Confocal-1 demo week: 34h before the commit and 37h after (92.5%). Confocal-2: 8h (20%). Both have 40 staffed hours.
- Exactly 8 flexible Confocal-1 hours (Wed and Thu 09:00–13:00), owned by `confocal_2_cert` holders, fit on Confocal-2. Moving them gives 29h / 16h, and the total stays at 45h.
- Patel's 3 anti-GFP packs plus Moreno's 2 (created by the lab flow, not seeded) form the only valid pool.
  - Unpooled cost is $640 and pooled cost is $545, so the potential saving is $95 ($75 volume + $20 shipping).
  - The TIPS_200 and DAPI_1ML decoys are blocked by ship-to location, the 7-day window and order state.
- Flow-Cytometer-2 is booked 4/40h (10%) in the demo week, with history `[6,5,7,4,6,5]`. Flow-Cytometer-1 has unmet demand to match against it.
- Confocal history is `[24,29,31,28,33,34]` and `[7,10,8,9,6,8]`. Booked hours in the demand table equal the sum of the booking rows.
- The last safe order date for anti-GFP and coverslips is Thu Oct 29 (2 business days before Mon Nov 2).

## Assumptions (values the docs leave open)

- **Staffed hours and clock**
  - Every instrument and room is staffed Mon–Fri 09:00–17:00 (40 h/week).
  - Sessions may end exactly at 17:00. Buffers only separate sessions.
  - Scenario clock is Wed Oct 28, 2026, 10:00 CDT. History bookings before then are `completed`; later ones are `confirmed`.
  - The 6 history weeks run Sep 21 – Oct 30, and the demo week is week 7.
- **People and qualifications**
  - Extra synthetic users: `sam_chen`, `riley_rivera` (both hold `confocal_2_cert`) and `jordan_patel`.
  - `chen_owner` is Chen Imaging's manager.
  - Qualification names: `flow_cert`, `pcr_basic`, `sequencer_cert`, `wet_prep`.
- **Instruments and rooms**
  - Buffers not given in the docs: thermal cyclers and plate reader 0 min, centrifuge 10, sequencer 15, widefield 10.
  - Room turnover not given: prep_b 10 min (same as prep_a), analysis and consult rooms 0.
  - Booked hours for the other seven instruments are invented, apart from Flow-Cytometer-1, which is set as a busy sibling to Flow-Cytometer-2.
  - Maintenance window: Plate Reader, Thu Nov 5 09:00–13:00.
- **Supplies and orders**
  - Prices, tiers, shipping and lead times for the 7 SKUs other than anti-GFP are invented.
  - Coverslips come from a different vendor, so the anti-GFP arithmetic stays exactly as in docs/05.
  - Lab stock levels are invented. Moreno holds 0 anti-GFP and 0 coverslips.
- **Funding hint:** Rivera, end of award on Dec 15, 2026. It is restricted and is a planning signal only.
- **Policy records:** these were added at the team's request and are not in the doc-05 entity table. They hold exactly the docs/09 score weights plus the scheduling, pooling, underuse and forecast parameters.
