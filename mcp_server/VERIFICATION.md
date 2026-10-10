# Verification record — 10 October 2026

Integration base: `origin/main` at `edfef95`. The final remote check showed no
new commits before the delivery commit. All upstream workflow tools were retained;
Exa candidate retrieval uses `fetch_market_evidence` to preserve the existing
backend fetch-and-import `fetch_web_source` contract. No unresolved Git conflicts.

| Check | Result |
| --- | --- |
| `uv run python -m pytest -q mcp_server/tests tests` | 452 passed |
| `uv run ruff check mcp_server tests/test_mcp.py` | Passed |
| `docker compose config --quiet` | Passed |
| Real Streamable HTTP MCP client → MCP server → FastAPI → temporary SQLite | Passed |
| Cached fetched Exa candidate → explicit selection → persisted provenance | Passed; exact source/evidence metadata, actor/rationale, original archive, duplicate reuse and one backend import audit |
| Synthetic feedback → deterministic proposals → PM approval → new conflicting evidence → cumulative update | Passed; stale decisions rejected, earlier versions/decisions preserved and chronological audit verified |
| Live Exa search/content | Not run: EXA_API_KEY absent. No provider fallback or live BMW query was sent |
| Docker stack startup, health and logs | Not run: daemon socket unavailable |

Provider tests use HTTP mocks for missing key, authentication/authorization failure,
credit exhaustion, rate limit, outage/timeout, malformed/empty responses, missing
dates, duplicate URLs, required public-input confirmation, private identifiers,
bounded request filters, stale replay, offline reuse, corruption, eviction and
preserved discovery provenance. Failed selection/ingestion never fabricates a
source, requirement, decision, or audit ID. Empty contents cannot be promoted from
search highlights into fetched evidence.

All databases, provider responses, PM identities and feedback used by the tests
are synthetic and isolated. Passing workflow tests does not validate substantive
BMW findings, real Exa extraction, real PM decisions or authenticated attribution.
The adapter preserves unreviewed status. Backend caller identity remains
self-asserted. Troy's Compose Exa environment/cache integration is still pending.

Independent review found and verified fixes for discovery-history loss after cache
eviction, incomplete cached-content integrity checks, eviction of unrelated JSON
files, and empty fetched text being mistaken for usable evidence.
