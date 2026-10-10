# Downloaded data inventory

All eight files in the [BMW-Data Drive folder](https://drive.google.com/drive/folders/1AyPzFu7qoNuCTW0tqlBCJggbmG_MZUem) were downloaded and independently reconciled against a fresh remote listing. Original input data and all derived cell values remain gitignored.

| File | Contents verified |
| --- | --- |
| `F70_feedback_hackathon.xlsx` | `Feedback_Explorer`: 4,076 data rows, 12 columns, 2,128 unique feedback IDs |
| `G60_feedback_hackathon.xlsx` | `Feedback_Explorer`: 5,005 data rows, 12 columns, 4,000 unique feedback IDs |
| `G70_feedback_hackathon.xlsx` | `Feedback_Explorer`: 4,690 data rows, 12 columns, 4,000 unique feedback IDs |
| `F70_G60_G68_G70_customer_studies.xlsx` | `CN_EU_2025`: 84 × 13 cells; `US_2025`: 934 × 5 cells, including headings and blank layout cells |
| `sales_volumes.xlsx` | `F70`, `G60_G68`, `G70`: each 5 × 5 including header |
| `F70_OptionList.PDF` | 23 pages |
| `G60_OptionList.PDF` | 28 pages |
| `G70_OptionList.PDF` | 27 pages |

Total feedback: 13,771 classification rows corresponding to 10,128 distinct vehicle-prefixed IDs. A row is not necessarily an independent customer or response.

## Feedback schema and caveats

Columns: `ID`, `Source`, `Brand`, `Sales Description`, `Country`, `Derivate (e-code)`, `Engine Type`, `Feedback Type`, `Customer Feedback`, `Vfc level2 3 Name`, `Vfc level2 Name`, `Vfc level3 Name`.

- IDs repeat across classification rows with the same verbatim. Preserve all rows and classifications, but count distinct feedback IDs when estimating recurrence. A feedback ID does not establish an individual respondent identity.
- F70 has one labeled source and only ICE feedback. G60/G70 include ICE, `BEVE` (retain the original code), and PHEV. Their feedback is heavily US-weighted, while F70 is concentrated in GB and JP. Market comparisons need denominators and coverage warnings.
- China appears in customer studies and sales, but no CN records occur in the three feedback workbooks. Do not invent Chinese verbatims or treat another country's feedback as Chinese evidence.
- Blank feedback types and `no_class_found` categories exist. Do not silently discard them.
- G70 has 4,000 IDs but 3,993 distinct verbatim texts. Identical text across IDs needs a documented deduplication policy; do not silently merge distinct IDs.
- Source A/B/C/D labels are anonymized. The workbook alone does not establish the provenance, reliability, independence, or sampling method of those sources.
- Feedback has no explicit date column. Do not fabricate a time series or date individual responses.

## Other interpretation issues

- The customer study sheets use different layouts and scales: CN/EU category means versus US percentage distributions. Parse section headings and market/model columns; do not treat them as one flat survey table or compare raw values without normalizing and explaining the scales.
- Sales columns are `market`, `market_code`, `volume_2024`, `volume_2025`, and `volume_2030`. The actual file is by model group and market, despite the generic data-source slide describing powertrain/region data. No powertrain column exists here. The 2030 values are future inputs, not realized sales.
- `sales_volumes.xlsx`, sheet `F70`, cell `C3` contains the formula `=-D3-C10` and a cached value of `0`. `C10` is blank. Preserve both formula and cache and flag this unusual reference for clarification; do not “repair” the supplied source without evidence.
- Option lists preserve tables/layout in their original PDFs. Plain PDF text can scramble table alignment, so cite pages and inspect the original when evaluating equipment availability.

## Documents and images

- Briefing: two image-only PDF pages; preserved as original PDF, rendered page images, and OCR text. Automated text extraction alone found no substantive text, so the rendered pages were read visually.
- Keynote: four slides; original PPTX retained with extracted slide text and speaker notes.
- BMW Group Report 2025: complete 434-page PDF plus searchable text and link index.
- Seven Discord images: original PNG downloads, not only the lower-resolution browser previews. All seven were inspected; they cover the findings-to-car concept, process, dataset descriptions, measurable requirements, SMART criteria, judging criteria, and full automotive lifecycle.
- Entire event guide: HTML snapshot and readable text, reached through the channel reference in the BMW discussion. It contains tool/setup guidance, not an additional BMW briefing deck.

Every primary source has a source URL, local path, byte size, and SHA-256 in `source-inventory.json`. The untouched original files retain workbook formatting and content not represented in the searchable derivatives.
