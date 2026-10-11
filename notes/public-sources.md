# Multi-source evidence: BMW files and public data

The pipeline no longer depends on one workbook. Three connectors write through the same import
(original archived by hash, every record located, duplicates skipped, run and audit event recorded),
and their records flow through the same analysis, requirement, scoring and PM review steps.

| Connector | Origin | What it adds | Leaves the system |
| --- | --- | --- | --- |
| BMW files (`POST /market-data/import-bmw`) | BMW internal | Feedback workbooks, customer studies, sales volumes, option-list PDFs for every vehicle × market | Nothing |
| NHTSA (`POST /public-sources/nhtsa/import`) | Public, official | Owner complaints and safety recalls for the vehicle's US models, each with its filing date and ODI or campaign number | Make, model, model year |
| Web research (`POST /public-sources/web-research/import`) | Public, web | Owner forum threads, owner reviews and press road tests per topic, found by OpenAI web search and paraphrased with URL and publication date | Public model name, market name, topic label |

Customer-voice sources (feedback, complaints, recalls, web pages) become findings and requirement
support. Studies and sales feed scoring context (market weights, preserve list, coverage); option lists
describe the product. `GET /public-sources/mix` reports this per source, and
`GET /public-sources/requirements/{id}` breaks one requirement version's linked records down by source.

## Safeguards

- **No BMW data to public services.** NHTSA receives only make/model/year; web research only public names.
- **Grounded web pages.** The model must return pages; a page is kept only when the web search itself
  returned or opened that URL (`include: web_search_call.action.sources`). Others are rejected and listed.
- **Paraphrases, not copies.** Web records are at most two-sentence AI paraphrases labelled
  `ai_paraphrase: true` with model and prompt version; the URL is the source of truth.
- **Incremental.** Re-running a connector imports only unseen ODI numbers, recall campaigns or URLs,
  so a scheduled run can drive the existing cumulative update and PM review flow.
- **Import is not a decision.** Connectors never approve anything; the rubric switch and requirement
  decisions stay human actions.

## Run it

Against a running stack (BMW files read from `DATA_DIR`, `OPENAI_API_KEY`/`OPENAI_MODEL` for web research):

```sh
uv run python scripts/run_multisource_pipeline.py --api-url http://127.0.0.1:8000 --vehicle G60 --market US
```

The script imports all BMW files, derives weights/preserve/coverage, pulls NHTSA and web research, runs
the initial pipeline (or a cumulative update when requirements already exist), scores sentiment and
derives priority inputs, then prints the source mix. In the web app, **Sources & imports → Data
connectors** runs each connector, and the Overview and every requirement's Evidence Trace show the mix.

## Measured on G60 / US (11 October 2026, fresh database, deterministic analysis)

| Source | Origin | Records | Dated | Supports requirements |
| --- | --- | ---: | ---: | ---: |
| G60_feedback_hackathon.xlsx | BMW internal | 4,365 | 0 | 11 |
| NHTSA owner complaints (8 model-years: i5, 530i, 540i, 550e, M5) | Public, official | 50 | 50 | 9 |
| Public web research (6 topics) | Public, web | 24 | 20 | 7 |
| NHTSA safety recalls | Public, official | 9 | 9 | 3 |
| Customer studies, sales volumes, option list | BMW internal | 853 | 0 | scoring/product context |

10 of 11 requirements now cite at least one public record; 1 web page was rejected as not returned by
the search. The full run took 72 s, most of it six parallel web searches. Web search is not deterministic:
an earlier run on another fresh database kept 26 pages (25 dated); answers are cached per database, so a
repeat run in the same database adds only new pages.

## Limits

- NHTSA covers the US only; complaints skew to safety defects, not product preference.
- Sample counts are not market prevalence, for public sources as for BMW feedback.
- Evidence grade stays C on these requirements: the existing rubric needs conflict-free evidence for
  B and fully dated evidence for A, and BMW feedback is undated.
- `market_demand` (rubric v2) stays "not measured" for G60: it needs requirements in at least two
  sales markets (US, EU, CN, ROW), and only G60 / US has them. `sentiment_momentum` uses an 8-week
  window, so most public records (2023–2026) fall outside it and are flagged `low_n`.
- Exa-based Signals watchlists still need `EXA_API_KEY`; the web research connector is independent of it.
