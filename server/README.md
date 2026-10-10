# BMW product management backend

The scope is customer-facing requirements for a successor vehicle, starting with G60 / US. A vehicle code identifies the predecessor evidence; requirements explicitly plan for a successor in three to five years. Original BMW files remain local and ignored. This is a local, trusted-team application: `actor` records the supplied PM identity, not an authenticated enterprise user.

## PM workflow and API

| BMW PM stage | Operations | Persisted output |
| --- | --- | --- |
| Situation analysis | `POST /imports/files` (multipart); `/imports/local` (path under `DATA_DIR`); `/imports/records`; `/imports/web` (supplied snapshot); `/imports/web-fetch` (one selected public URL) | Source registry, originals, hashes, exact spreadsheet rows/cells, PDF pages or URL offsets, vehicle/market, available observation dates |
| Structure and context | `POST /analyses`; `GET /findings`; `GET /findings/{id}` | Problems, needs, strengths and context with supporting/contrasting evidence IDs, provider and prompt version |
| Requirement definition | `POST /requirements/generate` with `run_id`; or manual `POST /requirements`; `PATCH /requirements/{id}` | Stable requirement identities, immutable versions, customer needs, acceptance criteria, explicit assumptions and evidence links |
| Prioritization | Automatic on creation/edit; `POST /requirements/{id}/scores` | Recorded factors, rubric weights, contributions, priority, evidence grade and limitations |
| Documentation and tracking | `POST /requirements/{id}/decisions`; `GET /requirements/{id}/trace`; `/versions`; `/audit`; `POST /updates` | Approved version and score snapshots, decisions, complete history, and targeted proposed revisions for review |

`POST /pipeline/run` runs analysis, requirement generation and scoring in sequence. `POST /updates` reruns cumulative scoped evidence and assesses existing decisions. Both accept `vehicle`, `market`, `provider`, and `actor`. Initial analysis may optionally select `source_ids`; updates require the complete scope. Use `GET /workspace` for available scopes, priority list, and open review items. `GET /requirements?needs_review=true` supplies the review filter. `GET /metrics` reports traceability, status counts, and elapsed time to first decision with explicit limitations.

The OpenAPI schema at `/docs` defines all request fields. Paginated evidence, findings, requirements, and trace evidence return `items`, `total`, `limit`, and `offset`. `/audit` uses increasing `sequence` and `next_after` cursors. Existing `GET /sources` remains a list for compatibility. Scope inputs normalize common aliases such as USA → US.

Metrics use one database snapshot for the selected scope. Source-link coverage counts current requirement versions with at least one supporting link through an in-scope finding, evidence record and source; it does not measure completeness or semantic correctness. Decision latency counts each decided version once, from creation to its first approve, reject, postpone or challenge action. Undecided versions are excluded, and later revisions are separate samples. This elapsed time includes idle time and is not active PM effort.

## Approval and revision contract

1. Fetch the requirement detail. It includes `current_version`, `approved_version`, their score snapshots, and review items.
2. Edit with `expected_version_id`, an `actor`, a `rationale`, and changed content. An edit creates an immutable version and immediately recalculates its score.
3. A decision sends the exact `version_id` and `score_id`, plus `action` (`approve`, `reject`, `postpone`, `challenge`), `actor`, and `rationale`. Stale versions or scores return HTTP 409. Reweighting optionally checks `expected_score_id` as well as `expected_version_id`; identical weights reuse the existing score.
4. Approval updates the approved pointers and resolves open review items. Proposed edits, changed weights, and new evidence preserve the previously approved version and score until another explicit approval. Rejecting a revision preserves the last approved baseline; postponement retains an open review item; a challenge creates one.
5. A new evidence batch creates revisions only for affected topics. The review includes the full comparison against the last approval, even after several unapproved updates. Explicit PM content edits and added supporting findings remain protected. Repeated imports/analysis are idempotent. Older or incomplete analyses cannot overwrite a newer decision basis.

When the OpenAI model and prompt contract stay the same, unchanged supporting/conflicting evidence and classifications retain the existing wording, targets and score. Model paraphrases, regrouping, or judgment variation alone do not reopen unrelated PM decisions; the analysis audit records why a proposal was retained. New evidence, changed classifications, and changed model/prompt contracts still pass through change assessment.

Actor denials from the database (AI/system decisions, inactive actors, or insufficient PM roles) return HTTP 403 and preserve the prior data and audit history. Version/score concurrency conflicts return HTTP 409.

Every decision, content version, priority calculation, and relevant source/detail access is audited. Original evidence, findings, requirement versions, scores, decisions and audit events are append-only at the SQLite layer. Writes are transactional and foreign keys are enabled. SQLite upgrades preserve the initial source-only database.

## Scoring and uncertainty

The default priority is `20 × (0.35 customer impact + 0.25 market relevance + 0.20 strategic fit + 0.10 differentiation + 0.10 feasibility)`, with each factor on a 0–5 scale. Factors, weights and each contribution are returned; evidence grade remains separate. Grade A requires at least three provenance labels, dated evidence and no conflicting links; B at least two provenance labels and no conflicts; C linked evidence; D no evidence. Provenance labels are recorded source metadata, not proof of statistically independent samples.

Reference-mode factors are transparent heuristics and PM assumptions. Sample record counts do not establish market prevalence. Missing dates remain null. Study aggregates, sales and option lists are context, not customer testimony. Positive feedback is preserved. Numeric acceptance targets must identify supporting target evidence or be labeled `PM assumption`; surveys measuring a value do not automatically justify using that value as a future target. Independent PM review is still needed for semantic support, relevance, feasibility and real acceptance protocols.

## AI and operational behavior

Set `OPENAI_API_KEY` and `OPENAI_MODEL` to use `provider=openai`; no specific model is assumed. Requests use structured Responses output and disable response storage. API requests are bounded by `ANALYSIS_BATCH_SIZE` (default 40; maximum 100), `ANALYSIS_MAX_BATCHES` (default 20; maximum 200), per-batch text budgets and per-record truncation. Returned warnings disclose truncation and omitted records. Increase batch bounds intentionally and set the MCP `API_TIMEOUT_SECONDS` long enough for the selected workload. A timed-out client should inspect current state before retrying a write; the API can still be finishing it. HTTP 503 reports unavailable providers; 422 invalid input/output; 409 stale or incomplete changes.

Selected web fetching retrieves one public HTML/text source, validates redirects and public addresses, and archives the decoded snapshot. Supplied web snapshots are useful for already collected research. PDFs use file import; scanned PDFs require OCR outside this backend. The prototype does not implement an open crawler, engineering requirements, detailed costs, or autonomous PM approval.

Use `uv run pytest -q` for regressions, `uv run python scripts/evaluate_pipeline.py` for labeled synthetic workflow evaluation, and `uv run python scripts/verify_backend.py --real-data` for live HTTP/MCP and real-data verification. The evaluator measures new review alerts across eight updates to two approved themes, includes TP/FP/FN/TN counts, and reports failures before exiting nonzero. Its supplied topic/sentiment metadata and small fixture do not benchmark AI extraction or unseen data. The default provider makes the complete reference workflow reproducible without external credentials; mocked provider tests exercise the real AI contract, while live AI calls require credentials.
