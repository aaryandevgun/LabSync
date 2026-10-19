# 03 — PHASE 3: Demo integration, story, and hackathon presentation (build THIRD)

## Communication strategy: one product, two levels

**Never open with "we built two products."** Say: **"LabSync coordinates one experiment for a researcher and turns those decisions into department-wide intelligence."** Start zoomed in, zoom out as consequence. Lab Assistant = action layer; Department Intelligence = learning/optimization layer; shared C3 data/agents underpin both.

## Recommended live demo: 3:00 minutes, scripted

| Clock | Speaker/interaction | Visible proof |
|---|---|---|
| 0:00–0:20 | "Running one experiment still requires coordinating equipment, rooms and supplies." Open Lab Workspace and enter seeded sample prompt. | Clear researcher use case and input |
| 0:20–0:50 | "The assistant plans the actual dependencies, not just a chat answer." Click Generate Plan. | Instrument + prep room + antibody/coverslips + constraints |
| 0:50–1:25 | Click `Find options`. Highlight Confocal-1 10–12 conflict, 15m turnaround, alternate, and `Ask Chen to move`. | Constraint-aware plan, no double booking |
| 1:25–1:50 | Switch to Chen role/approval inbox; accept shift to 13:30–15:30; switch back, commit Moreno. | Owner consent, booking persistence, calendar before/after |
| 1:50–2:10 | "The same plan created a potential pooled order." Switch to Department Intelligence. | Continuous story from first screen to second |
| 2:10–2:35 | Open shared purchasing card: $95 = $75 volume + $20 shipping, both labs must approve. | Quantified, auditable recommendation |
| 2:35–2:50 | Open overloaded confocal comparison: 37/40 vs 8/40, potential 8h shift. | Realistic departmental opportunity |
| 2:50–3:00 | "From one request to smarter shared infrastructure — powered by C3 agents, Types and workflows." Show trace + C3 proof if available. | Credible technology + memorable close |

**Flow Cytometer underuse** appears on macro page as third visible card even if not opened. If time allows, replace overload drill-down with buy/borrow/extend scenario explorer in extra 30 seconds.

## Live demo controls

- `Reset demo data` developer-only command (hidden from judge main UI) restores exact date/bookings, mock orders and agent results. Requires verification token/role; cannot reset real institution data.
- `Seed scenario: Imaging Tuesday` shortcut inputs exact request, not pre-commits outcomes.
- `Demo role switcher` Researcher Moreno / Researcher Chen / Department Admin; always label **simulated identity**.
- `Show execution trace` drawer shows agent requested tools, data IDs and commit proof from C3 run (where real).
- `Replay safely` restarts from fixture, does not send external emails or place real orders.
- Prerecorded **offline walkthrough video** or screenshots remain fallback; live version must not silently fake C3 execution.

## Slide deck plan: 6 slides / ~3 minutes pitch + demo

1. **The problem (20s):** "One experiment. Too many handoffs." 3 icons: instrument, room, supplies. Qualify optional old 42% FDP statistic accurately: administrative time across federally sponsored research; not all caused by booking.
2. **One product, two lenses (15s):** large split graphic (left researcher, right admin) connected by one continuous pipeline; do not call them two separate products.
3. **A researcher asks once (15s):** show actual goal sentence, generated dependencies, human-in-loop approval. Transition to live demo.
4. **Live product demo (approx 2min):** use demo script above, switch roles once.
5. **The department-level payoff (20s):** $95 potential pooled order; 8h movable confocal demand; 10% idle flow cytometer; **all synthetic demo assumptions** and distinct units.
6. **Why C3 + adoption (20s):** Type System source of truth, C3 agents/tools/workflows, traceability, additive iLab integration. Start in one biology department, later connect to approved systems.

### Visual storytelling rules

- 1 point per slide, <= 18 words headline/subhead where practical; UI screenshots are primary, not buzzword diagrams.
- One before/after diagram visually explains the value; put technical topology on the final slide only.
- Do not claim live UW integration, real dollar savings, autonomous procurement, or data access.
- Remove "multi-agent" from main headline; show it **in execution**, not buzzword soup.

## Presenter transition lines

- **Zoom in:** "For a scientist, this begins as a single request, not ten systems."
- **Conflict:** "Instead of double-booking, it routes the conflict to the researcher who owns it."
- **Zoom out:** "Now look at what changes when the department can learn from every approved plan."
- **Close:** "Our wedge is one building, but the data model supports an expanding network of shared cores."

## Backup plan and demo risk control

- Seed dates fixed to Tuesday Nov 3, 2026, with clearly synthetic future week context. **Do not use 'next Tuesday' dynamically.**
- Rehearse exact flow with network latency. If live C3 latency causes delay, show persisted dashboard and trace of prior seed test instead of inventing action status.
- Keep browser logged in and tokens away from screen share; use fullscreen 1440px, 100% zoom, avoid tiny text.
- Before demo: reset, smoke test 1 scenario, clear accidental proposals, check time zone `America/Chicago`, capture backup screenshots.
- If agent returns imperfect natural language, manually edit structured plan; transparent human control is a strength, not a demo failure.

## Phase 3 exit gate

- [ ] 3-minute script complete with screenshots matching actual implemented functionality.
- [ ] C3 usage demonstrable via UI/tool trace/logs (or fallback clearly disclosed).
- [ ] Every displayed savings/forecast number reconciles to seeded records.
- [ ] One-click reset + complete replay pass 3 consecutive times.
- [ ] Pitch slide claims fact-checked; 16:9 deck, UI screenshot and speaker notes ready for human creation.
- [ ] Browser responsive and accessible; no broken CTA, dead end or mock feature described as live.
