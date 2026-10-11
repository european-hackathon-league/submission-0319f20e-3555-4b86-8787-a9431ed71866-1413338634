# Platform evaluation (Pod H)

[`scripts/evaluate_platform.py`](../scripts/evaluate_platform.py) measures the platform capabilities
from [the platform build plan](../PLATFORM_BUILD_PLAN.md) on small labelled synthetic scenarios,
through the public HTTP API only. It runs every scenario once with `provider=deterministic` and once
with `provider=openai`, and reports both, so the pitch can show what the model adds and where the
offline baseline is already enough.

These numbers describe the system on our own synthetic sentences and requests. They are not a
validation on BMW data, real customers or real markets.

## Running it

```bash
docker compose up -d --build api                     # or any running API
uv run python scripts/evaluate_platform.py \
    --base-url http://127.0.0.1:8000 --providers deterministic,openai \
    --json-out platform-eval.json --markdown-out platform-eval.md
```

- `--providers deterministic` runs without any key. `openai` needs `OPENAI_API_KEY` and `OPENAI_MODEL`
  in the API's environment; without them every OpenAI metric is reported `not_available` with the
  API's 503 message. Nothing falls back to the other provider.
- `--strict` exits 1 unless every metric was measured (or is not applicable) and the audit hash chain
  verifies. `--timeout` bounds each HTTP request (default 600 s, for slow model calls).
- Each pass creates fresh synthetic vehicle scopes `EVAL-<token>-<SEN|MKT|REQ|RNK>-<D|O>`. Records are
  labelled `simulated`, stay in the database afterwards (rows are never deleted) and never mix with
  G60/G70/F70 data. Run it against a disposable or demo database, not a PM's working database.
- The evaluator uses the actor `Synthetic evaluator` (a human label). It acts as the PM only on its
  own simulated scopes: it sets factors on the ranking case and switches that scope to rubric v2.
- Setup always uses the deterministic reference pipeline (`POST /pipeline/run` with
  `provider=deterministic`). Only the capability under test changes provider.

Each metric has a status: `measured`, `not_available` (endpoint missing, 404/405, or provider
unavailable, 503), `failed` (any other API error, or a result produced by another method than the
requested provider) or `not_applicable` (deterministic code with no provider, measured once in the
deterministic pass). The Markdown table shows the counts behind each ratio; the JSON report adds per-item
errors, confusion matrices, method versions, the run ids observed and `endpoints`, which lists every
call and whether its contract was verified in merged pod code or assumed from §5.3.

## Gold sets

All under [`tests/fixtures/eval/`](../tests/fixtures/eval/), written by the evaluation pod, every
record `simulated: true`. Gold labels are never sent to the API.

| Fixture | Size | What is labelled |
| --- | --- | --- |
| `sentiment.json` | 40 sentences (36 EN, 4 ZH) | Sentence label `positive`/`negative`/`neutral`/`mixed`; categories plain, negation (7), contrast (7), intensifier, mixed, neutral, zh. Labels: 15 positive, 16 negative, 5 mixed, 4 neutral. A labelling guide is in the file. |
| `market_conflicts.json` | 3 markets × 21 records | CN wants rear space and a quieter cabin, US wants a louder exhaust, EU is balanced. Gold: one direction conflict (exhaust sound vs quietness, CN/US), two priority divergences (comfort CN/US, driving experience CN/EU/US). Connectivity is a control topic that must stay conflict-free. Record counts per topic (6…1) fix the reference ranks without ties. |
| `requests.json` | 30 requests | Gold cluster (13 clusters; 7 requests marked paraphrase), topic, scope flags (pricing ×2, homologation, engineering spec, supplier) and two hard negatives: a package request that mentions "price" and an engineering question about customer relevance. |
| `ranking.json` | 8 requirements | PM-set 0–5 factors. The top three strictly dominate the rest on every factor, so their order holds under any non-negative weights, including ±20 % one-at-a-time perturbation. |

## Metrics

| Metric | What it means | Endpoints (contract) | What it does not show |
| --- | --- | --- | --- |
| Sentiment accuracy, macro-F1 (also per class, per category, confusion) | Share of the 40 sentences whose label matches gold; macro-F1 averages F1 over the labels that occur, so the 5 mixed and 4 neutral sentences count as much as the positives. Scores from a method of the other provider are discarded and counted, never scored. | `POST /signals/sentiment/score`, fallback `GET /signals/sentiment/scores` (assumed, Pod A) | Aspect-level quality or spans; public web text; trend correctness. One sentence moves accuracy by 2.5 points. |
| Conflict precision / recall, markets covered, recommendation agreement, control topic, scenario ranks as designed | A detected conflict matches gold on (type, base topics). Markets covered: the gold markets are inside the detected ones. Recommendation agreement: the recommendation is one of the gold-acceptable options. The control topic must produce no conflict. "Ranks as designed" checks the setup itself, so a miss there is a setup problem, not a detector problem. | `POST /markets/conflicts/detect` (verified, Pod B; `provider` selects the direction extraction, the rules stay deterministic) | That the thresholds are the right product rules, or that a recommendation is a good decision. Three gold conflicts: precision and recall move in thirds. |
| Clustering pairwise precision / recall | Over all pairs of the 30 requests: a pair is positive when both share a cluster. Precision: predicted pairs that are gold pairs. Recall: gold pairs found. Requests left unclustered (flagged out of scope) are singletons. | `POST /requests/classify`, `POST /requests/cluster`, `GET /requests` (verified, Pod C) | Cluster naming or usefulness. Clusters form within one topic and exclude flagged requests, so a classification error also costs pairs. |
| Scope flags exact match, out-of-scope accuracy, per-flag precision/recall | Exact flag set per request; binary in/out of scope; per flag. Missing requests count as wrong. | `POST /requests/classify` (verified, Pod C) | Coverage of all out-of-scope phrasings; only 5 of 30 requests are out of scope. |
| Request topic accuracy | Topic matches gold for the 25 in-scope requests. | `POST /requests/classify` (verified, Pod C) | Attribute quality; the topic taxonomy is coarse. |
| Ranking v1 top-3 exact and stable | After the PM sets the factors, `GET /requirements` returns the gold top 3; the evaluator recomputes the v1 totals from the recorded factors and weights, checks they reproduce the API order, and perturbs each weight ±20 %. Stable: rank range ≤ 2 (Pod D's definition). Deterministic pass only. | `PATCH /requirements/{id}`, `GET /requirements` (verified, core API) | That the factor values are right. The case is designed to be stable. |
| Ranking v2 top-3 exact, repeat identical, identical across providers, Kendall τ vs v1 | Derive v2 inputs, switch the scope to `customer-priority-v2`, read the ranking twice. The OpenAI pass may add explanations but must not change ranks. | `POST /priorities/inputs/derive`, `POST /priorities/rubric`, `GET /priorities/ranking` (assumed, Pod D) | The derived factors' validity: on a synthetic single-market scope most v2 inputs are "not measured" and neutral. |
| Ranking v2 top-3 stable (sensitivity) | Pod D's own sensitivity result marks the gold top 3 `stable`. Deterministic pass only. | `POST /priorities/sensitivity` (assumed, Pod D) | Stability on real, closer-scored portfolios. |
| Single-source dominance flagged | The ranking scope has one simulated source holding 100 % of its evidence; Pod E's coverage report must warn (> 60 % rule). Matched on "dominance"/"single source" in the warning text. Deterministic pass only. | `POST /market-data/coverage` (assumed, Pod E) | Any other representativeness check. |
| Trace coverage | Share of new records observed in this pass that carry their link fields: requirements with an in-scope source link (`GET /metrics`), sentiment scores (run, subject), market conflicts (run, evidence per market, requirements), triage rows (run, request, factors), priority inputs (run, version, derivation). | the endpoints above plus `GET /metrics` | That the linked evidence supports the record; only that the link exists. |
| Runs with outcome audit event, OpenAI calls and tokens | Share of the platform runs this pass produced that have a `run.succeeded`/`run.failed` audit event; model calls and tokens summed from `metrics.llm`. | `GET /runs`, `GET /runs/{id}` (verified, Pod F) | Correctness of the run content. |
| Audit hash chain | The full `GET /audit` log re-verified with `database.integrity.verify_audit_chain`. | `GET /audit` (verified) | Anything about events never written. |

## Pre-integration dry run (not the Phase 3 result)

Before integration, the script ran in-process against Pods B, C and F merged onto the platform base
(temporary database, deterministic provider; Pods A, D and E not yet merged, so their metrics were
`not_available`). It shows the method, not final numbers:

- Conflicts: 3/3 precision and recall, control topic clean, ranks as designed; recommendations
  `selectable_mode` (sound, driving experience) and `market_variant` (rear space).
- Clustering with the Jaccard ≥ 0.5 baseline: precision 1/1, recall 1/34. Token overlap on title plus
  body almost never reaches 0.5, which is the case for the embedding method (`request-cluster-openai-v1`,
  cosine ≥ 0.82) that the OpenAI pass measures.
- Scope flags 29/30 exact: the keyword table flags the hard negative ("worth the price") as pricing.
  Topics 24/25: the heat-pump question is classified `driving-experience` instead of `range`.
- Ranking v1: top 3 exact and stable; local recomputation reproduces the API order.

## Phase 3 results

_Placeholder: paste the Markdown table from the Phase 3 run here (date, API commit, OpenAI model and
the evaluation token)._

| Metric | deterministic | openai |
| --- | --- | --- |
| _pending Phase 3_ | | |

## Limitations

- Small synthetic sets with our own gold labels; one labeller, no agreement study.
- Scenarios exercise the specified rules on designed inputs. Passing shows the rules work as
  specified, not that they are the right product decisions.
- OpenAI results depend on the model and prompt versions recorded in each run's `method_version`;
  cached responses make reruns identical, new prompts or models can change them.
- Requests and conflicts are scored by mapping API records back to fixture ids (request titles,
  evidence `location.fixture_id`); a pod that rewrites titles would show up as missing items.
