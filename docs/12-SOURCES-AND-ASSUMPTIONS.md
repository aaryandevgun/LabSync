# 12 — Public references, evidence, and claims policy

**Research status: references checked October 19, 2026.** These are public docs and high-level references; the actual C3 tenant and UW data integrations have NOT been inspected in this pack. Always verify platform version and capabilities before coding against it.

## C3 references (primary sources)

1. [C3 Agentic AI Platform 8.10 overview](https://docs.c3.ai/docs/platform/8.10/topic/platform-overview) — Type System, platform layers, agent workbench, custom tools and workflows.
2. [How C3 applications are structured](https://docs.c3.ai/docs/platform/8.10/topic/how-c3-applications-are-structured) — Type model, Data Fusion, ML, C3 API-backed UI, agents and human approval.
3. [Develop Gen AI Agents overview](https://docs.c3.ai/docs/genaiPlatform/8.10/topic/genaiPlatform-dev-overview) — `genaiPlatform`, `GenaiCore.Agent`, `GenaiCore.Tool`, Agent Gallery, Tool Workbench, observability.
4. [Create C3 Agents](https://docs.c3.ai/docs/genaiPlatform/8.10/topic/genaiPlatform-dev-quickstart-1) — prerequisite C3 app and `genaiPlatform` dependency.
5. [Configure workflows through UI](https://docs.c3.ai/docs/genAiSearch/8.10/topic/genai-dev-workflows-use-case) — steps, workflow state and built-in node templates incl User Input.
6. [Create C3 Action Tools](https://docs.c3.ai/docs/genaiPlatform/8.9/topic/genaiPlatform-dev-create-c3-tools) — older 8.9 overview of tools wrapping C3 methods; verify on actual release.
7. [C3 Type inheritance/persistable entities](https://docs.c3.ai/docs/platform/8.10/topic/type-inheritance) — stored entity Types.
8. [C3 UI package reference](https://docs.c3.ai/docs/uiInfrastructure/8.10/topic/ui-package-reference) — `uiComponentLibraryReact`, chart/graph packages, React UI infrastructure.
9. [Standard React components vs C3 Type definitions](https://docs.c3.ai/docs/uiComponentLibraryReact/8.10/topic/types-and-react) — using TSX in native C3 UI.
10. [Other UI frameworks with C3 REST](https://docs.c3.ai/docs/uiInfrastructure/8.10/topic/non-c3-ui-apps-served-by-server) — fallback for custom React, including same-origin/deployment considerations.
11. [C3 AI Studio Model Ops](https://docs.c3.ai/docs/platform/8.10/topic/studio-model-ops) — ML model routing, registry and training status, if enabled.
12. [C3 MCP quickstart](https://docs.c3.ai/docs/genaiPlatform/8.10/topic/mcpServer-quickstart) — Central MCP and App MCP; Claude Code authentication path, test tools.
13. [C3 MCP access](https://docs.c3.ai/docs/genaiPlatform/8.10/topic/app-mcp-access) — separate token/privilege management.
14. [C3 application modes](https://docs.c3.ai/docs/platform/8.10/topic/studio-app-modes) — develop in an editable application with test data.

**Platform scope warning:** the specific package, licensed features and enterprise integrations available in the hackathon environment might differ. Do not treat the public docs as proof that a given feature is accessible or that a specific REST schema exists. Map supported C3 features after the smoke test.

## UW–Madison references (primary sources)

1. [UW iLab resource center](https://ilab.wisc.edu/) — iLab supports services, equipment reservation management, usage, billing/reporting and core management.
2. [iLab Group/Lab user support](https://ilab.wisc.edu/index.php/lab-user-support/) — researcher equipment booking and service requests; PI/lab administrative approval roles.
3. [UW iLab core list](https://ilab.wisc.edu/index.php/cores/) — named participating shared resources (site currently lists 17).
4. [UW research core directory](https://www.resources.research.wisc.edu/) — public campus resource directory; listings/quantities change, verify before presentation.
5. [Research cores program](https://research.wisc.edu/research-cores/) — transparent access to shared facilities and usage fees.

**What these prove:** there are existing campus shared-resource programs and booking workflows. **What they do NOT prove:** LabSync has access to any systems, that iLab lacks cross-core reporting, or that vendor APIs are approved. The integration shown in the live prototype is a **local synthetic adapter** until separately verified.

## Faculty admin burden statistic (use with care)

- [Federal Demonstration Partnership survey resources](https://thefdp.org/demonstrations-resources/faculty-workload-survey/).
- [The FDP Faculty Burden Survey (2009 article)](https://pmc.ncbi.nlm.nih.gov/articles/PMC2887040/) reports faculty estimates that 42% of time allocated to federally funded research projects went to administration; survey comprised 6,081 respondents. **Old statistic covering many responsibilities** (grants, personnel, reporting, purchasing, compliance), not 42% of *all professors' work* and certainly not 42% time recoverable by this product. If used, put survey year/context on slide.

## All demo numbers are synthetic assumptions, never evidence of live outcomes

| Claim | Label / basis |
|---|---|
| 4 labs, 10 instruments, 4 rooms, 8 SKUs | Deliberately fabricated dataset |
| Confocal-1 37/40 h, Confocal-2 8/40 h | Constructed fixture **after** main booking action |
| 8h potential transfer | Only if scheduler finds concrete feasible schedule/owner approval; synthetic fixture |
| $95 shared-order saving | Calculated hypothetical vendor tier and shipping, not realized |
| 10% Flow-Cytometer-2 usage | Seed fixture: 4h/40h, not UW instrumentation claim |
| Forecast demand or error | Computed from six weeks fictional history; limit claims |
| Grant milestone/ramp | Synthetic planning signal, no grant account access |

## Communication do/don't

**Do:** "We prototyped a goal-to-booking assistant and cross-lab optimization on synthetic departmental data, using verified C3 platform primitives where connected."

**Don't:** "We've integrated with UW's iLab and grant system" without authorized working connection; "We saved the university $95" when only a recommendation exists; "We give researchers 42% of their time back"; "C3's forecasting app is running" when the license/access is not verified.
