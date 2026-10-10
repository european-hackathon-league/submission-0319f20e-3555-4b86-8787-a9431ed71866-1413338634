# BMW PM planning workflows

The workflow follows BMW's supplied [PM process](../materials/images/product-management-process.png):
situation analysis → structure and context → requirement definition → prioritization → documentation
and tracking. [Mentor guidance](bmw-guidance.md) places this challenge in **market research and product
planning**, with a requirement set revisited over approximately two years. Completing a run documents
PM planning decisions; it does not approve engineering, homologation, costs or production readiness.

## What agents do and where PMs decide

1. Import BMW spreadsheets/PDFs or explicitly selected source records using the existing import API.
2. Create a scoped initial or update workflow, then run it. It inventories exact source records, analyzes
   cumulative evidence, drafts requirements, and applies the existing deterministic scoring rubric.
3. The run stops at **awaiting review**. Open the decision brief to inspect supporting/conflicting
   findings, exact source locations, scoring contributions, PM-assumed targets and missing dates.
4. PMs edit proposals if needed, then approve or reject each current scoped requirement with its exact
   version and score IDs and a rationale. Postpone and challenge retain the open human gate.
5. Complete the workflow with a PM rationale. The record freezes requirement version, score and
   decision IDs. JSON and Markdown briefs keep those snapshots when later evidence changes.
6. Import new evidence and create an update run. Approved versions and PM-authored fields remain
   intact while revised proposals require another human decision.

`deterministic` is a labeled reference implementation, not live AI. `openai` uses the configured
`OPENAI_MODEL` and requires `OPENAI_API_KEY`; it never silently falls back. Both follow the same data,
scoring and decision gates. The workflow requires complete analysis coverage before generation;
large live datasets may require adjusting `ANALYSIS_BATCH_SIZE` / `ANALYSIS_MAX_BATCHES`.

## API and MCP contract

| API | MCP tool | Purpose |
| --- | --- | --- |
| `GET /actors` | `list_actors` | Declared actors and roles |
| `POST /workflows` | `create_pm_workflow` | Scope, provider, initial/update kind, actor and idempotency key |
| `GET /workflows?vehicle=G60&market=US` | `list_pm_workflows` | Persisted runs, newest first |
| `GET /workflows/{id}` | `get_pm_workflow` | Revision, stage checkpoints, errors and snapshot IDs |
| `POST /workflows/{id}/run` | `run_pm_workflow` | Execute/resume autonomous stages; stop for PM review |
| `GET /workflows/{id}/brief` | `get_pm_workflow_brief` | Evidence-backed live or frozen planning brief |
| `GET /workflows/{id}/brief?format=markdown` | — | Download the planning record |
| `POST /workflows/{id}/complete` | `complete_pm_workflow` | Human PM gate and frozen documentation |

Existing import, trace, edit, scoring and decision endpoints/tools remain available. Trace requests
can pin both `version_id` and `score_id`; an unrelated or nonexistent score returns 404. Trace history
can gain later decisions for that score, while the completed brief retains its exact final decision ID.

Creation requires `request_key`: replaying the identical request returns the same run; different
commands using that key return 409. `run` requires `expected_revision` and `actor`; `complete` adds
`rationale`. Get the current run before retrying a timed-out request. The response for an execution
failure is HTTP 200 with `status: failed` and a persisted `error` object. Invalid commands or stale
revisions return normal HTTP errors. Clients must inspect both the HTTP status and workflow status.

One renewable, fenced lease permits an active workflow per vehicle/market. Dead workers can be
recovered after the 120-second lease expires. Checkpoints and requirement generation commit together;
an expired worker cannot commit generation. A run awaiting review can process newly imported evidence
again through `/run`. With unchanged evidence it is a no-op. Completed runs cannot resume or mutate;
create a new update run instead. All transitions are included in the existing hash-chained audit.

## Evidence limits

The brief's readiness checks are deterministic prompts for PM judgment, not an AI assertion of truth.
A high priority does not establish evidence quality, market prevalence, validated SMART targets or
engineering feasibility. Assumed targets stay labeled after approval. No communication is sent and
no external enterprise integration is performed. Actor labels follow the existing local prototype's
self-declared identity model; the database enforces actor roles, but this is not SSO or authentication.

## Verification

Run against an isolated Compose project and database; the verifier adds auditable synthetic vehicle
scopes and never approves real G60 requirements:

```sh
uv run python -m scripts.verify_pm_workflows --api-url http://127.0.0.1:18000 --mcp-url http://127.0.0.1:18001/mcp
uv run python -m scripts.verify_pm_workflows --api-url http://127.0.0.1:18000 --mcp-url http://127.0.0.1:18001/mcp --provider openai
```

The verifier traverses HTTP and real Streamable HTTP MCP, initial run, source trace, mandatory gate,
PM edit/approval, frozen brief/export, changed evidence, preserved approval and PM wording, AI denial,
update completion, audit and historical JSON/Markdown stability. Tests cover failure/retry, idempotency
collisions, evidence changes during analysis, cross-scope isolation, stale revisions/scores, interrupted
leases and current decisions after manual requirements are added.
