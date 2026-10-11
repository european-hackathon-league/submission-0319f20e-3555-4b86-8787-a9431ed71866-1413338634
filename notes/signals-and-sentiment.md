# Public signals and sentiment

Signals are scoped to a predecessor vehicle, market and the existing `TOPICS` taxonomy. A human
PM creates a watchlist with a rationale. That record authorises repeated public searches; it does
not authorise a source import or a product decision. Creation, editing, pause/resume, importing and
dismissal reject automated actors in the API and database. This prototype records caller identity;
it does not authenticate enterprise identities.

Monitoring uses publicly indexed pages through Exa, **not a social firehose**. `DOMAIN_GROUPS` in
`server/signals.py` has press, forum, social and video defaults for US, EU, CN, DE and UK; the `all`
group is the union of a market's groups (at most 10 hostnames, Exa's limit), so a default watchlist
never searches the open web. Explicit public hostnames override the defaults. Vehicle templates cover G60, G70, F70 and F40. New scope
names need an explicit public template; arbitrary scope text never enters an Exa query.

Queries consist of fixed public model/market/topic names plus short PM-authorised public terms and
competitor names. Each term is limited to 60 characters and checked for personal identifiers,
secrets and imported evidence substrings in the same scope. This check repeats at execution time,
so newly imported private text can revoke a formerly valid query. Fixed taxonomy labels do not come
from customer records. The standing authorisation is not a general permission to paste private
text into search. BMW evidence is interpreted only by the configured OpenAI provider in
`server/llm.py`; nothing from the evidence table is sent to Exa.

A refresh searches the last `cadence_days` (1–90). Backfill accepts 1–12 disjoint seven-day
publication windows, newest first; there is exactly one search per window and at most 12 calls.
Exa's existing cache and errors are reused, including `cache_only` replay. A failed search batch
persists a failed run and no partial new items. Pausing or changing the watchlist during the
network request cancels persistence of the stale results. Completed discoveries have bounded
1,000-character excerpts, URL/content hashes, search provenance and the exact run/window. Identical
watchlist/URL/excerpt triples are idempotent; an edited page can produce a new item. Missing dates
are explicitly based on retrieval, never invented publication dates.

Signal items are not evidence. A human import fetches the chosen URL and invokes the existing
`mcp_server.ingestion.import_candidate` contract unchanged, through the same in-process backend as
`POST /research/exa/import` (`server.exa_research.LocalBackend`), so `server/evidence.py` is not
modified. That import is its own transaction and deduplicates by content hash. The signal review
(status, reviewer, evidence id and audit event) commits in a second transaction after re-checking
that the item is still unreviewed. If the review step fails, the run is recorded as failed and the
item stays unreviewed; the imported snapshot is a normal human-selected web source. A retry
reuses that source (`deduplicated: true` in the run output and audit metadata) and links it, so a
failure never produces a reviewed item without evidence or a duplicate source. The complete fetched candidate
lives in evidence metadata, and the original search lead remains on the signal item. An import or
dismissal is final; subsequent requests return 409. Imported web evidence remains unreviewed source
material and does not approve requirements.

## Sentiment and interpretation

`POST /signals/sentiment/score` defaults to `provider="openai"`; `provider="deterministic"` is the
explicit offline baseline. Missing OpenAI configuration returns 503 and records a failed run.
There is no fallback. Every score records its subject, input hash, run, method, aspects and provider
metadata. The OpenAI method is `openai:<configured-model>:aspect-sentiment-v1`. The shared client
records prompt version, usage, cache hits and latency in the run. Batches contain at most 25 texts.
Every returned ID must belong to its input batch and occur once. A non-neutral interpretation
requires an aspect quote; each quote is locally grounded to the supplied text. Any missing,
duplicated, foreign or ungrounded result fails the entire scoring batch with HTTP 502 and no
persisted scores. Public relevance flags exclude off-topic results from aggregation.

`lexicon-v1` has an English automotive lexicon plus a small Chinese lexicon, negation windows,
intensifiers, sentence splitting and contrast/concession weights. Its fingerprint is pinned in
tests; lexicon changes require a new version. The topic vocabulary remains `TOPICS`; finer
attributes are in `server.sentiment.ATTRIBUTES`. Both methods inspect the first 4,000 characters and
record truncation. Aspect spans index the stored subject text. One score per subject/method is
append-only; reruns return the stored result. Evidence gets its strongest topic; signal items use
their watchlist topic. `subject_type`, `subject_ids` and optional topic filter restrict scope;
foreign or dismissed IDs are rejected. At most 1,000 pending subjects are processed per call;
`remaining` tells callers to repeat until complete. A `topic` filter selects the primary resulting
topic; it does not rewrite an existing score.

The deterministic baseline is not a validated population sentiment estimator. It cannot reliably
resolve sarcasm, indirect comparisons or all languages. Counts are records, not unique customers,
and public search coverage is selective. AI interpretation is also provisional and reviewable.

## Weekly statistics and priorities contract

`v_sentiment_weekly` and `GET /signals/sentiment/timeseries` group independently by vehicle, market,
topic, source class and method version. Source classes are `bmw_evidence`, `public_monitoring` and
`public_imported`; callers must never add them or combine models into one curve. Dismissed and
explicitly irrelevant monitoring items are excluded. Each point contains `n`, `mean_polarity`,
negative/positive/mixed shares, `low_n` (n < 5), `subject_ids`, `undated_n`, `week_start` (Monday),
legacy `week` and ISO `iso_week`. New Year does not split a single Monday-aligned week. Public
imports retain the existing ingestion contract's missing observed-date flag even when the
candidate metadata contains a publication date.

`GET /signals/summary` returns one row per independent series. Overall mean and negative/positive
shares are weighted by record count over available history. `momentum` is the n-weighted
least-squares slope of weekly mean polarity (polarity units per week) in the last eight ISO weeks
ending at that series' latest observed week (no wall clock, so results are reproducible).
`momentum_weeks`, `window_start`, `recent_n`, `recent_low_n`, `recent_mean_polarity` and
`recent_negative_share` describe the same window, so a consumer can weigh the current level and the
trend without recomputing it. Missing weeks are not interpolated. Fewer than two dated points
returns `null`; it is not a zero-trend claim. `last_week` lets consumers identify stale history.
All aggregation uses `sentiment-summary-v1` and retains sample IDs.

The stable Python contract for prioritization is:

```python
from server.signals import summary_rows, weekly_momentum
rows = summary_rows("G60", "US", topic="comfort", source_class="bmw_evidence",
                    method_version="lexicon-v1")
slope = weekly_momentum(points)  # one series' points: n, mean_polarity, week_start or iso_week
                                 # ('2026-W01'); float | None
```

`POST /signals/summary` / `signals.summarise` records a run, reuses these deterministic metrics and
optionally drafts OpenAI observations citing exact subject text. Deterministic mode returns metrics
without invented prose. All claims carry provider, model, method and run metadata. These are
observations for a PM, never automatic decisions.

## HTTP and MCP surface

HTTP: `POST/GET /signals/watchlists`, `GET/PATCH /signals/watchlists/{id}`,
`POST /signals/watchlists/{id}/refresh|backfill`, `GET /signals/items`,
`GET /signals/items/{id}`, `POST /signals/items/{id}/import|dismiss`,
`POST /signals/sentiment/score`, `GET /signals/sentiment/scores`,
`GET /signals/sentiment/timeseries`, `GET/POST /signals/summary`.
Lists return `{items,total,limit,offset}` and accept vehicle/market filters. Writes return
`audit_event_id`, plus `run_id` for capability executions. Refresh returns `created`, `existing`,
`item_ids` and warnings. Score returns per-subject `items`, `created`, `reused` and `remaining`.

MCP tools: `list_signal_watchlists`, `get_signal_watchlist`, `refresh_signal_watchlist`,
`backfill_signal_watchlist`, `list_signal_items`, `get_signal_item`, `score_signal_sentiment`,
`list_sentiment_scores`, `get_sentiment_timeseries`, `get_signal_summary`, `summarise_signals`.
Human gate writes are intentionally absent. Exa-related descriptions repeat the data boundary.
Registered capabilities are `signals.refresh_watchlist`, `signals.backfill_watchlist`,
`signals.score_sentiment`, `signals.summarise` (all A0). Capability execution overrides any supplied
actor with the runtime's executing actor.

## Verification

All fixtures are simulated. Tests use real API routes, SQLite migrations/audit verification,
Exa with `httpx.MockTransport`, and the injected fake OpenAI client. Cases include privacy checks,
human gates, idempotent refresh/import/scoring, failed-review retry without duplicate sources, stale-authorisation races, bounded
weekly calls, grounded/invalid AI output, source/method separation, New Year alignment, n-weighted
momentum, truncation, pagination and adapter contracts. No tests use network services.

The pod uses isolated Compose project `ehl-signals`, API port 18010, MCP port 18110 and database
`/app/database/local/ehl-signals.db`. Original BMW files and local database/cache outputs stay
ignored. Live Exa/OpenAI quality is separately verified with configured credentials by integration;
no offline result establishes live semantic quality.
