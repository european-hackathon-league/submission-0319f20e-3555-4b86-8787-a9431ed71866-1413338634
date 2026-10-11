# G60 / US presentation runbook

**Candidate:** presentation build `77f0376` on `codex/bmw-demo-core`, migration 0009, local pre-decision snapshot `app-20261011T033717381575Z-bmw-predecision.db`. The [claim ledger](bmw-demo-claim-ledger.md) is the authority for numbers and wording. The deck may show only this frozen build's verified features.

## Reset and preflight

From `/Users/troy/.codex/worktrees/bmw-demo-core/ehl-final`:

```sh
scripts/reset_bmw_demo.sh predecision
```

This checks the snapshot hash, restarts only the isolated `bmw-demo-core` Compose project, restores the local database copy, and runs the web preflight. The original BMW inputs and snapshots stay ignored by Git. Keep `database/local/originals/` with the snapshot so original-source links resolve. The app is at <http://127.0.0.1:13203/g60/us>; API at port 18200; MCP at port 18201. Do not run the reset against the main checkout or stop its stack.

The prepared state has 4,365 G60 / US evidence rows, 11 proposed requirements, and **no decision** on the hero. An agent must not select a human identity or submit approval on the presenter's behalf. The presenter chooses their own declared reviewer and rationale. This prototype uses self-declared actors; BMW identity integration remains pilot work.

## Live path after the deck's opening

| Approx. live time | Driver action | Presenter wording |
| --- | --- | --- |
| 0:00–0:20 | Overview, G60 / US | “These are 4,365 imported feedback rows, not market prevalence. About 72.7% of unique feedback IDs come from one source.” |
| 0:20–0:50 | Requirements → search `charging` → open `REQ-G60-US-001` | “Here is a proposed customer outcome. The combined route experience is a PM solution hypothesis. Its 80% task-success target is explicitly a PM assumption.” |
| 0:50–1:15 | Evidence Trace; point to a checked workbook/sheet/row, such as `Feedback_Explorer` row 432 | “The source location is reconstructable. We checked 12 records against the archived workbook. The wider automatic links still contain false positives, so a PM reviews them.” |
| 1:15–1:35 | Score tab | “71.26 comes from recorded, deterministic factors and rubric v1. Evidence grade C is separate; the reference factors are provisional.” |
| 1:35–2:00 | Presenter selects their own reviewer, enters rationale and decides | “The database rejects AI-labelled approval. My decision binds this exact version and score.” Do not perform this step if the presenter has not reviewed the proposal. |
| 2:00–2:15 | Driver runs `scripts/run_bmw_demo_update.sh`, then refreshes Needs review | “This next input is simulated and undated. The update targets only the affected charging proposal.” |
| 2:15–2:30 | Needs review → Open review → Versions tab | “One new linked record changes the score from 71.26 to 71.33; wording and target stay the same. The approved v2 remains frozen beside proposed v3. Ten other current requirements were unchanged in the rehearsal.” |

The update command refuses to run until the hero has an approved version. It imports a synthetic record with `simulated=true`, runs deterministic cumulative analysis, checks that only charging changed and one open review remains, then takes a local post-update snapshot. `Recorded changes` expands raw JSON and is too dense for the pitch; use the Versions tab.

## Fallback and Q&A

- If the browser stalls, keep the deck visible and use its static evidence/requirement/update slides or the local [capture pack](bmw-demo-captures.md). A complete recorded live run has **not** been produced or timed yet; do not claim that it exists.
- If the presenter does not approve, stop before the update command. Show the decision gate and explain the update path as a verified disposable rehearsal, labelled as such.
- If asked about agents: this frozen candidate uses a labelled deterministic reference pipeline. The integrated platform branch has a registry and capability runtime, but a live multi-agent OpenAI chain is not part of this demo.
- If asked about security: AI-labelled approval is rejected; a client can still supply an actor string. SSO, permissions and BMW-hosted infrastructure require a pilot.
- If asked about sources: the hero's 12 checked records cover search/routing, availability, compatibility and positive experience separately. The full combined journey and numeric target need validation. One checked linked record was unrelated phone charging.

The browser path, API gates, local update, snapshots and audit chain have been checked. Two presenter-timed runs, venue display/audio and a recorded fallback still need the humans presenting to perform or confirm them.
