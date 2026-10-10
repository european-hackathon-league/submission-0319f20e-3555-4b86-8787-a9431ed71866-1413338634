# MCP evidence workstream

Base inspected: `origin/main` at `18275d7`, 10 October 2026. The starting local
checkout was empty; no staged work, unstaged draft, or MCP topic branch existed.
Troy's foundation and Jakob's parser, analysis, and workflow persistence commits
are included in this base. Read-only backend, MCP/Exa, and database/Docker reviews
confirmed the contracts below before implementation.

## Ownership and implementation plan

- Alex / lead: `mcp_server/` runtime, environment example, documentation.
- Backend test agent: `mcp_server/tests/test_backend_client.py` and
  `mcp_server/tests/test_roundtrip.py`, in `codex/mcp-contract-tests` worktree.
- Exa test agent: `mcp_server/tests/test_exa_client.py` and
  `mcp_server/tests/test_cache.py`, in `codex/mcp-exa-tests` worktree.
- Jakob retains `server/` (the actual backend directory) and API contracts.
- Troy retains `database/`, Compose, and shared deployment configuration.

1. Harden the two existing MCP source reads against the real FastAPI contracts.
2. Add public-only, bounded Exa search and content retrieval via the official API.
   Normalize provenance, deduplicate URLs, cache requests, sanitize errors.
3. Keep results explicitly unreviewed and unpersisted until selected-source
   ingestion preserves the complete provenance envelope through the backend.
4. Verify provider mocks, real MCP/HTTP/temporary SQLite roundtrip, Docker
   configuration, and a live Exa smoke only if a key is configured.
5. Document setup, stable tool contracts, offline demo, and remaining dependencies.
   Fetch and inspect remote changes at integration and before commit/push.

## API-contract checklist for Jakob and Troy

Confirmed at the inspected base: `GET /health`, `GET /sources` with optional
vehicle/market, `GET /sources/{id}`, `POST /sources`. SourceCreate accepts only
title, kind, reference, vehicle, market. Responses add id and created_at. Unknown
input fields are ignored; richer database metadata is omitted from responses.
The source-created event currently attributes every caller to `PM`.

Pending owner agreement (these are proposals, not operational endpoints):

- [ ] Jakob: define an atomic selected-web-source ingestion route and strict
  schema: provider, original/scoped query, result ID, request metadata, title,
  original/canonical URL, nullable publication date, retrieval timestamp,
  supporting excerpt/content, precise hash semantics, vehicle, market,
  applicability/uncertainty, caller identity, selection rationale, idempotency key.
- [ ] Jakob: return durable source/evidence identifiers, duplicate status, and
  a real audit event identifier; expose the saved provenance on source reads.
- [ ] Jakob + Troy: agree URL identity versus content revisions, transactional
  ingestion and audit creation, repeat-request semantics, immutable history.
- [ ] Jakob: expose persisted finding, requirement/version, scoring, challenge,
  review decision, and audit operations before corresponding MCP tools exist.
  Require identified PM review and expected-version checks. New evidence must
  reopen/rescore requirements without erasing earlier decisions over two years.
- [ ] Jakob: carry evidence strength, uncertainty, future assumptions, explicit
  market applicability, conflict links, and explainable priority rationale.
- [ ] Jakob: paginate source reads; reconcile server Docker dependencies before
  activating parser/analysis routes.
- [ ] Troy: agree Exa environment passthrough and a persistent public-response
  cache mount for Compose. Current Compose passes API_BASE_URL only.
- [ ] Troy: run the stack when the Docker daemon is available. The initial
  `docker compose config --quiet` passes; the daemon socket is absent here.

No shared schema or Compose file is changed in this workstream. Review agents
validated existing contracts; pending API extensions still require owner agreement.
Database tables and pure Python parsers alone do not make a complete pipeline.
