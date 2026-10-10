# Database

SQLite at `database/local/app.db` (`DB_PATH`) is the single system of record. The API creates and migrates it on startup. `database/local/` is bind-mounted into the API container, so data survives `docker compose down` and rebuilds. `data/` holds the original BMW inputs (read-only in the container). Live databases, snapshots and exports are local-only and ignored by Git. Snapshots contain BMW verbatims; share them only through the team's BMW Drive folder.

Interfaces (actor IDs, vehicle/market codes, requirement keys, view columns) are fixed in [notes/database-contract.md](../notes/database-contract.md). The plan and its rationale are in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## What the database enforces

These rules hold for any client, including direct SQL, because they are triggers rather than API code:

| Rule | Where |
| --- | --- |
| History tables are append-only, including `INSERT OR REPLACE` | `store.init_database()` |
| Every `actor` written to `audit_events`, `requirement_versions`, `decisions` is a known, active `actors.id` | `0003` |
| Unknown vehicle / market codes are registered as `discovered`, never rejected | `0003` |
| Decisions are made by humans only; `approve` / `reject` need role `pm` or `lead_pm` | `0004` |
| `approved_version_id` / `approved_score_id` change only when the latest decision on the requirement approves exactly that version and score | `0004` |
| `approved` / `rejected` / `postponed` status follows the latest decision; an approved requirement reopens via `needs_review`, not `proposed` | `0004` |
| Requirement keys (`REQ-G60-US-001`) are assigned by the database on insert, sequential per vehicle and market, never changed or reused; requirements are never deleted | `0004` |
| Every audit event extends a SHA-256 hash chain (`prev_hash` → `event_hash`); direct inserts that bypass `store.audit()` are refused | `0005` |

So an AI provider can propose requirement versions, but the database refuses to let it approve one.

Insert into `requirements` with named columns: the table gained a `key` column, so positional `VALUES (...)` no longer fits.

## Migrations

`init_database()` builds the `user_version = 2` base, then `database/migrate.py` applies `database/migrations/NNNN_*.sql` with a number above `user_version`, in order, in the same `BEGIN IMMEDIATE` transaction. A failing migration rolls back completely. Before migrating a database that already holds data it writes a `pre-migrate` snapshot (`MIGRATION_SNAPSHOTS=0` disables this).

| File | Adds |
| --- | --- |
| `0003_reference_and_people.sql` | `actors`, `vehicles`, `markets`, actor validation, discovered codes; seed from `seed.py` |
| `0004_decision_gates.sql` | `requirements.key`, key sequences, decision and approval gates, status workflow |
| `0005_audit_hash_chain.sql` | `audit_events.prev_hash` / `event_hash`, chain trigger, `(action, created_at)` index; seals pre-existing events under a genesis event |
| `0006_read_views.sql` | `v_requirement_list`, `v_requirement_trace`, `v_audit_timeline`, `v_topic_markets`, `v_open_reviews` |

Add a migration as the next number; never edit an applied one. New AI identities: `seed.ensure_actor(connection, seed.ai_actor_id("openai", model), "ai", name, "ai")`. `OPENAI_MODEL` is seeded automatically.

## Read views

One query traces a requirement to the spreadsheet row it came from:

```sql
SELECT version, relation, finding_summary, evidence_content, evidence_location, source_title
FROM v_requirement_trace WHERE key = 'REQ-G60-US-001';
```

`v_audit_timeline` resolves the requirement for requirement, version, score, decision and review events; order by `sequence`.

## Operations

```sh
docker compose exec api python -m database.cli snapshot --label NAME   # backup + manifest
docker compose exec api python -m database.cli verify [FILE]           # non-zero exit on failure
docker compose exec api python -m database.cli export --format csv --actor human:troy
docker compose exec api python -m database.cli seed
docker compose exec api python -m database.cli rebuild --target /app/database/local/rebuilt.db [--scope G60:US]
docker compose stop api && docker compose run --rm --no-deps api python -m database.cli restore /app/database/snapshots/FILE.db && docker compose start api
```

| Command | Behaviour |
| --- | --- |
| `snapshot` | Backup-API copy to `database/snapshots/app-<UTC>[-label].db` (single file, no WAL) and `<same>.manifest.json`: label, git commit, `user_version`, row counts, input SHA-256s, audit chain head, file SHA-256. No BMW content in the manifest. |
| `verify` | `integrity_check`, `foreign_key_check`, `user_version`, append-only and governance triggers, full audit chain walk (reports the first broken sequence), manifest SHA-256 for a snapshot file. Discovered codes and legacy actors are warnings. |
| `restore` | Requires a matching manifest and a passing verify (older schemas allowed, they migrate on start). Refuses while a writer holds the live DB. Takes a `pre-restore` snapshot, then replaces `app.db` and removes stale `-wal` / `-shm`. Stop the API first. |
| `export` | `v_requirement_list` as CSV or JSON to `database/snapshots/exports/`, audited as `access.export` with the actor and exported keys. |
| `rebuild` | Fresh database at `--target`: migrate, seed, import every Drive input in `DATA_DIR` whose SHA-256 matches `notes/source-inventory.json`, per scope. Inputs without evidence for a scope are skipped and reported. Cached analysis replay follows once analysis runs are persisted. |

Policy: snapshot before risky work (`pre-import`, `pre-analysis`). Append-only tables mean a wrong import cannot be deleted, so the snapshot is the undo. The `golden` snapshot is the frozen demo dataset; commit its manifest to `database/snapshot-manifests/golden.manifest.json` so every teammate can verify they hold the same file (`verify FILE` checks the SHA-256). Demo runs use a restored golden copy via `DB_PATH=/app/database/local/demo.db`, so rehearsals never touch it.

Originals preserved by the importer live in `database/local/originals/` (content-addressed, not part of a snapshot); `rebuild` recreates them from `data/`.

## Inspecting a snapshot

```sh
docker compose --profile inspect up -d inspect     # http://127.0.0.1:${INSPECT_PORT:-8002}
INSPECT_DB=/snapshots/FILE.db docker compose --profile inspect up -d inspect
```

[Datasette](https://datasette.io) serves an immutable copy of the newest `golden` snapshot (else the newest snapshot, or `INSPECT_DB`); it never opens the live WAL database. Canned queries: requirement list, trace, audit timeline, topic across markets, needs review.

## Postgres (production path, not built)

SQLite stays the only live store for the hackathon; running two stores would drift. The SQL is kept portable (TEXT UUIDs, ISO-8601 UTC strings, JSON as text). For production: triggers become plpgsql, `actors` maps to database roles, row-level security restricts PMs to their vehicle/market scopes, and a snapshot loads via `pg_dump` / `pg_restore`.
