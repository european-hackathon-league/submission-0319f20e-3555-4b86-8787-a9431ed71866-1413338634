# Source parser contract

`server.importers.parse_file(filename, data, vehicle="G60", market="US")` returns
JSON-serializable source records without writing files or accessing the network.
The API owns original-file preservation, source identities, transactions, and
deduplication. Dependencies: `openpyxl`, `pypdf[crypto]>=6.20,<7`, and `fonttools` for the
original BMW option-list fonts.

Each record has `content`, `location`, `metadata`, `vehicle`, `market`, and
`observed_at`. Country aliases such as USA normalize to US. Explicit scope in a
row, column, sheet, or filename is respected. Valid files containing only other
scopes return an empty list. Empty, unsupported, unreadable, or excessive inputs
raise `ValueError`; scanned PDFs require OCR before import.

- XLSX feedback preserves original columns, feedback ID, provenance, topic,
  subtopic, raw feedback type/sentiment, and engine type. Sheet and row numbers
  are one-based. Repeated feedback IDs retain their distinct classification
  rows; a downstream frequency calculation must count unique feedback IDs.
  Only nonblank text in a feedback/comment/review field is customer testimony;
  row summaries and structured metadata remain context.
- Survey matrices preserve each numerical cell, its topic heading, response,
  units, vehicle column, and country heading as `study_aggregate` records. These
  are aggregate statistics, never individual customer quotations. A "Sample
  total" value of 1 with percentage units is not a respondent count.
- Sales rows are `sales_aggregate` context with original volume-year columns.
  Combined vehicle sheets (for example G60_G68) retain `vehicle_scope` explicitly.
- PDFs produce `document_context` records with one-based page numbers. Document
  market applicability is not inferred from an import request. `scope_basis`
  distinguishes source-declared scope from requested scope.
- CSV records retain logical row plus exact physical start/end lines; quoted
  multiline fields, UTF-8 BOM, UTF-16 BOM, and common delimiters are supported.
- JSON accepts a record object, record array, or `{ "records": [...] }` object.
  Each location includes its JSON Pointer (`""`, `/0`, or `/records/0`), and
  duplicate object keys are rejected to avoid silently discarding evidence.
  TXT/Markdown produce document context. HTML removes scripts/styles and keeps
  readable text, without executing markup or following URLs.

`observed_at` is an explicit ISO observation date/timestamp or null. Raw date
values remain in metadata. A year in a survey sheet is `reporting_year`, with
`date_status: "period_only"`; it never becomes a fabricated observation date.
For normal records `date_status` is `available`, `unparsed`, or `absent`.

Imports bound file size, XLSX decompression and dimensions, total rows/cells,
metadata nesting and serialized metadata size, record count, PDF page count and
stream decompression, and extracted text. Output budgets are enforced as each
record is collected, including survey-cell expansion. File-wide
locations must be combined with the parent source ID and original file hash.

Run the synthetic contract suite from the repository root:

```sh
uv run --with openpyxl --with 'pypdf[crypto]>=6.20,<7' --with fonttools --with pytest python -m pytest -q tests/test_importers.py
```
