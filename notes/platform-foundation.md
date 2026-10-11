# Platform foundation (Phase 0, as built)

Binding details of the shared substrate that every platform pod builds on, beyond
[§5 of the platform build plan](../PLATFORM_BUILD_PLAN.md#5-shared-contracts). Where this note
and §5 differ, this note describes the code that exists.

## Schema (migration 0009)

[`database/migrations/0009_platform_foundation.sql`](../database/migrations/0009_platform_foundation.sql)
creates every §5.1 table plus `llm_cache` and `v_sentiment_weekly`. Read it before writing SQL.
Additions to §5.1 and the rules its triggers enforce:

| Table | Rule |
| --- | --- |
| all new tables | no `DELETE` (status changes instead); every actor column registers unknown actors as *discovered* (like 0007) and rejects inactive ones |
| `agents` | `id` is `ai:agent:<slug>` or `system:agent:<slug>`; inserting an agent registers its actor (kind `ai`/`system`). Pause/resume/retire must set `status_changed_by` (human) in the same `UPDATE` |
| `tasks` | every `UPDATE` must set `revision = revision + 1`; `id`, `requested_by`, `created_at` fixed |
| `runs` | `status = 'running'` ⇔ `finished_at IS NULL`; immutable once finished; identity and inputs fixed. Write runs only through `server.platform.record_run` |
| `threads` / `messages` | only a thread's `status` changes; messages are append-only and cannot be added to a closed thread |
| `watchlists` | `created_by` human only; status changes must set `status_changed_by` (human) in the same `UPDATE`; `id`, scope, `created_by`, `created_at` fixed |
| `signal_items` | content fixed; one review only: import/dismiss sets `review_status`, `reviewed_by` (human), `reviewed_at` (and `evidence_id` for imports) in one `UPDATE`. `imported` ⇔ `evidence_id` set; `unreviewed` ⇔ `reviewed_by` null |
| `market_conflicts` | only `status` and `metrics` change (supersede instead). At most one `open` row per `fingerprint`. `resolved` needs the latest `market_resolutions.decision` not in (`defer`, `dismiss`); `dismissed` needs it to be `dismiss`; a non-open conflict never changes status; `superseded` may be set by system code |
| `market_resolutions`, `request_decisions`, `scope_rubrics` | human actors only; append-only |
| `intake_requests` | `id`, `key`, scope, `title`, `body`, `requested_at`, `simulated`, `created_by`, `created_at` fixed. `converted`/`declined`/`deferred` need the latest `request_decisions.decision` to be `convert`/`decline`/`defer` |
| `request_links` | only `status` changes (`removed`, audited) |
| `request_triage`, `priority_inputs`, `sentiment_scores`, `llm_cache` | append-only |

Gate triggers raise `this action requires a human actor`, which `server/main.py` maps to HTTP 403
(as it does for `inactive actor`). `v_sentiment_weekly` has the §5.1 columns plus `undated_n`
(points dated by retrieval/import rather than publication/observation) and `subject_ids` (JSON array of
the scored subjects behind the point). Pod A may recreate it in its migration keeping those columns.

Migrations `0010`–`0015` exist on the pod base branch as reserved placeholders so numbering stays
consecutive on every branch; each pod replaces only its own file. Write your SQL before starting a
persistent (Docker) database, or delete that pod-local database after changing your migration:
a database already at version 15 does not rerun an edited file.

## `server/platform.py`

```python
with record_run(None, "markets.detect_conflicts", actor, METHOD_VERSION, inputs,
                vehicle="G60", market=None) as run:
    ...                                   # model calls are fine here: no write lock is held
    with transaction() as connection:     # your rows, referencing run.id
        ...
    run.outputs.update({...})             # finite JSON; stored on success
    run.metrics["records"] = n            # merged with duration_ms and llm usage
```

- `record_run(None, ...)` commits the `running` row and the outcome in their own short transactions,
  so failures stay visible (`status='failed'`, `error`, audit `run.failed`). Never call it with `None`,
  or call the OpenAI client, while holding a write transaction: SQLite would wait on itself. Passing an
  open connection makes the run atomic with that transaction instead (a failure then rolls back too).
- `Capability(name, description, input_model, handler, autonomy_level, writes)`; call
  `register_capability(...)` at module import (duplicates raise). Handler: `(validated_input, actor) -> dict`;
  it owns its transactions and records its runs.
- `run_capability(name, payload, actor, task_id=None)` validates (HTTP 422), returns
  `{capability, actor, task_id, run_ids, awaiting_human, outputs}`; unknown names are HTTP 404. The task
  id flows into `record_run` automatically. A handler signals "proposal waiting for a human gate" with
  `outputs["awaiting_human"] = True`.
- `require_human(actor, connection=None)` raises `HumanActorRequired` (an `HTTPException` 403 that is
  also a `ValueError`) for `ai:`/`system:` actors and, given a connection, for registered non-human or
  inactive actors. Use it in the API; the triggers enforce the same rule underneath.
- `input_hash(payload)` (SHA-256 of canonical JSON), `describe_capability(capability)`,
  `CAPABILITIES`.

## `server/llm.py`

```python
client, method_version = resolve_provider(command.provider, prompt_version=PROMPT_VERSION,
                                          deterministic_method="lexicon-v1")
with record_run(None, "signals.score_sentiment", actor, method_version, inputs) as run:
    if client is None:
        results = lexicon_scores(texts)                       # labelled offline baseline
    else:
        answer = client.structured(task="aspect_sentiment", prompt_version=PROMPT_VERSION,
                                   instructions=INSTRUCTIONS, input={"items": batch},
                                   schema=SentimentBatch, run=run)
        grounded = ground_citations(answer.model_dump()["aspects"], texts, id_key="item_id")
```

- `resolve_provider` returns `(None, deterministic_method)` or `(client, "openai:<model>:<prompt>")`; an
  unconfigured OpenAI raises `ProviderUnavailable` (HTTP 503). Never fall back silently.
- `client.structured(...)` sends one strict Structured Outputs request (`store: false`), validates the
  result against the Pydantic schema and returns the model instance. Invalid JSON/schema raises
  `LLMOutputInvalid` (HTTP 502); `LLMBudgetExceeded` when `OPENAI_MAX_CALLS_PER_RUN` is reached.
  Identical requests are served from `llm_cache` without a call. Usage, latency, model, prompt version
  and input hash accumulate in `run.metrics["llm"]`.
- `client.embed(texts, run=run)` returns vectors in input order (cached per text).
- Strict schemas make every property required (optional fields become nullable) and disallow
  additional properties: model free-form maps as lists of objects. Length limits are re-validated by
  Pydantic after the call, not sent.
- Grounding: ask the model for exact quotes, never offsets. `ground_citations(citations, {id: text},
  id_key=..., quote_key="quote")` adds `span: [start, end]` and raises `LLMOutputInvalid` for an id
  outside the supplied scope or a quote not in that record. `locate_quote(text, quote)` is the primitive.
- Configuration: `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_EMBEDDING_MODEL` (default
  `text-embedding-3-small`), `OPENAI_MAX_CALLS_PER_RUN` (40), `OPENAI_TIMEOUT_SECONDS` (90).

## Tests

- `db` and `client` fixtures as before. `fake_llm` installs an offline `LLMClient` for the test: set
  `fake_llm.responder = lambda request: {...}` to return the parsed schema output
  (`json.loads(request["input"])` recovers dict inputs; `request["text"]["format"]["name"]` is the task),
  optionally `fake_llm.embedder`. `fake_llm.calls("/responses")` lists requests. See
  [`tests/fakes.py`](../tests/fakes.py). No test may use the network.
- [`tests/test_platform_foundation.py`](../tests/test_platform_foundation.py) covers the triggers,
  runs, registry and client.

## API and MCP registration

- Stub routers with fixed prefixes are already included by `server/main.py`: `server/signals.py`
  (`/signals`), `server/markets.py` (`/markets`), `server/intake.py` (`/requests`),
  `server/prioritization.py` (`/priorities`), `server/market_data.py` (`/market-data`) and
  `server/agent_runtime.py` (every router in its `routers` tuple: `/agents`, `/capabilities`, `/tasks`,
  `/runs`, `/threads`). Pods add routes to their router; nobody edits `server/main.py`.
- MCP stubs `register_<pod>_tools(mcp, api_request, identifier)` in `mcp_server/{signals,markets,intake,
  priority,market_data,agent}_tools.py` are called by `mcp_server/main.py`. Use
  `await api_request("GET", "/signals/items", params={...})` and `identifier(value)` for path segments.
  `tests/test_mcp.py` discovers pod tool names automatically.

## Response conventions

So the web pod and the evaluation script can code against the backends before they merge:

- A record is its §5.1 row with JSON columns decoded, plus computed fields.
- Lists are `{"items": [...], "total": n, "limit": l, "offset": o}` with `limit`/`offset` query
  parameters, filterable by `vehicle` and `market`.
- Writes return the record's fields at the top level plus `run_id` (when a run was recorded) and
  `audit_event_id` (`store.audit` returns it).
- Every AI-generated value carries `provider`, `model`/`method_version` and `run_id`, so the UI can label
  it "Generated by AI".
