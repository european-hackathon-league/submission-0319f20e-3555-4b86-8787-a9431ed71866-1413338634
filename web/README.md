# BMW Product Intelligence

The product planning frontend for the shared FastAPI/MCP/database runtime. It starts at **G60 / US**, preserves the BMW dashboard supplied by the user, and connects sources, findings, requirement versions, scores and human decisions. The vehicle studio adds Alex's licensed G60 i5 and G70 i7 artist models as spatial views of the same requirement register.

## Run

From the repository root, with the existing backend configuration:

```sh
docker compose --profile web up --build -d
```

Open [the workspace](http://127.0.0.1:3003/g60/us). `WEB_PORT` changes the host port. The optional `web` profile does not change the existing API/MCP startup command. Frontend writes reach the same API and database as MCP.

For development:

```sh
cd web
bun install --frozen-lockfile
EHL_API_URL=http://127.0.0.1:8000 bun dev
```

`EHL_API_URL` is a server-only setting. The browser uses `/api/backend/…`; the allowlisted same-origin proxy preserves API errors, stale-write conflicts, multipart uploads and original-file/brief downloads. The frontend never opens SQLite and has no separate copy of workflow business rules. Use Node 24 for production builds; Bun 1.3.9 is pinned for dependencies and tests.

## Implemented screens

| Screen | Behavior |
| --- | --- |
| Overview | Focused evidence-to-decision story: live evidence, finding and requirement counts; one highest-priority proposal with its separate evidence grade; source-link coverage and the G60/US source-concentration disclosure. |
| Requirements | Ranked list and search up front. Filters, saved views, density, exports and creation remain under **Filters and tools**. |
| Requirement detail | Statement, measurable criteria, explicit target basis, assumptions, paged supporting/conflicting evidence, exact sheet/row/page, original downloads, score contributions and unsaved weight simulation. |
| Decisions and versions | PM edits create a new scored version. Approval/rejection/postponement/challenge require rationale and exact version/score IDs. Lead PMs can save reweighted scores. Approved/current comparison, historical snapshots and audit history. |
| Needs review | Persisted reasons, before/after changes, priorities and keyboard navigation (`j`, `k`, `o`/Enter). |
| Evidence | Search, source filter, analysed findings by kind/topic, preserved originals, metadata and reverse links into current requirement versions. |
| Vehicle studio | G60/G70 3D model explorer with named topic anchors, camera presets, priority/evidence/review layers, live scoped requirement roll-ups and links into the existing source-to-decision drawer. A local response hypothesis, notes, illustrative paint preview and JSON export support planning without changing governed records. The supplied schematic appears when WebGL or model loading fails. |
| Sources and imports | Original-file checksums/metadata, XLSX/CSV/PDF upload, server-local inputs and supplied web snapshots. |
| Pipeline | Initial and cumulative update runs, explicit provider selection, persisted stages and failures, live readiness checks, human decision gate, frozen planning briefs and Markdown download. |
| Market comparison | Actual topic/requirement records across US, CN and EU for the selected vehicle; absent evidence is labelled. |
| Audit and settings | Filtered event timeline, event/hash inspection, JSON export, declared actor roles, theme/density and API/MCP links. |

Filters, selected requirement/tab, immutable version/score, selected evidence, and workflow selection use shareable URLs. Stable-key links such as `/g60/us/requirements/REQ-G60-US-003/trace` work. Global search uses ⌘K/Ctrl+K. The register uses a semantic paginated table; paged API reads are collected without silently truncating records. TanStack Query manages server state. Input contracts are generated in `lib/generated-api.ts`; `lib/types.ts` describes additional response shapes from the current API.

The sidebar shows Overview, a collapsible Software group for requirements, evidence and the other PM tools, Multi-agentic system, and Vehicle Studio. Multi-agentic system currently opens an empty page. The reviewer selector sits at the bottom of the sidebar; a reviewer can also be selected within the requirement drawer before recording a decision. See [the three-minute demo guide](DEMO.md).

## Vehicle studio assets and data

Open `/g60/us/twin` or `/g70/us/twin`. The two static model packages in `public/models/` are byte-identical copies of the licensed handoffs in [`assets/vehicles/`](../assets/vehicles/). Their GLBs, manifests, posters, schematics, official-facts files and licence notices stay together. `/draco/` contains the decoder from the same pinned Three.js version as the loader. The 3D bundle loads only when the studio is opened.

The manifest's `zone.topics` maps a visual anchor to live `/requirements` records for the selected vehicle and US market. A requirement opens the existing drawer for located customer evidence, score, versions, decisions and audit history. Empty G70 data remains empty; G60 records and official product facts are never substituted. The model years in the manifests describe reference vehicles, not an evidence filter. Studio scenario choices persist only in this browser and download as a review-only JSON file with linked requirement/version/score IDs. Paint colors are illustrative and do not claim to be BMW orderable options. G60 has exterior geometry only; G70's cabin is simplified. All internal/feature zone positions are planning approximations.

## Reference checkpoint

**`33bc645` — `feature: preserve exact BMW dashboard baseline`** is the unadapted copy of `/Users/troy/Desktop/finance-bmw`, the site at port 3002. All 116 application/asset files were byte-compared with that source before adaptation. Dependencies, generated output, credentials and private local data were excluded. The original finance directories were left unchanged.

Inspect or run the baseline separately without changing the current checkout:

```sh
git worktree add --detach ../ehl-bmw-baseline 33bc645
```

That baseline retains the original financial demo scripts. The adaptation replaces those routes and data access with product-planning operations while retaining the fonts, colors, square geometry, motion field, brand assets and UI primitives. See [DESIGN.md](DESIGN.md).

## Validation

```sh
cd web
bun run typecheck
bun run lint
bun test lib/*.test.ts
bun run build
node scripts/demo-preflight.mjs http://127.0.0.1:3003
# This creates synthetic verification records; use a dedicated local database.
node scripts/verify-integration.mjs http://127.0.0.1:3003
```

The integration verifier calls only the frontend proxy. It imports synthetic evidence into a unique `WEBQA… / US` scope, runs analysis, checks an exact source location, edits/re-scores, rejects stale approval, approves, completes and downloads the frozen brief. It then edits again and verifies that the approved baseline and completed brief remain unchanged. It also checks the audit record. It never decides a G60 requirement.

During implementation, Compose project `ehl-frontend` uses API 18000, MCP 18001, web 3003 and the ignored SQLite backup `database/local/frontend/app.db`. Existing stacks are left running. The browser walkthrough additionally exercised initial/update workflow controls, PM edits and decisions in the synthetic scope, source trace pagination, narrow-screen navigation, filtered deep links, dark mode and downloads. The original G60/US decisions were preserved.

Regenerate API input types against a running API with `bun run generate:api` (defaults to port 18000), or run `bunx openapi-typescript http://127.0.0.1:8000/openapi.json -o lib/generated-api.ts`.

## Current boundaries

- Identity is explicitly declared, as in the existing API; it is not SSO. All writes remain subject to server-side role and version checks.
- The current HTTP API has no audit-chain verification or dedicated export-audit endpoint. The UI shows hash fields and this limitation; it never claims verification or fabricates `access.export` events. Local exports preserve trace/version IDs.
- Reverse evidence links inspect current requirement versions. Historical uses remain available through immutable version traces.
- ReqIF is a basic string-attribute interchange file of approved snapshots; interoperability with a specific enterprise requirements tool has not been certified.
- The broader proposal's draggable dashboard, virtualized enterprise grid, German translation, SSO, webhooks, and embeddable portal remain roadmap work. The supplied BMW reference determines the layout and typography. The studio does not configure validated equipment, create requirement versions from a zone, or save a planning scenario to the governed database.
- No automatic approval, invented trend deltas, fabricated evidence, or silent AI-provider fallback. Empty/error states remain visible when data is unavailable.
