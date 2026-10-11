# Prioritization v2 (Pod D, as built)

`customer-priority-v2` keeps the five PM-judged v1 factors and adds three factors **derived from recorded
data**. Every derived value is a `priority_inputs` row whose `derivation` holds the formula, inputs, flags
and source ids. `customer-priority-v1` stays the default for every scope until a human PM switches it.
Code: [`server/prioritization.py`](../server/prioritization.py), scoring hooks in
[`server/requirements.py`](../server/requirements.py), `Weights` in [`server/models.py`](../server/models.py),
migration [`0013_prioritization.sql`](../database/migrations/0013_prioritization.sql), MCP tools in
[`mcp_server/priority_tools.py`](../mcp_server/priority_tools.py), tests in
[`tests/test_prioritization.py`](../tests/test_prioritization.py).

*LLMs interpret and draft, deterministic code counts and scores, humans decide.* OpenAI only writes the
plain-language ranking explanation. It never sets or changes a factor value.

## Rubric and weights

Priority = Σ factor × weight × 20 (factors 0–5, priority 0–100), as in v1.

| Factor | v1 default | v2 default | Source |
| --- | --- | --- | --- |
| customer_impact | 0.35 | 0.25 | PM judgment |
| market_relevance | 0.25 | 0.15 | PM judgment |
| strategic_fit | 0.20 | 0.15 | PM judgment |
| differentiation | 0.10 | 0.07 | PM judgment |
| feasibility | 0.10 | 0.08 | PM judgment |
| market_demand | – | 0.12 | derived, `market-demand-v1` |
| sentiment_momentum | – | 0.08 | derived, `sentiment-momentum-v1` |
| request_pressure | – | 0.10 | derived, `request-pressure-v1` |

`Weights` accepts the three derived keys as optional. Either all three are present (v2) or none are (v1).
Absent keys are left out when serialized, so v1 payloads, stored v1 weights and `scores.weights` are
unchanged. `rubric_of(weights)` and `Weights.rubric_version` tell the rubrics apart by their keys.

## Derived factors (all 0–5; missing input → 2.5 + `not_measured` flag, never 0)

**market_demand**: `5 × Σ_m share_m × p_m / Σ_m share_m` over markets that have requirements for the
vehicle. `p_m` is this topic's base priority ÷ the highest base priority in market `m` (0 when the topic
has no requirement there). Base priority = the PM-judged v1 factors × the default v1 weights × 20, with
no derived factor, so there is no feedback loop. Shares come from the latest `market_weights` period and
method (Pod E). A sub-market whose parent also has a weight is rolled up. Not measured without
`market_weights` (the equal-share index is still recorded as `equal_share_index`, for information only)
or with fewer than two markets.

**sentiment_momentum**: read from `v_sentiment_weekly` for vehicle × market × topic over the 8 Monday
weeks (strftime `%Y-%W`) ending in the `as_of` week (default today, UTC).
- Per source group, one method version is used: the one with the most points. Any others are listed in
  `other_methods` and never mixed in.
- `group = 0.5 × (5 × negative share) + 0.5 × clamp(2.5 − 25 × slope, 0, 5)`. `slope` is the n-weighted
  least-squares slope of weekly mean polarity in polarity per week. Weeks dated only by import are
  excluded, and fewer than 3 dated weeks means no trend, so the trend half is 2.5.
- Groups: BMW evidence (`bmw_evidence`) and public web (`public_monitoring` + `public_imported`, labelled).
  Value = 0.75 × BMW + 0.25 × public. Without public data the BMW value is used alone. With low-n BMW,
  the value is 0.75 × 2.5 + 0.25 × public. Fewer than 5 points in both groups gives 2.5, not measured.
- The slope is computed in **one isolated function**, `server.prioritization.weekly_momentum(points)`
  with points `(week_index, n, mean_polarity)`. At integration it can be swapped for Pod A's
  `server.signals.weekly_momentum` (same formula, as agreed) without changing anything else.

**request_pressure**: counts triaged, in-scope (no `scope_flags`), non-declined `intake_requests` for
the vehicle and topic, using each request's latest `request_triage`. Own-market requests weigh 1 and
other markets 0.5.
- Formula: `0.5 × 5·min(1, weighted requests/5) + 0.2 × 5·min(1, distinct markets/3) + 0.3 × weighted
  mean triage (0–5)`.
- Triage intensity comes from the triage factors × weights when they are readable. Otherwise it is the
  total, read as a 0–5 or 0–100 scale; the basis is recorded.
- With no triaged request anywhere for the vehicle, the factor is not measured (2.5). With none for this
  topic, it is a measured 0.
- Declined, out-of-scope and untriaged requests are listed under `excluded`. Simulated requests are
  flagged.

`priority_inputs` is append-only. An identical latest derivation for the same version (apart from
`as_of`) is reused rather than duplicated. `v_priority_inputs_latest` (0013) gives the latest row per
version and factor.

## Rubric switch (human gate)

`POST /priorities/rubric` with `{vehicle, market, rubric_version, weights?, actor, rationale, as_of?}`:
- Rejects `ai:*` and `system:*` actors in the API (`require_human`) and with the 0009 trigger. 0013 also
  rejects unknown rubric versions and non-object weights.
- Writes `scope_rubrics` (append-only). For v2, it derives inputs for the scope in a recorded
  `priorities.derive_inputs` run.
- Rescores every current version through `score_version`. It opens a review item (the existing
  mechanism) **only for approved requirements whose total changed**, and audits
  `priorities.rubric_switched`.
- Repeating the active rubric and weights returns `changed: false` and writes nothing.

After a switch:
- New versions in the scope are scored with the scope rubric. `score_version` with v2 weights calls
  `ensure_inputs`, which derives inputs in a recorded run when the version has none.
- `POST /requirements/{id}/scores` scores without weights using the scope's weights. It returns 409
  when the submitted weights belong to the other rubric, so one ranking never mixes rubrics silently.
- v2 scores cite their inputs in `explanation.derived_inputs` (priority_input_id, value, measured,
  flags, method_version, run_id) and list `explanation.not_measured`.

## Endpoints (`/priorities`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/rubrics?vehicle&market` | v1/v2 definitions, formulas, default weights; `history` of `scope_rubrics`; `active` for a scope |
| POST | `/rubric` | Human-only switch (above) |
| POST | `/inputs/derive` | Derive the three factors for a scope (`requirement_ids?`, `as_of?`, `rescore=true`). In v2 scopes, rescores changed values and opens reviews for approved requirements whose total changed |
| GET | `/inputs?vehicle&market&requirement_id&version_id&factor&latest_only` | Paginated derived values with derivations |
| GET | `/ranking?vehicle&market` | Rank (competition ranks), total, per-factor value/weight/contribution, derivation per derived factor, evidence grade, `not_measured`, `v2_preview` for v1 scopes (never stored), preserve warnings, stability from the latest sensitivity run (marked stale when scores changed), open review |
| POST | `/sensitivity` | Records `priority_sensitivity`: each weight ±20 % (renormalised), then a 3×3 grid over the two largest scope weights. Per requirement: rank, min/max rank, `stable` = range ≤ 2, best and worst scenario |
| GET | `/sensitivity?vehicle&market` | Paginated analyses |
| GET | `/portfolio?vehicle` | Topic × market matrix of totals and v2 totals (current v2 score or preview), global demand index per topic, `pattern` hint (`global_candidate` when markets holding ≥ 60 % of measured sales give the topic ≥ 0.5 normalised priority; `market_specific_candidate`; `low_priority_everywhere`; `insufficient_data`), open `market_conflicts` per topic |
| POST | `/explain` | Plain-language explanation (`provider: openai` default, or the `deterministic` template). The model sees only recorded facts. Every cited id must be the item's score id, priority_input ids, preserve-attribute ids or sensitivity id; anything else is rejected (502, failed run). Unconfigured OpenAI → 503, no fallback |

Writes return the record plus `run_id` and `audit_event_id`. Lists use `{items, total, limit, offset}`.

**Preserve guard (`preserve-guard-v1`)**: a requirement whose topic, text or targets touch a
`preserve_attributes` row in its scope gets a warning ("Customers love X; confirm this requirement does
not degrade it."). Matching is by same topic, the label, or a `TOPICS` keyword with a left word boundary.
The score never changes.

## Capabilities and MCP tools

Capabilities (all A0), registered at import: `priorities.derive_inputs`, `priorities.rank` (records a
ranking snapshot), `priorities.sensitivity`, `priorities.explain`. The rubric switch is human-only and
not a capability.

MCP tools: `get_priority_rubrics`, `derive_priority_inputs`, `list_priority_inputs`,
`get_priority_ranking`, `run_priority_sensitivity`, `list_priority_sensitivity`,
`get_priority_portfolio`, `explain_priority_ranking`. The rubric switch is not exposed.

## Known limitations

- `market_demand` uses base priorities of current requirement versions and `market_weights`. Pod B's
  `/markets/compare` matrix was not on this branch, so its sentiment and evidence metrics are not used.
- `request_pressure` reads Pod C's tables directly. The triage scale is detected (factors × weights,
  else a 0–5 or 0–100 total) because Pod C's final factor format was not available.
- `sentiment_momentum` uses `%Y-%W` Monday weeks as in `v_sentiment_weekly`, not ISO week numbers. The
  window is still 8 calendar weeks.
- With ≤ 3 requirements in a scope, every item is `stable` by definition (rank range ≤ 2).
- Preserve keyword matching is intentionally broad (e.g. "comfortably" touches *comfort*). It only
  warns.
