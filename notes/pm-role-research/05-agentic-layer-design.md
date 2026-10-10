# 5. Agentic layer: design implications

This checks the existing [Product Management Factory](../pm-factory.md) vision against the PM research and proposes what to add. It is a **design proposal [Inference]**, not a description of what is built. The factory's agent roster, A0–A3 autonomy levels, control tower and safe-communication rules stay the baseline; this note maps them to documented PM jobs and fills the gaps the research exposes. Tool names refer to the existing `bmw-evidence` MCP server (`mcp_server/`), which calls the FastAPI backend (`server/`). Agents add orchestration and drafting on top of these governed tools. They never bypass the API, the deterministic scoring, or the human decision gate.

## 5.1 Positioning: "AIconic for Product Management"

BMW already operates a governed multi-agent system: the **AIconic Agent** in Purchasing. It has 10 agents covering quality, purchasing and supplier data, and process support, with 1,800+ active users. It runs on the central BMW Group AI Assistant platform, and BMW's roadmap moves it from search toward recommending and automating actions [BMW-public]. At the 2026 Capital Market Day BMW reportedly said it will use specialised digital agents on its existing IT systems to automate routine work [BMW-public, via WardsAuto].

Our framing: **a governed agent team for vehicle product management that reads, reconciles, drafts and defends, while the PM decides.** The agents expose the same MCP tools that any enterprise agent host could call. Codebeamer remains the downstream system of record [BMW-public].

## 5.2 Agent roster mapped to PM jobs

The first column uses the [factory roster](../pm-factory.md#agent-roster) names where an agent already exists there. Rows marked **new** are additions the PM research justifies.

| Agent | PM job it takes over (see [02](02-day-in-the-life.md), [03](03-stakeholders-and-communications.md)) | Factory level | Existing tools | Gap to build |
| --- | --- | --- | --- | --- |
| **Orchestrator / "PM chief of staff"** (new) | Plans the run for a scope (vehicle × market), sequences agents, compiles the morning brief that fronts the control tower | A0 planning; stops at gates | `create_pm_workflow`, `run_pm_workflow`, `get_pm_workflow`, `list_pm_workflows` | Morning-brief composer; visible plan |
| **Feedback analyst** | I1–I2, I15: read and cluster verbatims and studies; likes, defects, wants, difficulties; must-not-lose attributes | A0 extract, A1 findings | `import_local_file`, `import_records`, `analyze_evidence`, `get_analysis`, `list_findings`, `get_finding`, `list_evidence`, `get_evidence` | Surface a "what customers love" list |
| **Trend scout** and **Competitor analyst** | I8, I9: competitor and trend scanning on the public web only | A0 search; A1 import (PM selects) | `search_market_evidence`, `fetch_market_evidence`, `fetch_web_source`, `import_web_candidate`, `import_web_source` | Watchlist per segment and market |
| **Market balancer** (new) | P1: compare US / EU / China, detect conflicts, propose global vs market-specific requirements | A1 | `list_findings` (by market), `list_requirements` | Cross-market conflict view |
| **Comms triage**, extended to **request triage** | I6, I7, I10, I11: structure inbound market or dealer requests and engineering questions; attach evidence for and against; flag selection bias; draft the PM's position | A0 classify, A1 position | `create_requirement` (as proposal), `trace_requirement` | Request object and status; two simulated requests (BMW NA, China), labelled simulated |
| **Requirement writer** | O1: SMART drafting with need, response and acceptance test separated; targets labelled as PM assumptions | A1 | `generate_requirements`, `edit_requirement`, `get_requirement_versions` | — |
| **Scorer** (deterministic, not an LLM) | O2: score and evidence grade | A0 (`system:scoring`) | `score_requirement` | Agents only *explain* scores |
| **Critic**, extended to a **challenger** | Moments of truth 1 and 4: grounding check *plus* argues against a draft (missing evidence, contradicting markets, unrealistic targets, scope drift into pricing or engineering) | A0 critique; A2 resolve | `trace_requirement`, `list_evidence`, `get_finding`, `server/grounding.py` | Challenge record linked to the requirement version |
| **Change watcher** | P4, O4: what changed since the approved baseline; which decisions it touches | A0 detect; A2 accept | `assess_updates`, `list_reviews`, `get_pm_workflow_brief` | Severity ranking for the morning brief |
| **Comms drafter** | O3, O5, O6, O8, O10: gate pack, market response, engineering handoff, sales "why buy", minutes; all from recorded decisions | A3 (draft only) | `get_pm_workflow_brief`, `trace_requirement`, `list_audit` | Audience templates; exports (Markdown, slides, Codebeamer-ready structure) |
| **Research synthesiser**, extended to a **research planner** | O9: links studies to assumptions, and turns evidence gaps (low grade, conflicts, missing market) into a research or clinic brief | A1 | `list_requirements`, `list_findings` | Brief generator |

That is eleven LLM roles plus the deterministic scorer, the same order of size as AIconic's ten agents. Each role maps to a documented PM job.

What the research adds to the factory:

1. **Market balancer.** Balancing markets is the first PM pain point BMW named. The factory has no agent for it.
2. **Request triage.** Comms triage classifies messages. PMs mostly receive *requests to negotiate*, so triage should prepare a position with evidence, not just a label.
3. **Challenger.** The critic checks grounding. The rubric also rewards surfacing weak, conflicting or uncertain evidence, and the challenger argues that case.
4. **Morning brief.** The control tower is the right home; the brief is its daily entry point, built for a PM whose "daily routine is to scan the market".

## 5.3 Human gates (non-negotiable; factory levels A2–A3)

| Gate | Who | What is frozen | Mechanism today |
| --- | --- | --- | --- |
| Import a public web candidate | PM | Selected source | `import_web_candidate` requires explicit selection |
| Approve, reject or postpone a requirement version | PM (human actor) | Version ID + score ID + rationale | `decide_requirement` with exact IDs; AI actors denied |
| Accept a revision after new evidence | PM | New version replaces the approved baseline | Review items via `assess_updates` |
| Complete a workflow / planning round | PM | Frozen brief with snapshot IDs | `complete_pm_workflow` |
| Send any outbound communication | PM | — | Out of system; drafts only |
| Change scoring weights | PM / product line | New score run | Recorded in score inputs |

## 5.4 Interaction design: how the PM experiences the agents

1. **Morning brief (inbox, not chat).** Illustrative numbers: "Since Friday: 312 new verbatims (US), 2 market requests, 1 competitor launch. 3 approved requirements affected; 1 needs a decision." Each line deep-links to the trace.
2. **Agent activity stream.** Visible, timestamped steps (e.g. "Signal Analyst: N records → M findings, 100% with exact spans"; show real run numbers, never mock ones). This shows the autonomous part and feeds the audit trail.
3. **Decision cards.** Every card shows: the requirement, SMART target with assumption label, score breakdown, evidence grade, conflicts, the challenger's objections, and buttons for Approve, Edit, Reject, Postpone or Challenge.
4. **Outbound drafts tray.** Four tabs per decision (Engineering, Market, Board, Sales), all citing the same version and score IDs, each with a "copy / export" action and no "send" button.
5. **Ask-anything with citations.** "Why is seat comfort ranked above rear space in China?" The answer cites findings, scores and decisions, never free-floating claims.

## 5.5 Scalability story (judging criterion 5)

- **Scope as a parameter.** Every agent runs per vehicle × market × workflow. G60/US is the demo; G70, F70, EU and China reuse the same agents. BMW asked for adaptability, not a one-off [BMW-hackathon].
- **Batching and caching.** Analysis is batched and cached by source hash and prompt version, so re-runs over billions of findings only process deltas.
- **Enterprise fit.** MCP tools are a standard interface; an enterprise agent platform could host the agents. Codebeamer receives decided requirements.
- **Model openness.** BMW reportedly avoids dependence on a single LLM provider [BMW-public, NTT DATA case study]. Our provider is configurable (reference / OpenAI today) and never silently falls back.

## 5.6 Build priorities (if time is short)

1. **Morning brief + Change Watcher.** Highest PM value; mostly existing endpoints.
2. **Request Triage with two simulated market requests** (e.g. a US request for a performance derivative feature, a China request for rear-seat comfort and space). This covers the #1 BMW pain point and the "negotiation" reality.
3. **Challenger** on a single requirement. It shows honesty about uncertainty, which the rubric rewards.
4. **Communications Drafter** for one decision → four audiences.
5. Everything else is already in the backend; expose it as agent steps in the activity stream.
