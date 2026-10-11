# Platform build handoff (complete)

Status of [`PLATFORM_BUILD_PLAN.md`](../PLATFORM_BUILD_PLAN.md) as of 2026-10-11: **Phases 0–3 are done and on
`origin/main`** (merge `5cc423e`). Nothing from this note needs resuming.

- Integrated on `codex/platform-integration-main` (the plan's name `codex/platform-integration` was already
  taken by Codex), merged into `main` with a merge commit because `main` had gained the readiness-plan docs.
- Pods: A signals, B markets, C intake and F runtime come from Codex's `*-complete` branches; D priorities,
  E market data, G web (`codex/platform-web-complete`) and H eval were finished by Claude sub-agents.
- Integration fixes: named columns in tests broken by 0010/0014 column additions; priorities use
  `server.signals.weekly_momentum`; markets, priorities and intake read current, reported sales shares
  (`server.platform.REPORTED_MARKET_WEIGHTS`, no 2030 projection, no superseded rows); coverage warnings
  in live decision briefs; MCP `score_requirement` accepts v2 weights; MCP adapter drops unset query
  parameters; simulated request fixture shipped in the API image; rubric switch dialog width.
- Checks: ruff, 869 pytest, web lint/typecheck/49 tests/build; live journey
  (`scripts/verify_backend.py --platform`, deterministic, OpenAI `gpt-6-luna`, and `--real-data`) passed;
  browser check of all platform screens; evaluation table in `notes/platform-evaluation.md`.

Open follow-ups:

- Tasks for capabilities that take only an id (e.g. `signals.refresh_watchlist`) are not checked against
  the task's vehicle/market scope (`server/agent_runtime.py`).
- `POST /markets/compare` without an explicit market list compares sub-markets with their parent (DE with
  EU), falls back to equal weights and warns; the web screen offers a market selector.
- Request clustering under-joins (OpenAI recall 8/34 on the gold set); tune `request-cluster-openai-v1`.
