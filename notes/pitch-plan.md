# Pitch plan: 30-second trailer + 2:30 live

Status: **draft**, 11 October 2026. Format is 3 minutes of pitch plus 3 minutes of Q&A ([BMW guidance](bmw-guidance.md)). Builds on [pitch and demo research](pm-role-research/06-pitch-and-demo.md), [the challenge](challenge.md) and [web/DEMO.md](../web/DEMO.md).

> **Frozen presentation override (11 October, build `77f0376`):** This is a pre-freeze creative draft, not the verified script. Use the [G60 / US runbook](bmw-demo-runbook.md), [claim ledger](bmw-demo-claim-ledger.md), and [Q&A card](bmw-demo-qa.md) for the 11:30 presentation. The frozen candidate uses deterministic reference analysis, has no verified live OpenAI multi-agent chain or trailer recording, and has no Codebeamer or BMW identity integration. The live PM must personally make any decision. Do not use the draft lines below that say agents drafted the hero, AI chose its 80% target, or decided requirements already flow to Codebeamer.

The later [pitch story and video direction](pitch-story-and-video.md) develops the
pipeline-to-agent-runtime reveal, presenter tone and a claim-safe three-minute arc.
It remains creative direction; the frozen runbook and claim ledger govern the live demo.
The [final run of show](pitch-final-run-of-show.md) is the stage script: film, hook, 1:55 demo, close.

## The one sentence

> **Agents do the reading, counting, drafting and defending. The PM makes the decision. Every requirement is one click from the customer's own words.**

Every beat below has to support that sentence. If a beat doesn't, cut it.

## What the judges score

The judges are BMW product-management people. There are five criteria, and no weights were given. Each one needs a visible moment:

| Criterion | Where they see it |
| --- | --- |
| Decision and scoring logic | Score breakdown with a **separate** evidence grade; a high score with weak evidence looks different |
| Workflow and human decisions | AI drafts; only a PM can approve; the target is labelled `PM assumption` |
| Traceability and audit | Requirement → finding → the original workbook row in one click; the audit event appears after the decision |
| Solution quality and feasibility | Real G60/US data, a real UI, and honest data limits (72.7% Source B) |
| Innovation, scale and impact | The two-year update loop (only affected decisions resurface), any *Baureihe* and market, MCP, upstream of Codebeamer |

The rubric explicitly **rewards honesty**. Saying what the data cannot prove scores points; overselling loses them.

## Run of show (3:00 hard stop)

| Time | Block | Who |
| --- | --- | --- |
| 0:00–0:30 | **Trailer** (video, no one speaks) | Plays from the laptop |
| 0:30–2:45 | **Live product story**: one requirement, end to end | Presenter speaks, driver clicks |
| 2:45–3:00 | **Close**: scale, fit and the one sentence | Presenter |

The trailer should do the "wow" and the feature awareness. The live part is **one story about one requirement**, not a feature tour. Live, we show the details the trailer only flashes.

## Part 1: the 30-second trailer

### Concept

Apple product-film grammar: black background, one idea per shot, big type, a music hit on every cut, and the product UI shown as the hero. No voiceover; titles carry it, so the venue audio can fail without losing the message. The arc goes from BMW's own funnel to the product to "you decide".

### Shot list

| Sec | Picture | On-screen text |
| --- | --- | --- |
| 0–3 | Black. Thousands of tiny feedback snippets drift like particles | **1,000,000,000 findings.** |
| 3–5 | Particles condense into a column of cards | **1,000 requirements.** |
| 5–8 | Cards collapse into a light sweep that reveals the G60 i5 M60 silhouette (3D studio render) | **One car.** |
| 8–11 | Three quick cuts: US / EU / CN, each a different car zone glowing (charging, rear seat, cockpit) | **Two years. Three markets. Different wants.** |
| 11–13 | Hard cut to black, then the product name | **[Product name]** |
| 13–15 | Real UI capture: verbatims stream into findings | **Listens.** 4,365 feedback records |
| 15–17 | Score bars animate; an evidence grade badge drops in next to them | **Weighs.** Priority ≠ proof |
| 17–19 | A line draws from the requirement to the original customer sentence | **Traces.** One click to the source |
| 19–21 | Audit events tick in | **Remembers.** Every change, every reason |
| 21–24 | A cursor hovers Approve; it's disabled for the AI actor, then the PM clicks it | **AI drafts. You decide.** |
| 24–28 | 3D car turns; the charging port, seats and cockpit light up in sequence | — |
| 28–30 | End card | **[Product name]. Every requirement, one click from the customer.** Team name |

### Rules for the trailer

- **Only show features that work.** Every UI shot is a real screen capture from the demo database. Judges will see the same screens live 30 seconds later; a mismatch costs credibility.
- No BMW website or configurator imagery. Use the licensed 3D models from the vehicle studio and credit them in small type on the end card (CC BY: "2023 BMW i5 M60 by Nazh Design").
- No invented numbers. "1 billion → 1,000 → one car" is BMW's keynote funnel; 4,365 is our G60/US record count.
- Export 1080p and 4K H.264 with music baked in. Also export a silent, captioned version in case the venue audio fails.

### How to build it (about 3–4 hours)

1. **Captures (45 min):** Record 60 fps screen captures of each UI beat from the prepared demo database (see below), at 1.5× browser zoom so the type reads on a projector. Record the 3D studio orbit and hotspot glow.
2. **Composition (2 h):** Use Remotion via the `content-vault:launch-video` skill (React composition, beat-anchored timing, music and sound effects). Keep the type in one weight and one size per shot, with white on black and a single BMW-blue accent.
3. **Music:** One licence-free track with a clear hit roughly every 2 seconds. Cut picture to the hits, not the other way round.
4. **Review (30 min):** Play it on the projector-sized screen. Each title must be readable in under 1 second.

## Part 2: the live story (2:30)

**Hero requirement:** `REQ-G60-US-001` (charging), G60 / i5 M60 / US. It has the strongest customer-experience story, a `PM assumption` target to edit, conflicting evidence and a 3D charge-port hotspot.

| Time | Click | Say (approximately) |
| --- | --- | --- |
| 0:30–0:50 | Overview, G60 · US | "BMW told us yesterday that a PM's hardest problems are balancing markets and turning predecessor feedback into the next car's requirements, over two years, not once. This is the real G60 US data: 4,365 feedback records. And here's the first thing our tool tells you: 73% come from one source. So these are sample counts, not market share. It says what the data *can't* prove." |
| 0:50–1:20 | Open the charging requirement → Evidence Trace | "The agents drafted this requirement. Priority 71, but evidence grade C, and those are deliberately separate. Click: here's the customer's own sentence, workbook, sheet and row. And here's the evidence that *disagrees*; we show it rather than hide it." |
| 1:20–1:50 | Score tab → decision footer | "The score is deterministic code, not the LLM. Same inputs, same score. The AI proposed a target of 80%, labelled *PM assumption*, because nothing in the data justifies it. The AI can't approve; the database refuses. I'm the PM: I edit the target, give a reason, approve. That's a new immutable version, linked to its exact score, and it's in the audit trail." |
| 1:50–2:20 | Import the simulated new batch → Needs review | "It's a two-year process, so new feedback arrives. This batch is labelled simulated, since the data has no dates. Only the charging requirement comes back for review, with my approved version side by side with the proposed change. Ten other requirements are untouched. The PM reviews deltas, not the whole list again." |
| 2:20–2:45 | 3D studio → click the charge port | "The same trace from the car itself: click the charging port and you're back at the customer's words." *(Cut first if over time.)* |
| 2:45–3:00 | Back to overview or a closing slide | "Same pipeline for any *Baureihe* and market. Any governed agent can plug in over MCP, and decided requirements flow upstream into Codebeamer. Agents do the reading, counting, drafting and defending. The PM makes the decision." |

**Cut order if the rehearsal runs long:** 3D beat → the conflicting-evidence sentence → the Score tab (keep the decision footer).

**Swap option:** if the market balancer (`codex/platform-markets`) is merged and verified before the freeze, replace the 3D beat with a market-conflict beat: "the US wants X, China's evidence says Y, the PM decides global vs market-specific." That hits BMW's pain point #1 directly and is stronger than 3D. Decide at the freeze, not on stage.

### Live vs recorded

Drive it live: judges trust a live product. Keep a **recorded run of the same 2:30** in the same playlist as the trailer, one keystroke away. If anything stalls for more than 3 seconds, switch to the recording and keep talking without apologising.

## Demo database prep (the biggest risk)

The current G60/US database was built by the rule-based reference provider (`System:reference`). Every requirement is titled "Improve X", all have evidence grade C, and the priorities cluster between 68 and 76. Three problems for this audience:

1. **"Where's the AI?"** The visible text is templated.
2. **"Improve charging experience" is not SMART.** BMW's mentors said almost exactly this ("a fridge with *a lot of space* is not specific").
3. **"Improve driving experience" is ranked #1**, but driving dynamics is something US customers *love*. It should read as a must-not-lose attribute, not something to fix.

Fix before capturing the trailer:

- [ ] Rebuild a **copy** of the demo database with `provider: "openai"` (`gpt-6-luna`), and check that the requirement titles and statements are specific and still cite sources. Keep the reference run as the fallback.
- [ ] Hand-check the hero requirement's claims against its source rows (the [proposal](winning-demo-proposal.md) requires material AI claims to be checked before the demo).
- [ ] Confirm that driving experience and design appear as **preserve** requirements. If not, fix that in the pipeline output or don't show the register's top row.
- [ ] Prepare the simulated update batch file. Rehearse that it flags only the charging requirement.
- [ ] Run `bun run demo:check http://127.0.0.1:3003` against the demo copy.
- [ ] Snapshot the prepared database (`python -m database.snapshot`) so every rehearsal starts from the same state.

## Q&A (3 minutes, about 4 questions)

Roles: **presenter** takes the question and routes it. **Product/scoring** answers how it works; **data/AI** answers data, models and limits. Answer in under 30 seconds, with the number first and the caveat second.

| Likely question | Answer anchor |
| --- | --- |
| Where does the AI stop and the code start? | The LLM extracts and drafts with exact source spans. Counting, deduplicating and scoring are deterministic code. Approval is human only, enforced in the database. |
| What if it hallucinates? | Findings must cite exact spans or they aren't persisted. Targets without a source are labelled `PM assumption`. Same inputs give the same score. |
| Why is everything grade C? | The data is selected, undated feedback, and 73% comes from one source. We'd rather show C honestly than fake A. Customer studies and market data raise the grade. |
| How did you choose the weights (35/25/20/10/10)? | They're a declared starting rubric, versioned with every score. The PM can change them, and the change itself is audited. The evidence grade is never mixed into the priority. |
| Are these counts representative? | No, and the UI says so. They're sample evidence, not prevalence. The next step is a targeted study to close the gap. |
| Does BMW data go to OpenAI? | In the prototype, the analysis step calls the configured model API. Public web research (Exa) never receives BMW data. In production, this runs against BMW's governed model endpoint; the provider is a config switch. |
| How does it scale to 1,000 requirements over two years? | Runs are scoped by vehicle and market and cached by source hash. Updates are delta only: only affected decisions resurface for review. |
| How would it fit BMW's tools? | It sits upstream of Codebeamer. MCP lets BMW's agent platforms (as with AIconic) call the same governed operations. |
| What about cost and the business case? | Out of scope by BMW's definition. Rough effort is one scoring factor, and dependencies like "needs a cost estimate" are flagged. |
| What didn't you build? | Live Codebeamer and SSO, real market-request inboxes, a validated time study. We measure grounding rate, review effort per update and time-to-trace instead of claiming hours saved. |

## Timeline to pitch

| When | What | Gate |
| --- | --- | --- |
| Now → T-10h | Decide the open questions below; rebuild the demo database with OpenAI; pick and check the hero requirement | Demo database snapshot exists |
| T-10h → T-6h | Trailer captures plus Remotion build, in parallel with the live-script rehearsal | Trailer v1 renders |
| **T-6h** | **Feature freeze.** No merges to the demo stack after this. Decide the market-balancer swap | Stack + snapshot tagged |
| T-6h → T-3h | 5 timed full run-throughs (trailer + live + mock Q&A); record the backup run | Two runs in a row under 3:00 |
| T-3h → T-1h | Final trailer cut, export the captioned variant, test on an external display | Files on two laptops + USB |
| T-1h | Venue check: HDMI/USB-C, audio, browser zoom, notifications off, restore the snapshot | — |

## Open decisions

1. **Product name** for the trailer title and end card (working name: *Requirement Twin*).
2. **Who presents, who drives, who answers which Q&A topics.**
3. **3D beat or market-balancer beat** at the freeze.
4. **BMW logo** on the end card: the [3D plan](3d-twin-plan.md) says to avoid it unless BMW confirms. Safest is the team name only and the car badge as-is.
