# Final pitch run of show: 30-second film, 2-minute demo, 3:00 hard stop

Status: **stage script**, 11 October 2026. This replaces the timing in the
[pitch story](pitch-story-and-video.md) and the [pitch plan](pitch-plan.md). The
[runbook](bmw-demo-runbook.md) still governs reset and preflight, and the
[claim ledger](bmw-demo-claim-ledger.md) governs every number. The deck is
[`pitch/output/pitch-final.html`](../pitch/output/pitch-final.html), with a static backup in
[`pitch/output/pdf/pitch-final.pdf`](../pitch/output/pdf/pitch-final.pdf).

## Why this shape

The judges are BMW product managers. They score five criteria and reward honesty
([challenge](challenge.md)). Their stated pains are a two-year requirements process,
turning predecessor feedback into the next car's requirements, and balancing markets
([guidance](bmw-guidance.md)). Every PM has to defend a requirement on three questions,
so the pitch is built around them. The slides only frame those questions and close
them. The product answers them live.

| Question on the hook slide | Live answer | Criterion it earns |
| --- | --- | --- |
| Where did it come from? | Evidence Trace → workbook, sheet, row 432 | Traceability and auditability |
| How sure are we? | Priority 71.26 beside grade C; 80% labelled `PM assumption` | Decision and scoring logic |
| (decision) | The presenter approves the exact version; AI approval is refused | Workflow and human decision-making |
| What changed since we decided? | 1 of 11 reopened, +0.07, approved v2 frozen | Innovation, scale and impact |
| (whole demo) | Real G60 / US data in a working UI, limits stated | Solution quality and feasibility |

## Timing

The slides get 25 seconds and the demo gets 1:55. That leaves 10 seconds of buffer
inside 3:00. These are rehearsal targets; no presenter has timed them yet.

| Clock | Screen | Driver | Presenter says (about 110 words per minute) |
| --- | --- | --- | --- |
| 0:00–0:30 | **Film** (deck slide `Film`) | Press → once to play. The deck moves to the hook when the film ends. | Nothing. |
| 0:30–0:40 | **Hook** slide | — | “For two years, every requirement has to survive three questions. Where did it come from? How sure are we? What changed since we decided? Here's the G60 i5 in the US, live.” |
| 0:40–0:50 | App: Overview, G60 / US | Switch to the app tab. | “4,365 imported feedback rows. And the first thing it tells you: about 73% of feedback IDs come from one source. So these are samples, not market share.” |
| 0:50–1:15 | Requirements → search `charging` → `REQ-G60-US-001` → Evidence Trace → row 432 | Click while the presenter talks. | “Here's a proposal: charging. Where did it come from? One click: workbook, sheet, row 432, the customer's own words. 264 linked rows. We checked 12 by hand, and the one false positive stays visible.” |
| 1:15–1:35 | Score tab, then the acceptance target | — | “How sure are we? Priority 71.26 from a versioned rubric: same inputs, same score. Evidence grade C sits beside it, never inside it. And the 80% target is labelled PM assumption, because no data proves it.” |
| 1:35–1:55 | Decision footer | The **presenter** selects their own reviewer, types a rationale and approves. Then the driver runs `scripts/run_bmw_demo_update.sh`. | “So the PM decides. I approve this exact version and score. An AI actor can't do this; the API refuses it. And it's in the audit trail.” |
| 1:55–2:35 | Refresh → Needs review → Open review → **Versions** | Open the review as soon as the script finishes. | “Two years of new feedback. This record is simulated. Only charging comes back, one of eleven. One new linked row moves priority from 71.26 to 71.33. Wording and target are unchanged, and my approved version stays frozen beside the new one. The PM reviews the change, not the whole list.” |
| 2:35–2:50 | **Close** slide | Switch to the deck tab, press →. | “The machine prepares and flags what's uncertain; the PM decides. The same pipeline works for any *Baureihe* and market, and the platform can run these operations as scoped agent tasks over MCP. Agents prepare. Product managers decide.” |

Pause briefly after row 432, after “grade C” and before the final line.

## Cut rules

1. **Running more than 10 seconds late at 1:35:** shorten the overview to “4,365 rows, 73% from one source, so samples, not market share.”
2. **The update script takes more than 10 seconds:** keep talking through the decision line. Time it in rehearsal and type the command in the terminal beforehand.
3. **The presenter does not approve after reviewing:** stop before the update. Switch to the deck, press `B` and go to **B5**: “In our rehearsal, new input reopened only this proposal.” Say that it was a rehearsal.
4. **Never** let anyone but the presenter make the decision, and never describe the saved post-update snapshot's automated `PM` test as a human approval.

## Fallback if the app stalls for more than 3 seconds

Switch to the deck tab and press `B`. Backup slides **B1–B5** follow the demo beats in
order: overview, trace, score, decision, update. Keep talking from the same script without
apologising. The local capture pack ([`bmw-demo-captures.md`](bmw-demo-captures.md)) is the
second fallback. No recorded live run exists yet.

## Q&A

Answer in under 30 seconds: the number first, the caveat second. Use the
[Q&A card](bmw-demo-qa.md). Two backup slides support common questions:

- **B6 Built today, pilot next:** for “what didn't you build?”, Codebeamer, SSO or scale.
- **B7 The agent-ready runtime:** for “where are the agents?”. It belongs to the integrated platform build, not the frozen demo, and LLM orchestration is the next phase.

## Stage setup

- One Chrome window, presentation mode (`⌘⌃F`). Tab 1 is the deck, tab 2 is
  <http://127.0.0.1:13203/g60/us> after `scripts/reset_bmw_demo.sh predecision`.
  Switch with `⌘⌥→` and `⌘⌥←`. The deck's own `F` fullscreen ends when you switch tabs, so do not use it.
- Put the exported film at `pitch/output/pitch-film.mp4`, next to the deck. Without it, the
  film slot shows a title card. Play it once before the session so it is buffered, then reload
  the deck (it reopens on the slide in the URL hash, e.g. `#1`).
- App browser zoom set so table text reads at the back of the room; check it on the venue display.
- Notifications off, terminal open in the `bmw-demo-core` worktree with the update command typed.

## Deck keys

`→`/Space next (on the film slide, the first press plays the film) · `←` back ·
`B` first backup slide · `C` close slide · `T` rehearsal stopwatch · `E` edit text ·
`R` replay slide animation. The toolbar appears on hover only.
