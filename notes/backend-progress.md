# Backend implementation

Scope follows `IMPLEMENTATION_PLAN.md`: source import → evidence analysis → customer requirements → priorities → PM decisions, followed by new evidence → targeted review of proposed revisions. Vehicle/market scope and source locations are preserved throughout.

Implementation milestones:

1. Transactional persistence and immutable history; migrate the existing source registry without data loss.
2. BMW spreadsheet/PDF and supplied web evidence import with original files, deduplication, and exact locations.
3. Deterministic reference analysis and optional configured AI analysis; grounded findings and customer-facing requirement proposals.
4. Requirement versions, explicit scoring, evidence details, and PM approval/edit/reject/postpone.
5. Cumulative updates, approved/proposed comparisons, targeted review and evaluation.
6. MCP/API parity, Compose deployment, real-data and HTTP/MCP end-to-end verification.

Each milestone is independently reviewed by GPT-6.1 Sol before integration into main. Parallel agents use separate worktrees. Real-data inputs, database contents, and generated snapshots remain ignored.

The deterministic provider is a reproducible reference workflow and is labeled as such. Real AI execution requires `OPENAI_API_KEY` and `OPENAI_MODEL`; it must never silently fall back to reference output.

Implemented backend components map to the planned PM process:

| Component | Implementation | Verification |
| --- | --- | --- |
| Persistence and history | `database/store.py`, `database/workflow.sql` | Migration, rollback, concurrent startup and append-only regression tests |
| Source import | `server/importers.py`, `server/evidence.py`, `server/web_fetch.py` | Generated fixtures, all eight original BMW input formats, scoped live imports and original download integrity |
| Evidence analysis | `server/analysis_engine.py` | Reference replay, positive preservation, structured provider mocks, citation/target/coverage validation |
| Requirements and prioritization | `server/requirements.py` | Exact version/score decisions, recalculated edits, weighting, source trace and approvals |
| Change assessment | `server/pipeline.py` | Labeled relevant/unrelated updates, stale and partial analysis, concurrency, PM edit and approved-state preservation |
| PM workspace/API/MCP | `server/main.py`, `mcp_server/main.py` | Live `scripts/verify_backend.py`; API and actual Streamable HTTP MCP protocol |
| Evaluation | `server/evaluation.py`, `scripts/evaluate_pipeline.py` | Eight labeled updates measuring new PM review alerts, complete confusion counts including wrong predictions, current-version source-link coverage and per-version first-decision latency |

Evaluation is isolated from the configured database and original archive. Metadata labels are given to the deterministic provider; the fixture measures workflow regressions rather than live AI extraction accuracy or statistical confidence. Latency excludes undecided versions and includes idle time. Live OpenAI semantics and real PM productivity require separate evaluation.

Run all checks using the root README. No original BMW data, local database, audit content, or secret is committed. The graphical frontend and 3D presentation remain outside this backend implementation request.
