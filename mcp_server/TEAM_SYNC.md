# Team push coordination

Owner: Alex's MCP workstream. This documents the user's 10 October 2026 request
to watch Jakob/Troy pushes and publish smaller tested milestones. It does not
change Jakob's backend or Troy's database/Compose ownership.

## Cadence

A five-minute recurring check is attached to Alex's chat. It checks Git changes,
uses review agents when relevant changes arrive, and reports meaningful results,
failures or ownership conflicts. Unchanged checks stay quiet. Local scheduling
requires the computer and desktop app to remain running. It does not keep idle
agents continuously computing and does not make Exa requests.

Keep last-inspected remote refs in the automation's local state, outside tracked
files. Do not commit a timestamp or empty change on every poll. Start from reviewed
main `edfef95` and MCP implementation `a5b911c`, then follow their descendants.

## Each check or active-work milestone

1. Check Git status and ownership; preserve all staged, unstaged and untracked work.
2. `git fetch origin`; inspect newly pushed refs, authors, commits and affected
   files, including main and teammate topic branches. A branch name alone is not
   evidence that a change is ready for integration.
3. Review backend contract, MCP registration, storage and deployment implications.
   Use independent read-only reviewers; each editing agent gets its own worktree
   and branch with explicit file ownership. The lead integrates their results.
4. Publish each small coherent milestone as soon as relevant checks pass. Fetch
   and inspect again immediately before committing and pushing. Do not accumulate
   unrelated completed changes, publish broken WIP, or force an arbitrary timer
   when a change is not ready. Include affected interfaces and validation in the
   commit/documentation so teammates can consume it.
5. `codex/mcp-evidence` is already published. Preserve its history: use reviewed
   normal merges for incoming integration commits, and normal pushes. Never rebase,
   amend or reset published commits; never force-push or push/merge to main.
   On a genuinely clean integration checkout, use `git pull --ff-only`.
6. The user authorized reconciling MCP implementations while preserving Jakob's
   operational tools. If competing semantics, API schemas or Compose changes need
   an owner decision, identify exact files/contracts and coordinate before editing;
   never discard either side. Existing `fetch_web_source` imports through the
   backend; Exa `fetch_market_evidence` only returns candidates. Keep both contracts.
7. Once verified, push the topic branch promptly. Report meaningful integrations,
   checks that fail, or decisions needed. No unsolicited external messages.

## Checks and limits

For combined MCP/backend integrations run:

```sh
uv run python -m pytest -q mcp_server/tests tests
uv run ruff check mcp_server tests/test_mcp.py
docker compose config --quiet
```

Plain `pytest` discovers only `tests/` under the current configuration, so name
both suites explicitly. For smaller changes use relevant tests; documentation-only
changes need a diff/format check, not a repeat of the whole suite. Run Docker
health/log checks when its daemon is available without disturbing another stack.

Never commit private BMW inputs, live databases, cache contents or credentials.
Monitoring must not consume Exa credits or change billing. Latest implementation
verification: [452 passing tests](VERIFICATION.md). Live Exa validation still needs
an environment key, and Docker runtime validation needs a running daemon.

Frequent fetches and small pushes reduce stale integration work; they cannot
eliminate conflicts or guarantee another teammate's agent is also fetching.
