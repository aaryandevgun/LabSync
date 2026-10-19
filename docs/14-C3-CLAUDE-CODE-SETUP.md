# 14 — Connecting Claude Code to C3 (maximize authentic C3 implementation)

## Why this matters

As of public C3 platform 8.10 documentation, C3 offers **Central MCP** (platform knowledge for coding assistants) and **App MCP** (tools for your live C3 application). C3's official quickstart specifically includes a **Claude Code** configuration path. This can help Claude discover live Type schema and run tests rather than guessing what your tenant supports.

References:
- https://docs.c3.ai/docs/genaiPlatform/8.10/topic/mcpServer-quickstart
- https://docs.c3.ai/docs/genaiPlatform/8.10/topic/app-mcp-access

## Recommended developer setup (do not put any token in repo)

1. Visit [C3 Central MCP portal](https://mcp.c3.ai) and sign in **if your hackathon C3 account is authorized**.
2. Use the portal's **Claude Code install instructions**. Copy/paste the exact command from the portal rather than inventing CLI flags or saving credentials to markdown.
3. In **C3 AI Studio**, open your development application, then `MCP > Access`. Under `My Tokens`, use `Generate Token` and choose **Other (including Claude Code)** according to official documentation. The portal should provide the App MCP URL/token and IDE configuration guidance.
4. Add the **App MCP** to Claude Code using the IDE's supported configuration method. **Never commit the token, URLs with secrets, or MCP config with auth headers** to Git. If config must live at project root, use gitignored file and scrub it from screenshots/logs.
5. In `MCP > Tools` enable only necessary safe tools; test discovery and metadata first. Public C3 documentation describes `getC3TypeInformation` and `runTest` as useful for a test-driven loop. `App Admin` permission may be needed to enable tools.
6. Verify Claude can query your test Type schema **without reading any real data** and execute a harmless fixture test. Note returned metadata and calls in BUILD-STATUS.md.
7. Only then let Claude implement Stage 1 Types and domain methods based on actual schema. Apply least-privilege; don't expose production data or write tools outside synthetic app sandbox.

## Important nuance

- Central MCP can provide platform guidance without access to a specific application; App MCP is required for live application capabilities.
- Token authentication and MCP connection settings are version-specific; **never hardcode example tokens**. C3's 8.10 documentation mentions `C3Bearer` for App MCP authorization in its sample; prefer generated setup and actual docs over copying a sample blindly.
- Never assume C3 services such as forecasting, app-level workflows or provider LLM integration are enabled solely because MCP connects.
- Keep local Claude Code authoring **separate** from a deployed C3 agent: Claude writes/tests the application; Lab Planner and Department Agents run inside C3 when verified.

## C3 proof checklist for judges

- One screenshot of C3 AI Studio Type entity and canonical record.
- One screenshot of deployed Lab Planner Agent and tool binding or run trace.
- One C3 workflow and a human-approval checkpoint/audit source.
- One department insight rendered from C3 Type queries, with IDs/fields.
- One live UI action followed by C3 persisted data change/re-fetch.

Only collect screenshots of actual accessible systems; if any component unavailable, disclose in demo notes and prioritize correctness.
