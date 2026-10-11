# MCP workflow interface

The MCP service exposes the same evidence-to-decision workflow as the HTTP API at
`http://localhost:8001/mcp` using Streamable HTTP. All tools call the API;
validation, scope isolation, persistence, scoring, optimistic concurrency, and
review rules remain in the API. The adapter never accesses SQLite directly.

`API_BASE_URL` defaults to `http://localhost:8000` outside Compose.
`API_TIMEOUT_SECONDS` defaults to 180 seconds per HTTP operation, with connection
timeout capped at 10 seconds. A timed-out write may already have reached the API:
inspect persisted state before retrying. HTTP failures become MCP tool errors
(`isError: true`) and include the HTTP status and API validation/conflict detail.
Unsupported tool arguments are rejected before contacting the API, so a typo in
a scope or an unsupported source subset cannot silently change the requested work.

## Initial workflow

1. `import_local_file`, `import_records`, `import_web_source`, or `fetch_web_source` import evidence.
   Local paths refer to the API's configured input directory, not the AI client's
   filesystem. Web import requires supplied page text, URL, and optional observed
   date; `fetch_web_source` retrieves one explicitly selected public HTML/text URL.
   Each record preserves its original
   location. Records that omit vehicle/market inherit the import's scope.
2. `run_pipeline` analyzes imported evidence, builds requirements, and calculates
   priorities. Use `analyze_evidence` followed by `generate_requirements` to inspect
   findings before generation. Scope defaults to G60 / US. The deterministic
   provider is available without external credentials; `openai` uses credentials
   configured on the API service.
3. `get_workspace` and `list_requirements` show the priority list. Inspect a
   proposal with `get_requirement`, then use `trace_requirement` to reconstruct
   its source → finding → requirement version → score → decision chain.
4. `decide_requirement` records approve/reject/postpone/challenge with the exact
   current `version_id`, current `score_id`, actor, and rationale. A stale version
   or score returns an error. Reload and review the current proposal before
   submitting a new decision.

## Updates and PM edits

After importing new evidence, `assess_updates` reanalyzes **all evidence in the
selected scope**. It deliberately has no source subset parameter: a partial
update must not discard earlier supporting evidence. `list_reviews` and
`list_requirements(needs_review=true)` identify proposals needing attention.
Approved versions remain available while revisions are reviewed.

`edit_requirement` takes `expected_version_id`, actor, and rationale. Omitted
fields remain unchanged; explicit empty lists are sent to the API for normal
validation. Edits create proposals and recalculate priority without implicit
approval. `score_requirement` accepts custom weights plus the same version lock
and optional `expected_score_id` to guard concurrent reweighting. Identical weights
reuse the current recorded score.
`create_requirement` supports manually authored, evidence-linked proposals with
explicit acceptance criteria, assumptions, and factor judgments.

## Reads and pagination

- `health`, `list_sources`, and `get_source` expose availability and source metadata.
- `list_evidence` accepts source, scope, and text filters; `get_evidence` returns an
  individual original record.
- `get_analysis`, `list_findings`, and `get_finding` expose persisted analysis results.
- `get_requirement_versions` and `trace_requirement(version_id=...)` preserve access
  to historical evidence and decisions.
- `list_evidence`, `list_findings`, `list_requirements`, and trace evidence use `limit`/`offset`;
  list results include `items`, `total`, `limit`, and `offset`.
- `list_audit` uses `after`/`limit`; pass the returned `next_after` for the next page.

Adapter contract tests cover every tool, payload/query preservation, encoded IDs,
errors, and a Streamable HTTP initialization/discovery/call/error round trip:

```sh
uv run --frozen pytest tests/test_mcp.py -q
```

## Platform tools

Each platform pod registers its tools from its own `mcp_server/<pod>_tools.py`; every tool calls the
HTTP API, never SQLite. Human-gate operations (watchlist creation and pause, item import and dismiss,
conflict resolution, request decisions and curation, rubric switches, agent pause/resume) are
deliberately absent: they stay with a human PM in the API or web workspace. Exa-backed tools build
queries only from public model, market, topic and competitor names; BMW records never leave the system
except through `server/llm.py` to the configured OpenAI provider.

| Area | Tools | Notes |
| --- | --- | --- |
| Signals | `list_signal_watchlists`, `get_signal_watchlist`, `refresh_signal_watchlist`, `backfill_signal_watchlist`, `list_signal_items`, `get_signal_item`, `score_signal_sentiment`, `list_sentiment_scores`, `get_sentiment_timeseries`, `get_signal_summary`, `summarise_signals` | [signals and sentiment](signals-and-sentiment.md) |
| Market balancer | `compare_markets`, `detect_market_conflicts`, `extract_market_directions`, `list_market_conflicts`, `get_market_conflict`, `draft_market_conflict_brief`, `list_market_weights`, `get_market_balance_rules` | [market balancer](market-balancer.md) |
| Requests | `create_requests`, `list_requests`, `get_request`, `classify_requests`, `cluster_requests`, `list_request_clusters`, `propose_request_evidence`, `triage_requests`, `draft_request_positions`, `get_request_aggregates`, `load_simulated_requests` | [request intake](request-intake.md) |
| Priorities | `get_priority_rubrics`, `derive_priority_inputs`, `list_priority_inputs`, `get_priority_ranking`, `run_priority_sensitivity`, `list_priority_sensitivity`, `get_priority_portfolio`, `explain_priority_ranking` | [prioritization v2](prioritization-v2.md) |
| BMW data | `import_bmw_data`, `derive_sales_weights`, `list_sales_weights`, `derive_preserve_attributes`, `list_preserve_attributes`, `derive_coverage_reports`, `list_coverage_reports`, `extract_report_context`, `list_market_context`, `list_data_scopes` | [BMW data coverage](bmw-data-coverage.md) |
| Agent runtime | `list_agents`, `get_agent`, `list_capabilities`, `create_task`, `list_tasks`, `get_task_board`, `get_task`, `update_task`, `execute_task`, `list_runs`, `get_run`, `create_thread`, `list_threads`, `get_thread`, `post_thread_message` | [agent runtime](agent-runtime.md) |

`score_requirement` accepts the three derived weights (`market_demand`, `sentiment_momentum`,
`request_pressure`) for `customer-priority-v2`; omit them for v1. In a scope a PM switched to v2,
omitting weights scores with the scope's weights.

## Interactive MCP Apps

`get_requirement` and `trace_requirement` now advertise self-contained scoring and
trace resources through `_meta.ui.resourceUri`. Their tool schemas and JSON results
remain unchanged. The widgets use host-mediated MCP calls for all reads and writes.
Save slider changes and review the saved version/score before deciding; stale writes
reload without an automatic retry. Approved snapshots stay visible separately.

For local Python/stdio use, run `npm ci && npm run build` in `mcp_server/ui` first
(Node 22.12+). Compose builds the widgets in the MCP image; use
`docker compose up -d --build` after changing them. See the
[MCP Apps guide](mcp-apps-widgets.md) for contracts, testing and host setup.
