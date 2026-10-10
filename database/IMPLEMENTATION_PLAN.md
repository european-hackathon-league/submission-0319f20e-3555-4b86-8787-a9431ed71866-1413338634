# Database implementation plan

Scope: make the shared database ready for enterprise use by BMW product managers: enforced human decision gates, named people and roles, tamper-evident history, one-query traceability, and reproducible data snapshots that the team can share and restore. Follows the root [implementation plan](../IMPLEMENTATION_PLAN.md); G60 / US first, vehicle and market on every record.

## Starting point (on `main`, 6c963af)

Milestone 1 of the backend stream ([backend progress](../notes/backend-progress.md)) is already merged:

- `database/schema.sql` + `database/workflow.sql`: `sources → imports → evidence → analysis_runs → findings → finding_evidence → requirements → requirement_versions → requirement_findings → scores → decisions → review_items`, plus `audit_events`.
- `database/store.py`: atomic `init_database()` (`BEGIN IMMEDIATE`, rollback on failure, `PRAGMA user_version = 2`), `transaction()`, `audit()` written in the same transaction as the change, JSON `CHECK`s, foreign keys on.
- Append-only triggers on every history table, including `INSERT OR REPLACE`; tests in `tests/test_database.py`.
- Milestone 2 (6c963af): `server/importers.py` parses the BMW spreadsheets, PDFs and other formats into records with exact locations ([importer contract](../notes/importer-contract.md)).

The pipeline chain the judges score (**source → evidence → finding → requirement version → score → decision → audit**) therefore already exists. This plan does **not** redesign it. It closes the gaps between "stores history" and "an enterprise system a PM organisation can trust", and adds the snapshot and Compose operations.

## Gaps this plan closes

| Gap today | Why it matters for BMW / judging | Fix |
| --- | --- | --- |
| `actor` is free text everywhere | No people, roles, or accountability. An AI run can write `actor = 'PM'`. | `actors` table (human / ai / system, role); DB triggers validate every actor written. |
| Approval gate is application-only | `requirements.approved_version_id` can be set without a decision. | Trigger: approved version must have a human `approve` decision by a PM role. AI can propose, never approve. |
| Audit is append-only but not tamper-evident | "Reconstructable history" is stronger when it can be verified. | Hash chain on `audit_events` (`prev_hash`, `event_hash`) plus `verify` command. |
| No access events | Challenge defines the audit trail as including access events. | `access.*` audit actions for requirement/evidence views (API writes them; DB indexes them). |
| Vehicle / market are free text | Typos split scopes; no catalogue for the PM workspace selector. | `vehicles` and `markets` reference tables, seeded; unknown codes registered as `discovered` for PM confirmation, never rejected. |
| No human-readable requirement IDs | Deliverable requires a "unique identifier" PMs can cite. | `requirements.key` (`REQ-G60-US-001`), unique, assigned on creation. |
| Traceability requires hand-written joins | Every consumer (API, MCP, UI, export) re-derives the chain. | Read-only SQL views: requirement list, full trace, audit timeline, cross-market topic view. |
| Ad-hoc schema upgrades in `init_database()` | Every new table/column edits the same function; risky with append-only data. | Numbered migrations from `user_version` 3 onward, applied in the existing atomic transaction. |
| Snapshot is a bare `.db` copy | No way to know what a snapshot contains, verify it, or restore safely. | Labelled snapshots with manifest, `restore` with safety copy, `verify`, golden demo snapshot. |
| No rebuild-from-source path | Snapshot is the only copy of expensive AI output; data/ inputs must stay out of Git. | `rebuild` = fresh DB → migrate → seed → import → (cached) analysis. `analysis_runs.input_hash` is the cache key. |

## Decision: SQLite now, Postgres as the documented production path

| | SQLite (keep) | Postgres |
| --- | --- | --- |
| Ops | Zero. Runs in the API process; one file. | Extra service, credentials, volume, healthcheck. |
| Snapshot | One consistent file via the backup API: copy, share, restore. | `pg_dump` / `pg_restore`; heavier to pass between teammates. |
| Fit with existing code | Code relies on SQLite triggers (`RAISE(ABORT)`), `json_valid`, `PRAGMA`s, `BEGIN IMMEDIATE`. | Persistence layer and triggers would need rewriting (plpgsql). |
| Concurrency | WAL: many readers, one writer. Enough for a PM team demo. | Many writers, row-level security, roles. The production path. |

**Do not run both live.** Dual writes drift, and every bug becomes two bugs. Keep SQLite as the single system of record for the hackathon. Keep SQL portable where it is free (TEXT UUIDs, ISO-8601 UTC strings, JSON as TEXT), and document the Postgres mapping (plpgsql triggers, roles, RLS per market) as the enterprise story in `database/README.md`. A `postgres` Compose profile that loads a snapshot is a stretch goal only, and the first thing to cut.

"Live copies in the beginning" maps to: each developer runs a live local `app.db`; the team exchanges **named snapshots**; the demo runs on a restored **golden** copy (`DB_PATH=/app/database/local/demo.db`), so rehearsals never pollute it.

## Target additions

All new objects arrive as numbered migrations. Existing tables only gain columns (`ALTER TABLE … ADD COLUMN`) and triggers. Rows that are already append-only are never rewritten.

### Reference and people (migration 0003)

| Table | Columns | Notes |
| --- | --- | --- |
| `actors` | `id` (text key used in existing `actor` columns, e.g. `pm:jakob`, `ai:openai:<model>`, `system:importer`), `kind` (`human`/`ai`/`system`), `display_name`, `role` (`lead_pm`, `pm`, `analyst`, `engineering`, `viewer`, `ai`, `system`), `active`, `created_at` | Seeded with team members' PM personas, the importer, and the AI provider identities. Legacy value `'PM'` is seeded as a human `pm` so existing rows stay valid. |
| `vehicles` | `code` (`G60`, `G68`, `G70`, `F70`), `series`, `body`, `status` (`seeded` / `discovered` / `confirmed`) | From `notes/source-inventory.json`. |
| `markets` | `code` (`US`, `CN`, `EU`, `DE`, `GB`, `ROW`, as `normalize_market()` emits), `name`, `parent_code` (`DE`, `GB` → `EU`), `status` | Region roll-up for Europe views. |

`BEFORE INSERT` triggers on tables with an `actor` column reject unknown actors. This uses triggers rather than foreign keys because SQLite cannot add an FK to an existing table without rebuilding it, and rebuilding append-only tables is not allowed. Unknown vehicle and market codes are **not** rejected, because the importer accepts any `[FG]\d{2}` code and rejecting one would drop real evidence. The import transaction registers them as `discovered`, and `verify` lists them for a PM to confirm.

All IDs, codes, key formats and view columns are fixed in the [database interface contract](../notes/database-contract.md).

### Decision gates (migration 0004)

- `decisions` insert: actor must be `kind = 'human'`; `approve` / `reject` require role `pm` or `lead_pm`.
- `requirements` update of `approved_version_id` / `approved_score_id`: the new version must have a matching `approve` decision with the same `score_id`; otherwise `RAISE(ABORT, 'approval requires a PM decision')`.
- `requirements.status` transitions limited to the workflow (`proposed → approved | rejected | postponed | needs_review`, `needs_review → …`).
- `requirements.key` column + unique index; `store` helper allocates the next number per vehicle/market inside the creating transaction.

This is the strongest auditability claim for judges: **the database itself refuses an AI approval**, independent of API code.

### Tamper-evident audit (migration 0005)

- `audit_events.prev_hash`, `audit_events.event_hash` (SHA-256 over the previous hash plus canonical JSON of the row, using the existing `encode()`).
- `audit()` computes both within its transaction. `BEGIN IMMEDIATE` already serialises writers, so the chain is linear.
- Existing events cannot be back-filled (append-only). The migration writes an `audit.chain.started` genesis event whose hash covers all earlier rows, so pre-migration history is sealed too.
- Access events: `access.requirement.viewed`, `access.evidence.viewed`, `access.export` with actor and request metadata. Index `(action, created_at)`.
- `verify` walks the chain and reports the first broken sequence.

### Read models (views, migration 0006)

| View | Purpose / consumer |
| --- | --- |
| `v_requirement_list` | The deliverable list: key, title, statement, status, latest score + rank, evidence grade, assumptions, finding count, source count, last decision (actor, action, rationale, time). Backs the PM workspace list and CSV/JSON export. |
| `v_requirement_trace` | One row per requirement version → finding → evidence → source with `evidence.location`. API "explain", MCP `trace_requirement`, UI evidence panel. |
| `v_audit_timeline` | Audit events joined to actor name/role, filterable by requirement (including its versions, scores, decisions, reviews). |
| `v_topic_markets` | Same `topic` across markets side by side: status, score, evidence grade. Addresses BMW's "balance markets" pain point. |
| `v_open_reviews` | `review_items` that are `open`, with approved vs proposed version and changes. The "Needs review" filter. |

Views are read-only and add no write paths, so they are safe to ship early and let API/MCP/UI work in parallel.

### Numeric facts (optional, coordinate with importer)

Sales volumes and study ratings are numbers that scoring needs (market weight, satisfaction gap). If `evidence.metadata` turns out awkward to query, add `metrics(evidence_id, name, dimensions JSON, value REAL, unit)`. Decide after the importer has profiled the real sheets; do not pre-build it.

## Migrations mechanism

Keep the existing `init_database()` contract (atomic, idempotent, concurrent-safe). After the current `user_version = 2` steps, it calls `apply_migrations(connection)`:

- Files: `database/migrations/0003_reference_and_people.sql`, `0004_decision_gates.sql`, …
- Applies every file with number > `user_version` inside the same `BEGIN IMMEDIATE` transaction, via the existing `_execute_schema()`, then sets `user_version`.
- Takes an automatic `pre-migrate` snapshot first when the DB is non-empty and a migration is pending.
- Test: a v2 database with data upgrades with no row changes and with every history table still append-only. Re-running is a no-op; a failing migration rolls back fully (mirrors the existing test).

This is the **only** edit to `database/store.py` in this stream: one call plus the hash-chain lines in `audit()`. Agree it with the backend owner before starting.

## Snapshots and data operations

One CLI, `python -m database.cli <command>`, run in the container with `docker compose exec api …` or `docker compose run --rm --no-deps api …`:

| Command | Behaviour |
| --- | --- |
| `snapshot [--label NAME]` | Backup-API copy to `database/snapshots/app-<UTC>-<label>.db` + `<same>.manifest.json`. |
| `verify [FILE]` | `PRAGMA integrity_check`, `foreign_key_check`, audit hash chain, append-only triggers present, `user_version` matches code. Non-zero exit on failure. |
| `restore FILE` | Refuses while the API holds the DB (`BEGIN IMMEDIATE` lock probe). Verifies the file and its manifest, auto-snapshots the current DB as `pre-restore`, replaces `app.db`, removes stale `-wal`/`-shm`. |
| `seed` | Idempotent reference data: vehicles, markets, actors, rubric defaults. |
| `rebuild` | Fresh DB at a target path → migrate → seed → run the importer over `data/` (verifying SHA-256 against `notes/source-inventory.json`) → optionally replay cached analysis. |
| `export --format csv\|json` | `v_requirement_list` to `database/snapshots/exports/`; writes an `access.export` audit event. |

**Manifest** (no BMW content, safe to commit): created_at, label, git commit, `user_version`, row counts per table, input-file SHA-256s, last audit `event_hash`, snapshot file SHA-256.

**Policy**

- Auto-snapshots: `pre-migrate`, `pre-import`, `pre-analysis`, `pre-restore`. Append-only tables mean a wrong import cannot be deleted, so the snapshot is the undo.
- `golden`: the frozen demo dataset, taken once the end-to-end requirement works. Its manifest is committed to `database/snapshot-manifests/golden.manifest.json` so every teammate can verify they hold the same file.
- Snapshot `.db` files contain BMW verbatims. They stay out of Git (already ignored) and are shared through the team's BMW Drive folder only.
- AI output is the expensive, non-deterministic part. `analysis_runs (provider, model, prompt_version, input_hash)` is the cache key, so `rebuild` reuses a prior result instead of spending credits again.

## Docker Compose changes

Coordinate with the backend owner before merging; `compose.yml` is shared.

- `api`: add read-only `./data:/app/data:ro` and `DATA_DIR=/app/data` for `rebuild` and the importer. Add `DATA_DIR` to `.env.example`.
- `inspect` profile: [Datasette](https://datasette.io) service on `127.0.0.1:${INSPECT_PORT:-8002}`. It opens the **latest or golden snapshot as immutable** (`-i`), never the live WAL file, and ships canned queries for the trace and timeline views. Judges and PMs can click from requirement to original feedback row without any custom UI. Add `INSPECT_PORT` to `.env.example`.
- No separate database service for SQLite. `postgres` profile only if the stretch goal is reached.

```sh
docker compose up --build -d
docker compose exec api python -m database.cli snapshot --label golden
docker compose --profile inspect up -d inspect
```

## Ownership and parallel work

| Owner / stream | Files |
| --- | --- |
| **Database stream** (`codex/database`, this plan) | `database/migrations/`, `database/cli.py`, `database/snapshot.py`, `database/seed.py`, `database/README.md`, `database/snapshot-manifests/`, `tests/test_migrations.py`, `tests/test_governance.py`, `tests/test_snapshot.py`; `compose.yml` profile additions (coordinated) |
| **Backend stream** (Jakob; milestones 2–6 in `notes/backend-progress.md`) | `database/workflow.sql`, `database/store.py` (except the agreed hook), importer, analysis, scoring, `server/` |
| MCP / UI | Consume the views through the API; no direct DB access |

Interface contract to agree **before** parallel work: [notes/database-contract.md](../notes/database-contract.md) (actor IDs, vehicle/market codes, requirement keys, view columns). After that, API, MCP and UI build against the views while migrations land.

## Sequence and checks

| # | Milestone (one commit each) | Done when | Effort |
| --- | --- | --- | --- |
| 0 | Restore `data/` from Drive; verify SHA-256 against inventory | All 8 inputs match | 15 min, human |
| 1 | Migration runner + 0003 reference/people + seed | v2 DB upgrades cleanly; existing tests green; unknown actor rejected; unknown market registered as `discovered` | 1–1.5 h |
| 2 | 0004 decision gates + requirement keys | Tests: AI approve fails; approval without decision fails; PM approve succeeds and is audited | 1 h |
| 3 | 0005 audit hash chain + access events + `verify` | Tampering with a copied DB is detected at the exact sequence | 45 min |
| 4 | 0006 views | A single query traces one G60/US requirement to sheet + row | 45 min |
| 5 | CLI: snapshot/manifest/restore/verify/export/rebuild | Round-trip snapshot → restore → verify gives identical counts and chain head | 1 h |
| 6 | Compose: data mount, `inspect` profile, `.env.example`, README | `docker compose up --build`, `ps` healthy, logs clean; Datasette shows the trace | 30 min |
| 7 | Golden snapshot + committed manifest | After the first end-to-end requirement exists | 10 min |
| — | Stretch: `postgres` profile loading a snapshot | Only if 0–7 are done | cut first |

Checks before every commit: `uv run pytest`, `uv run ruff check`, and for milestones 5–6 `docker compose up --build -d` + `docker compose ps` + `docker compose logs api`. Do not stop a stack another worker is using.

## Agent execution

- **One agent, one worktree, sequential milestones.** The work is small, contract-heavy, and concentrated in a few files that all touch the same schema. Parallel agents inside this stream would collide on migrations and `store.py` and produce conflicting triggers. Append-only data makes a wrong migration expensive to undo.
- **Highest-capability model at high effort for milestones 1–3** (schema, gates, hash chain). Lower effort is fine for 4–6 (views, CLI, Compose, docs).
- **Parallelism happens across streams, not within this one:** database (this plan) ‖ backend/importer (Jakob) ‖ MCP tools ‖ PM workspace UI, each in its own worktree once the interface contract above is agreed.
- **One independent review** (`/code-review` or the team's reviewer model) per milestone before merging to an integration branch, matching the backend stream's practice.
