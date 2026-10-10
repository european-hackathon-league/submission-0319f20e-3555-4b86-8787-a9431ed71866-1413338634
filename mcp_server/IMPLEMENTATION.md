# MCP evidence workstream

## Integration record and ownership

The initial workspace was an empty Git repository: no staged changes, unstaged
MCP draft or local topic branch. It was connected to the requested repository.
Three independent agents reviewed backend contracts, MCP/Exa, and database/Docker
before implementation. Editing agents used separate worktrees and topic branches.

- Initial base `18275d7`: Troy's foundation plus Jakob's parser, analysis and
  persistence modules, but only basic source HTTP routes. Web ingestion was blocked.
- Import milestone `f5cd4e3`: inspected new strict `POST /imports/records` and
  source/evidence reads; safely preserved draft work and rebased. This unblocked
  full Exa provenance ingestion through the backend. `POST /imports/web` alone
  was insufficient because its command does not accept Exa metadata.
- Workflow milestone `71d3266`: incoming edits overlapped `mcp_server/main.py`
  and `mcp_server/requirements.txt`. Integration stopped; the user explicitly
  approved combining both implementations while preserving Jakob's tools.
  The lead preserved all 26 upstream tools, added three research tools through
  `research_tools.py`, and verified every workflow tool has a real backend route.
  Both sides required the identical HTTPX dependency. No competing behavior was
  discarded; research retains its bounded/sanitized backend client for ingestion.

- Final base `edfef95`: inspected additional backend runtime/evaluation changes.
  A new upstream `fetch_web_source` directly fetches AND imports via the backend.
  Preserved it unchanged, named the Exa candidate fetch `fetch_market_evidence`,
  and retained the new `expected_score_id` concurrency guard. The final server
  exposes 30 tools (27 upstream plus 3 research tools), with no registration collision.
  This reconciliation follows the user's existing instruction to combine both versions.

Assigned ownership:

- Alex / lead: `mcp_server/` runtime and documentation; final integration.
- MCP/Exa test agent: `mcp_server/tests/test_exa_client.py`, `test_cache.py`.
- Backend test agent: `mcp_server/tests/test_backend_client.py`, `test_roundtrip.py`.
- Lead owns the one-line `tests/test_mcp.py` advertised-tool assertion update as
  part of the user-approved MCP reconciliation; existing workflow tests remain.
- Jakob retains backend routes and schemas in `server/`; Troy retains database,
  Docker and Compose. No shared API schema, database or deployment file was edited.

During simultaneous preservation, Git's repository-wide stash stack caused the
agents to restore duplicate test copies into the lead checkout. The lead's draft
was recovered from its exact Git object; duplicates were preserved separately.
Subsequent preservation used commits/explicit identities. No work was lost.

## Implementation and API checklist

- [x] Inspect repository state, latest pushes, real routes and ownership.
- [x] Retain working API-backed source tools and all incoming workflow tools.
- [x] Add public-only bounded Exa search/fetch, exact provenance, URL deduplication,
  local caching, explicit cache-only replay, safe errors and no provider fallback.
- [x] Add explicit selection through `POST /imports/records`, full provenance in
  source AND record metadata, `document_context` classification, source readback,
  durable source/import IDs, and backend-owned deduplication/history.
- [x] Preserve all existing findings/requirements/scoring/review/audit tools only
  after confirming their real routes. Research never approves a claim or decision.
- [x] Keep publication date, retrieval time and observed_at distinct. Label scope
  applicability and uncertainties honestly; exact snapshots never overwrite history.
- [x] Test provider failures/cache safeguards and real MCP→HTTP→temporary SQLite
  reads/imports, including actor/rationale, metadata, duplicates and actual history.
- [x] Document environment, contracts, credential-free demo and limits.

Remaining owner dependencies / limitations:

- [ ] Jakob: actor identities are self-asserted, and several detail-read audits
  still use `PM`; production attribution/authentication remains incomplete.
- [ ] Jakob + Alex: source imports return source/import IDs, but not evidence IDs
  or an audit event ID. These must be obtained through existing evidence/audit
  reads; the research tool does not invent them.
- [ ] Jakob: source listing is unpaginated; add bounded pagination.
- [x] Preserve upstream `expected_score_id` in the scoring tool and test version/score locks.
- [ ] Troy: agree Exa environment passthrough and a persistent public-cache mount
  for Compose; current MCP service passes API_BASE_URL and API_TIMEOUT_SECONDS.
- [ ] Troy: run Compose with health/log/persistence checks once its Docker daemon
  is available. `docker compose config --quiet` passes; the daemon is absent here.
- [ ] Alex: run one live Exa smoke when EXA_API_KEY is configured; no key was present.
- [ ] Team: validate actual BMW evidence, conflicts, uncertainty, future assumptions,
  market applicability and explained priorities through real PM review. Existing
  deterministic workflow tests are not proof of substantive research quality or
  production readiness across the two-year decision lifecycle.

Read-only reviews established the published contracts. No private BMW input was
sent to Exa, and the adapter never writes directly to Troy's database.
