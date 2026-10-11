# Pitch story and video direction: pipeline to agent runtime

Status: **creative direction**, 11 October 2026. This is a proposed narrative for a
three-minute BMW pitch (plus three minutes of Q&A), not a verified demo script or a
finished video. Use the [frozen G60 / US runbook](bmw-demo-runbook.md) for live actions
and the [claim ledger](bmw-demo-claim-ledger.md) for exact numbers and boundaries.

## The idea

**The future of product management is a team of bounded specialist agents preparing
evidence-backed work, with the PM coordinating trade-offs and owning decisions.**

Show this as an evolution, not as two unrelated products:

1. **The PM problem:** customer evidence arrives from many sources and markets over a
   multi-year product cycle. A PM has to turn it into defensible requirements and
   revisit decisions when the evidence changes.
2. **The foundation:** our pipeline takes an original source through a finding,
   candidate requirement, deterministic priority and evidence grade to a versioned
   PM decision. A reviewer can return to the source and inspect assumptions.
3. **The evolution:** the integrated platform makes those governed operations
   available as scoped capabilities and tasks. The agent registry, task queue,
   scheduler and run history make delegation and oversight visible.
4. **The payoff:** the PM spends the visible moment reviewing evidence, handling
   uncertainty and deciding. The source trail and decision history remain available
   when a simulated new input reopens the affected proposal.

BMW [describes agentic AI](https://www.bmwgroup.com/en/news/general/2026/agentic-AI.html)
as a way to reduce repetitive coordination and leave people more room for strategic
thinking and considered decisions. The pitch should make that benefit concrete in a
BMW PM workflow rather than announce a generic AI future.

## Tone and visual language

- **Cinematic in the film, precise in the room.** Use a confident reveal of the
  product, then slow down enough to let a judge follow one source and one decision.
- **Product first.** Use legible captures of real screens, short titles and a single
  musical lift when the agent runtime appears. Avoid robot imagery, invented agent
  conversations, fake terminal activity and abstract architecture animations that
  cannot be tied back to the product.
- **Human agency is the climax.** End the film on review and a PM decision, rather
  than an autonomous approval. Call the requirement a proposal until a PM acts.
- **Honesty adds credibility.** Say when a target is a `PM assumption`, an evidence
  grade is C, a source is concentrated, or an update is simulated. These are visible
  product behaviors, not apologies. The [BMW rubric](challenge.md) explicitly
  evaluates uncertainty and human decision gates.

Do not spend pitch time on an agenda slide or a tour of every platform module. The
video establishes breadth; the live demonstration proves one path end to end.

## Thirty-second opening film

Make this understandable without audio: no voiceover is needed, and every important
line appears on screen. Keep titles to one idea per shot and verify every product
capture against the build it came from.

| Time | Picture | Suggested on-screen line |
| --- | --- | --- |
| 0–7s | Feedback fragments resolve into the G60 / US context. | **One car. Thousands of signals.** |
| 7–15s | Real pipeline screens: source → finding → requirement; show priority beside its separate evidence grade and a source link. | **A decision you can trace.** |
| 15–23s | Reveal the integrated platform's agent registry, scoped task queue and recorded runs. | **Now the work can be coordinated.** |
| 23–30s | A PM inspects the proposal and decision gate; finish on the product name/team. | **Agents prepare. Product managers decide.** |

Use a restrained, driving track with one clear lift at 15 seconds. Choose readable
type, high contrast and one accent color. Export a captioned silent fallback. Do not
show a model-generated run as if it occurred in the frozen G60 / US state. If the
film includes the latest integrated platform screen, identify it as the platform
runtime capture; the frozen G60 / US candidate is a different verified build.

## Three-minute run of show

> **Superseded timing:** the stage version uses a 30-second film, a 10-second hook slide, a 1:55 demo and a 15-second close. See the [final run of show](pitch-final-run-of-show.md). The table below is the earlier draft.

The film carries the V2 reveal; the live portion stays anchored to the verified
charging proposal `REQ-G60-US-001`. These are target times for rehearsal, not a
claim that the sequence has been timed by the presenter.

| Time | Presenter and screen | Point to land |
| --- | --- | --- |
| 0:00–0:30 | Play the film. | Broad arc: evidence pipeline → agent runtime → human decision. |
| 0:30–0:45 | G60 / US overview. | 4,365 imported evidence rows; selected feedback, not market prevalence. |
| 0:45–1:20 | Open the charging proposal and Evidence Trace. | Return to an original workbook row; explain that the combined solution remains a PM hypothesis. |
| 1:20–1:50 | Score and acceptance target. | Priority 71.26 is deterministic; grade C is separate; the 80% target is a PM assumption. |
| 1:50–2:15 | Show the decision gate; the presenter personally reviews and acts if ready. | The prototype rejects AI-labelled approval; only the presenter's action is a live human decision. |
| 2:15–2:40 | If that decision was made, run the labelled simulated update and open Needs review → Versions. | One linked record changes priority by +0.07; the approved version remains frozen. |
| 2:40–3:00 | Close on a static platform-runtime capture or a closing slide. | The same governed operations can be assigned, observed and reviewed as agent tasks. PMs own the trade-offs. |

If the presenter does not approve after reviewing the proposal, stop before the
update command and describe the update as a verified disposable rehearsal. If time
runs short, omit the update beat and preserve the trace, score and decision boundary.
The [runbook](bmw-demo-runbook.md) remains authoritative for reset, click path,
fallbacks and the fact that a full recorded live run has not yet been produced.

## Presenter language

**Opening after the film:**

> BMW PMs need to know which customer signal matters, where a proposal came from,
> and what changed. Let me show you charging.

**V2 close (use after the live proof):**

> That was the evidence-to-decision pipeline. Now its governed operations can run
> as scoped tasks for specialist roles, with every run visible. The PM still owns
> the decision.

Deliver these lines with short pauses after the source trace, the evidence grade
and the V2 reveal. Keep the pace conversational; do not race through feature names.

## Claim boundaries and preparation

The [integrated platform](../PLATFORM_BUILD_PLAN.md) has an agent registry,
capability executor, scoped tasks, scheduler, run history and MCP access. Its
bounded LLM orchestrator and sub-agent loop are **next-phase work**. Describe V2
as an **agent-ready runtime** or **operating layer for coordinated agents**, not a
fully autonomous multi-agent team already running the frozen demo. The [agent
runtime note](agent-runtime.md) defines what tasks and runs actually do.

The frozen G60 / US demo uses labelled deterministic reference analysis. It has
no verified live OpenAI agent chain, BMW identity integration or Codebeamer
connector. Do not claim measured PM time savings. The 4,365 figure counts
imported evidence rows, and the later charging input is synthetic and undated.
Keep those distinctions in the film, narration, slides and Q&A.

Before presenting:

1. Capture only real screens and keep a record of which build and data state
   produced each shot. Verify that the V2 capture and frozen live candidate are
   clearly distinguished.
2. Rehearse the complete three-minute sequence twice with the actual presenter,
   click driver and display. Keep the live V2 screen switch out unless it has its
   own preflight and timed rehearsal.
3. Check the film at projector size with audio on and off. Keep the captioned
   version, static deck and [capture pack](bmw-demo-captures.md) available.
4. Prepare short Q&A answers for what uses AI, who can approve, what the score
   means, how source links were checked and what V2 can run today. Use the
   [Q&A card](bmw-demo-qa.md) for the frozen candidate.
