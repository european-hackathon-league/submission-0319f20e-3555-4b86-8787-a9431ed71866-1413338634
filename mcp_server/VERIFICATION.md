# Verification record — 10 October 2026

Initial MCP integration base: `origin/main` at `edfef95`. The subsequent database
integration includes Troy's `40068e3`, reviewed from that base. All upstream workflow
tools were retained. The latest integration also includes `703159f` and its actor
denial handling and MCP Apps implementation guide.
Exa candidate retrieval uses `fetch_market_evidence` to preserve the existing
backend fetch-and-import `fetch_web_source` contract. No unresolved Git conflicts.

| Check | Result |
| --- | --- |
| `uv run python -m pytest -q mcp_server/tests tests` | 525 passed after actor-denial integration |
| `uv run ruff check mcp_server tests/test_mcp.py` | Passed |
| `docker compose config --quiet` | Passed |
| Real Streamable HTTP MCP client → MCP server → FastAPI → temporary SQLite | Passed |
| Cached fetched Exa candidate → explicit selection → persisted provenance | Passed; exact source/evidence metadata, actor/rationale, original archive, duplicate reuse and one backend import audit |
| Synthetic feedback → deterministic proposals → PM approval → new conflicting evidence → cumulative update | Passed; stale decisions rejected, earlier versions/decisions preserved and chronological audit verified |
| Live Exa search | Passed: one public BMW query, one result, provider-reported cost $0.007; see below |
| Live Exa `/contents` and live-source import | Not run; search lead remains unreviewed and unpersisted |
| Docker stack startup, health and logs | Not run: daemon socket unavailable |

Provider tests use HTTP mocks for missing key, authentication/authorization failure,
credit exhaustion, rate limit, outage/timeout, malformed/empty responses, missing
dates, duplicate URLs, required public-input confirmation, private identifiers,
bounded request filters, stale replay, offline reuse, corruption, eviction and
preserved discovery provenance. Failed selection/ingestion never fabricates a
source, requirement, decision, or audit ID. Empty contents cannot be promoted from
search highlights into fetched evidence.

All databases, provider responses, PM identities and feedback used by automated tests
are synthetic and isolated. Passing workflow tests does not validate substantive
BMW findings, real Exa extraction, real PM decisions or authenticated attribution.
The adapter preserves unreviewed status. Backend caller identity remains
self-asserted. Troy's Compose Exa environment/cache integration is still pending.

Independent review found and verified fixes for discovery-history loss after cache
eviction, incomplete cached-content integrity checks, eviction of unrelated JSON
files, and empty fetched text being mistaken for usable evidence.

## Database integration review

Reviewed `origin/main` and `origin/codex/database` at `40068e3`: migrations 0003–0007,
declared actor roles and decision gates, requirement keys, audit hash chaining,
read views, snapshot/CLI operations and the opt-in Datasette inspection profile.
The normal merge has no conflicts. Existing MCP source selection, provenance,
deduplication, PM decisions and cumulative-update tests pass against this schema.
No MCP tool or backend HTTP contract was changed by the merge.

Actors supplied by the API are registered as discovered; role/kind gates do not
authenticate the caller. Compose still lacks Exa key/cache passthrough. Its snapshot
inspection service binds to loopback and mounts snapshots read-only. Docker runtime
checks remain unavailable because the daemon is not running; no image build ran.
Troy's existing `.dockerignore` does not exclude local `.env` files, so explicit
credential-file exclusion remains a deployment-owner follow-up before building.
No provider request or external message was made by this integration check.

Independent synthetic reproductions found two database-owner follow-ups outside
current MCP/API paths: direct SQL can clear both approval pointers while leaving
`status=approved`, and integrity verification still succeeds; `database.cli rebuild`
can exit 0 with no imports when required input files are missing. Existing backend
routes do not clear approval pointers or call rebuild. These findings are recorded
in the [owner checklist](IMPLEMENTATION.md); no competing database behavior was
edited in the MCP workstream.

## MCP Apps guide and actor-denial integration

Reviewed `40068e3..703159f`: Troy's `77d9280` adds an
[MCP Apps implementation guide](../notes/mcp-apps-widgets.md) for a scoring/decision
panel and trace explorer in Claude. It contains a plan and examples; executable
widgets, UI resources and a Claude connection test are still outstanding.

Jakob's actor-denial handler returns HTTP 403 only for the three known database
permission denials. Other integrity failures remain server errors. Regression
tests verify rollback, unchanged approved state and audit integrity, and rejection
through MCP. The Exa import client already maps a backend 403 to an access-denied
error; no tool schema or success response changed. The combined 525-test suite,
Ruff and Compose configuration checks pass. No live provider request ran.

## Live search smoke

On 10 October 2026, `mcp_server.smoke_exa` completed one live `/search` request for
`BMW 5 Series charging features`, scoped to G60 / US, restricted to `bmwusa.com`,
with `max_results=1`. Exa reported request ID `9bfad62e4f164e263ffbcfd6e595452a`
and `cost_dollars_total: 0.007`.

The result was [BMW 5 Series Sedan Plug-in hybrid: Overview](https://www.bmwusa.com/vehicles/5-series/sedan/bmw-5-series-sedan-phev-overview.html),
retrieved at `2026-10-10T19:11:47.359243+00:00`, with a supporting excerpt and a
null publication date. Requested G60 / US applicability remains unverified. The
candidate remains a search lead: unreviewed, cached locally and not persisted to
the backend. This verifies live authentication, search and response normalization;
it does not verify live full-text extraction, source selection or substantive claims.
Credentials and raw provider responses are not part of this verification record.
