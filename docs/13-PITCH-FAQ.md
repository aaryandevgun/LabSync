# 13 — Presenter talking points, expected judge questions, case study flow

## The answer in one breath

"LabSync is an AI operating layer for shared research facilities. A lab manager describes the experiment they're trying to run; agents assemble equipment, rooms, and supplies into one approved plan. Because the same C3 data layer sees demand across participating labs, a department agent can recommend joint purchases, rebalanced bookings, and smarter capacity investments."

## Keep the explanation chronological, not architectural

**Problem:** separate workflows and hidden demand. **Action:** researcher expresses a goal once. **Proof:** agent checks true scheduling constraints, negotiates with owner, and commits only with consent. **Consequence:** cross-lab opportunities become visible. **Technology:** C3 entity model, tools, agents and workflows. **Start small:** one life-sciences department.

## Three memorable use cases to mention

1. **Experiment orchestration:** a grad student requests confocal imaging, a prep room and supplies; LabSync plans dependencies, exposes conflict, asks the other lab to authorize a change, and records a confirmed booking.
2. **Joint purchasing:** Moreno and Patel want the same anti-GFP pack. A hypothetical quantity tier reduces the combined estimate from $640 to $545; both lab managers and finance must approve.
3. **Capacity forecasting:** Confocal-1 is 92.5% booked while a compatible instrument is at 20%; recommendation shows feasible, permissioned shift candidates. A separate flow cytometer is underused at 10%, prompting a borrow/extend/buy analysis rather than automatic procurement.

## FAQs with grounded responses

**Isn't this just another calendar or iLab?**  
No: we treat existing booking systems as systems of record to integrate with. Our difference is turning a **research goal** into a dependency-checked, multi-resource request and using permitted data across labs to recommend better shared utilization. We do not assert existing platforms have no reporting capabilities.

**What makes this agentic rather than an LLM wrapper?**  
The lab agent calls actual resource and policy tools; the coordination workflow requests owner consent, revalidates and writes a booking. The admin agent uses deterministic opportunity detectors/forecast outputs and tracks proposed follow-up actions. Show a real C3 tool trace rather than asking judges to believe an animated diagram.

**What is actually running on C3?**  
Answer from `BUILD-STATUS.md` only. Ideally Type entities/read-write, C3 agent/tool runs, workflow states, C3 UI calls and traces. If an element runs locally, name it specifically; never claim components are deployed without proof.

**Why do we need a department agent if every lab already has one?**  
Individual agents have only the lab's permissioned view and optimize one person's experiment. Department-level authorization can expose aggregated overlaps: identical supplies, surges and idle alternatives. Privacy boundary is central to the design.

**Will agents cancel a PI's booking?**  
Never unilaterally. They can suggest a move and create an approval request; the existing booking owner/core scheduler controls it according to policy. The transaction rechecks for conflicts before committing.

**Can you purchase from different grants together?**  
A shared vendor order can be proposed when compliant, but the actual legal/accounting allocation remains separate and must be authorized. Our demo does not spend money or transfer expenses between grants. Grant metadata is a planning signal, not spending permission.

**Can a model predict lab demand from just six weeks?**  
Six weeks is enough to demonstrate a transparent baseline and backtesting procedure, not to establish production quality. We label forecast uncertainty and would expand historical data and monitor accuracy before decisions depend on it.

**How would you get real iLab data?**  
Institutional permission and vendor integration discovery first. We can start with approved exports/manual sync and only automate reservations through supported/authorized interfaces. For the hackathon we use synthetic data.

**Why wet labs instead of campus-wide?**  
Shared expensive instruments and repetitive consumables create tangible coordination opportunities. One building means realistic logistics, compatible equipment and accountable approving roles. It is an integration wedge, not a promise to cover every lab immediately.

**What is the realistic customer?**  
Lab managers and grad students use the planner; a core director/department administrator sponsors the efficiency view. The first pilot can use scheduling/utilization data and purchasing proposals, then expand only with stakeholder approval.

**Are the savings real?**  
No. $95 is the **potential** advantage of a synthetic pooled order at hypothetical price tiers. The product would measure realized savings only after a verifiable executed order. The schedule example quantifies potential hours moved, not money.

**What happens when an agent is wrong?**  
Its plan is editable; hard rules and authorization are checked by Type methods; error states show blockers. An incorrect or stale proposal cannot commit. Human review and trace logs are visible.

## 30-second architecture explanation (if asked)

"Every instrument, booking, room, lab, supply proposal and approval is a C3 Type. Lab agents use tools to query this model, an orchestrated workflow validates and routes approval, and the same records power department detectors and forecasts. The UI surfaces it in two role-specific views. External iLab integration would sit behind an authorized adapter."

## Numbers to double-check immediately before pitching

- Did we actually create 34h initial and 37h after Moreno booking, with no impossible buffers?
- Does $95 equal `640 – 545` with the intended order quantities and hypothetical vendor tier?
- Is every suggested 8h transfer backed by concrete viable slot moves?
- Are "estimated", "potential", "forecast" and "committed" consistently distinguished?
- Is any screenshot/example labeled `Synthetic demo` and C3 integration status truthful?
