# ehl-final

BMW — AI for Product Decision Making, EHL Munich, 10–11 October 2026.

## Run the backend

Copy `.env.example` to `.env` before starting. Each teammate can set local host ports in `.env`; keep the container paths and MCP API URL on the Compose network.

```sh
cp .env.example .env
docker compose up --build -d
```

The FastAPI server is at [http://localhost:8000/docs](http://localhost:8000/docs), with a health check at `/health`. The MCP server uses Streamable HTTP at `http://localhost:8001/mcp`. Both interfaces use the same validation, persistence, scoring, and PM decision rules.

The backend implements BMW's PM process: **situation analysis → structure and context → requirement definition → prioritization → documentation and tracking**. It imports original evidence, generates linked findings and requirements, records PM decisions, and proposes reviewed revisions when evidence changes. The backend supplies the PM workspace API; a graphical frontend is a separate component.

Import the real G60/US feedback and run the initial workflow:

```sh
curl -X POST http://localhost:8000/imports/local -H 'Content-Type: application/json' \
  -d '{"path":"BMW-Data/G60_feedback_hackathon.xlsx","kind":"feedback","vehicle":"G60","market":"US"}'
curl -X POST http://localhost:8000/pipeline/run -H 'Content-Type: application/json' \
  -d '{"vehicle":"G60","market":"US","provider":"deterministic"}'
curl 'http://localhost:8000/workspace?vehicle=G60&market=US'
```

`deterministic` is an explicitly labeled reference provider: it requires no credentials and preserves source links, positive attributes, assumptions, and explainable scoring. For AI analysis, set `OPENAI_API_KEY` and `OPENAI_MODEL` in `.env`, recreate the API service, and send `"provider":"openai"`. AI uses bounded Responses requests and validates citations and structured output before persisting them. Missing credentials or invalid output produce an error, with no silent provider fallback. Returned `analyzed_evidence_ids` and warnings disclose coverage; incomplete coverage cannot silently remove evidence from an existing requirement. Batch bounds and client timeouts are configurable in `.env`.

SQLite lives in `database/local/app.db` and persists on the host. Run `docker compose exec api python -m database.snapshot` to save a consistent copy in `database/snapshots/`. See [database/README.md](database/README.md) for restore steps. The BMW input files in `data/` are separate and are never copied into the images.

Stop the services with `docker compose down`.

## Verify the complete backend

```sh
uv sync --locked
uv run pytest -q
uv run ruff check server database mcp_server scripts tests
uv run python scripts/evaluate_pipeline.py
uv run python scripts/verify_backend.py --real-data
```

The live verifier calls the running HTTP API and MCP protocol, using a unique synthetic vehicle scope for PM edits and decisions. It checks original downloads, deduplication, analysis, priorities, approval, stale requests, cumulative updates, unchanged evidence, traceability, and audit history. `--real-data` additionally imports the local G60/US feedback, studies, sales, and equipment PDF, runs their pipeline, and verifies source links while preserving existing approvals. Original inputs remain unchanged; verification records remain in the local database. Omit `--real-data` on a clone without BMW's ignored files. Use `--api-url` and `--mcp-url` for custom host ports.

The evaluation script uses an isolated temporary database and original-file archive. Eight authored update scenarios cover new supporting/conflicting evidence, unrelated themes, duplicate imports, replay with an open review, and market isolation. It reports complete confusion counts for newly raised PM review alerts against two approved baseline requirements, even when predictions are wrong; failed labels or missing source coverage produce a nonzero exit status. Topic/sentiment labels are supplied to the deterministic provider, so this evaluates workflow behavior rather than AI extraction accuracy. The small fixture supplies no statistical confidence estimate or real PM productivity measurement. Live OpenAI verification requires configured credentials.

For local development without Docker, run `uv run uvicorn server.main:app --host 127.0.0.1 --port 8000` and, in another terminal, `API_BASE_URL=http://127.0.0.1:8000 uv run python -m mcp_server.main`. Local processes read environment variables; Compose reads `.env` for its settings.

See [backend API and decisions](server/README.md), [MCP tools](notes/mcp-api.md), [import formats](notes/importer-contract.md), and [analysis providers](notes/analysis-engine.md).

## Implementation

- [High-level implementation plan: components, connections, and workflows](IMPLEMENTATION_PLAN.md)
- [Internal research: papers, existing approaches, and evaluation metrics](research/RESEARCH.md)
- [PM workspace and 3D Requirement Twin: enterprise UI, integration, and north star](notes/pm-workspace-and-3d-twin.md)
- [Product Management Factory: agents do the PM work, humans oversee and decide](notes/pm-factory.md)
- [3D Requirement Twin: model, asset pipeline, stack, and milestones](notes/3d-twin-plan.md)

## Challenge and guidance

- [Challenge, scope, deliverables, and judging criteria](notes/challenge.md)
- [BMW team's complete guidance](notes/bmw-guidance.md)
- [Source URLs, filenames, sizes, and checksums](notes/source-inventory.json)

## Files

| Location | Contents | Git |
| --- | --- | --- |
| `materials/BMW_Hackathon_Briefing_Short.pdf` | Two-page BMW challenge briefing | Included |
| `materials/261010_BMW_Product_Management_Key_Note.pptx` | Four-slide BMW keynote | Included |
| `materials/images/` | All seven images shared by BMW: process, data, requirements, SMART goals, judging criteria, and lifecycle | Included |
| `materials/BMW-Group-Report-2025-en.pdf` | Complete 434-page annual report recommended by BMW | Ignored: 17.8 MB |
| `data/BMW-Data/` | All eight Google Drive input files: three feedback workbooks, customer studies, sales volumes, and three equipment PDFs | Ignored at BMW's request |

The ignored files are downloaded in this workspace. They are not included in a GitHub clone; keep them when backing up or moving the project. All 18 original source files retain their original bytes, verified against the recorded SHA-256 checksums.

Sources: [BMW channel](https://discord.com/channels/1553151744047976549/1553306479019429939), [BMW data folder](https://drive.google.com/drive/folders/1AyPzFu7qoNuCTW0tqlBCJggbmG_MZUem), [annual report](https://www.bmwgroup.com/content/dam/grpw/websites/bmwgroup_com/ir/downloads/en/2026/bericht/BMW-Group-Report-2025-en.pdf).

Snapshot: 10 October 2026. Guidance includes every BMW team post available when the channel was checked through 17:17.
