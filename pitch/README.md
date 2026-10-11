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
| 1 | Customer-first promise | Start after the trailer; move promptly into the demo. |
| 2 | G60 / US sample boundary | Say 4,365 records and 72.7% from one source describe this sample, not the market. |
| 3 | Priority versus proof | Open the charging requirement; show score, evidence grade, and a source row. |
| 4 | PM decision boundary | Show the AI draft, the labelled PM assumption, then the PM edit and approval record. |
| 5 | Change monitoring | This is a **simulated update**. Show the new evidence and the affected requirement beside its approved version. |
| 6 | Close | Repeat that agents read and the PM decides. |

Before presenting, verify the prepared charging update path against the demo database, as the pitch plan requires.

## Source and assets

Content is drawn from [`notes/pitch-plan.md`](../notes/pitch-plan.md) and the G60 / US prototype. The reference styling follows the [Invertix security page](https://www.invertix.ai/security). Its copper texture and four line icons are included in `assets/`. The BMW version uses the dashboard roundel and a cropped local car render. The car render is “2023 BMW i5 M60” by Nazh Design / Sketchfab, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); it is an independent artist model. Font licenses are in `assets/licenses/`.

To regenerate both HTML files after editing source styles or slide structure, run `node pitch/build-motion.mjs` and then `node pitch/build-reference.mjs` from the repository root. The HTML files themselves need no build step.
