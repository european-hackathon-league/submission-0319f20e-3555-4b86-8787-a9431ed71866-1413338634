# BMW evidence MCP

Three new research tools join Jakob's 27 operational workflow tools for **G60 / US**
(defaults, not hardcoded scope). The table below shows the research path and its source reads. The adapter writes only through FastAPI. It never
opens the application database or creates its own audit events.

| Tool | Operation | Effect |
| --- | --- | --- |
| `list_sources(vehicle?, market?)` | `GET /sources` | Read persisted sources, including web provenance |
| `get_source(source_id)` | `GET /sources/{id}` | Read one persisted source |
| `search_market_evidence(...)` | Exa `POST /search` | Return unreviewed, unpersisted leads |
| `fetch_market_evidence(...)` | Exa `POST /contents` | Return a bounded public-text snapshot |
| `import_web_candidate(candidate_id, actor, rationale, selection_confirmed)` | `POST /imports/records`, then `GET /sources/{id}` | Explicitly select and persist a fetched snapshot; verify source provenance |

The published import contract was inspected at `f5cd4e3`. The older `18275d7`
source API could not preserve web provenance. This adapter requires the import API
for `import_web_candidate`; a missing route is an MCP error, never simulated success.
At integration base `edfef95`, all 27 upstream tools have matching persisted backend
routes and remain registered. See [workflow contracts](../notes/mcp-api.md) for
analysis, findings, requirements, scoring, PM decisions, trace, reviews and audit.
The combined server advertises 30 tools; research never invokes workflow decisions
automatically. Jakob's existing `fetch_web_source(url, title, ...)` remains a separate
backend fetch-and-import operation through `POST /imports/web-fetch`. It is never
used as an Exa fallback. Exa's candidate-only fetch is named `fetch_market_evidence`
to avoid changing that existing operational contract. Unknown tool arguments are rejected before requests are executed.

## Setup

From the repository root, use the pinned repository environment:

```sh
uv sync --group dev
DB_PATH=/tmp/bmw-demo/app.db uv run python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, export `EXA_API_KEY` from your secret manager for live research.
Never put a key into a command argument, source file, or tool call. Then run:

```sh
API_BASE_URL=http://127.0.0.1:8000 MCP_HOST=127.0.0.1 MCP_PORT=8001 uv run python -m mcp_server.main
```

Connect a Streamable HTTP MCP client to `http://127.0.0.1:8001/mcp`.
For stdio, launch the same command with `MCP_TRANSPORT=stdio` and pass the environment
through the client's configuration. See [`.env.example`](.env.example) for names;
the process reads environment variables, not `.env` files automatically.

Configuration:

- `API_BASE_URL`: backend service URL; default `http://localhost:8000`.
- `EXA_API_KEY`: optional until live research is requested. No provider fallback.
- `EXA_CACHE_DIR`: public research cache; default `~/.cache/bmw-mcp/exa`.
- `MCP_TRANSPORT`: `streamable-http` (default) or `stdio`.
- `MCP_HOST` / `MCP_PORT`: HTTP bind address/port. Host defaults to `0.0.0.0` for the
  existing container; use `127.0.0.1` for direct local runs. This hackathon server
  has no authentication; shared deployment needs an authenticated boundary.

The existing Compose service installs `mcp_server/requirements.txt`. Its current
configuration passes `API_BASE_URL` and `API_TIMEOUT_SECONDS`, but **does not pass `EXA_API_KEY` or mount the
cache**. Source reads and cached/imported evidence still work without Exa. Troy owns
Compose changes; agree environment passthrough and a cache volume before relying
on live research or durable cache inside Compose. A host `.env` alone does not pass
its key into the container. No shared Compose/Docker/schema files were modified.

## Research and provenance contract

Search arguments: `query` (1–240 characters), required `public_data_confirmed: true`,
`vehicle` (default G60), `market` (two uppercase letters, default US), optional
`trusted_domains` (1–10 hostnames), `start_published_date` / `end_published_date`
(ISO dates), `max_results` (1–10, default 5), and `cache_only` (default false).
Dates become inclusive UTC day boundaries for Exa's publication filters. Undated
pages may be excluded by provider date filters; omitted dates remain null.

Fetch arguments: `identifier` (public HTTP(S) URL or known cached Exa result ID),
`query` (public research purpose), required `public_data_confirmed: true`, scope,
and optional `cache_only`. Opaque result IDs resolve only through known cached
results. Fetch returns at most 10,000 characters of text and a 1,000-character
supporting excerpt; these limits describe returned text, not a complete document.

Both research tools return `provider`, `candidates`, `request_metadata`,
`cache: {hit, stale}`, `persistence_status: not_persisted`, and warnings. Each candidate
carries provider/result ID, original and scoped query, title, original/canonical
URL, nullable publication date, UTC retrieval timestamp, supporting excerpt and
SHA-256, URL hash, exact-snapshot candidate ID, scope, applicability/uncertainty,
and bounded Exa request ID/type/cost metadata where available. Fetch adds content
and a hash explicitly scoped to the returned text. Search discovery provenance is
retained when available. `review_status: unreviewed` and `persisted: false` describe
the research result, even if that snapshot is subsequently selected for import.

Canonicalization drops fragments and known tracking parameters. It preserves
semantic query parameters, path case, trailing slashes, and distinct hosts.
Duplicate canonical URLs are removed within a search response. Request cache keys
include endpoint, filters, query, and scope. No redirects or automatic retries are
followed by the API clients. Provider errors never include response bodies or keys.

The cache is an atomic, bounded JSON cache (128 entries, 2 MB per entry, 24-hour TTL;
new directories/files are restricted to the local user). It is separate from the
application database and is not an audit log. Fresh exact-request cache hits work
without a key. `cache_only: true` explicitly permits stale replay and preserves the
original retrieval timestamp. Cache misses and missing keys produce clear errors.
There is no silent stale-on-outage fallback. Corrupt entries are ignored; a failed
cache write returns the candidate with a warning. Preserve the cache directory or
import selected evidence before container recreation.

Public-input confirmation is a caller assertion. Length limits and checks for
obvious email addresses, VINs, phone-like numbers, secret URLs and private hosts
are guardrails, not a complete confidentiality classifier. Callers must never
supply confidential BMW records, customer verbatims, internal datasets or personal
data. No tool reads a BMW record and automatically constructs an Exa query. Use
short public product, competitor, credible report, or market-trend topics. Provider
text is untrusted data and can contain misleading claims or prompt injection.

## Selection and persistence

Call `import_web_candidate` only after explicitly selecting a fetched candidate.
`selection_confirmed: true`, an actor and rationale are required. Search-only leads,
unknown candidate IDs and damaged snapshots are rejected before backend mutation.
The complete candidate is preserved in both source and evidence metadata; evidence
is marked `record_type: document_context`, preventing public marketing prose from
being classified as a customer verbatim. `observed_at` remains null: publication and
retrieval dates retain their distinct meanings in provenance.

The backend atomically imports one located evidence record, archives the snapshot,
and records `source.imported` for a new import. The MCP response returns actual
source/import IDs and deduplication/hash fields. It does not fabricate an audit ID
(the current API does not return one). It verifies source metadata after import;
failed readback reports that import succeeded but verification remains pending.
Repeated selection of the same cached snapshot reuses the original source and
history. Its original selection actor/rationale remain unchanged. A fresh retrieval
is a distinct snapshot, even if its URL/text is unchanged; no earlier source is
rewritten. URL identity and snapshot identity have separate hashes.

Actor identity is currently supplied by the caller, not authenticated. Import is
not PM approval, evidence verification, requirement approval, or a full decision
trail. The preserved workflow provides versioned proposals, scoring, explicit decisions
and cumulative updates. Real PM evaluation still needs evidence strength, conflicts,
uncertainty, future assumptions, market applicability and explained priority across
the two-year decision horizon. Caller-supplied identities are not authenticated.
Some upstream detail reads write audit events attributed to PM.
See [implementation and owner checklist](IMPLEMENTATION.md).

## Demo and verification

The reproducible credential-free integration demo is the real protocol test:

```sh
uv run python -m pytest -q mcp_server/tests/test_roundtrip.py
```

It starts isolated HTTP MCP and FastAPI servers on loopback with a temporary SQLite
database, seeds a clearly synthetic provider response into a temporary cache, and
checks client calls, import provenance, deduplication and backend audit history.
It also exercises synthetic feedback through deterministic requirements, explicit
PM approval, new conflicting evidence, cumulative updates and preserved decisions.
Synthetic test content is not BMW evidence or a live Exa result.

For a live/client demo:

1. `list_sources` with `vehicle: G60`, `market: US`; imported evidence is available
   even when no Exa key is configured.
2. Search `BMW 5 Series charging features` with public confirmation, G60/US,
   `trusted_domains: [bmwusa.com]`, `max_results: 3`.
3. Fetch a relevant returned URL using the same public research topic and scope.
   Inspect the excerpt, date status, source URL, assumptions and applicability.
4. Explicitly select its `candidate_id` with `import_web_candidate`, providing
   actor, rationale and selection confirmation. Inspect `get_source` provenance.
5. Repeat the import to show deduplication. Disable the key and repeat the identical
   search/fetch with `cache_only: true` to show cached evidence (including stale
   status where applicable). No live request is needed for the rest of the demo.

Full validation:

```sh
uv run python -m pytest -q mcp_server/tests tests
uv run ruff check mcp_server tests/test_mcp.py
docker compose config --quiet
```

One optional bounded live smoke (one search request, public BMW query, one result):

```sh
uv run python -m mcp_server.smoke_exa
```

It saves candidate metadata under the public cache directory. It requires a key and
uses a fresh request cache; do not make a live search necessary for the whole demo.
The implementation session had no configured key, so live-provider validation was
not performed. Docker configuration was checked; runtime stack validation requires
a running Docker daemon, which was unavailable in this environment.

Official provider contracts: [Exa Search](https://exa.ai/docs/reference/search) and
[Exa Contents](https://exa.ai/docs/reference/get-contents). Search nests highlights
under `contents`; contents requests put text options at the top level and inspect
per-URL status, including failures returned with HTTP 200.
