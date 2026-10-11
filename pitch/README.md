# G60 / US pitch slides

Six slides for the 30-second trailer and 2:30 live product story in [`notes/pitch-plan.md`](../notes/pitch-plan.md). The slides support the demo; they do not need to fill its full three minutes.

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
| 5 | Change monitoring | After the live decision, run the **simulated update**. In the browser, use **Needs review → Open review → Versions** to compare the approved baseline with the current proposal. |
| 6 | Close | Repeat that the proposal is source linked and the PM decides. |

Before presenting, verify the prepared charging update path against the demo database, as the pitch plan requires.

## Claim boundaries for the presenter

- The 4,365 count is imported evidence rows. Source B supplies 2,626 of 3,610 unique feedback IDs (72.74%); it supplies 60.2% of imported rows. Neither figure describes market prevalence.
- The 71.26 priority score comes from a deterministic rubric whose reference factors include heuristics and PM assumptions. Grade C measures source strength separately. The source links trace the proposal; they do not prove its entire solution. One linked record is unrelated phone charging.
- The proposed 80% task-success target has no supporting study; it is explicitly a PM assumption. The combined first-time and in-car route journey is PM synthesis that needs validation.
- The demonstrated candidate uses deterministic reference analysis. It is not a verified live OpenAI multi-agent run. The approval gate checks a client-supplied PM actor string, so describe it as a prototype gate rather than production identity assurance. The saved post-update snapshot contains a disposable API test in which automation declared the `PM` actor. That is not a human PM approval. The live presenter must make any actual decision.
- The later charging record is synthetic and has no observation date. In the rehearsal snapshot it reopened only the charging proposal among eleven; the prior approved version stayed frozen. Do not describe it as newly observed BMW feedback. Use the **Versions** tab for the comparison; the **Recorded changes** expander shows raw JSON and is unsuitable for the pitch.

## Source and assets

Content is drawn from [`notes/pitch-plan.md`](../notes/pitch-plan.md) and the G60 / US prototype. Numerical and demo claims were checked against `notes/bmw-demo-claim-ledger.md` on `codex/bmw-demo-core` at commit `463b226`, which records the frozen application build (`fb245f3`) and source-workbook checks. The reference styling follows the [Invertix security page](https://www.invertix.ai/security). Its copper texture and four line icons are included in `assets/`. The BMW version uses the dashboard roundel and a cropped local car render. The car render is “2023 BMW i5 M60” by Nazh Design / Sketchfab, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); it is an independent artist model. Font licenses are in `assets/licenses/`.

To regenerate both HTML files after editing source styles or slide structure, run `node pitch/build-motion.mjs` and then `node pitch/build-reference.mjs` from the repository root. The HTML files themselves need no build step.
