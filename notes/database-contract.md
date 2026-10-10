# Database interface contract

Status: **proposed by the database stream, awaiting backend review (Jakob)**. Change the status line to "agreed" in a commit to accept it. After that, changes to any section need both owners.

This fixes the four interfaces the API, MCP server, importer, and UI share with the database, so the streams can work in parallel. It matches the importer on `main` (`server/importers.py`, [importer contract](importer-contract.md)) and the `audit()` signature in `database/store.py`. See the [database implementation plan](../database/IMPLEMENTATION_PLAN.md) for how each item is built.

## 1. Actor IDs

Every `actor` column (`audit_events`, `requirement_versions`, `decisions`, and future tables) holds an `actors.id`:

| Format | Kind | Examples |
| --- | --- | --- |
| `human:<slug>` | human | `human:troy`, `human:jakob` |
| `ai:<provider>:<model>` | ai | `ai:openai:<model>`, `ai:reference:v1` (deterministic reference workflow) |
| `system:<component>` | system | `system:importer`, `system:migration`, `system:scoring` |

Slugs are lowercase `[a-z0-9-]`. Human roles: `lead_pm`, `pm`, `analyst`, `engineering`, `viewer`.

| Action | Allowed actors |
| --- | --- |
| `approve`, `reject` decision | human with role `pm` or `lead_pm` |
| `postpone`, `challenge` decision | any human |
| New requirement version | human (PM edit) or ai (proposal), with rationale |
| Imports, scoring, migrations | system |

AI and system actors never write `decisions`. The database enforces both rules.

Legacy: the existing value `PM` (today's default for the `actor` field in API request bodies) is seeded as a human with role `pm`, so current rows and calls stay valid. New code sends an `actors.id` in that same `actor` field; until there is SSO the client chooses it. An unknown actor is refused by the database (`unknown or inactive actor`), so the API should validate it and return 422.

## 2. Vehicle codes

Uppercase codes exactly as the importer emits them (`[FG]\d{2}`). Seeded catalogue:

| Code | Vehicle |
| --- | --- |
| `G60` | BMW 5 Series Sedan (first target) |
| `G68` | BMW 5 Series long-wheelbase (China) |
| `G70` | BMW 7 Series |
| `F70` | BMW 1 Series |

A record spanning several vehicles keeps the primary code in `vehicle` and the full list in `metadata.vehicle_scope`, as the importer already does.

## 3. Market codes

Codes exactly as `normalize_market()` emits them:

| Code | Market | Parent |
| --- | --- | --- |
| `US` | United States (first target) | |
| `CN` | China | |
| `EU` | Europe (BMW sales region) | |
| `DE` | Germany | `EU` |
| `GB` | United Kingdom | `EU` |
| `ROW` | Rest of world | |

The parent lets a Europe view include country-level evidence. It is a region roll-up, not a claim about EU membership.

The database never rejects an unknown vehicle or market code. Rejecting one would drop real evidence. The importing transaction registers the code as `discovered` in `vehicles` / `markets`, and `database.cli verify` lists discovered codes for a PM to confirm.

## 4. Requirement keys

- Format: `REQ-<VEHICLE>-<MARKET>-<NNN>`, e.g. `REQ-G60-US-001`. The number is zero-padded to at least 3 digits and sequential per vehicle and market.
- Assigned once by the database (`AFTER INSERT` trigger) in the transaction that creates the requirement. Inserting an explicit key is refused. Never changed or reused, including after rejection.
- Insert into `requirements` with named columns; the table now has a `key` column.
- `requirements.id` stays the internal UUID used in foreign keys. `key` is what people, exports, MCP tools and the UI show.
- The existing uniqueness of (vehicle, market, topic) is unchanged.

## 5. Read views

Read-only views for the API, MCP and UI. Columns may be added later; existing ones are not renamed or removed without agreement. JSON columns are returned as JSON text.

**`v_requirement_list`**: one row per requirement.
`requirement_id`, `key`, `vehicle`, `market`, `topic`, `status`, `current_version_id`, `version`, `title`, `statement`, `customer_need`, `acceptance_criteria`, `assumptions`, `score_id`, `score_total`, `rank` (by `score_total` within vehicle and market), `evidence_grade`, `rubric_version`, `approved_version_id`, `finding_count`, `evidence_count`, `source_count`, `last_decision_action`, `last_decision_actor`, `last_decision_rationale`, `last_decision_at`, `open_review_count`, `updated_at`.
The score is the latest one for the current version.

**`v_requirement_trace`**: one row per version → finding → evidence → source link.
`requirement_id`, `key`, `version_id`, `version`, `finding_id`, `finding_kind`, `finding_topic`, `finding_summary`, `finding_confidence`, `relation` (`supports` / `conflicts`), `evidence_id`, `evidence_content`, `evidence_location`, `evidence_metadata`, `evidence_observed_at`, `source_id`, `source_title`, `source_kind`, `source_original_path`, `source_content_hash`.

**`v_audit_timeline`**: one row per audit event, in `sequence` order.
`sequence`, `created_at`, `actor`, `actor_name`, `actor_kind`, `actor_role`, `action`, `entity_type`, `entity_id`, `requirement_id` (resolved for requirement, version, score, decision and review events; otherwise null), `rationale`, `before_state`, `after_state`, `event_hash`.

**`v_topic_markets`**: the same topic across markets.
`vehicle`, `topic`, `market`, `requirement_id`, `key`, `status`, `score_total`, `evidence_grade`, `approved_version_id`.

**`v_open_reviews`**: the PM "Needs review" list.
`review_id`, `requirement_id`, `key`, `vehicle`, `market`, `reason`, `changes`, `suggested_action`, `approved_version_id`, `proposed_version_id`, `created_at`.

## Changes to backend-owned files

The database stream changes `database/store.py` in two agreed places only:

1. `init_database()` calls `apply_migrations(connection)` after the existing `user_version = 2` steps, in the same transaction.
2. `audit()` computes `prev_hash` and `event_hash`. Its signature is unchanged.

It does not change `database/workflow.sql` or `server/`. New tables, columns, triggers and views go in `database/migrations/0003+`.
