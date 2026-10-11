# Multi-agent implementation and acceptance

This implements the agent layer described in `notes/pm-factory.md` and
`notes/pm-role-research/05-agentic-layer-design.md`, after completing `PLATFORM_BUILD_PLAN.md`.
The scope is a governed local PM system: agents prepare work; humans decide; drafts stay internal.

1. Complete and integrate platform pods A–H, retaining exact evidence links and deterministic scores.
   Verify task claims, retries, scheduling, version gates, missing-data behavior and provider errors.
2. Add bounded, persistent orchestration sessions on the OpenAI Responses API through `server/llm.py`.
   The orchestrator sees recorded scope context and permitted capability schemas. It delegates to
   roster agents through queued tasks; execution uses the runtime and recorded actor permissions.
   Scope, allowed agents/tools, turn/call/token budgets and pauses are checked in code for every action.
   Store planning messages, tool calls/results, child task IDs, provider/model and usage. Failed or
   interrupted sessions stay inspectable and resumable without silently replaying successful writes.
   An explicit deterministic reference planner supports offline testing and is visibly labelled.
3. Implement source-linked specialist outputs: challenge records for exact requirement versions,
   research briefs from evidence gaps, audience drafts from approved versions and scores, and a morning
   brief with real counts and links. Store these as immutable run/message artifacts. Never send a draft.
4. Replace the empty agents page with the control room: orchestrator and agent roster, pause controls,
   a scoped task board, session intent/start/resume, activity and errors, source-linked morning brief,
   challenges and audience drafts. Wire platform screens and the pipeline's capability run feed.
5. Test malicious/unavailable tool calls, cross-scope references, budget exhaustion, paused agents,
   failed and repeated tool calls, interrupted sessions, human gates and source citations. Verify an
   isolated Compose stack through HTTP/MCP, browser interactions and a live configured OpenAI journey.
   Publish measured evaluation results and limitations, then commit the integrated result.

Live email/Teams/Jira, enterprise SSO and external publishing remain roadmap items. API actor identities
are explicit local declarations under the existing prototype contract, not authenticated enterprise users.
