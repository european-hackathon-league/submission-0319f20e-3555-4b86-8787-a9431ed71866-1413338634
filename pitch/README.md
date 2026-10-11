# G60 / US pitch slides

**Present with [`output/pitch-final.html`](output/pitch-final.html)** (static backup: [`output/pdf/pitch-final.pdf`](output/pdf/pitch-final.pdf)). It is built for a 30-second film, a 2-minute live demo and a 3:00 hard stop. The [final run of show](../notes/pitch-final-run-of-show.md) has the word-for-word script, driver clicks, cut rules and stage setup.

| Slide | When | Purpose |
| --- | --- | --- |
| Film | 0:00–0:30 | Plays `output/pitch-film.mp4` if it sits next to the HTML (ignored by Git); otherwise shows a title card. Press → to play. The deck advances to the hook when the film ends. |
| Hook | 0:30–0:40 | Three questions every requirement has to survive. The live demo answers them. |
| Close | 2:35–2:50 | Agents prepare, PMs decide: automated, surfaced and PM-only work. |
| B1–B5 | Fallback | The demo beats in order (overview, trace, score, decision, update) if the app stalls. Press `B`. |
| B6–B7 | Q&A | Built today versus pilot next; the agent-ready runtime. |

Keys: →/Space next, ← back, `B` backup, `C` close, `T` rehearsal stopwatch, `E` edit, `R` replay. Modifier shortcuts such as `⌘⌥→` pass through to the browser for tab switching. The URL hash keeps the current slide across reloads. Rebuild with `node pitch/build-final.mjs`.

The final deck is deliberately minimal: a roundel, a headline and a few large cards per slide, with no footers, IDs or fine print. Caveats, source rows and IDs are spoken (see the run of show and the [claim ledger](../notes/bmw-demo-claim-ledger.md)). The car render is credited here rather than on the slides; add the CC BY credit back to the slides if the deck is distributed.

The earlier six-slide versions below remain as style references.

## Open these files

| Version | Editable presentation | Static backup |
| --- | --- | --- |
| Reference style (copper, editorial type, square cards) | [`output/pitch-reference-template.html`](output/pitch-reference-template.html) | [`output/pdf/pitch-reference-template.pdf`](output/pdf/pitch-reference-template.pdf) |
| BMW dashboard style (roundel, Barlow, blue, motion) | [`output/pitch-bmw-motion.html`](output/pitch-bmw-motion.html) | [`output/pdf/pitch-bmw-dashboard.pdf`](output/pdf/pitch-bmw-dashboard.pdf) |

The HTML files contain their fonts, icons, images, styles, and scripts. They work offline. The PDFs embed their fonts and show all six slides.

## Edit and present

1. Open either HTML file in a browser. Click **Edit text** or press `E`, then click any headline, caption, card, or label to change it.
2. Click **Save HTML** to download a new, self-contained copy with your changes. Open that saved file to present it. Browser edits alone do not change the source file on disk.
3. Click **Print PDF** to export your edited version as a static PDF. Use landscape mode, no margins, and background graphics if the print dialog asks.
4. Use Right/Left, Space, Page Up/Page Down, Home/End, or the on-screen arrows to navigate. Press `F` for fullscreen, `R` to replay a slide, or Escape to leave edit mode. Slides advance only when you choose.

## Story and demo cues

| Slide | Purpose | Live cue |
| --- | --- | --- |
| 1 | Evidence-to-decision promise | Start after the trailer; move promptly into the demo. |
| 2 | G60 / US sample boundary | Say 4,365 imported rows; 72.74% refers to unique feedback IDs from Source B, not rows or market share. |
| 3 | Priority versus proof | Open charging requirement `REQ-G60-US-001`: score 71.26, grade C, 264 linked evidence records. Show one exact workbook row. |
| 4 | PM decision boundary | Show the deterministic reference proposal and 80% PM assumption. The live presenter must make any actual decision; the saved rehearsal approval was automated. |
| 5 | Change monitoring | After the live decision, run the **simulated update**. In the browser, use **Needs review → Open review → Versions**: one linked record is added, priority 71.26 to 71.33 (+0.07), while wording and the target stay the same. |
| 6 | Close | Repeat that the proposal is source linked and the PM decides. |

Before presenting, verify the prepared charging update path against the demo database, as the pitch plan requires.

## Claim boundaries for the presenter

- The 4,365 count is imported evidence rows. Source B supplies 2,626 of 3,610 unique feedback IDs (72.74%); it supplies 60.2% of imported rows. Neither figure describes market prevalence.
- The 71.26 priority score comes from a deterministic rubric whose reference factors include heuristics and PM assumptions. Grade C measures source strength separately. The source links trace the proposal; they do not prove its entire solution. One linked record is unrelated phone charging.
- The proposed 80% task-success target has no supporting study; it is explicitly a PM assumption. The combined first-time and in-car route journey is PM synthesis that needs validation.
- The demonstrated candidate uses deterministic reference analysis. It is not a verified live OpenAI multi-agent run. The approval gate checks a client-supplied PM actor string, so describe it as a prototype gate rather than production identity assurance. The saved post-update snapshot contains a disposable API test in which automation declared the `PM` actor. That is not a human PM approval. The live presenter must make any actual decision.
- The later charging record is synthetic and has no observation date. In the rehearsal snapshot it reopened only the charging proposal among eleven; the prior approved version stayed frozen. The review summary explains one added linked record and a score change of +0.07 (71.26 to 71.33), with wording and acceptance target unchanged. Do not describe it as newly observed BMW feedback. Use the **Versions** tab for the comparison; the **Recorded changes** expander shows raw JSON and is unsuitable for the pitch.

## Source and assets

Content is drawn from [`notes/pitch-plan.md`](../notes/pitch-plan.md) and the G60 / US prototype. Numerical and demo claims were checked against `notes/bmw-demo-claim-ledger.md` on `codex/bmw-demo-core` at docs checkpoint `1bfec69`. The frozen presentation build is `77f0376` (API/MCP base `fb245f3`). The reference styling follows the [Invertix security page](https://www.invertix.ai/security). Its copper texture and four line icons are included in `assets/`. The BMW version uses the dashboard roundel and a cropped local car render. The car render is “2023 BMW i5 M60” by Nazh Design / Sketchfab, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); it is an independent artist model. Font licenses are in `assets/licenses/`.

The local screenshot fallback is listed in `notes/bmw-demo-captures.md` on the core branch and stored under ignored `database/local/demo-captures/`. Keep those BMW-derived images out of Git and use them only with the matching build and snapshot.

To regenerate the HTML files after editing source styles or slide structure, run `node pitch/build-final.mjs`, `node pitch/build-motion.mjs` and then `node pitch/build-reference.mjs` from the repository root. `assets/g60-car-faded.png` is the car render with its studio backdrop faded to transparency for the final deck. The HTML files themselves need no build step.
