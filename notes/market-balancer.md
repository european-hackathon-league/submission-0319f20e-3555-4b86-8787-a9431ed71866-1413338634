# Market balancer

Pod B implements market comparison, conflict proposals and human resolutions in `server/markets.py`.
It reads shared tables directly, without importing the signals, requests, priority or market-data pods.
The original Claude worktree was copied into an isolated continuation branch; its working files remain intact.

## Deterministic decisions and explicit interpretation

`market-balance-v1` counts evidence, ranks current requirements and proposes conflicts. Direction interpretation
uses configured OpenAI by default (`market-directions-v1` prompt), or explicitly selected `direction-terms-v1`
offline regex rules. OpenAI outputs cite exact source text; unknown IDs, fabricated quotes and out-of-scope
attributes fail before proposals are stored. OpenAI configuration failures never fall back to the offline rules.
Customer text goes only through `server/llm.py` to the configured OpenAI provider.

The comparison returns `markets` (weights, coverage and requirement counts) and `topics`, each with a `cells`
map keyed by market. Cells contain evidence count/grade and source IDs, BMW-evidence sentiment, requirement
version/score/rank, acceptance targets, request pressure and a `missing` reason map. Unmeasured requirements,
priorities, sentiment, targets and request pressure are null; actual known counts may be zero. BMW sentiment
excludes imported public web evidence and uses only the most-covered method (ties: lexical method name).
If other sentiment methods exist, the response says which method was selected and that they were not mixed.

Weights use the latest recorded period/method, normalize shares across compared markets, and retain original
sales shares for evidence-gap thresholds. A missing weight in any compared market gives equal weights for
all, with a visible warning. EU may roll up direct DE/GB children when no EU row exists; comparisons including
both a parent and child warn about overlapping customers. Coverage-report warnings flow into the comparison
and detection response, with their source report/run available in the market's `coverage` field.

The global demand index is `sum(normalized market weight × priority/100)`. Missing priorities do not become
zero observations: `demand_coverage` and `unmeasured_markets` accompany the partial index, and the index is
null if no market is measured. Request pressure exposes count, clusters, simulated/flagged counts, triage mean,
statuses and request IDs; untriaged means remain null.

## Rules

All thresholds are exported by `GET /markets/rules` and copied into each conflict's metrics.

| Conflict | Condition | Recommendation |
| --- | --- | --- |
| Priority divergence | Score gap ≥20 points, or top-third versus bottom-half rank (≥3 ranked requirements) | Configurable attribute's lever; otherwise `pm_tradeoff` with demand index |
| Direction conflict | Opposite directions for the same attribute, or a listed cross-topic tension across markets | Configurable attribute's lever; otherwise `pm_tradeoff` |
| Target incompatible | Same normalized metric/unit; numeric relative spread >10% | `global` harmonization if top-third everywhere, otherwise `market_variant` |
| Evidence gap | Market share ≥15%, no analyzed customer evidence, topic top-5 elsewhere | `needs_research` |
| Aligned high priority | At least two measured markets rank the topic in the top third | Comparison's `global` priority recommendation, subject to detected direction/target conflicts |

The attribute table contains rear space, compact exterior, soft ride, firm handling, exhaust sound and cabin
quietness. Tensions are rear space ↔ compact exterior, softer ride ↔ firmer handling, louder exhaust ↔ quietness.
Regex quotes carry exact character spans; preceding negators suppress matches, and overlapping phrases choose
the longest match. Direction severity counts distinct evidence/version/request records, not separate fields of
the same record.

| Configurable attribute | Proposed customer option |
| --- | --- |
| Exhaust sound | `selectable_mode`: selectable sound experience |
| Rear space | `market_variant`: long-wheelbase derivative |
| Ride/handling | `optional_package`: adaptive suspension package |

These are planning hypotheses for PM review; they do not approve an engineering solution. Templated rationales
are authoritative. `POST /markets/conflicts/{id}/brief` separately writes an AI-generated explanation into
`metrics.ai_brief`, with exact evidence quotes, model, prompt version and run ID. It cannot change the
recommendation or decide. Evidence-based briefs must contain a validated citation. Long input text is bounded
to 4,000 characters per OpenAI excerpt; truncation is reported visibly.

## Lifecycle and traceability

Each capability records a run and audit event. Comparison/extraction responses contain `run_id` and
`audit_event_id`; detection also contains `direction_run_id`, individual conflict audit IDs and the
`created`, `unchanged`, `superseded` ID lists. Detection reads a consistent snapshot, performs interpretation
without a database write lock, then rejects HTTP 409 if the inputs changed before persistence.

Conflict identity is a stable hash of vehicle, topics/attributes, markets and type. Unchanged inputs reuse
the existing record, including a resolved or dismissed record, so automated refresh cannot undo a human
resolution. Changed inputs supersede an open conflict; changed inputs after a closed human decision create
a new open proposal and retain that decision. Conflicts that disappear are superseded only within the fully
scanned topic/market scope. The detail route returns complete history and per-market evidence references.

Only humans can resolve; both API checks and SQL triggers reject `ai:*`, `system:*` and registered nonhuman
actors. `defer` leaves the proposal open, `dismiss` closes it as dismissed, and the other decisions resolve it.
Closed/superseded conflicts cannot be resolved again. Resolutions can link in-scope requirements, or for
`market_variants`/`selectable_mode`, create market-scoped proposals through `create_requirement`. Their findings
must match the scope/topic. Creation, resolution and all audit events occur in one transaction. Proposals
remain proposed; requirement approval remains a separate PM gate. Existing requirements should be linked
instead of duplicated; the `(vehicle, market, topic)` uniqueness rule is preserved.

## API, capabilities and MCP

HTTP: `POST /markets/compare`, `POST /markets/directions`, `POST /markets/conflicts/detect`,
`GET /markets/conflicts`, `GET /markets/conflicts/{id}`, `POST /markets/conflicts/{id}/brief`,
`POST /markets/conflicts/{id}/resolve`, `GET /markets/weights`, `GET /markets/rules`.
Lists support limit/offset, scope filters and status/topic filters where applicable.

Capabilities: `markets.compare` (A0), `markets.extract_directions` (A0), `markets.detect_conflicts` (A1),
`markets.draft_conflict_brief` (A1). The minimum detection payload is
`{"vehicle":"G60","markets":["US","CN","EU"],"provider":"deterministic"}`.

MCP tools: `compare_markets`, `extract_market_directions`, `detect_market_conflicts`, `list_market_conflicts`,
`get_market_conflict`, `draft_market_conflict_brief`, `list_market_weights`, `get_market_balance_rules`.
There is no resolution tool: agents propose through the same API and leave human decisions to the PM.

## Verification and limitations

`tests/test_markets.py` uses explicitly simulated CN/US/EU feedback and no network: exact tensions,
recommendations, priority/target/gap thresholds, weights/missing data, request/sentiment/coverage inputs,
OpenAI grounding/cache/failures, stale-input races, human gates, idempotence, supersession, atomic traceable
proposals and MCP routing. `tests/test_markets_schema.py` verifies migration-level resolution guards.

The offline direction rules cover English only. OpenAI receives every scoped text (including Chinese) without
an English regex filter, within an explicit 1,000-text default budget. Inputs beyond that budget fail clearly
and require a narrower scope or a raised budget. Long-text excerpt limits still require evaluation.
Numeric targets with different units are not converted; no cross-unit incompatibility is inferred. Sales
weights and coverage reports must be derived by the market-data pod for representative production views.
An initial synthetic test pass establishes workflow correctness, not live model semantic quality or BMW market
representativeness; those belong to the integrated evaluation.

Verified on the Pod B continuation branch: `uv run --no-sync ruff check .` passed and
`uv run --no-sync pytest -q` passed **638 tests** using the shared project virtualenv.
`COMPOSE_PROJECT_NAME=ehl-markets API_PORT=18011 MCP_PORT=18111 DB_PATH=/app/database/local/ehl-markets.db
 docker compose up -d --build` produced healthy API startup and a running MCP server. A fresh synthetic
three-market HTTP journey produced exactly two directional tensions, reused unchanged conflicts, returned
403 for an AI resolution, and preserved a human resolution on rerun. MCP initialize/discovery found all
eight new tools, and `compare_markets` completed through the live HTTP adapter. Final rebuilt API passed
the same conflict replay. Logs showed no startup/runtime errors. Only this owned stack was stopped with
`docker compose down`; the primary stack was untouched. The synthetic database remains ignored locally.
