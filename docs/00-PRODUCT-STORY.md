# 00 — Product story, use cases, and crisp positioning

## The promise

**LabSync: one research request, one coordinated plan, smarter use of every shared resource.**

A researcher explains the experiment outcome they want. LabSync translates that goal into a **human-reviewable plan** covering shared instrument access, required preparation room/time, and consumables. The same authorized operational data is analyzed across a department to discover sharing, scheduling, and investment opportunities. **One platform, two lenses.**

### What we are NOT claiming

- That all academic admin burdens go away; our scope addresses booking, preparation and supplies.
- That UW has granted API access to iLab or budget/grant records.
- That agent-to-agent free-form conversation by itself guarantees fair or conflict-free plans.
- That volume discounts, savings, costs or predictions are real unless labeled and independently verified.

## People / jobs to be done

| Role | Problem | First screen | Can approve |
|---|---|---|---|
| Grad student | Orchestrate experiment without clicking through systems | Lab Workspace | Own draft and requests; not spending |
| Lab manager | Coordinate their team's equipment, rooms, shared supplies | Lab Workspace + requests | Lab-local approval within simulated policy |
| Core scheduler | Preserve fair access and trained user requirements | Equipment details + conflict inbox | Reassignment/booking overrides per facility policy |
| Department admin | Spot waste/capacity bottlenecks | Department Intelligence | Department-level recommendations (not other labs' spending) |
| PI | Benefit from reduced overhead; occasional sign-off | Approvals inbox | Spending/fund allocation where authorized |

## Primary demo use case: cross-lab instrument conflict

**Tuesday, Nov 3, 2026:** a researcher in *Moreno Cell Biology* types: 
> "I need to image GFP-tagged cells Tuesday morning: three hours on a confocal, a prep room beforehand, and enough anti-GFP antibody and coverslips. I need the results by Wednesday."

LabSync:
1. Parses explicit objective, 3-hour run, due date; infers equipment/room/consumables as **editable suggestions**.
2. Checks instrument capabilities, training/eligibility, 15-minute cleaning buffers, available slots, room precedences, available lab stock, and delivery lead time.
3. Finds *Confocal-1* conflict with *Chen Imaging* 10:00–12:00; suggests rescheduling only because Chen booking was flagged flexible. Alternate Confocal-2 offered if appropriate/eligible.
4. Proposes Chen's shift to 13:30–15:30 and Moreno's booking 10:00–13:00; **does not commit until Chen authorizes change and Moreno confirms**.
5. Books the prep room 09:00–09:45, proposes supplies to be ordered by Monday (or exposes insufficient lead time); emits a clear summary and audit records.

**Narrative bridge to macro:** the lab's supply proposal is added to department demand. *Patel Neurobiology* is ordering the same antibody. The macro agent finds an opportunity to combine purchasing while preserving grant allocation and approvals.

## Department insights: only three initially

1. **Shared purchasing:** two labs propose the same SKU; recommend aggregate order with traceable separate costs, not transfer of grant money. Example from seeded prices: 5 total packs × ($120 list – $105 volume) = $75; one shipping charge instead of two saves $20; **$95 potential savings**, not realized.
2. **Overload rebalancing:** Confocal-1 has 37/40 booked hours forecast next week vs Confocal-2 at 8/40; 8 compatible hours could move to the second instrument if training and maintenance constraints permit. Rebalancing is a suggestion until confirmations.
3. **Underuse/capacity strategy:** Flow-Cytometer-2 at 4/40 hours. Recommend cross-lab discoverability and loan/shared slots; compare borrowing/longer hours/purchase when actual demand warrants. **Do not claim equipment should be sold based on a single low-use week.**

## Secondary use cases to mention (don't implement all)

- Multi-step experiment dependencies: microscope + room + reagents, respecting setup and cleanup.
- Supply sharing when inventory compatibility, chain of custody and grants allow it.
- Surge forecasting: next month's confocal bookings likely to peak; trial off-hours or instrument substitution before buying another microscope.
- Investment decision: compare **borrow**, **extend hours**, **buy new** using demand curves, capital/operating costs, staff availability and constraints; Stage 2 includes an illustrative scenario explorer, not procurement execution.

## Demo sound bites

- Before: "Three calendars, two labs, and a purchase request just to run one experiment."
- After the lab story: "The request didn't stop at a booking; it became a structured signal of future demand."
- Reveal: "Individual labs optimize their experiments. LabSync optimizes the resources they share."

## Positioning vs iLab

UW's public iLab service supports equipment reservations, service requests, tracking and billing. **Do not claim nobody has visibility across cores**: actual data access and reporting capabilities vary. Our distinction is **goal-first cross-resource orchestration and permission-aware recommendations across participating labs**, rather than another calendar or billing system.

## Minimum success

A researcher and administrator must both recognize their job in under ten seconds. Four clicks after entering the request should take user through inspect → negotiate proposal → approve → booked. A single role switch reveals calculated cross-lab recommendations based on shared records.
