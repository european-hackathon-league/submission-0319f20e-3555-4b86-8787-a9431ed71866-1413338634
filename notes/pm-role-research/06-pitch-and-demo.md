# 6. Pitch and demo implications

Format: **3-minute pitch + 3-minute Q&A** [BMW-hackathon]. Judges are BMW product-management people, so speak their language: *Fachbereiche*, markets, gates, SMART targets, "what customers love", Codebeamer, AIconic.

## 6.1 Core message

> **"A BMW PM's week, compressed into minutes, and every decision still theirs."**
>
> Agents do the reading, reconciling, drafting and defending. The PM does the deciding. Every requirement is one click from the customer's own words, and every decision is in an audit trail BMW can reconstruct two years later.

Avoid "AI generates requirements". BMW's own framing is that the PM *derives, prioritises and decides*, with AI standardising findings, finding duplicates, grouping themes and connecting insights (keynote process slide) [BMW-hackathon].

## 6.2 Features to showcase, ranked by judge impact

| Rank | Feature | PM reality it answers | Judging criterion | Status |
| --- | --- | --- | --- | --- |
| 1 | **Click a requirement → original customer words, score, decision, audit** in seconds | "Where does this come from?" | Traceability | Built (trace drawer, MCP trace explorer) |
| 2 | **Morning brief: what changed since the approved baseline**, with affected decisions | Two-year rolling process | Workflow, Innovation | Backend built (`assess_updates`); brief UI to add |
| 3 | **Market request triage** (e.g. BMW NA request vs China and EU evidence) with conflict detection | Pain point #1: balancing markets; negotiation load | Decision logic, Workflow | To add (simulated requests, clearly labelled) |
| 4 | **SMART requirement with PM-assumption target**, edited, then approved with exact version and score | "Range: 600 or 700 mi?" | Decision logic, Human decision | Built |
| 5 | **Challenger agent objects**: weak evidence, source concentration (72.7% one source), out-of-scope drift | Honesty about uncertainty, rewarded by the rubric | Decision logic | To add |
| 6 | **One decision → four drafted messages** (engineering, market, board, sales), never sent | Same decision, many audiences | Usability, Business impact | To add |
| 7 | **"What customers love" protected list** (driving dynamics, design) | Preserve positives | Solution quality | Built in findings; surface it |
| 8 | **Agent activity stream** showing autonomous vs assisted vs human steps | Required workflow boundaries | Workflow | Partially built (workflow stages) |
| 9 | **3D studio hotspots** linking vehicle zones to requirements | Makes the funnel tangible | Innovation | Built (visual layer, not the core) |
| 10 | **Codebeamer-ready export** of decided requirements | Enterprise fit | Feasibility, Scalability | To add (export format only; no live integration claim) |

## 6.3 Three-minute narrative (draft)

| Time | Beat | On screen |
| --- | --- | --- |
| 0:00–0:20 | **The problem in BMW's words.** "One billion findings, one thousand requirements, one car, over two years, across markets that want different things." | Keynote funnel restated with our G60/US numbers |
| 0:20–0:45 | **Meet the PM's agent team.** The morning brief shows what changed and what needs a decision. | Morning brief + activity stream |
| 0:45–1:20 | **Market tension.** The US asks for X; the agents attach evidence and show China and EU conflicting or supporting, then draft a position. | Request triage card |
| 1:20–1:55 | **Decide.** SMART requirement, target flagged as PM assumption, challenger objections, score breakdown, evidence grade. PM edits the target and approves the exact version. | Decision card |
| 1:55–2:20 | **Trace and audit.** Click from the decision or 3D hotspot to the original verbatim; show the hash-chained audit. | Trace drawer + audit |
| 2:20–2:40 | **Communicate.** One click: four drafts for engineering, the US market, the board and sales, all citing the same IDs. Nothing is sent automatically. | Drafts tray |
| 2:40–3:00 | **Impact and scale.** Content-heavy PM work is where McKinsey measured ~40% savings; ours is measured on grounding and review effort. Same agents for any series and market; decided requirements flow into Codebeamer. | Metrics panel |

## 6.4 Q&A bank

| Likely question | Answer anchor |
| --- | --- |
| *Why multiple agents and not one prompt?* | Each agent maps to a distinct PM job and tool set with its own autonomy level, as with BMW's AIconic (10 agents). Separation also makes the audit trail legible: you can see which agent did what. Scoring stays deterministic. |
| *What if the AI hallucinates?* | Findings require exact source spans; grounding checks run before anything reaches the PM; counts and scores come from code, not the LLM; targets without a source are labelled PM assumptions. |
| *Who is accountable?* | Only a human actor can approve, reject or postpone, with exact version and score IDs. AI actors are denied at the database level. Drafts are never sent automatically. |
| *How does it handle conflicting markets?* | Market Balancer shows per-market evidence and conflicts. The PM decides global vs market-specific; the rationale is recorded. |
| *Are the counts representative?* | No, and we say so: feedback is selected and undated, and G60/US is 72.7% one source. We show counts as sample evidence, not market prevalence, and the Research Planner proposes studies to close gaps. |
| *How does it scale to 1,000 requirements and more data?* | Scope-parameterised runs, batched and cached analysis by source hash, delta-only update runs, review items only for affected decisions. |
| *How would this fit BMW's landscape?* | Upstream of Codebeamer (BMW's requirements standard since 2026); MCP tools any governed agent platform can call; model-provider agnostic; internal data never goes to public research tools. |
| *What about pricing and the business case?* | Out of scope by design. We flag dependencies ("needs cost estimate") and use only rough effort as a factor. |
| *What did you not build?* | Live Codebeamer or SSO integration, real market-request inboxes, a validated time study. These are next steps, with the measurement plan below. |

## 6.5 Measurement plan to cite instead of invented ROI

1. **Grounding rate:** % of findings and requirement claims with exact source spans (target 100%).
2. **PM spot-check agreement:** sample N findings and have a human confirm the classification.
3. **Review effort:** decisions needed per update run vs total requirements (only affected items surface).
4. **Time-to-trace:** seconds from requirement to original verbatim (live in the demo).
5. **Consistency:** identical inputs, weights and versions give identical scores.

Quote external figures with attribution only (McKinsey ~40% on content-heavy PM tasks, n≈40). Do not claim BMW-specific hours saved.

## 6.6 Vocabulary cheat sheet

| Term | Meaning | Use it when |
| --- | --- | --- |
| *Fachbereiche* | Specialist departments | Talking about engineering and other functions |
| *Baureihe* / derivative | Model series / variant (e.g. G60 5 Series / i5 M60) | Scope selection |
| *Sonderausstattung (SA)* | Optional equipment | Packages and options |
| Take rate | Share of buyers choosing an option | Offer structure |
| NSC / market | National sales company (e.g. BMW of North America) | Market requests |
| LCI | Life Cycle Impulse, BMW's mid-cycle update | Current-generation work |
| G0 / G1, concept freeze | Gates in BMW's challenge diagram | Decision points |
| *Zielvereinbarung* | Target agreement in the BMW product development process | Gate packs |
| Codebeamer | BMW's group-wide requirements management tool (2026) | Enterprise fit |
| AIconic | BMW Purchasing's multi-agent system | Agent framing |
| Neue Klasse | BMW's new EV platform and design generation | Forward assumptions and technology fit |
