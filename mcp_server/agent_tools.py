"""Pod F agent runtime tools: registry, capabilities, tasks, runs and internal threads.

Pausing, resuming or retiring an agent, changing its model, cancelling a task and accepting a proposal that
waits at a human gate are human decisions and are not exposed here; post a thread message to ask a PM.
Tools call the API through the injected api_request(method, path, *, params=None, payload=None) and use
identifier(value) to encode path segments. Registered by mcp_server/main.py.
"""

from typing import Literal

TaskStatus = Literal["backlog", "queued", "running", "awaiting_human", "succeeded", "failed", "cancelled"]


def _present(**values) -> dict:
    return {key: value for key, value in values.items() if value is not None}


def register_agent_tools(mcp, api_request, identifier):
    @mcp.tool()
    async def list_agents(
        department: str | None = None, status: Literal["active", "paused", "retired"] | None = None,
        vehicle: str | None = None, market: str | None = None, limit: int = 100, offset: int = 0,
    ) -> dict:
        """List the agent registry (hierarchy, autonomy level, permitted capabilities, model, task counts)."""
        return await api_request("GET", "/agents", params=_present(
            department=department, status=status, vehicle=vehicle, market=market, limit=limit, offset=offset))

    @mcp.tool()
    async def get_agent(agent_id: str) -> dict:
        """Read one agent by id or slug, with its capabilities (registered or not) and recent runs."""
        return await api_request("GET", f"/agents/{identifier(agent_id)}")

    @mcp.tool()
    async def list_capabilities(format: Literal["json", "openai-tools"] = "json", agent_id: str | None = None) -> dict:
        """List registered capabilities with input schemas; openai-tools exports Responses API function tools
        (tool name = capability name with '.' replaced by '-'), optionally only those one agent may run."""
        return await api_request("GET", "/capabilities", params=_present(format=format, agent_id=agent_id))

    @mcp.tool()
    async def create_task(
        capability: str, title: str, requested_by: str, vehicle: str = "G60", market: str = "US",
        input: dict | None = None, topic: str | None = None, assigned_agent_id: str | None = None,
        parent_task_id: str | None = None, status: Literal["backlog", "queued"] = "queued", priority: int = 50,
        recurrence_days: int | None = None, due_at: str | None = None,
    ) -> dict:
        """Queue a capability execution for a vehicle and market. The task runs as its assigned agent, which
        must be granted the capability. Never put BMW records or verbatims into tasks for web-search capabilities."""
        return await api_request("POST", "/tasks", payload=_present(
            capability=capability, title=title, requested_by=requested_by, vehicle=vehicle, market=market,
            input=input if input is not None else {}, topic=topic, assigned_agent_id=assigned_agent_id,
            parent_task_id=parent_task_id, status=status, priority=priority, recurrence_days=recurrence_days,
            due_at=due_at))

    @mcp.tool()
    async def list_tasks(
        vehicle: str | None = None, market: str | None = None, status: TaskStatus | None = None,
        capability: str | None = None, assigned_agent_id: str | None = None, parent_task_id: str | None = None,
        limit: int = 100, offset: int = 0,
    ) -> dict:
        """List tasks by priority with status, assigned agent, revision, last run and error."""
        return await api_request("GET", "/tasks", params=_present(
            vehicle=vehicle, market=market, status=status, capability=capability,
            assigned_agent_id=assigned_agent_id, parent_task_id=parent_task_id, limit=limit, offset=offset))

    @mcp.tool()
    async def get_task_board(
        vehicle: str | None = None, market: str | None = None,
        group_by: Literal["status", "agent", "department"] = "status", limit: int = 50,
    ) -> dict:
        """Kanban view of tasks grouped by status, agent or department, with counts per column."""
        return await api_request("GET", "/tasks/board", params=_present(
            vehicle=vehicle, market=market, group_by=group_by, limit=limit))

    @mcp.tool()
    async def get_task(task_id: str) -> dict:
        """Read a task with its runs, occurrences (children) and linked threads."""
        return await api_request("GET", f"/tasks/{identifier(task_id)}")

    @mcp.tool()
    async def update_task(
        task_id: str, expected_revision: int, actor: str, status: Literal["backlog", "queued"] | None = None,
        title: str | None = None, priority: int | None = None, due_at: str | None = None,
        input: dict | None = None, rationale: str | None = None,
    ) -> dict:
        """Move a task between backlog and queued or edit it, passing its current revision (stale fails).
        Cancelling and accepting gated proposals are human decisions in the PM workspace."""
        return await api_request("PATCH", f"/tasks/{identifier(task_id)}", payload=_present(
            expected_revision=expected_revision, actor=actor, status=status, title=title, priority=priority,
            due_at=due_at, input=input, rationale=rationale))

    @mcp.tool()
    async def execute_task(task_id: str, actor: str, expected_revision: int | None = None) -> dict:
        """Run a queued or failed task now. A capability failure returns the task as failed with its error;
        a proposal needing a PM leaves it awaiting_human. Paused agents' tasks do not run."""
        return await api_request("POST", f"/tasks/{identifier(task_id)}/execute", payload=_present(
            actor=actor, expected_revision=expected_revision))

    @mcp.tool()
    async def list_runs(
        vehicle: str | None = None, market: str | None = None, capability: str | None = None,
        task_id: str | None = None, actor: str | None = None,
        status: Literal["running", "succeeded", "failed"] | None = None, limit: int = 50, offset: int = 0,
    ) -> dict:
        """List recorded capability runs (method version, input hash, metrics, LLM usage, errors), newest first."""
        return await api_request("GET", "/runs", params=_present(
            vehicle=vehicle, market=market, capability=capability, task_id=task_id, actor=actor, status=status,
            limit=limit, offset=offset))

    @mcp.tool()
    async def get_run(run_id: str) -> dict:
        """Read one run with its outputs, audit events, task and messages citing it."""
        return await api_request("GET", f"/runs/{identifier(run_id)}")

    @mcp.tool()
    async def create_thread(
        kind: Literal["agent", "human", "request", "review"], subject: str, created_by: str,
        entity_type: str | None = None, entity_id: str | None = None, vehicle: str | None = None,
        market: str | None = None, body: str | None = None, payload: dict | None = None,
    ) -> dict:
        """Open an internal working thread, optionally linked to a task, requirement, request, conflict or run.
        Threads are never sent outside the system."""
        return await api_request("POST", "/threads", payload=_present(
            kind=kind, subject=subject, created_by=created_by, entity_type=entity_type, entity_id=entity_id,
            vehicle=vehicle, market=market, body=body, payload=payload))

    @mcp.tool()
    async def list_threads(
        vehicle: str | None = None, market: str | None = None, entity_type: str | None = None,
        entity_id: str | None = None, status: Literal["open", "closed"] | None = None, limit: int = 100, offset: int = 0,
    ) -> dict:
        """List internal threads with message counts."""
        return await api_request("GET", "/threads", params=_present(
            vehicle=vehicle, market=market, entity_type=entity_type, entity_id=entity_id, status=status,
            limit=limit, offset=offset))

    @mcp.tool()
    async def get_thread(thread_id: str, limit: int = 200, offset: int = 0) -> dict:
        """Read a thread and its append-only messages in order."""
        return await api_request("GET", f"/threads/{identifier(thread_id)}", params={"limit": limit, "offset": offset})

    @mcp.tool()
    async def post_thread_message(
        thread_id: str, author: str, role: Literal["human", "agent", "system", "tool"], body: str,
        payload: dict | None = None, run_id: str | None = None,
    ) -> dict:
        """Append a message (cited ids and tool call/result JSON go in payload). Messages are immutable and
        internal; nothing is ever sent externally. Agents post as 'agent' or 'tool', never as 'human'."""
        return await api_request("POST", f"/threads/{identifier(thread_id)}/messages", payload=_present(
            author=author, role=role, body=body, payload=payload, run_id=run_id))
