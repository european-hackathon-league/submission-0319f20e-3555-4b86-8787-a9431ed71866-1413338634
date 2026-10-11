# BMW presentation readiness plan

**Working plan — 11 October 2026.** The BMW deadline is **today, Sunday 11 October at 11:30, Europe/Madrid**. This plan protects the presentation first, then defines the remaining product, data, agent and enterprise work after the challenge. It builds on the existing [platform build](PLATFORM_BUILD_PLAN.md) without restarting its eight pods. The immediate schedule uses the [pitch plan's](notes/pitch-plan.md) T-minus freeze.

## 1. Outcome and boundaries

The outcome is a **verified prototype with a clear enterprise pilot path**. The live product must turn BMW input and selected public evidence into a customer-facing requirement, explain its score and uncertainty, let a PM decide, and revisit only affected decisions when evidence changes. The presentation must show that flow in three minutes, with a reconstructable source-to-decision trail and a reliable backup.

This is the challenge's market-research and product-planning scope: situation analysis → structure and context → requirement definition → prioritization → documentation and tracking. The supplied lifecycle diagram calls its contextual gates G0 and G1; those labels must **not** be presented as verified BMW internal approval gates. Requirements evolve over roughly two years. Start with **G60 / US**, then show that vehicle and market are parameters, with a second market only when its evidence and comparison are verified. Keep pricing, detailed cost, homologation and engineering specifications outside the product workflow; flag dependencies on their owners instead.

The [BMW challenge record](notes/challenge.md) and [mentor guidance](notes/bmw-guidance.md) govern scope and judging. The [implementation plan](IMPLEMENTATION_PLAN.md) governs the existing core. [PM research](notes/pm-role-research/README.md) contains public information and explicitly marked inferences; do not turn those inferences into claims about BMW's internal systems or policies. The [pitch plan](notes/pitch-plan.md) governs the three-minute story and deck handoff.

**Language for BMW:** “We have a working, auditable prototype aligned to the planning activities you described. Identity integration, production infrastructure and internal connectors require a BMW pilot.” Do not call the current SQLite/OpenAI/actor-string deployment production-ready.

## 2. Starting checkpoint and coordination

| State on 11 October | Consequence for this plan |
| --- | --- |
| Core API, MCP, SQLite trace, PM decisions, update workflow and G60 / US client are committed on `main`. | Preserve the source → evidence → finding → requirement version → score → human decision → audit chain. |
| `PLATFORM_BUILD_PLAN.md` has eight pods for signals, markets, intake, priorities, BMW data, agent substrate, web and evaluation. Several completed branches are being integrated in `codex/platform-integration-main`; the web integration still has local changes elsewhere. | Finish and verify that integration before branching feature work from it. Do not duplicate or cherry-pick unfinished pod work into this plan's branch. |
| The slide deck is being generated in `codex/pitch-deck` with uncommitted `pitch/` files. | Deck owner keeps that worktree. Give them a claim/evidence ledger and frozen captures; do not edit their files. |
| The primary `main` checkout contains uncommitted test and handoff files. | Identify their owner before staging or branch changes there. This document lives on `codex/bmw-readiness-plan` in a separate worktree. |
| Original BMW inputs are local in `data/`; local databases and snapshots are ignored. | Use them only in isolated local runs. Commit synthetic fixtures and redacted metrics, never raw BMW files, verbatims, personal data, or database copies. |

**Entry gate R0:** the platform integrator records a clean committed integration hash, merged pod reports, migration version, API/MCP contract, service health, full Python/web checks and known failures. The owner of `codex/platform-integration-main` remains responsible for that work. The next orchestrator branches from **that agreed commit**, not from this planning commit if integration has advanced. No merge or push to `main` is implied by this plan.

## 3. What BMW should be able to assess

| BMW judging criterion | Product proof | Acceptance evidence |
| --- | --- | --- |
| Decision and scoring logic | A requirement's specific, measurable customer outcome, score factors, evidence grade, conflict and sensitivity. | Score recomputes from stored inputs and rubric version; every quantitative input has a derivation; unsupported targets say `PM assumption`. |
| Workflow and human decisions | An agent prepares a proposal; a PM edits, approves, rejects, postpones or challenges the exact version. | API and database reject nonhuman decisions; approved version stays frozen through a later update; actor and rationale appear in audit. |
| Trace and audit | One click from recommendation to workbook/sheet/row or public URL/date, then forward to the decision. | Trace is complete for every claim shown; audit chain verifies; replay reconstructs the frozen brief. |
| Usability and feasibility | A PM sees what changed, why it matters and the next action, without reading every record again. | Timed G60 / US journey works in browser; representative PM can find the source and decide without a developer explaining the UI. |
| Innovation, scale and impact | The same workflow takes a scoped update, market conflict or request through governed agents. | New runs are scoped by vehicle/market, duplicate import is idempotent, affected decisions surface, and measured latency/quality are reported with limits. |

### The BMW-facing story

1. **Situation analysis:** show G60 / US feedback and source coverage, including concentration, missing dates and positive attributes that must be preserved. Public competitor or trend evidence is clearly separate from BMW input.
2. **Structure and context:** show a finding and a conflicting or weak signal, with its exact location and market. If the second-market comparison is ready, show a real conflict; otherwise use a labelled simulated request and state what it demonstrates.
3. **Requirement and priority:** show a specific customer outcome, acceptance criterion, assumption label, deterministic score, evidence grade and a challenge from the critic.
4. **Decision and tracking:** show the human-only approval and immutable baseline; import a labelled later batch; show the proposed delta and only the affected review item. Open the audit/trace from the decision.

The live story follows [the pitch plan](notes/pitch-plan.md). The deck and trailer may show **only features that pass the same frozen build**. Every numeric slide claim gets a source, query or run ID; every screenshot gets a build hash and demo snapshot ID. A recorded run of that exact build is the fallback.

## 4. Priority tiers and release gates

At 03:30 Madrid time, about eight hours remain and the T-6h feature freeze is at **05:30**. **Start the orchestrator now.** It should finish the existing platform integration, assign bounded work to five coding streams in waves, and admit each result into the demo only after verification. The full enterprise backlog remains executable after the presentation. Use the committed G60 / US core as the fallback if integration misses the freeze.

### P0 — presentation blockers

- Decide by **04:30** whether the platform integration branch is green enough to demo. Require a committed build, consecutive migrations, full Python/web checks and one Compose/browser/API/MCP journey. If it misses this gate, demonstrate the already verified core from committed `main`.
- Produce a **reviewed G60 / US demo dataset** from a local copy: exact source checks for the hero requirement, SMART wording, a truthful preserve attribute, and a clearly labelled simulated update. Use a real OpenAI run only if it finishes and is reviewed before the freeze; otherwise label the reference run. Snapshot locally and make reset reproducible.
- Show an agent chain only if it is real and verified by the freeze: task, governed capability call, grounded or rejected result, deterministic score and PM decision gate, with actual run IDs/status/errors. Otherwise show the current pipeline honestly and explain the orchestrator/worker design as the next phase.
- Keep trace and human gates intact across new sources and agents. No BMW data or verbatims go to public-web search; no agent or MCP tool may impersonate an approval.
- Freeze new capabilities at **05:30 (T-6h)**. After that, fix only a presentation blocker, re-run its journey, and update the deck/recording to match. Complete two timed runs under three minutes, a Q&A rehearsal, projector check and recorded fallback.

### P1 — include only if already integrated and verified before 05:30

- Add a second market with checked evidence, a resolved conflict and explicit global-versus-market-specific rationale.
- Add a small, source-labelled public competitor/trend set and a market request with source/date/selection metadata. Show how these alter or fail to alter a priority.
- Show five distinct product-agent roles only if each performs a real, logged capability. A morning brief, challenger objection and queue are optional.
- Add a local, identity-bound demonstration mode only if permission tests pass. State the production SSO/RBAC boundary honestly.

### P2 — full refinement and enterprise pilot work, continuing after 11:30

- Complete W1–W5 below: wider sources, semantic quality, the full orchestrator/worker loop, decision-first UX, evaluation and operational controls.
- BMW-approved identity/role mapping, data classification, retention and deletion policy, model/region/egress agreement, security review and connector permissions.
- Production database choice and migration, backup/restore drills, observability and availability targets, load tests at the expected data volume, disaster recovery and operating ownership.
- Governed integrations to BMW-approved research, request and downstream requirements systems, including Codebeamer **only if BMW confirms the interface and ownership**. Live mail/Teams/Jira ingestion and outbound messaging need explicit scope and human send controls.

**Cut order before 11:30:** remove 3D and trailer polish first, then extra markets/sources, then the full agent dashboard. Keep the grounded requirement, score explanation, human decision, update comparison, audit trail and a working fallback. Do not use invented metrics to fill gaps.

## 5. Work packages for remaining implementation

W1–W5 are independently reviewable work after the platform's R0 integration gate. The orchestrator can assign each stream immediately for inspection and preparation; implementation branches start from the committed R0 base. Before today's feature freeze, merge only small verified slices. The full exit criteria remain the target for the continuing build; they are not claims about what will be delivered by 11:30.

### W1 — Source coverage and data quality

Inventory the provided G60, G70 and F70 feedback, customer studies, option lists, sales volumes and annual report against actual import results. Reconcile record counts, duplicates, ignored sheets/pages, vehicle/market assignment and dates. For each source class, record owner, acquisition date, usage boundary, exact locator, dedup key, original-content hash, freshness and representativeness. Keep a “what customers love” lane separate from complaints.

Add public competitor/trend sources only with URL, retrieval time, publication date when known, market, topic and a selectable import decision. Treat remote text as untrusted. Template Exa queries from public model/topic/market names; never interpolate BMW records. If a source is undated or selected, the UI must say so, and counts must never be presented as prevalence.

**Exit:** a coverage report reconciles every supplied input; duplicate imports do not multiply evidence; sampled source links open the correct row/page/URL; source dates and gaps are visible. The G60 / US hero has a manually checked local citation set. Remaining source types are listed with permissions needed.

### W2 — Requirement and prioritization quality

Audit the full chain for the hero and a negative case: extraction → cluster/consolidation → requirement draft → scoring → decision → changed-evidence review. Keep need, proposed response, acceptance test, target, assumption and source distinct. Reject out-of-scope or unsupported model claims before persistence. Preserve positive attributes; do not turn “customers love driving” into a defect. Surface conflicting evidence and missing coverage.

Keep all counts, weights, ranks, change thresholds and sensitivity in deterministic, versioned code. The LLM may classify, draft and explain from recorded facts; it cannot set a score, approve or silently fall back to a reference method. Store provider/model/prompt version/input hash/usage and show a clear failure. A changed rubric must create a new score and review where an approved outcome changes.

**Exit:** repeated scoring on the same inputs is identical; the hero requirement passes a PM review of specificity and source support; a labelled update flags the intended requirement without rewriting approved history; explanation IDs resolve to stored derivations. Report measured grounding, duplicate, false-alert and review-effort results, including sample size and uncertainty.

### W3 — Governed multi-agent execution

Build on the platform's registry, capabilities, tasks, runs and threads. A planning orchestrator receives a vehicle/market/goal, creates bounded tasks, dispatches only allowed capabilities, gathers results and asks for a human decision at the gate. The initial five *product roles* are: feedback analyst, public-signal/competitor scout, market/request balancer, requirement writer, and challenger/change watcher. The scorer remains deterministic system code. Roles can be composed or split later; the demo must show the actual jobs and their tool calls.

Each task needs scope, input hash, dependency IDs, idempotency key, status, retry policy, timeout, budget, actor, tool arguments/results (redacted as needed), run ID and audit event. Failed work is visible and retryable; a stale result cannot overwrite a newer requirement. Capability permissions live in the API, not only in prompts. The challenger checks grounding, conflicting evidence, unrealistic targets and scope drift; it returns a reasoned objection, not an approval.

**Exit:** a fresh G60 / US task executes at least one genuine multi-step chain through API/MCP, persists a visible run for each worker involved, supports pause/retry without duplicate effects, blocks disallowed tools and stops at a human gate. An injected instruction inside a source is ignored. No outbound message is sent automatically.

### W4 — Enterprise controls and integration seam

Document the actual data-flow map: local BMW files → API/database → configured OpenAI analysis; public query → Exa → selected import; web/MCP → API. Separate prototype controls that exist from pilot controls that need BMW infrastructure. Threat-model the high-risk paths: client-supplied `actor` strings, MCP tool identity, prompt injection, public-search leakage, cross-market data access, provider errors and audit tampering.

Add feasible pre-demo controls: API authorization boundary suitable for later SSO mapping, role/scope checks on writes, redaction of secrets and verbatims in logs, safe errors, bounded runs, health/readiness, backup/restore instructions, and an operator kill switch. Test these without asserting production identity assurance. Specify an adapter contract for downstream export of *approved* requirement versions; do not claim a live Codebeamer integration.

**Exit:** forbidden actor and scope tests fail closed at API and database; audit verification passes; a stopped agent cannot execute; secrets and full BMW records are absent from operational logs; a local snapshot can restore the demo. The pilot gap register names the BMW approvals and infrastructure still required.

### W5 — PM experience, evaluation and presentation evidence

Make the PM home answer: “What needs me?”, “Why?”, “What changed?”, and “What is the source?” The agent board is secondary to decision cards. Every generated statement shows provider and provenance; score and evidence grade remain visually distinct; simulated data is unmistakably labelled. Make long-running, failed and stale runs understandable. Keep the vehicle studio only if it shortens the path to a requirement's trace.

Create a small synthetic gold set in Git and a separate, local human-reviewed G60 / US checklist. Evaluate source-span validity, topic/market fit, requirement quality, preserve/complaint distinction, conflict handling, ranking stability, update precision, agent permission failures and time-to-trace. Record baseline, sample sizes and failure examples; never infer hours saved from a scripted demo.

Supply the deck owner a **claim ledger** (`claim → exact source or run → screen → build/snapshot → approved wording`) and a frozen screenshot pack. Synchronize the 3-minute script, deck, live app and recorded fallback at the freeze. Keep evidence for likely BMW questions about source bias, AI boundaries, human control, security, scale and integrations.

**Exit:** the browser journey passes on the frozen snapshot; evaluation output is reproducible; every material slide claim resolves to the ledger; two consecutive timed rehearsals fit three minutes; backup playback works offline.

## 6. One orchestrator and five coding streams

The *coding team* below is separate from the five **product-agent roles** in W3. The coding orchestrator owns contracts, integration, tests and the release decision. Each worker gets a distinct branch and worktree from R0, one bounded brief, and no overlapping file edits. Current Codex collaboration has four concurrent slots including the orchestrator: run at most **three workers at once**, then the other two in a second wave. If another runtime permits more slots, the same ownership rules still apply. Start the orchestrator immediately; it can use available worker slots for R0 triage and source/demo review while the integration base is finalized, then issue W1–W5 briefs from that base.

| Coding worker | Branch and wave | Primary package | Owned files / boundaries | Deliverable |
| --- | --- | --- | --- | --- |
| A Data and sources | `codex/bmw-data`, wave 1 | W1 | `server/importers.py`, `server/market_data.py`, `server/signals.py`, their MCP modules and tests, `notes/bmw-data-coverage.md` and new source-ledger docs. | Reconciled source inventory, provenance and selected new sources. |
| B Pipeline quality | `codex/bmw-pipeline`, wave 1 | W2 | `server/analysis_engine.py`, `server/grounding.py`, `server/requirements.py`, `server/prioritization.py`, `server/workflows.py`, related tests and evaluation scripts. | Reviewed G60 / US path, score derivations and update behavior. |
| C Agent execution | `codex/bmw-agents`, wave 1 | W3 | `server/agent_runtime.py`, new agent-loop modules, `mcp_server/agent_tools.py`, agent tests and runtime docs. | Genuine orchestrator/worker run with retry and human stop. |
| D Enterprise seam | `codex/bmw-governance`, wave 2 | W4 | New auth/policy modules, `database/` migrations and integrity code, security tests and runbook docs. | Permission boundary, failure controls and pilot gap register. |
| E PM experience | `codex/bmw-experience`, wave 2 | W5 | `web/` except generated API types, browser tests and presentation claim-ledger docs. | Decision-first UI, verified screens and deck handoff. |

**Shared files belong to the orchestrator:** `server/main.py`, `mcp_server/main.py`, `compose.yml`, `.env.example`, `web/lib/generated-api.ts`, root plans/README and live verifier. The orchestrator freezes response shapes, actor/scope contract, event schema, capability names and migration numbering before workers branch. If a worker needs a shared change, they provide a patch request in their report; they do not edit the shared file. Reserve consecutive migration numbers from the actual R0 schema, with one owner per migration. A stream that needs a new table or column waits for D's schema contract or uses an existing R0 table; it does not edit `database/` itself. Reconcile conflicts in a dedicated integration worktree, not in a worker checkout.

**Worker brief template:**

> Read `AGENTS.md`, `IMPLEMENTATION_PLAN.md`, `PLATFORM_BUILD_PLAN.md`, `BMW_READINESS_PLAN.md` and the R0 contract snapshot. Work only in your assigned branch/worktree and files. Preserve source-to-decision IDs, human gates and data boundaries. Implement your work package with the stated exit evidence. Run relevant checks, commit reviewable milestones locally, and report branch/hash, endpoints/schema, checks/results, measured limitations and requests to the orchestrator. Do not push or merge to `main`.

**Integration order:** R0 → orchestrator-owned shared contracts and migration reservations → A source model → B pipeline → C agent execution → D policy controls → E UI → cross-package verifier/evaluation → freeze. Work can overlap within this order where contracts are stable. Use `codex/bmw-integration` for this merge train. The orchestrator reviews the staged diff, merges one branch at a time, runs Python checks after each backend merge, regenerates API types, then runs web and isolated Compose checks. Do not stop an existing stack owned by another worker.

## 7. Verification and evidence package

1. **Static and unit:** `uv run ruff check .`, `uv run pytest -q`; web lint, typecheck, tests and build per `web/package.json`. Verify migration from both empty and existing local databases, without using the demo database as a test fixture.
2. **Integration:** isolated Compose project and ports; inspect API/MCP/web service status and logs. Exercise all new writes through API and MCP where exposed, with exact source IDs and actor/scope checks. Test failed provider, duplicate import, retry, stale task and invalid human-gate attempt.
3. **Live AI:** execute a real configured OpenAI run, record model/prompt/input hash/usage and inspect representative outputs against original local sources. Keep the deterministic baseline as an explicitly labelled comparison. Public research steps skip honestly if credentials or verified sources are unavailable.
4. **Browser:** run G60 / US initial and update journeys on a disposable local database; check trace, score, evidence grade, agent status, decision, error states and audit. Verify one second-market case only after data review.
5. **Evaluation:** publish a table of numerator/denominator, method version, sample composition and failures for grounding, source coverage, source bias, duplicate rate, conflict/change precision, decision time and agent/tool failures. Mark unavailable or unmeasured values as such.
6. **Demo artifact:** commit code and redacted evaluation/report docs; keep snapshot and BMW inputs local; tag/record integration hash, migration version, model/prompt/rubric versions, demo snapshot checksum, deck version and recording version together.

### Stop conditions

Stop a release candidate if the hero's material claim lacks a verified source, an AI/system actor can approve, a public search receives BMW text, a score changes without a recorded method/input, approved history is rewritten, a demo slide claims an unmeasured number, or Compose/browser verification fails on the frozen build. Fix or cut the failing feature and re-run its journey. A feature that cannot be verified becomes a clearly labelled roadmap item.

## 8. Timing, freeze and handoff

The deadline is **Sunday 11 October, 11:30 Madrid time**. Treat the gates as latest times. If R0 slips, keep the existing verified G60 / US story and cut unintegrated platform features; never let a late merge invalidate the demo snapshot or deck.

| Gate | Madrid deadline | Owner | Evidence |
| --- | --- | --- | --- |
| R0 platform go/no-go | **04:30** | Existing platform integrator | Green committed build and live journey; otherwise select committed core. |
| R1 golden G60 / US story | **05:15** | Orchestrator + data/pipeline owners | Verified source pack, PM decision, update, audit, demo reset. |
| R2 product and deck lock | **05:30 (T-6h)** | Orchestrator + deck owner | Frozen build/snapshot, claim ledger, captures, recorded backup plan. |
| R3 rehearsal and recording | **05:30–08:30** | Presenter + driver | Two consecutive <3:00 runs; 3-minute Q&A practice; recorded fallback. |
| R4 final deck and venue check | **08:30–10:30** | Deck owner + presenter | Claims match frozen build; offline playback, display/audio, snapshot reset. |
| BMW deadline | **11:30** | Presenter | Product, deck and fallback ready. |

A short handoff at each gate should report: latest green integration hash, open blockers, next merge, demo-state checksum and scope cuts. The deck owner needs the claim ledger at R1 and final captures at R2.

## 9. Decisions to obtain from the team or BMW

These are **decision inputs**, not reasons to delay independent implementation:

1. Presenter/driver/Q&A roles and whether the venue permits a live network call.
2. Product name and final demo beat (market conflict or 3D), chosen only after verification.
3. Which BMW data classes may leave the laptop for the configured model, and whether a BMW-hosted model endpoint is available for a later pilot.
4. BMW's actual identity, role, retention, region, connector and downstream system requirements for a pilot. The challenge diagram and public research do not settle these.
5. Whether BMW wants a proof of a particular market/derivative beyond G60 / US. Do not sacrifice the verified first slice for extra breadth.

**Immediate next action for today:** launch the orchestrator with the prompt below. It gets the platform go/no-go result, freezes a source-checked G60 / US story, gives the claim ledger to the deck owner and starts the five coding streams from the committed R0 base. Work that misses the freeze continues as the enterprise backlog.

## 10. Copy-paste prompt to launch the orchestrator

Use this in a new Codex coding task rooted at `/Users/troy/Desktop/ehl-final`. The task should read this plan from branch `codex/bmw-readiness-plan` (commit recorded in the handoff), or from its attached worktree at `/Users/troy/.codex/worktrees/bmw-readiness-plan/ehl-final/BMW_READINESS_PLAN.md` if the branch has not been integrated. The plan is the brief; the following prompt starts execution:

```text
You are the coding orchestrator for BMW presentation readiness. The deadline is Sunday
11 October 2026 at 11:30 Europe/Madrid. Read AGENTS.md, IMPLEMENTATION_PLAN.md,
PLATFORM_BUILD_PLAN.md, notes/challenge.md, notes/bmw-guidance.md, notes/pitch-plan.md,
and BMW_READINESS_PLAN.md from branch codex/bmw-readiness-plan before changing files.

Start now by inspecting git status/worktrees and the owners of all uncommitted changes.
Continue the existing platform integration in codex/platform-integration-main; do not
duplicate its pod work or touch the deck owner's codex/pitch-deck files. Establish a
committed, checked R0 base and a frozen API/MCP/schema contract. Use distinct worktrees
and branches for the five coding streams W1–W5 in BMW_READINESS_PLAN.md, with no file
overlap. In this Codex runtime use at most three workers concurrently plus yourself;
queue the other streams for wave two. Give each worker the work-package exit criteria,
ownership row, data boundaries, human gates and deadline. Own shared files and merge
their verified commits one at a time on an integration branch.

By 04:30 Madrid time, decide whether the platform integration is demo-ready. If not,
use the committed G60 / US core for the presentation. By 05:15, verify the hero's exact
sources, SMART requirement, score, human decision, simulated update and audit trace in
a resettable local database. Freeze new demo capabilities at 05:30. Keep working on
critical fixes, deck claim ledger, recording and rehearsals through the 11:30 deadline.
Only show a multi-agent chain or extra market/source when its real run and browser path
pass end-to-end. Record every cut and all unmeasured claims honestly.

Run relevant Ruff/pytest, web and isolated Docker Compose checks, inspect service logs,
and preserve source-to-decision trace across API, MCP and database. Keep BMW data,
database/local and database/snapshots out of Git. Commit reviewable milestones locally;
do not push or merge to main. Report the integrated hash, checks, demo snapshot ID,
claim ledger, slide/recording handoff, limitations, and remaining W1–W5 work.
Do not stop at a proposal: execute the verified slices that fit before the freeze and
continue the remaining implementation as separate reviewable milestones.
```
