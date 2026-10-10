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
