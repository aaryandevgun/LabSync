# LabSync demo script (standalone web app, about 3 minutes)

This follows the run of show in `docs/03-PHASE-3-DEMO.md`, adapted to the local web app. Everything on screen is synthetic. The app says so in the header ("Synthetic campus data", "Local demo · C3 not connected"), and the presenter should say it too.

## Before the demo

1. Start the server and copy the reset token it prints:
   ```sh
   python3 -m labsync_app.web --fresh            # offline mock agents
   python3 -m labsync_app.web --fresh --live     # Claude agents (needs ANTHROPIC_API_KEY)
   ```
   Then open http://127.0.0.1:8000 in a browser at 1440 px wide and 100% zoom.
2. Open **Demo controls**, enter the token and press **Reset demo data**. Do this before every run.
3. Run the smoke test once: `python3 -m pytest tests/web -q`. It drives the whole flow below in a headless browser.
4. Set the simulated identity to **Morgan · researcher**.

## Run of show

| Clock | Do | Say / point at |
|---|---|---|
| 0:00–0:20 | On **Home**, click the chip **Schedule imaging experiment**. | "Running one experiment means coordinating equipment, rooms and supplies." |
| 0:20–0:50 | Press **Generate plan**. | The Lab Agent turned the sentence into tasks (prep, then 3 h imaging), a window and supplies. The banner lists the checks it ran. "Nothing is booked yet." |
| 0:50–1:25 | Point at the timeline. Click Chen's striped block on Confocal-1. | The popover says "Owned by Chen Imaging · confirmed 10:00–12:00 · flexible (request permission)". Point out the 15-minute cleaning buffers, the Option 2 that moves no one, and the red note that Confocal-2 requires certification. |
| | Press **Hold option 1**, then **Ask Chen to move**, then **Send request**. | Commit stays disabled, and the reasons are listed under it. |
| 1:25–1:50 | Switch identity to **Chen · lab manager**. Open **Approvals**. | The before/after bar and the impact list. The Conflict Negotiator's advice is labelled "You decide". |
| | Press **Approve** and confirm. | "Approving permits the move only if constraints still validate." |
| | Switch back to **Morgan**. Open the plan from Home. Press **Approve final schedule**, then **Commit plan**. | The commit dialog lists the exact writes. The receipt shows the booking ids, and the timeline now has Morgan 10:00–13:00 with Chen's session at 13:30–15:30. |
| | Press **Draft supply requests**. | They are "Proposed · awaiting lab approval". Nothing is ordered. |
| 1:50–2:10 | Switch to **Department admin**. Open **Insights** and press **Run department review**. | "The same plan created a potential pooled order." Point at the three cards, which use different units ($, hours, %). |
| 2:10–2:35 | On the anti-GFP card, press **Review recommendation**. | $640 separate vs $545 pooled, so $95 potential = $75 volume + $20 shipping. Both labs and the department must agree. Open **How calculated**. Press **Propose shared order**. |
| 2:35–2:50 | Back on Insights, point at **Capacity imbalance**. | Confocal-1 37/40 h vs Confocal-2 8/40 h. Moving 8 flexible hours gives 29 h and 16 h, and nothing moves until each owner agrees. Flow-2 at 10% is the third card. |
| 2:50–3:00 | Open the plan's **View audit trail** and tick **Tool execution**. | Every change shows an actor, a time and before/after, plus the agent tool log. "From one request to smarter shared infrastructure." |

## If something goes wrong

- **Live agent is slow or down.** The app shows `LLM_UNAVAILABLE` and saves nothing. Restart without `--live`: the mock agents produce the same story.
- **Wrong state.** Use Demo controls → Reset. The **Seed scenario: Imaging Tuesday** button fills in the sample request without submitting it.
- **Rejection path, if asked.** As Chen, press **Suggest different time** or **Reject**. Chen's booking stays put. Morgan's plan shows the decline and offers the options again, including the 12:15–15:15 slot that moves no one.

## What not to claim

- C3 isn't connected. This is a local Python app with a JSON file for storage.
- None of the data is real: no UW data, no real prices, no real grants. The $95 is a potential saving, not a realized one.
- The offline mock agents are rule-based. Only `--live` runs Claude.
