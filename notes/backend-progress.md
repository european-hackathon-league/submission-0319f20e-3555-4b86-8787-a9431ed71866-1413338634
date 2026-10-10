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
