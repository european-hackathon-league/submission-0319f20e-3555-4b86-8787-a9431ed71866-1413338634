# BMW data coverage and market context (Pod E)

Pod E imports every BMW input for every vehicle × market it contains and derives three deterministic,
versioned context layers that Pods B and D read with SQL: sales-based **market weights**, the
**"must not lose"** list of what customers love, and **coverage** (representativeness) reports. It also
extracts cited market context from annual-report pages. Code: [`server/market_data.py`](../server/market_data.py),
schema: [`0014_market_data.sql`](../database/migrations/0014_market_data.sql).

*LLMs interpret and draft, deterministic code counts and scores, humans decide.* Every number here comes
from versioned code; OpenAI only names/summarises preserve attributes and drafts report statements, with
every quote grounded locally in the cited record. Each write is a recorded run with audit events, and
re-running unchanged inputs writes nothing.

## Operations

| Capability (A0) | API | MCP tool | Method |
| --- | --- | --- | --- |
| `market_data.import_bmw` | `POST /market-data/import-bmw` | `import_bmw_data` | `bmw-import-v1` |
| `market_data.derive_weights` | `POST /market-data/weights/derive`, `GET /market-data/weights` | `derive_sales_weights`, `list_sales_weights` | `sales-share-v1` |
| `market_data.derive_preserve` | `POST /market-data/preserve/derive`, `GET /market-data/preserve` | `derive_preserve_attributes`, `list_preserve_attributes` | `preserve-v1` (+ `openai:<model>:preserve-naming-v1` labels) |
| `market_data.coverage` | `POST /market-data/coverage`, `GET /market-data/coverage` | `derive_coverage_reports`, `list_coverage_reports` | `coverage-v1` |
| `market_data.extract_report_context` | `POST /market-data/context/extract`, `GET /market-data/context` | `extract_report_context`, `list_market_context` | `report-pages-v1` or `openai:<model>:report-context-v1` |
| – | `GET /market-data/scopes` | `list_data_scopes` | evidence counts per vehicle × market × record type |

None is a human decision gate, so all are exposed to MCP (actor default `ai:mcp`). Lists follow the
platform conventions (`items`, `total`, `limit`, `offset`, `vehicle`/`market` filters, `status=current`
by default). Writes return `run_id`, `audit_event_id` and `method_version`.

Command line (in-process, same capabilities, counts only):

```bash
DATA_DIR=/path/to/data DB_PATH=database/local/app.db uv run python scripts/import_bmw_data.py --markdown
# --provider openai names preserve attributes through the configured OpenAI provider (fails clearly without a key)
```

## Import (`bmw-import-v1`)

All supported files in `DATA_DIR/BMW-Data` (`.xlsx .pdf .csv .json .txt .md .html`, any case) are parsed
once before any write; one unreadable file fails the run with nothing imported. `server/importers.py`
`file_scopes` lists every scope a file declares and `parse_scopes` returns exactly what `parse_file` would
for each, so the existing locations, metadata and date rules are unchanged.

- Scopes the source declares (feedback `Country` × `Derivate`, study country headings × vehicle columns,
  sales `market_code` × sheet vehicles) are imported as declared. A combined sheet such as `G60_G68` is
  imported under both vehicles.
- Files declaring a vehicle but no market (option-list PDFs) go to each reference market (`US CN EU DE GB
  ROW`) where that vehicle has customer feedback or study evidence in the same import.
- Files declaring neither (e.g. the annual report) go to `document_scopes` (default `G60/US`).
- Each scope is one source through `server.evidence.import_records`: original bytes archived by hash,
  dedup on (content hash, vehicle, market), one audited transaction per scope. Re-running deduplicates
  everything; an interrupted run resumes by re-running.

Feedback rows stay one evidence row per classification; analyses count unique feedback IDs.

## Market roll-up

`sales_volumes.xlsx` reports four non-overlapping regions: `EU` (BMW's Europe sales region), `CN`, `US`,
`ROW`. Feedback names countries; 0014 seeds `DK ES FI FR LV NO SE → EU` and `AU CA JP KR ZA → ROW`
(`DE`, `GB → EU` already come from `database/seed.py`) through `markets.parent_code`. Coverage reports
roll sub-markets up into their region (`rollup`, `sub_market_evidence`) but keep them as separate scopes,
and weights never count a sub-market twice.

## Market weights (`sales-share-v1`)

From `sales_aggregate` evidence per vehicle: `share = units(market, period) / Σ units over the
non-overlapping markets in that period`. A market with a reported ancestor (e.g. `DE` under `EU`) is listed
under `metrics.nested_markets` of its parent and never enters the denominator, so current shares sum to 1
per vehicle and period. Only the most recently imported sales file is used (`older_sales_file_ignored`).
`metrics` records the source cell column and locations, total, partition, and `period_type`: periods after
the year the file was imported are `projection` (warning `projection_periods`; in the BMW file `2030`).
Combined sheets warn `combined_vehicle_sales` (G60/G68 units are reported together). Changed inputs update
the row in place (`revision + 1`, new `run_id`, audit before/after); a market missing from the latest file
is `superseded`. Consumers that only want current rows read `v_market_weights_current`.

## Preserve attributes (`preserve-v1`)

"What customers love", per vehicle × market, with evidence ids and a strength in [0, 1]:

- **Feedback:** explicit source classifications only (`Feedback Type` = Likes/positive). Per topic
  (`analysis_engine.TOPICS`) and per attribute (`Vfc level2 Name`), strength = Wilson 95 % lower bound
  of liked feedback IDs / all feedback IDs on it; kept when ≥ 5 liked IDs and strength ≥ 0.5; at most five
  attributes per topic. Small samples cannot look certain.
- **Studies:** top-2 box (`I Love It` + `Delightful`) ≥ 60 % → strength = that share. Mean-only studies
  state no scale, so the mean's percentile among the scope's own rated topics ≥ 0.75 → strength = percentile.
- Out of scope (price, value for money, cost of ownership, resale, warranty) is never an attribute; the
  excluded study topics are reported per market.
- `provider=openai` (default) names and summarises feedback attributes with 1–3 exact quotes per attribute,
  grounded locally (`ai.citations[].span`); strength and evidence ids stay deterministic. Ungrounded output
  fails the run (HTTP 502) and nothing is written. `deterministic` keeps the source category as label.
- Rows are identified by a fingerprint (vehicle, market, topic, attribute, source type); changes update in
  place with `revision + 1`, attributes that no longer qualify are `retired`.

## Coverage (`coverage-v1`)

One report per vehicle × market (every market with evidence, plus the sales regions and weighted
markets): evidence by record type and by source file (share), unique feedback IDs by provenance and
engine type, dated share, per-topic counts (feedback IDs, strengths/problems/needs, provenances, study
cells), sales weight and region, sub-market roll-up. Warnings (objects with `code`, `severity`, `message`
and the numbers behind them):

| Code | Rule |
| --- | --- |
| `single_source_dominance` (high) | one provenance supplies > 60 % of the scope's feedback IDs |
| `no_evidence` / `no_customer_evidence` | nothing, or only sales/documents; high when the market holds ≥ 15 % of sales (Pod B `evidence_gap`) |
| `aggregate_only` | study aggregates but no individual feedback |
| `small_sample` | fewer than 30 feedback IDs |
| `undated_evidence` | under 50 % of feedback IDs carry an observation date |
| `sub_market_evidence` | countries under this region have their own scopes |
| `no_sales` (low) | the sales file reports zero units; missing evidence there is expected |
| `no_sales_weight`, `unmapped_market` | context gaps |

A new report is written only when its inputs changed; the previous one is `superseded` (reports are
otherwise immutable).

## Annual-report context

`extract_report_context` reads `document_context` pages of a source. The deterministic locator picks
pages by category keywords (regional sales, series deliveries, EV adoption, digital services, Neue
Klasse, R&D) and cites the first matching sentence; OpenAI drafts statements with an exact page quote,
an optional value that must appear in the quote, and a subject market. Statements or quotes about
earnings, margins, prices, costs or business cases are rejected. Rows are append-only and deduplicated.

## Local verification against the real BMW files (2026-10-11)

Fresh database, `scripts/import_bmw_data.py` against the 8 files in `data/BMW-Data`, then run again and
through the Compose API (`ehl-marketdata`, port 18014). Counts only; no verbatims.

- First run: 8 files → 67 vehicle × market sources, 15,858 evidence rows; 48 weight rows (4 vehicles × 4
  regions × 3 periods); 164 preserve attributes (F70 36, G60 60, G68 9, G70 59; deterministic labels);
  49 coverage reports.
- Second run and the Compose `POST /market-data/import-bmw`: 67 of 67 sources deduplicated, 0 new
  evidence, every weight, preserve attribute and coverage report unchanged.
- G60/US: largest provenance supplies 72.7 % of 3,610 feedback IDs → `single_source_dominance` (high).
- G60/CN holds 25.3 % of 2025 sales but has no customer evidence (G68 is the China study vehicle) →
  `no_customer_evidence` (high). F70 sells nothing in CN/US → `no_sales`.
- No BMW feedback row carries an observation date; study cells carry only a reporting year.
- Weight warnings: `combined_vehicle_sales` (G60/G68), `projection_periods` (2030).
- The annual report is not among the local inputs, so report context was verified only with simulated
  pages in the tests.

| Vehicle | Market | Region | Sources | Evidence | Feedback rows | Feedback IDs | Study cells | Sales rows | Document pages | Share 2025 | Preserve | Coverage warnings |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| F70 | AU | ROW | 1 | 30 | 30 | 16 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| F70 | CN | CN | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 0.0% | 0 | no_sales |
| F70 | DK | EU | 1 | 13 | 13 | 8 | 0 | 0 | 0 |  | 2 | single_source_dominance, small_sample, undated_evidence |
| F70 | EU | EU | 3 | 61 | 0 | 0 | 37 | 1 | 23 | 75.2% | 9 | aggregate_only, sub_market_evidence |
| F70 | FI | EU | 1 | 11 | 11 | 8 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| F70 | FR | EU | 1 | 75 | 75 | 53 | 0 | 0 | 0 |  | 2 | single_source_dominance, undated_evidence |
| F70 | GB | EU | 2 | 2813 | 2790 | 1293 | 0 | 0 | 23 |  | 11 | single_source_dominance, undated_evidence |
| F70 | JP | ROW | 1 | 1026 | 1026 | 672 | 0 | 0 | 0 |  | 10 | single_source_dominance, undated_evidence |
| F70 | KR | ROW | 1 | 5 | 5 | 4 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| F70 | ROW | ROW | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 24.8% | 0 | no_customer_evidence, sub_market_evidence |
| F70 | SE | EU | 1 | 121 | 121 | 71 | 0 | 0 | 0 |  | 2 | single_source_dominance, undated_evidence |
| F70 | US | US | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 0.0% | 0 | no_sales |
| F70 | ZA | ROW | 1 | 5 | 5 | 3 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| G60 | AU | ROW | 1 | 7 | 7 | 3 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| G60 | CA | ROW | 1 | 41 | 41 | 18 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| G60 | CN | CN | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 25.3% | 0 | no_customer_evidence |
| G60 | DK | EU | 1 | 49 | 49 | 20 | 0 | 0 | 0 |  | 2 | single_source_dominance, small_sample, undated_evidence |
| G60 | ES | EU | 1 | 1 | 1 | 1 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| G60 | EU | EU | 3 | 66 | 0 | 0 | 37 | 1 | 28 | 38.9% | 9 | aggregate_only, sub_market_evidence |
| G60 | FI | EU | 1 | 14 | 14 | 9 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| G60 | FR | EU | 1 | 14 | 14 | 8 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| G60 | GB | EU | 2 | 117 | 89 | 36 | 0 | 0 | 28 |  | 3 | single_source_dominance, undated_evidence |
| G60 | JP | ROW | 1 | 76 | 76 | 53 | 0 | 0 | 0 |  | 2 | single_source_dominance, undated_evidence |
| G60 | KR | ROW | 1 | 278 | 278 | 205 | 0 | 0 | 0 |  | 6 | single_source_dominance, undated_evidence |
| G60 | LV | EU | 1 | 3 | 3 | 1 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| G60 | NO | EU | 1 | 17 | 17 | 8 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| G60 | ROW | ROW | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 9.5% | 0 | no_customer_evidence, sub_market_evidence |
| G60 | SE | EU | 1 | 51 | 51 | 28 | 0 | 0 | 0 |  | 2 | single_source_dominance, small_sample, undated_evidence |
| G60 | US | US | 4 | 5218 | 4365 | 3610 | 824 | 1 | 28 | 26.4% | 36 | single_source_dominance, undated_evidence |
| G68 | CN | CN | 2 | 38 | 0 | 0 | 37 | 1 | 0 | 25.3% | 9 | aggregate_only |
| G68 | EU | EU | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 38.9% | 0 | no_customer_evidence |
| G68 | ROW | ROW | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 9.5% | 0 | no_customer_evidence |
| G68 | US | US | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 26.4% | 0 | no_customer_evidence |
| G70 | AU | ROW | 1 | 2 | 2 | 2 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| G70 | CA | ROW | 1 | 11 | 11 | 8 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| G70 | CN | CN | 3 | 65 | 0 | 0 | 37 | 1 | 27 | 23.8% | 9 | aggregate_only |
| G70 | DK | EU | 1 | 5 | 5 | 2 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| G70 | ES | EU | 1 | 9 | 9 | 1 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| G70 | EU | EU | 3 | 65 | 0 | 0 | 37 | 1 | 27 | 31.0% | 9 | aggregate_only, sub_market_evidence |
| G70 | FI | EU | 1 | 2 | 2 | 2 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| G70 | FR | EU | 1 | 3 | 3 | 3 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| G70 | GB | EU | 2 | 49 | 22 | 8 | 0 | 0 | 27 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| G70 | JP | ROW | 1 | 56 | 56 | 40 | 0 | 0 | 0 |  | 1 | single_source_dominance, undated_evidence |
| G70 | KR | ROW | 1 | 157 | 157 | 137 | 0 | 0 | 0 |  | 4 | single_source_dominance, undated_evidence |
| G70 | NO | EU | 1 | 1 | 1 | 1 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| G70 | ROW | ROW | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 16.7% | 0 | no_customer_evidence, sub_market_evidence |
| G70 | SE | EU | 1 | 2 | 2 | 2 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |
| G70 | US | US | 4 | 5270 | 4418 | 3792 | 824 | 1 | 27 | 28.6% | 36 | single_source_dominance, undated_evidence |
| G70 | ZA | ROW | 1 | 2 | 2 | 2 | 0 | 0 | 0 |  | 0 | single_source_dominance, small_sample, undated_evidence |

Option-list pages (Document pages) appear under each reference market with customer evidence for that
vehicle (G60: EU, GB, US; G70: CN, EU, GB, US; F70: EU, GB).

## Limitations

- Counts describe the imported samples, not customer prevalence; the coverage warnings say so per scope.
- Sales shares for G60 and G68 are identical because the source reports them combined.
- Option lists are placed by customer-evidence markets, not by an explicit market in the PDF.
- The annual report is not in the local inputs; `extract_report_context` needs it imported first (with
  `document_scopes`).
- `preserve-v1` thresholds (5 liked IDs, Wilson ≥ 0.5, top-2 box ≥ 60 %, mean percentile ≥ 0.75) are
  versioned PM-adjustable assumptions, not BMW-approved targets.
