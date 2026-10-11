# Agent runtime

The runtime executes registered capabilities through a persistent, scoped task queue. It exposes
`/agents`, `/capabilities`, `/tasks`, `/runs` and `/threads`, with equivalent MCP preparation/read tools.
These operations share the pipeline's evidence, requirement versions, scores and audit chain.

## Running work

Create a task with `vehicle`, `market`, `capability`, `title`, `requested_by` and `input`. An optional
`assigned_agent_id` selects an agent; otherwise a capability granted to exactly one agent is assigned
automatically. Input cannot override the executing actor. Scope fields and analysis references must
match the task scope. Child tasks preserve their parent's scope.

Tasks follow `backlog → queued → running → succeeded|failed|awaiting_human`. PATCH takes
`expected_revision`; stale writes and duplicate concurrent executions return 409. A capability error
is a completed HTTP request with `status: failed`, its error, and a failed persisted run. Consumers
must inspect task status, not just HTTP success. Failed tasks can be retried. Completed and cancelled
tasks are final. Human acceptance of a task never approves a requirement: requirement decisions still
require their exact version, score and rationale through the existing decision API.

Assigned agents run only capabilities in their registry. Pausing an agent blocks new executions and
messages. Pausing does not interrupt a capability already executing. A worker lost for longer than
`TASK_STALE_SECONDS` is marked failed on the next scheduler sweep; unfinished runs are closed as failed
and a late task result cannot overwrite a recovered task. Review its trace before retrying writes.

## Scheduling

`docker compose --profile scheduler up -d --build` enables the optional scheduler. It calls
`POST /tasks/run-due` every `SCHEDULER_INTERVAL_SECONDS` (900 by default). Recurring tasks remain queued
as schedule templates. Each due slot creates one child occurrence and advances the schedule atomically;
missed historical slots are skipped. Paused agents are reported as skipped. The scheduler has no
provider credentials; it calls the API, where capabilities and gates are enforced.

The API image includes the scheduler script. `python scripts/run_scheduler.py --once` provides a
manual health/scheduling check. An isolated worktree may set `DATA_DIR` to the original local input
folder; BMW source files remain outside Git and are mounted read-only.

## Observability and governance

`GET /tasks/board` groups real tasks by status, agent or department. Runs include method version, input
hash, inputs, outputs, errors and model usage when the capability records it. The runtime creates a
run for handlers that fail before recording one. Threads hold append-only internal messages and
optional task/requirement/request/conflict references. Nothing sends outbound communications.

`GET /capabilities?format=openai-tools` exports Responses API function definitions; strict schemas
are used when representable, with Pydantic validation remaining authoritative. The deterministic
scorer has no model. Model changes and pause/resume/retire actions require human actors and rationale.
The 12-role registry is the substrate; the orchestration layer adds bounded agent sessions above it.

Validation covers task transitions, stale revisions, concurrent claiming, durable failure and retry,
recurrence, pause controls, cross-market isolation, tool exports and immutable conversation records.
