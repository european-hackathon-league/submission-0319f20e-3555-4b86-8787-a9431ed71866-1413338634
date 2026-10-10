# MCP Apps: interactive product evidence review

Owner: Alex. Two widgets implement Troy’s proposal using the official MCP Apps
SDK. See [verification](../mcp_server/VERIFICATION.md) for tested hosts and limits.

## Workflow

The scoring panel opens from `get_requirement`. It shows the requirement key,
statement, acceptance criteria, assumptions, five factors, weights, priority and
approved baseline. Sliders are previews: save factors, save weights if changed,
review the fresh version and score, then explicitly record approve/reject/postpone/
challenge with a human name and rationale. Decisions never save an unsaved preview.

The trace explorer opens from `trace_requirement`. It shows historical versions,
findings, supporting/conflicting evidence, exact text and locations, source
provenance, scores, decisions and audit history. Evidence uses bounded limit/offset
pages and audit uses its after cursor. A decision retains its exact score ID even
when the latest score on that version differs. Trace reads create normal backend
`trace_viewed` audit events.

Widgets call existing MCP tools through the host. The API owns validation,
concurrency, persistence and decision rules; the widgets do not connect directly
to the API or hold credentials. Tool names, arguments and return values are
unchanged. These widgets provide a PM interface; they do not add an autonomous
analysis agent or another LLM provider.

## Brand frame

Both widgets use the PM workspace's visual identity from [web/DESIGN.md](../web/DESIGN.md):
Barlow and IBM Plex Mono (embedded as WOFF2, since the resource CSP allows no font domains),
the workspace colour tokens, square borderless panels, status chips, evidence grades and the
navy airflow header ported from the overview's `MotionField`. The header animation pauses on
request, off screen, when hidden, or when reduced motion is preferred. The host's light/dark
theme is applied, but host style variables no longer replace the brand tokens.

The widgets have two fixed frames and never scroll or zoom:

- **Landscape** reports a height of exactly 9/16 of the frame width (720 × 405 in a 720 px
  chat column). Requirement brief, priority factors and decision share tabs beside an always
  visible sign-off column; the trace explorer shows a step rail beside a drill-down pane.
- **Square** reports a height equal to the width and keeps the brief in view above the controls.

The header toggle switches frames and remembers the choice where storage is available. Below
600 px only the square frame is offered, and below 560 px the body becomes a single column
(sign-off turns into a tab; trace steps become a grid). The SDK's content auto-resize is off:
the shell reports the frame height itself and respects a host `containerDimensions` height cap.
Content that does not fit is divided into pages (`src/shared/fit.ts`) rather than scrolled;
long text and JSON split at word or line boundaries. Ctrl/⌘ zoom, pinch and programmatic
scrolling are blocked inside the frame.

The PM sign-off (name and rationale) applies to every save and decision, so it stays visible
next to the priority and decision panes. After a factor or weight save the panel opens the
decision pane on the freshly read version. Trace findings open into their supporting and
conflicting evidence, then the exact quote, location, dates and source record.

## Resource and tool contracts

| Tool | Resource |
| --- | --- |
| `get_requirement` | `ui://bmw-evidence/scoring-panel.html` |
| `trace_requirement` | `ui://bmw-evidence/trace-explorer.html` |

Tool `_meta.ui.resourceUri` points to a static resource with MIME
`text/html;profile=mcp-app` and `prefersBorder: false`, because the widgets draw their own
edge-to-edge brand header. Both HTML files contain their own JavaScript and CSS;
resource CSP declares no external connection or asset domains. The handlers serve
fixed filenames without environment interpolation. A missing build returns an
explicit build instruction without breaking normal tool discovery or calls.

The official `App` SDK performs the host handshake. Each widget registers its tool
result handler before connecting, supports host themes, and decodes both structured
results and JSON text (the current Python SDK emits bare dict results as text).
Clients without MCP Apps support keep the ordinary text result.

- Factor edits: `expected_version_id`, actor and rationale.
- Weight saves: `expected_version_id` and `expected_score_id`, actor and rationale.
- Decisions: exact `version_id`, `score_id`, action, actor and rationale.
- Stale writes reload for a fresh review; writes are never retried automatically.
- Uncertain transport outcomes block further writes until state is reloaded.
- The actor field is caller-supplied. Database role/kind checks do not authenticate
  the human; production authentication remains a backend owner dependency.

## Build and run

Local Python/stdio runs need Node 22.12 or later:

```sh
cd mcp_server/ui
npm ci
npm test
npm run build
```

For design review without an MCP host, `npx vite --port 18190` serves
`preview/index.html`, which mounts either widget with an invented in-memory fixture and
emulates host widths, frames and themes.

`build.mjs` runs two independent Vite/singlefile builds and verifies that the output
has no external script, stylesheet or shared chunk. `dist/` and `node_modules/`
are ignored. Return to the repository root and start the API and MCP processes as
shown in [the MCP README](../mcp_server/README.md). Connect a compatible MCP host to
`http://127.0.0.1:8001/mcp`, or launch the MCP server with `MCP_TRANSPORT=stdio`.

For Compose, the MCP Dockerfile builds the HTML in a Node stage and copies only
Python runtime files and built HTML into its final image:

```sh
docker compose up -d --build
docker compose ps
docker compose logs --tail=50 api mcp
```

A restart alone does not rebuild widgets. The API has a Compose healthcheck; MCP
readiness is verified by initialization, tools/resource discovery and a resource
read. Its service does not currently define a healthcheck. The MCP-specific Docker
ignore file allowlists build inputs and excludes local keys, databases and caches.
The root API build context still needs its separate credential exclusion follow-up.

## Host acceptance

The [local smoke host](../mcp_server/ui/smoke-host/README.md) exercises both widgets
without a public tunnel. From `mcp_server/ui`, use `npm run smoke:host` against
the isolated synthetic MCP endpoint on port 18001. Host
rendering depends on MCP Apps support; preserve the text fallback in every client.
Host-specific Claude acceptance is separate from local protocol/browser tests.

For claude.ai, use a **separate synthetic-only database and input directory** before
exposing a temporary HTTPS tunnel to the MCP port. The server has no authentication:
using a sample query against the normal database does not isolate other records.
Configure that test endpoint’s `/mcp` URL as a custom connector, ask for a requirement
or trace, explicitly record a synthetic PM decision, and verify it in `list_audit`.
Never expose the BMW input database through this test tunnel.

Verify the chain after a test using `python -m database.cli verify` against that
same test database. The combined Python suite is:

```sh
uv run python -m pytest -q mcp_server/tests tests
uv run ruff check mcp_server tests/test_mcp.py
docker compose config --quiet
```

Implementation references: [official MCP Apps specification](https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/2026-01-26/apps.mdx)
and [official testing guide](https://apps.extensions.modelcontextprotocol.io/api/documents/Testing_MCP_Apps.html).
