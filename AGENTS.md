# Agent working agreement

## Project context

- Follow `IMPLEMENTATION_PLAN.md` for scope and sequence. Start with G60 / US and preserve source-to-decision traceability across the API, MCP server, and database.
- The original BMW files in `data/` and the large annual report are local inputs. Keep them out of Git, along with `database/local/` and `database/snapshots/` contents.

## Branches and concurrent work

- Check `git status --short --branch` before editing. Preserve any existing changes and identify their owner before staging or changing branches.
- Start a fresh `codex/<scope>` branch when an implementation stream begins, from the latest agreed, committed integration base. Do not create empty branches during planning. Examples: `codex/backend` for the FastAPI server, `codex/mcp-server`, and `codex/database`. Split server and backend into separate branches only when the tasks have distinct scopes.
- Give simultaneous agents separate Git worktrees and branches. Never have two agents switch branches or edit the same files in one checkout. Agree on shared interfaces and file ownership before parallel edits.
- Keep changes within the assigned scope. Coordinate shared files such as `compose.yml`, schemas, and API contracts before changing them. Bring completed branches together through reviewed merges or cherry-picks, resolving integration issues on an integration branch.
- Do not overwrite, reset, or commit another agent's work. Do not push or merge to `main` unless the user asks.

## Local commits

- After each completed implementation request, make a local commit on that work's branch. For longer requests, commit each independently reviewable milestone. Commit changed plan or documentation files too; a conversation with no file changes needs no commit.
- Run relevant checks before committing. For backend or integration changes, validate with Docker Compose and inspect service status and logs. Do not stop a stack that was already running for another worker.
- Stage only the files belonging to your work, review the staged diff, and use a concise `type: summary` message (`feature`, `fix`, `docs`, `refactor`, `test`, or `chore`).
- Report the branch, commit hash, checks run, and any uncommitted work at the end of the request.
