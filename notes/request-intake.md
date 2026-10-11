# Request intake and triage

Pod C turns stakeholder asks into a traceable request inbox. Requests remain stakeholder asks, not customer evidence. LLMs classify and draft; deterministic code clusters, counts and scores; humans curate and decide. No request decision approves a requirement.

## Workflows and API

All endpoints are under `/requests`. A single creation is a request object; a batch is `{requests: [...], actor}`. Request fields are `vehicle`, `market`, `origin_type`, `origin_name`, `title`, `body`, optional `requested_at`, optional `external_ref`, optional PM `effort` (`low|medium|high`), and `simulated` (false by default). Scope starts at G60/US; markets are normalized. Keys `MR-<vehicle>-<market>-NNNN` are assigned atomically. Reusing `external_ref` with the same immutable input returns the existing request; different input returns 409. Batches roll back together on a conflict. Request identity and source text cannot be rewritten.

| Route | Behavior |
| --- | --- |
| `POST /requests` | Receive one or a batch, record the keyword baseline classification and audit. |
| `GET /requests` | Paginated inbox with vehicle, market, topic, status, origin, cluster, simulated, flagged and text filters; sort by triage score, requested date or key. |
| `GET /requests/{id}` | Full classification history, evidence spans, links, triage explanations, decisions, clusters and position messages; records detail access. |
| `PATCH /requests/{id}` | Human edit of topic, attribute, effort, origin, scope flags or cluster, with rationale. Explicit null clears effort, attribute or cluster. PM-pinned interpretations survive later model runs. |
| `POST /requests/classify` | OpenAI structured topic, attribute and scope classification with exact request quotes; `provider: deterministic` selects the keyword baseline. |
| `POST /requests/cluster` | Cluster within vehicle and topic; cross-market recurrence is intentional. |
| `GET /requests/clusters` | Paginated clusters; vehicle, market and topic filters. A market filter selects clusters containing that market and preserves cross-market membership context. |
| `POST /requests/links/propose` | Grounded supporting/conflicting evidence proposals plus existing requirements addressing the ask. |
| `POST /requests/{id}/links` | Human link creation with rationale and optional evidence quote. |
| `PATCH /requests/{id}/links/{link_id}` | Human removal/restoration with rationale. No deletion. |
| `POST /requests/triage` | Versioned deterministic score and explanation. `link_provider` defaults to `none`; linking may be explicitly requested with `openai` or `deterministic`. Custom weights require a human. |
| `POST /requests/positions` | A triaged request's case for, case against and open questions, in a request thread. Defaults to OpenAI; the deterministic template is explicitly labelled “not AI”. |
| `POST /requests/{id}/decide` | Human `convert`, `link`, `decline` or `defer`, with rationale and optional `triage_id` optimistic check. |
| `GET /requests/aggregates` | Counts by market × topic × status × origin, demand, age and untriaged SLA breaches. Optional `as_of` makes time-based outputs reproducible. |
| `POST /requests/fixtures/simulated` | Idempotent load of six synthetic requests, each marked `simulated: true`. |

Classification, linking, triage and positions accept `{vehicle, market?, request_ids?}`; explicit request IDs must match the selected scope. Clustering accepts `{vehicle, topic?, provider}` and deliberately joins across markets. HTTP commands accept `actor`; capabilities receive actor identity from their executor. Human actors are labels in this local prototype, consistent with the existing application; this is not authentication.

## Methods and traceability

`request-classify-v1` scores shared `server.analysis_engine.TOPICS` keywords and a small documented customer-attribute table in `server/intake.py`. Unmatched text is `overall-experience` and flagged as a classification fallback. Pricing, business cases, homologation, engineering specifications and supplier asks receive scope flags and a suggested decline. Flagged requests are excluded from clustering, evidence proposals, position drafting and conversion; triage still records their capped score and the reason. A PM can correct a mistaken flag with an audited edit.

OpenAI classification (`request-classify-openai-v1`) validates that every supplied request is returned exactly once and every quote occurs in its request text. Model output and request/evidence text are untrusted data. All model traffic goes through `server/llm.py` to the configured OpenAI provider. No Exa or other external research provider receives requests or BMW evidence. Missing configuration fails with HTTP 503; invalid output/citations fail with HTTP 502, with no silent switch to the baseline.

Clustering uses connected components of a similarity graph within vehicle + topic. `request-cluster-v1` uses content-token Jaccard ≥ 0.5. OpenAI embeddings use cosine ≥ 0.82 and method `openai:<embedding_model>:request-cluster-openai-v1`. Thresholds are named constants, not learned confidence levels. Existing identities are reused on reruns; PM placements and already clustered converted requests stay fixed. Declined and out-of-scope requests do not contribute to clustering or recurrence. In a connected component, not every pair necessarily meets the threshold.

`request-link-v1` proposes evidence behind the latest customer findings using attribute keywords or overlapping content tokens, with exact quote offsets. Current-state strengths can conflict with change requests. Loud exhaust requests also inspect quietness findings as a named tension. OpenAI linking (`request-link-openai-v1`) selects from bounded same-vehicle candidates and must return valid evidence IDs and verbatim quotes. System/AI proposals preserve method, run, finding, market, quote and span in `request_links.basis`. A removed link stays removed across reruns. Old-topic automatic links are ignored in scoring; explicit PM links remain visible.

Every derived operation records a run, method version, inputs and outputs; model usage, prompt version and request hash are recorded by the shared client. Completed runs provide `audit_event_id`. Failed model runs persist as failed, while all proposed domain writes roll back together. Classifications and triages are append-only. Repeated identical triage inputs reuse their score row; the input hash includes provenance and derivation inputs, so new evidence/weight records create a new explanation even when the numeric total stays unchanged. Identical position drafts reuse the existing thread message.

## Triage rubric: request-triage-v1

Each factor is 0–5. Default weights total 1:

| Factor | Weight | Derivation |
| --- | --- | --- |
| market_weight | 0.20 | `5 × origin market share / largest market share` for the latest period/method; a parent region may supply the share. |
| evidence_support | 0.25 | `5 × (0.75 × min(1, log2(1 + weighted_evidence)/log2(9)) + 0.25 × grade_credit)`. |
| evidence_conflict | 0.10 | `5 × min(1, log2(1 + weighted_conflicting_evidence)/log2(9))`, subtracted as a penalty by contributing `5 − value`. |
| recurrence | 0.20 | `5 × (0.5 × min(1,(cluster_size−1)/4) + 0.5 × min(1,(distinct_markets−1)/2))`. |
| alignment | 0.15 | Best addressing requirement: approved 5; proposed top third 4; other proposed 2.5; postponed 1.5; rejected 0.5; measured absence 0. |
| effort | 0.10 | PM rough estimate: low 5, medium 3, high 1. No financial calculation. |

`total = 20 × Σ(weight × factor_credit)`, so the range is 0–100. Out-of-scope asks are capped at 20. Unknown inputs use 2.5 with an explicit “not measured” flag; a measured absence uses zero. Missing effort is neutral and flagged.

Count unique underlying customer evidence IDs, including when both a finding and its evidence are linked. Related-market evidence weighs 1, other-market evidence 0.5. Context-only records, requirements and conflict records alone do not count as customer support. Grade A requires at least three independent provenances and all records dated; B requires at least two provenances; C means some customer evidence; D means none. Grade credit is A=1, B=.75, C=.4, D=0. Sources, provenances, dates, markets, evidence/link IDs and the grade rubric are all recorded in the factor explanation. Support and conflict grades are separate; conflicting evidence remains an explicit penalty.

Suggested actions prepare the PM: scope flag → decline; an addressing requirement → link; adequate measured support plus score ≥50 → consider conversion; otherwise defer for evidence. These suggestions never change decision state. Request volume is not market prevalence. Aggregate demand uses origin-market sales shares and excludes declined/out-of-scope requests. Missing shares yield a visibly labelled equal-market baseline. Requests older than 14 days without triage are SLA breaches.

## Human gate and conversion

API and database triggers reject AI/system request decisions. Link removal/restoration is also enforced in both layers. Manual curation, PM effort and custom weights require a human at the API. Omitted `triage_id` permits a direct PM decision; supplied IDs must match the current score and its current input hash. A changed input or score returns 409 for a reload/retriage.

Conversion uses `server.requirements.create_requirement` / `new_version` in the same transaction as the request decision. Customer findings must match vehicle, market and topic. The request alone is never evidence. If linking/curation ran, conversion uses active supporting findings; it cannot silently reintroduce removed/conflicting evidence. A PM may explicitly supply reviewed finding IDs. With no prior linking, the latest same-topic customer findings are used and their basis is recorded.

The stable `(vehicle, market, topic)` requirement identity is preserved. An existing requirement gets a new proposed version; an approved version and score remain intact, with an open review item. `request_decisions` freezes the exact requirement version and score IDs, and request keys/origin context appear in version assumptions and audit. The default 80% customer-evaluation target and heuristic factors are clearly labelled PM assumptions for review. Already converted requests cannot be converted twice.

## Capabilities and MCP

Registered capabilities: `requests.classify` (A0), `requests.cluster` (A0), `requests.link_evidence` (A1), `requests.triage` (A0), `requests.draft_position` (A1). A1 outputs signal `awaiting_human` when proposals exist. Agent tasks use these same functions and transactions; no capability decides requests.

MCP tools: `create_requests`, `list_requests`, `get_request`, `classify_requests`, `cluster_requests`, `list_request_clusters`, `propose_request_evidence`, `triage_requests`, `draft_request_positions`, `get_request_aggregates`, `load_simulated_requests`. Decision, curation, effort and custom-weight operations are deliberately absent. The adapter only calls HTTP and does not open SQLite.

## Validation and deployment

`tests/test_intake.py` verifies synthetic fixture idempotence, atomic batches/keys, both cluster methods, pinning, scope exclusions, exact deterministic factors and provenance, deduplicated evidence counts, grounded links, human gates at API/SQL layers, conversion and approved-version preservation, aging/demand, OpenAI classification/link/position grounding failures, visible configuration failures and append-only histories. `tests/test_intake_mcp.py` covers discoverability, all tool routes, actor defaults, identifier encoding and rejection of decision/weight injection. OpenAI is a local fake; tests make no network requests.

The API image must contain `tests/fixtures/simulated_requests.json` at `/app/tests/fixtures/simulated_requests.json`. The isolated Compose test mounts that file read-only because the shared Dockerfile change is integrator-owned. Project `ehl-intake` uses API 18012, MCP 18112 and its own `database/local/ehl-intake.db`; it never touches the default stack.

No live OpenAI quality claim follows from these deterministic/fake-provider tests. Public deployment still needs the application's broader authentication/authorization layer, and embedding similarity should be evaluated on the labelled gold set.

Validation on this Pod C branch: the whole Python suite passes **666 tests** (57 intake/API/MCP cases), Ruff passes, and isolated Compose API/MCP smoke checks pass for fixture reloads, clustering, capped triage, human rejection, position drafts, aggregation and a real Streamable HTTP MCP tool call. API health and service logs were inspected; the `ehl-intake` stack was then stopped. Live OpenAI semantic evaluation remains part of platform integration.
