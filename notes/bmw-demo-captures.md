# Local frozen demo captures

The seven JPEGs in `database/local/demo-captures/` were captured at 1280 × 720 from the isolated `bmw-demo-core` Compose stack on presentation build `77f0376a9847bcdca9d1168a557c41180e16cfa6`. They are local, ignored by Git, and should be handled as BMW source material. `03` displays a workbook-derived feedback record. Do not publish the pack without source-owner review.

| File | Snapshot state | Visible proof | SHA-256 |
| --- | --- | --- | --- |
| `01-overview-predecision.jpg` | pre-decision | G60 / US scope, evidence/requirement counts, concentration caveat | `4902516aed6c31214e82b0412fadeb371a225aba275372b1219abb679be1d0b1` |
| `02-charging-proposal-predecision.jpg` | pre-decision | Proposed customer outcome and no decision | `b0f4fe62b8090001a834d151f688e173f3c47ebabac59b1a0381ba45632f13e9` |
| `02b-assumption-predecision.jpg` | pre-decision | 80% target labelled PM assumption | `50f1a966b36182036eacf143b13ef478b6ba65019f5874f5bbdb036b8fcb0105` |
| `03-charging-source-row-432-predecision.jpg` | pre-decision | Checked workbook, sheet and row locator | `77b06eb6a1031dcb3a6ca0e72212bdf0a4bea18dec56fe973adc7e59dfcd44bc` |
| `04-charging-score-predecision.jpg` | pre-decision | Rubric, recorded factors, separate grade C | `29ec270862f30d3d8d45de41ebc14a456c4e4db34dca3d4e26d28b38a20c66f7` |
| `05-needs-review-automated-rehearsal.jpg` | after simulated update | One open review and exact delta | `a192c714c1a3edbc2d2fd58990a2d8e62db0e5d92b538f7fcfab820c5b6076a7` |
| `06-versions-automated-rehearsal.jpg` | after simulated update | Approved v2 versus proposed v3 and exact delta | `93e26ec2eaa1cb6f4887a12c1031e7d4e60b98981f926ce341afc1876668fc30` |

The pre-decision files use snapshot `app-20261011T033717381575Z-bmw-predecision.db` (SHA-256 `4d2fb748119e8be91c988f451e3aeec59de94be48e5b3e1cc56fa5fa0015de52`). The two rehearsal files use `app-20261011T033741205747Z-bmw-after-update.db` (SHA-256 `9804739c0e59fbec1f32649b95901f3569179df87932e1ba14ca4f74c3c308d3`). Its `PM` actor was declared by automation in a disposable API test. No screenshot proves a human decision, a timed rehearsal or a recorded live run.
