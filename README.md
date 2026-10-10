# ehl-final

BMW — AI for Product Decision Making, EHL Munich, 10–11 October 2026.

## Run the backend

Copy `.env.example` to `.env` before starting. Each teammate can set local host ports in `.env`; keep the container paths and MCP API URL on the Compose network.

```sh
cp .env.example .env
docker compose up --build -d
```

The FastAPI server is at [http://localhost:8000/docs](http://localhost:8000/docs), with a health check at `/health`. The MCP server uses Streamable HTTP at `http://localhost:8001/mcp` and exposes `list_sources` and `get_source`. The `POST /sources` endpoint adds a source record; this is a small foundation for the import workflow, not a BMW data importer yet.

SQLite lives in `database/local/app.db` and persists on the host. Run `docker compose exec api python -m database.snapshot` to save a consistent copy in `database/snapshots/`. See [database/README.md](database/README.md) for restore steps. The BMW input files in `data/` are separate and are never copied into the images.

Stop the services with `docker compose down`.

## Implementation

- [High-level implementation plan: components, connections, and workflows](IMPLEMENTATION_PLAN.md)
- [Internal research: papers, existing approaches, and evaluation metrics](research/RESEARCH.md)
- [PM workspace and 3D Requirement Twin: enterprise UI, integration, and north star](notes/pm-workspace-and-3d-twin.md)
- [Product Management Factory: agents do the PM work, humans oversee and decide](notes/pm-factory.md)

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
