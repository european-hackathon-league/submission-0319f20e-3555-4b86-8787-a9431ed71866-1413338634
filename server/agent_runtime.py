"""Pod F – agent runtime substrate: agent registry, capability catalogue, task queue and board, runs,
threads and messages. No LLM agent loop yet. server/main.py registers every router in `routers`.

Rules (PLATFORM_BUILD_PLAN.md §2, notes/agent-runtime.md):
- Tasks run through server.platform.run_capability. Claiming a task and recording its outcome are short,
  revision-guarded transactions; the capability itself runs outside any write transaction.
- Failures stay visible: the task becomes `failed` with its error, and a failed run plus audit events exist
  even when the capability is not registered or rejects its input before recording a run.
- A task runs as its assigned agent (or, unassigned, as the caller); a registered agent may run only the
  capabilities its registry entry grants. Paused and retired agents do not act.
- Pause/resume/retire, model changes, cancelling a task and accepting a gated proposal are human decisions:
  require_human here, database triggers (0009, 0015) underneath.
- Threads and messages are internal, append-only working records; nothing is ever sent externally.
"""

import copy
import json
import math
import os
import re
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field, StringConstraints, ValidationError, field_validator, model_validator

from database.store import audit, connect, decode, encode, new_id, now, transaction
from server.analysis_engine import PROMPT_VERSION
from server.evidence import scope_filters
from server.models import AnalysisRequest, Command, GenerateRequest, Scope, json_size
from server.pipeline import assess_update, generate_requirements, run_analysis
from server.platform import (
    CAPABILITIES,
    MAX_ERROR_CHARS,
    Capability,
    describe_capability,
    record_run,
    register_capability,
    require_human,
    run_capability,
)

agents_router = APIRouter(prefix="/agents", tags=["agents"])
capabilities_router = APIRouter(prefix="/capabilities", tags=["agents"])
tasks_router = APIRouter(prefix="/tasks", tags=["tasks"])
runs_router = APIRouter(prefix="/runs", tags=["runs"])
threads_router = APIRouter(prefix="/threads", tags=["threads"])
routers = (agents_router, capabilities_router, tasks_router, runs_router, threads_router)

RUNTIME_METHOD = "agent-runtime-v1"      # method_version of runs the runtime records on a capability's behalf
RUNTIME_ACTOR = "system:agent-runtime"   # fences executions that stopped reporting
SCHEDULER_ACTOR = "system:scheduler"
REFERENCE_METHOD = "keyword-rules-v1"    # deterministic analysis rules (server/analysis_engine.py)
GENERATE_METHOD = "requirement-builder-v1"
STALE_TASK_SECONDS = float(os.getenv("TASK_STALE_SECONDS", "3600"))
if not math.isfinite(STALE_TASK_SECONDS) or STALE_TASK_SECONDS <= 0:
    raise ValueError("TASK_STALE_SECONDS must be a finite positive number")
MAX_INPUT_BYTES = 64 * 1024
DEPARTMENTS = ("orchestration", "customer_insights", "market_intelligence", "requirements", "governance", "communications")
STATUSES = ("backlog", "queued", "running", "awaiting_human", "succeeded", "failed", "cancelled")
STATUS_LABELS = {"backlog": "Backlog", "queued": "Queued", "running": "Running", "awaiting_human": "Awaiting human",
                 "succeeded": "Succeeded", "failed": "Failed", "cancelled": "Cancelled"}
# Status changes through PATCH. running/succeeded/failed/awaiting_human are otherwise set by execution only.
TRANSITIONS = {
    "backlog": {"queued", "cancelled"},
    "queued": {"backlog", "cancelled"},
    "awaiting_human": {"queued", "succeeded", "cancelled"},   # succeeded = a human accepted the gated proposal
    "failed": {"queued", "backlog", "cancelled"},
    "running": set(), "succeeded": set(), "cancelled": set(),
}
EXECUTABLE = ("queued", "failed")
STATUS_ACTIONS = {"queued": "task.queued", "backlog": "task.moved_to_backlog", "cancelled": "task.cancelled",
                  "succeeded": "task.accepted"}
# Thread links: entity type -> table holding that id.
ENTITY_TABLES = {"task": "tasks", "requirement": "requirements", "requirement_version": "requirement_versions",
                 "request": "intake_requests", "market_conflict": "market_conflicts", "review_item": "review_items",
                 "run": "runs", "agent": "agents", "watchlist": "watchlists", "signal_item": "signal_items"}
AUTONOMY_NOTES = {"A0": "runs autonomously", "A1": "proposes; a PM reviews the result",
                  "A2": "its proposals need a human accept", "A3": "drafts only; a human acts"}
# OpenAI strict function schemas: structural keywords strict mode lacks make a tool non-strict; value
# constraints Pydantic re-validates server-side (lengths, defaults, unsupported formats) are dropped.
STRICT_STRUCTURAL = {"allOf", "oneOf", "not", "if", "then", "else", "prefixItems", "patternProperties",
                     "unevaluatedProperties", "unevaluatedItems", "propertyNames", "minProperties", "maxProperties",
                     "contains", "minContains", "maxContains", "dependentRequired", "dependentSchemas"}
STRICT_DROPPED = ("minLength", "maxLength", "examples", "uniqueItems")
STRICT_FORMATS = {"date-time", "time", "date", "duration", "email", "hostname", "ipv4", "ipv6", "uuid"}
OPENAI_TOOL_NAME = re.compile(r"[a-zA-Z0-9_-]{1,64}")

Actor = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Rationale = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ModelName = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")]


# Helpers --------------------------------------------------------------------------------------------

def _utc(value: str | None) -> str | None:
    """Normalize an ISO date or timestamp to store.now()'s UTC format, so stored times compare as text."""
    if value is None:
        return None
    try:
        moment = (datetime.combine(date.fromisoformat(value), datetime.min.time()) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
                  else datetime.fromisoformat(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("Expected an ISO date or timestamp") from exc
    moment = moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)
    return moment.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _after(timestamp: str, seconds: float) -> str:
    return _utc((datetime.fromisoformat(timestamp) + timedelta(seconds=seconds)).isoformat())


def _next_due(due_at: str, recurrence_days: int, current: str) -> str:
    """First slot of the schedule strictly after `current`; missed periods are skipped, not backfilled."""
    period = timedelta(days=recurrence_days)
    elapsed = datetime.fromisoformat(current) - datetime.fromisoformat(due_at)
    steps = max(1, math.floor(elapsed / period) + 1)
    return _utc((datetime.fromisoformat(due_at) + steps * period).isoformat())


def _error_text(exc: BaseException) -> str:
    detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
    if not isinstance(detail, str):
        try:
            detail = encode(detail)
        except (TypeError, ValueError):
            detail = str(detail)
    return f"{type(exc).__name__}: {detail}"[:MAX_ERROR_CHARS]


def _validation_errors(exc: ValidationError) -> list[dict]:
    return [{"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]} for error in exc.errors()]


def _page(connection, table: str, clauses: list[str], params: list, order: str, limit: int, offset: int, project) -> dict:
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    total = connection.execute(f"SELECT count(*) FROM {table}{where}", params).fetchone()[0]
    rows = connection.execute(f"SELECT * FROM {table}{where} ORDER BY {order} LIMIT ? OFFSET ?",
                              [*params, limit, offset]).fetchall()
    return {"items": [project(connection, row) for row in rows], "total": total, "limit": limit, "offset": offset}


def _filters(**values) -> tuple[list[str], list]:
    clauses, params = [], []
    for column, value in values.items():
        if value is not None:
            clauses.append(f"{column}=?")
            params.append(value)
    return clauses, params


class CapabilityUnavailable(LookupError):
    """The task names a capability this server has not registered (e.g. its pod is not merged yet)."""


class CapabilityNotPermitted(PermissionError):
    """The acting agent's registry entry does not grant the task's capability."""


# Capability catalogue and OpenAI tool export ---------------------------------------------------------

def openai_tool_name(capability: str) -> str:
    """'signals.refresh_watchlist' -> 'signals-refresh_watchlist'. Capability names have exactly one '.' and
    never contain '-', so replacing the dot with '-' is reversible (capability_for_tool)."""
    name = capability.replace(".", "-")
    if not OPENAI_TOOL_NAME.fullmatch(name):
        raise ValueError(f"Capability name cannot be an OpenAI tool name: {capability}")
    return name


def capability_for_tool(tool_name: str) -> str:
    if tool_name.count("-") != 1 or not OPENAI_TOOL_NAME.fullmatch(tool_name):
        raise ValueError(f"Not a capability tool name: {tool_name}")
    return tool_name.replace("-", ".")


def strict_parameters(schema: dict) -> dict | None:
    """The input schema in OpenAI strict function form, or None if it needs constructs strict mode lacks
    (free-form objects, oneOf/allOf, tuples...). Every property becomes required; defaults move into the
    description; the server re-validates the arguments with the capability's Pydantic model."""
    schema = copy.deepcopy(schema)

    def visit(node) -> bool:
        if not isinstance(node, dict) or STRICT_STRUCTURAL & node.keys():
            return False
        if "$ref" in node:
            for key in [key for key in node if key != "$ref"]:
                node.pop(key)
            return True
        if "default" in node:
            default = node.pop("default")
            note = f"Default: {json.dumps(default, ensure_ascii=False)}."
            node["description"] = f"{node['description'].rstrip('. ')}. {note}" if node.get("description") else note
        for key in STRICT_DROPPED:
            node.pop(key, None)
        if "format" in node and node["format"] not in STRICT_FORMATS:
            node.pop("format")
        ok = True
        if node.get("type") == "object" or "properties" in node or "additionalProperties" in node:
            properties = node.get("properties")
            if not isinstance(properties, dict) or node.get("additionalProperties", False) is not False:
                return False
            node["required"] = list(properties)
            node["additionalProperties"] = False
            ok = all(visit(child) for child in properties.values())
        if "items" in node:
            ok = ok and visit(node["items"])
        if "anyOf" in node:
            ok = ok and isinstance(node["anyOf"], list) and all(visit(child) for child in node["anyOf"])
        if "$defs" in node:
            ok = ok and all(visit(child) for child in node["$defs"].values())
        return ok

    return schema if visit(schema) and schema.get("type") == "object" else None


def openai_tool(capability: Capability) -> dict:
    """One OpenAI Responses API function tool for a registered capability."""
    description = describe_capability(capability)
    parameters = strict_parameters(description["input_schema"])
    note = AUTONOMY_NOTES[capability.autonomy_level]
    writes = ", ".join(capability.writes) or "nothing"
    return {"type": "function", "name": openai_tool_name(capability.name),
            "description": f"{capability.description} [{capability.autonomy_level}: {note}. Writes: {writes}.]"[:1024],
            "parameters": parameters if parameters is not None else description["input_schema"],
            "strict": parameters is not None}


def _granted(connection) -> dict[str, list[str]]:
    granted: dict[str, list[str]] = {}
    for row in connection.execute("SELECT a.id, j.value FROM agents a, json_each(a.capabilities) j ORDER BY a.rowid"):
        granted.setdefault(row[1], []).append(row[0])
    return granted


def _capability_record(capability: Capability, granted: dict[str, list[str]]) -> dict:
    return {**describe_capability(capability), "registered": True, "tool_name": openai_tool_name(capability.name),
            "agents": granted.get(capability.name, [])}


@capabilities_router.get("")
def list_capabilities(format: Literal["json", "openai-tools"] = "json", agent_id: str | None = None):
    """The capability registry. format=openai-tools exports Responses API function tools (optionally only the
    registered capabilities one agent may run); tool names map '<module>.<operation>' to '<module>-<operation>'."""
    with closing(connect()) as connection:
        granted = _granted(connection)
        agent = _agent_record(connection, _agent_row(connection, agent_id)) if agent_id is not None else None
    names = sorted(CAPABILITIES)
    if agent is not None:
        names = [name for name in names if name in agent["capabilities"]]
    if format == "openai-tools":
        tools = [openai_tool(CAPABILITIES[name]) for name in names]
        return {"format": "openai-tools", "agent_id": agent["id"] if agent else None,
                "agent_status": agent["status"] if agent else None, "tools": tools,
                "name_map": {tool["name"]: name for tool, name in zip(tools, names)}, "total": len(tools),
                "name_rule": "tool name = capability name with its single '.' replaced by '-'"}
    declared = sorted(set(agent["capabilities"] if agent else granted) - set(CAPABILITIES))
    return {"items": [_capability_record(CAPABILITIES[name], granted) for name in names], "total": len(names),
            "unregistered": [{"name": name, "registered": False, "agents": granted.get(name, [])} for name in declared]}


@capabilities_router.get("/{name}")
def get_capability(name: str):
    capability = CAPABILITIES.get(name)
    if capability is None:
        raise HTTPException(404, f"Capability not registered on this server: {name}")
    with closing(connect()) as connection:
        record = _capability_record(capability, _granted(connection))
    return {**record, "openai_tool": openai_tool(capability)}


# Agents ---------------------------------------------------------------------------------------------

class AgentStatusCommand(Command):
    actor: Actor
    rationale: Rationale


class AgentUpdate(Command):
    actor: Actor
    rationale: Rationale
    model: ModelName | None = Field(description="Model for this agent; null uses OPENAI_MODEL at run time")


def _agent_row(connection, agent_id: str):
    row = connection.execute("SELECT * FROM agents WHERE id=? OR slug=?", (agent_id, agent_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Agent not found")
    return row


def _agent_record(connection, row) -> dict:
    agent = decode(row, ("capabilities",))
    deterministic = agent["id"].startswith("system:")
    agent["kind"] = "system" if deterministic else "ai"
    agent["provider"] = "deterministic" if deterministic else "openai"
    agent["effective_model"] = None if deterministic else (agent["model"] or os.getenv("OPENAI_MODEL", "").strip() or None)
    agent["registered_capabilities"] = [name for name in agent["capabilities"] if name in CAPABILITIES]
    agent["unregistered_capabilities"] = [name for name in agent["capabilities"] if name not in CAPABILITIES]
    agent["children"] = [child[0] for child in connection.execute(
        "SELECT id FROM agents WHERE parent_agent_id=? ORDER BY rowid", (agent["id"],))]
    return agent


def _task_counts(connection, vehicle, market) -> dict[str | None, dict[str, int]]:
    clauses, params = _filters(vehicle=vehicle, market=market)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    counts: dict[str | None, dict[str, int]] = {}
    for row in connection.execute(f"SELECT assigned_agent_id, status, count(*) FROM tasks{where} "
                                  "GROUP BY assigned_agent_id, status", params):
        counts.setdefault(row[0], {})[row[1]] = row[2]
    return counts


@agents_router.get("")
def list_agents(department: Literal[DEPARTMENTS] | None = None,  # type: ignore[valid-type]
                status: Literal["active", "paused", "retired"] | None = None, parent_agent_id: str | None = None,
                vehicle: str | None = None, market: str | None = None,
                limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    """The agent registry in hierarchy order, with task counts per status (in the vehicle/market scope if given)."""
    vehicle, market = scope_filters(vehicle, market)
    clauses, params = _filters(department=department, status=status, parent_agent_id=parent_agent_id)
    with closing(connect()) as connection:
        counts = _task_counts(connection, vehicle, market)
        page = _page(connection, "agents", clauses, params, "parent_agent_id IS NOT NULL, rowid", limit, offset,
                     _agent_record)
    for agent in page["items"]:
        agent["task_counts"] = {status: counts.get(agent["id"], {}).get(status, 0) for status in STATUSES}
    return page


@agents_router.get("/{agent_id}")
def get_agent(agent_id: str):
    with closing(connect()) as connection:
        agent = _agent_record(connection, _agent_row(connection, agent_id))
        agent["capability_details"] = [
            {"name": name, "registered": name in CAPABILITIES, "tool_name": openai_tool_name(name),
             "autonomy_level": CAPABILITIES[name].autonomy_level if name in CAPABILITIES else None}
            for name in agent["capabilities"]]
        counts = _task_counts(connection, None, None).get(agent["id"], {})
        agent["task_counts"] = {status: counts.get(status, 0) for status in STATUSES}
        agent["recent_runs"] = [_run_record(connection, row) for row in connection.execute(
            "SELECT * FROM runs WHERE actor=? ORDER BY rowid DESC LIMIT 10", (agent["id"],))]
    return agent


def _change_status(agent_id: str, command: AgentStatusCommand, target: str, allowed_from: tuple[str, ...], action: str):
    with transaction() as connection:
        require_human(command.actor, connection)
        row = _agent_row(connection, agent_id)
        before = _agent_record(connection, row)
        if row["status"] not in allowed_from:
            raise HTTPException(409, f"Agent is {row['status']}; it cannot be {action}")
        timestamp = now()
        cursor = connection.execute("UPDATE agents SET status=?, status_changed_by=?, updated_at=? WHERE id=? AND status=?",
                                    (target, command.actor, timestamp, row["id"], row["status"]))
        if cursor.rowcount != 1:
            raise HTTPException(409, "Agent changed concurrently; reload it")
        after = _agent_record(connection, _agent_row(connection, row["id"]))
        event = audit(connection, "agent", row["id"], f"agent.{action}", command.actor, command.rationale,
                      before=before, after=after)
    return {**after, "audit_event_id": event}


@agents_router.post("/{agent_id}/pause")
def pause_agent(agent_id: str, command: AgentStatusCommand):
    """Human only. A paused agent's tasks cannot execute and the agent cannot create tasks or post messages."""
    return _change_status(agent_id, command, "paused", ("active",), "paused")


@agents_router.post("/{agent_id}/resume")
def resume_agent(agent_id: str, command: AgentStatusCommand):
    """Human only."""
    return _change_status(agent_id, command, "active", ("paused",), "resumed")


@agents_router.post("/{agent_id}/retire")
def retire_agent(agent_id: str, command: AgentStatusCommand):
    """Human only. Retirement is final; the agent and its history stay in the registry."""
    return _change_status(agent_id, command, "retired", ("active", "paused"), "retired")


@agents_router.patch("/{agent_id}")
def update_agent(agent_id: str, command: AgentUpdate):
    """Human only: set the agent's model (null uses OPENAI_MODEL at run time). Deterministic agents have none."""
    with transaction() as connection:
        require_human(command.actor, connection)
        row = _agent_row(connection, agent_id)
        if row["id"].startswith("system:") and command.model is not None:
            raise HTTPException(422, "Deterministic agents have no model")
        before = _agent_record(connection, row)
        connection.execute("UPDATE agents SET model=?, model_changed_by=?, updated_at=? WHERE id=?",
                           (command.model, command.actor, now(), row["id"]))
        after = _agent_record(connection, _agent_row(connection, row["id"]))
        event = audit(connection, "agent", row["id"], "agent.model_changed", command.actor, command.rationale,
                      before=before, after=after)
    return {**after, "audit_event_id": event}


def _acting_agent(connection, actor: str) -> dict | None:
    """The registered agent behind an actor id (None for humans and non-agent system actors). Paused and
    retired agents do not act; unregistered ai: actors have no permissions in the runtime."""
    actor_row = connection.execute("SELECT active FROM actors WHERE id=?", (actor,)).fetchone()
    if actor_row is not None and not actor_row[0]:
        raise HTTPException(403, "inactive actor")
    lowered = actor.strip().lower()
    if not lowered.startswith(("ai:", "system:agent:")):
        return None
    row = connection.execute("SELECT * FROM agents WHERE id=?", (actor,)).fetchone()
    if row is None:
        if lowered.startswith("ai:"):
            raise HTTPException(403, "Unregistered AI actors cannot act in the agent runtime; register the agent first")
        return None
    if row["status"] != "active":
        raise HTTPException(409, f"Agent {actor} is {row['status']}; a human must resume it before it acts")
    return decode(row, ("capabilities",))


def _assignable(connection, agent_id: str, capability: str) -> dict:
    row = _agent_row(connection, agent_id)
    agent = decode(row, ("capabilities",))
    if agent["status"] == "retired":
        raise HTTPException(422, f"Agent {agent['id']} is retired")
    if capability not in agent["capabilities"]:
        raise HTTPException(422, f"Agent {agent['id']} may not run {capability}")
    return agent


# Tasks ----------------------------------------------------------------------------------------------

def _bounded_input(value: dict) -> dict:
    if json_size(value) > MAX_INPUT_BYTES:
        raise ValueError("Task input must be at most 64 KiB of JSON")
    if "actor" in value:
        raise ValueError("Task input must not name an actor; a task runs as its assigned agent or its caller")
    return value


class TaskCreate(Scope):
    topic: Identifier | None = Field(default=None, max_length=100)
    capability: str = Field(pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$", max_length=100)
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    input: dict = Field(default_factory=dict)
    requested_by: Actor
    assigned_agent_id: Identifier | None = None
    parent_task_id: Identifier | None = None
    status: Literal["backlog", "queued"] = "queued"
    priority: int = Field(default=50, ge=0, le=100, strict=True)
    recurrence_days: int | None = Field(default=None, ge=1, le=365, strict=True)
    due_at: str | None = None

    _bounded = field_validator("input")(_bounded_input)
    _due = field_validator("due_at")(_utc)


class TaskUpdate(Command):
    actor: Actor
    expected_revision: int = Field(ge=0, strict=True)
    rationale: Rationale | None = None
    status: Literal["backlog", "queued", "succeeded", "cancelled"] | None = None
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)] | None = None
    priority: int | None = Field(default=None, ge=0, le=100, strict=True)
    assigned_agent_id: Identifier | None = None
    due_at: str | None = None
    input: dict | None = None

    _due = field_validator("due_at")(_utc)

    @field_validator("input")
    @classmethod
    def bounded(cls, value):
        return None if value is None else _bounded_input(value)

    @model_validator(mode="after")
    def changes_something(self):
        if not self.model_fields_set - {"actor", "expected_revision", "rationale"}:
            raise ValueError("Name at least one field to change")
        for name in ("status", "title", "priority", "input"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class TaskExecute(Command):
    actor: Actor
    expected_revision: int | None = Field(default=None, ge=0, strict=True)


class RunDue(Command):
    actor: Actor = SCHEDULER_ACTOR
    limit: int = Field(default=10, ge=1, le=100, strict=True)


def _task_row(connection, task_id: str):
    row = connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Task not found")
    return row


def _task_record(_connection, row) -> dict:
    task = decode(row, ("input",))
    for key in ("position", "agent_department"):
        task.pop(key, None)
    task["capability_registered"] = task["capability"] in CAPABILITIES
    task["recurring"] = task["recurrence_days"] is not None
    return task


def _card(row) -> dict:
    card = _task_record(None, row)
    card.pop("input")
    return card


def _effective_input(capability: Capability, vehicle: str, market: str, raw: dict) -> dict:
    """The capability payload: the task scope fills missing vehicle/market fields and must match given ones."""
    fields = capability.input_model.model_fields
    payload = dict(raw)
    scope = {"vehicle": vehicle, "market": market}
    for key in scope:
        if key in fields:
            payload.setdefault(key, scope[key])
    try:
        validated = capability.input_model.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(422, {"capability": capability.name, "errors": _validation_errors(exc)}) from None
    for key, value in scope.items():
        if key in fields and getattr(validated, key) != value:
            raise HTTPException(422, f"Task input {key} {getattr(validated, key)!r} differs from the task scope {value!r}")
    # ID-only capabilities must not smuggle another scope into a task.
    if capability.name == "pipeline.generate_requirements":
        with closing(connect()) as connection:
            analysis = connection.execute("SELECT vehicle, market FROM analysis_runs WHERE id=?",
                                          (payload.get("analysis_id"),)).fetchone()
        if analysis is None:
            raise HTTPException(422, "Analysis not found")
        if tuple(analysis) != (vehicle, market):
            raise HTTPException(422, "Analysis belongs to another task scope")
    return payload


def _registry_assignment(connection, capability: str) -> str | None:
    """Auto-assign a task to the single non-retired agent granted its capability; otherwise leave it unassigned."""
    rows = connection.execute("SELECT a.id FROM agents a WHERE a.status <> 'retired' AND EXISTS "
                              "(SELECT 1 FROM json_each(a.capabilities) j WHERE j.value=?) ORDER BY a.rowid",
                              (capability,)).fetchall()
    return rows[0][0] if len(rows) == 1 else None


def _insert_task(connection, values: dict, actor: str, rationale: str, metadata: dict) -> tuple[dict, str]:
    timestamp = now()
    task_id = new_id()
    connection.execute(
        "INSERT INTO tasks (id, vehicle, market, topic, capability, title, input, requested_by, assigned_agent_id, "
        "parent_task_id, status, priority, recurrence_days, due_at, updated_by, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (task_id, values["vehicle"], values["market"], values["topic"], values["capability"], values["title"],
         encode(values["input"]), values["requested_by"], values["assigned_agent_id"], values["parent_task_id"],
         values["status"], values["priority"], values["recurrence_days"], values["due_at"], actor, timestamp, timestamp))
    record = _task_record(connection, _task_row(connection, task_id))
    return record, audit(connection, "task", task_id, "task.created", actor, rationale, after=record, metadata=metadata)


@tasks_router.post("", status_code=201)
def create_task(command: TaskCreate):
    """Queue (or backlog) a capability execution. Registered capabilities validate the input now; an
    unregistered one is accepted and fails visibly when executed. Recurring tasks are due immediately unless
    due_at is given."""
    values = command.model_dump()
    with transaction() as connection:
        _acting_agent(connection, command.requested_by)
        capability = CAPABILITIES.get(command.capability)
        if capability is not None:
            values["input"] = _effective_input(capability, command.vehicle, command.market, command.input)
        if command.assigned_agent_id is not None:
            values["assigned_agent_id"], assignment = _assignable(connection, command.assigned_agent_id, command.capability)["id"], "explicit"
        else:
            values["assigned_agent_id"] = _registry_assignment(connection, command.capability)
            assignment = "registry" if values["assigned_agent_id"] else "unassigned"
        if command.parent_task_id is not None:
            parent = _task_row(connection, command.parent_task_id)
            if (parent["vehicle"], parent["market"]) != (command.vehicle, command.market):
                raise HTTPException(422, "A child task must share its parent's vehicle and market")
        if command.recurrence_days is not None and values["due_at"] is None:
            values["due_at"] = now()
        record, event = _insert_task(connection, values, command.requested_by, f"Created task: {command.title}",
                                     {"assignment": assignment, "capability_registered": capability is not None})
    return {**record, "audit_event_id": event}


@tasks_router.get("")
def list_tasks(vehicle: str | None = None, market: str | None = None,
               status: Literal[STATUSES] | None = None,  # type: ignore[valid-type]
               capability: str | None = None, assigned_agent_id: str | None = None, parent_task_id: str | None = None,
               requested_by: str | None = None, recurring: bool | None = None,
               limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    vehicle, market = scope_filters(vehicle, market)
    clauses, params = _filters(vehicle=vehicle, market=market, status=status, capability=capability,
                               assigned_agent_id=assigned_agent_id, parent_task_id=parent_task_id, requested_by=requested_by)
    if recurring is not None:
        clauses.append("recurrence_days IS NOT NULL" if recurring else "recurrence_days IS NULL")
    with closing(connect()) as connection:
        return _page(connection, "tasks", clauses, params, "priority DESC, created_at, id", limit, offset, _task_record)


@tasks_router.get("/board")
def task_board(vehicle: str | None = None, market: str | None = None,
               group_by: Literal["status", "agent", "department"] = "status",
               limit: int = Query(50, ge=1, le=500, description="Cards per column")):
    """Kanban columns with counts: every status, every agent (plus unassigned) or every department."""
    vehicle, market = scope_filters(vehicle, market)
    clauses, params = _filters(**{"t.vehicle": vehicle, "t.market": market})
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    key = {"status": "t.status", "agent": "t.assigned_agent_id", "department": "a.department"}[group_by]
    with closing(connect()) as connection:
        rows = connection.execute(
            f"SELECT * FROM (SELECT t.*, a.department AS agent_department, ROW_NUMBER() OVER (PARTITION BY {key} "
            f"ORDER BY t.priority DESC, coalesce(t.due_at, t.created_at), t.created_at, t.id) AS position "
            f"FROM tasks t LEFT JOIN agents a ON a.id = t.assigned_agent_id{where}) WHERE position <= ?",
            [*params, limit]).fetchall()
        grouped = connection.execute(f"SELECT {key}, t.status, count(*) FROM tasks t LEFT JOIN agents a "
                                     f"ON a.id = t.assigned_agent_id{where} GROUP BY {key}, t.status", params).fetchall()
        agents = [_agent_record(connection, row) for row in connection.execute(
            "SELECT * FROM agents ORDER BY parent_agent_id IS NOT NULL, rowid")]
    counts: dict = {}
    for group, status, n in grouped:
        counts.setdefault(group, {})[status] = n
    cards: dict = {}
    for row in rows:
        group = {"status": row["status"], "agent": row["assigned_agent_id"], "department": row["agent_department"]}[group_by]
        cards.setdefault(group, []).append(_card(row))
    if group_by == "status":
        columns = [{"key": status, "label": STATUS_LABELS[status]} for status in STATUSES]
    elif group_by == "agent":
        columns = [{"key": None, "label": "Unassigned"}] + [
            {"key": agent["id"], "label": agent["display_name"], "agent": {
                field: agent[field] for field in ("id", "slug", "department", "autonomy_level", "status", "parent_agent_id")}}
            for agent in agents if agent["status"] != "retired" or agent["id"] in counts]
    else:
        columns = [{"key": None, "label": "Unassigned"}] + [
            {"key": department, "label": department.replace("_", " ").capitalize()} for department in DEPARTMENTS]
    for column in columns:
        group_counts = counts.get(column["key"], {})
        column.update(count=sum(group_counts.values()),
                      status_counts={status: group_counts.get(status, 0) for status in STATUSES},
                      items=cards.get(column["key"], []))
    totals = {status: sum(group.get(status, 0) for group in counts.values()) for status in STATUSES}
    return {"group_by": group_by, "vehicle": vehicle, "market": market, "total": sum(totals.values()),
            "status_counts": totals, "columns": columns, "limit": limit}


def _stale_cutoff(timestamp: str) -> str:
    return _after(timestamp, -STALE_TASK_SECONDS)


def recover_stale_tasks(actor: str = RUNTIME_ACTOR) -> list[dict]:
    """Fail running tasks that recorded no outcome within TASK_STALE_SECONDS (the worker stopped). A late
    worker's outcome is then fenced by the revision guard; its runs stay recorded."""
    recovered = []
    with transaction() as connection:
        timestamp = now()
        for row in connection.execute("SELECT * FROM tasks WHERE status='running' AND (started_at IS NULL OR started_at < ?)",
                                      (_stale_cutoff(timestamp),)).fetchall():
            error = (f"Interrupted: no outcome was recorded within {STALE_TASK_SECONDS:g} s of the claim at "
                     f"{row['started_at']}; inspect its runs and requeue it")
            before = _task_record(connection, row)
            active_runs = connection.execute("SELECT id FROM runs WHERE task_id=? AND status='running' ORDER BY rowid",
                                             (row["id"],)).fetchall()
            for active_run in active_runs:
                connection.execute("UPDATE runs SET status='failed', outputs=NULL, error=?, finished_at=? WHERE id=?",
                                   (error, timestamp, active_run["id"]))
                audit(connection, "run", active_run["id"], "run.failed", RUNTIME_ACTOR, error,
                      after={"status": "failed", "task_id": row["id"], "error": error})
            if active_runs:
                last_run = active_runs[-1]["id"]
            else:
                try:
                    with record_run(connection, row["capability"], RUNTIME_ACTOR, RUNTIME_METHOD,
                                    decode(row, ("input",))["input"], row["vehicle"], row["market"], row["id"]) as recovery:
                        recovery.metrics["recovered"] = True
                        raise RuntimeError(error)
                except RuntimeError:
                    pass
                last_run = recovery.id
            connection.execute("UPDATE tasks SET status='failed', error=?, finished_at=?, updated_by=?, updated_at=?, "
                               "last_run_id=?, revision=revision+1 WHERE id=? AND revision=?",
                               (error, timestamp, RUNTIME_ACTOR, timestamp, last_run, row["id"], row["revision"]))
            after = _task_record(connection, _task_row(connection, row["id"]))
            audit(connection, "task", row["id"], "task.interrupted", RUNTIME_ACTOR, error, before=before, after=after,
                  metadata={"recovered_by": actor})
            recovered.append({"task_id": row["id"], "error": error})
    return recovered


def _run_actor(connection, task, trigger: str) -> str:
    """Who the capability runs as: the assigned agent, else the caller. Checks pause state and hierarchy."""
    trigger_agent = _acting_agent(connection, trigger)
    if task["assigned_agent_id"] is None:
        return trigger
    agent = decode(_agent_row(connection, task["assigned_agent_id"]), ("capabilities",))
    if agent["status"] != "active":
        raise HTTPException(409, f"Agent {agent['id']} is {agent['status']}; a human must resume it before its tasks execute")
    if trigger_agent is not None and trigger_agent["id"] not in (agent["id"], agent["parent_agent_id"]):
        raise HTTPException(403, f"Agent {trigger} may not execute tasks assigned to {agent['id']}")
    return agent["id"]


def _spawn_occurrence(connection, template, actor: str, advance: bool) -> dict:
    """One occurrence (a child task) of a recurring task. Advancing the schedule is the revision-guarded claim
    that makes run-due safe to call concurrently."""
    timestamp = now()
    if advance:
        next_due = _next_due(template["due_at"], template["recurrence_days"], timestamp)
        cursor = connection.execute("UPDATE tasks SET due_at=?, updated_by=?, updated_at=?, revision=revision+1 "
                                    "WHERE id=? AND revision=? AND status='queued'",
                                    (next_due, actor, timestamp, template["id"], template["revision"]))
        if cursor.rowcount != 1:
            raise HTTPException(409, "Recurring task was claimed or changed by another worker")
        audit(connection, "task", template["id"], "task.rescheduled", actor, "Scheduled the next occurrence",
              before={"due_at": template["due_at"]}, after={"due_at": next_due})
    values = {key: template[key] for key in ("vehicle", "market", "topic", "capability", "assigned_agent_id", "priority")}
    scheduled = template["due_at"] if advance else timestamp
    values.update(title=f"{template['title']} ({scheduled[:10]})", input=decode(template, ("input",))["input"],
                  requested_by=actor, parent_task_id=template["id"], status="queued", recurrence_days=None, due_at=None)
    record, _ = _insert_task(connection, values, actor, f"Occurrence of recurring task {template['id']}",
                             {"occurrence_of": template["id"], "scheduled_for": scheduled})
    return record


def _claim(connection, task: dict, trigger: str, run_actor: str) -> dict:
    if task["status"] not in EXECUTABLE:
        hint = {"running": "it is already running", "backlog": "move it to queued first",
                "awaiting_human": "it waits for a human decision; requeue it to run again"}.get(task["status"], "it is final")
        raise HTTPException(409, f"Task is {task['status']}; {hint}")
    timestamp = now()
    cursor = connection.execute("UPDATE tasks SET status='running', error=NULL, started_at=?, finished_at=NULL, "
                                "updated_by=?, updated_at=?, revision=revision+1 WHERE id=? AND revision=? AND status=?",
                                (timestamp, trigger, timestamp, task["id"], task["revision"], task["status"]))
    if cursor.rowcount != 1:
        raise HTTPException(409, "Task was claimed or changed by another worker; reload it")
    marker = connection.execute("SELECT coalesce(max(rowid), 0) FROM runs").fetchone()[0]
    claimed = _task_record(connection, _task_row(connection, task["id"]))
    audit(connection, "task", task["id"], "task.started", trigger, f"Executing {task['capability']} as {run_actor}",
          before=task, after=claimed, metadata={"run_actor": run_actor, "triggered_by": trigger})
    return {"task": claimed, "run_actor": run_actor, "trigger": trigger, "marker": marker}


def _record_runtime_run(task: dict, actor: str, payload: dict, outputs: dict | None, error: BaseException | None) -> None:
    """Record the run a capability did not record itself, so last_run_id always points at the attempt."""
    try:
        with record_run(None, task["capability"], actor, RUNTIME_METHOD, payload, task["vehicle"], task["market"],
                        task["id"]) as run:
            run.metrics["recorded_by"] = "agent-runtime"
            if error is not None:
                raise error
            run.outputs.update(outputs or {})
    except Exception as exc:
        if exc is not error:
            raise


def _run_claimed(claim: dict) -> dict:
    task, actor = claim["task"], claim["run_actor"]
    capability = CAPABILITIES.get(task["capability"])
    payload, result, failure = task["input"], None, None
    try:
        if capability is None:
            raise CapabilityUnavailable(f"Capability {task['capability']} is not registered on this server; "
                                        "its pod may not be merged yet")
        with closing(connect()) as connection:
            agent = connection.execute("SELECT capabilities FROM agents WHERE id=?", (actor,)).fetchone()
        if agent is not None and task["capability"] not in json.loads(agent[0]):
            raise CapabilityNotPermitted(f"Agent {actor} may not run {task['capability']}")
        payload = _effective_input(capability, task["vehicle"], task["market"], task["input"])
        if "actor" in capability.input_model.model_fields:
            payload["actor"] = actor
        result = run_capability(task["capability"], payload, actor, task_id=task["id"])
    except Exception as exc:  # the task records every failure; nothing propagates as a crash
        failure = exc
    with closing(connect()) as connection:
        run_ids = [row[0] for row in connection.execute("SELECT id FROM runs WHERE task_id=? AND rowid>? ORDER BY rowid",
                                                        (task["id"], claim["marker"]))]
    with closing(connect()) as connection:
        has_failed_run = connection.execute(
            "SELECT 1 FROM runs WHERE task_id=? AND rowid>? AND status='failed'",
            (task["id"], claim["marker"])).fetchone() is not None
    if not run_ids or (failure is not None and not has_failed_run):
        try:
            _record_runtime_run(task, actor, payload, result["outputs"] if result else None, failure)
        except Exception as exc:
            failure = failure or exc
        with closing(connect()) as connection:
            run_ids = [row[0] for row in connection.execute(
                "SELECT id FROM runs WHERE task_id=? AND rowid>? ORDER BY rowid", (task["id"], claim["marker"]))]
    error = _error_text(failure) if failure is not None else None
    awaiting = bool(result and result["awaiting_human"]) and error is None
    status = "failed" if error else "awaiting_human" if awaiting else "succeeded"
    last_run_id = run_ids[-1] if run_ids else None
    with transaction() as connection:
        timestamp = now()
        cursor = connection.execute(
            "UPDATE tasks SET status=?, last_run_id=coalesce(?, last_run_id), error=?, finished_at=?, updated_by=?, "
            "updated_at=?, revision=revision+1 WHERE id=? AND revision=? AND status='running'",
            (status, last_run_id, error, timestamp, actor, timestamp, task["id"], task["revision"]))
        if cursor.rowcount != 1:
            raise HTTPException(409, f"Task changed while it ran (runs {run_ids} are recorded); reload it")
        record = _task_record(connection, _task_row(connection, task["id"]))
        event = audit(connection, "task", task["id"], f"task.{status}", actor,
                      error or ("Proposal waits at a human gate" if awaiting else f"{task['capability']} succeeded"),
                      before=task, after=record, metadata={"run_ids": run_ids, "triggered_by": claim["trigger"]})
    return {**record, "run_id": last_run_id, "run_ids": run_ids, "audit_event_id": event, "awaiting_human": awaiting,
            "outputs": result["outputs"] if result and not error else None}


def execute(task_id: str, trigger: str, expected_revision: int | None = None, scheduled: bool = False) -> dict:
    """Claim and run one task (a recurring task runs as a new occurrence). HTTP errors mean nothing ran."""
    with transaction() as connection:
        row = _task_row(connection, task_id)
        task = decode(row, ("input",))
        if expected_revision is not None and task["revision"] != expected_revision:
            raise HTTPException(409, "Task changed; reload it and use its current revision")
        if scheduled and (task["status"] != "queued" or task["due_at"] is None or task["due_at"] > now()):
            raise HTTPException(409, "Task is no longer due")
        run_actor = _run_actor(connection, row, trigger)
        if task["recurrence_days"] is not None:
            if task["status"] != "queued":
                raise HTTPException(409, f"Recurring task is {task['status']}; queue it to resume its schedule")
            occurrence = _spawn_occurrence(connection, row, trigger, advance=scheduled)
            claim = _claim(connection, occurrence, trigger, run_actor)
            claim["occurrence_of"] = task["id"]
        else:
            claim = _claim(connection, task, trigger, run_actor)
    result = _run_claimed(claim)
    result["occurrence_of"] = claim.get("occurrence_of")
    return result


@tasks_router.post("/run-due")
def run_due(command: RunDue = RunDue()):
    """Scheduler entry point: fail stale running tasks, then execute queued tasks whose due_at has passed
    (recurring tasks spawn one occurrence and advance to their next slot). Safe to call concurrently."""
    with closing(connect()) as connection:
        _acting_agent(connection, command.actor)
    recovered = recover_stale_tasks(command.actor)
    timestamp = now()
    with closing(connect()) as connection:
        due = connection.execute("SELECT id, revision FROM tasks WHERE status='queued' AND due_at IS NOT NULL AND due_at<=? "
                                 "ORDER BY priority DESC, due_at, created_at, id LIMIT ?",
                                 (timestamp, command.limit)).fetchall()
    executed, skipped = [], []
    for task_id, revision in due:
        try:
            result = execute(task_id, command.actor, expected_revision=revision, scheduled=True)
        except HTTPException as exc:
            skipped.append({"task_id": task_id, "status_code": exc.status_code, "reason": _error_text(exc)})
            continue
        executed.append({"task_id": result["id"], "occurrence_of": result["occurrence_of"], "status": result["status"],
                         "run_id": result["run_id"], "error": result["error"]})
    return {"now": timestamp, "actor": command.actor, "recovered": recovered, "executed": executed,
            "skipped": skipped, "count": len(executed)}


@tasks_router.get("/{task_id}")
def get_task(task_id: str):
    with closing(connect()) as connection:
        task = _task_record(connection, _task_row(connection, task_id))
        task["runs"] = [_run_record(connection, row) for row in connection.execute(
            "SELECT * FROM runs WHERE task_id=? ORDER BY rowid DESC LIMIT 50", (task_id,))]
        task["children"] = [_card(row) for row in connection.execute(
            "SELECT * FROM tasks WHERE parent_task_id=? ORDER BY created_at DESC, id LIMIT 100", (task_id,))]
        task["threads"] = [dict(row) for row in connection.execute(
            "SELECT * FROM threads WHERE entity_type='task' AND entity_id=? ORDER BY created_at", (task_id,))]
    return task


@tasks_router.patch("/{task_id}")
def update_task(task_id: str, command: TaskUpdate):
    """Edit or move a task with optimistic `expected_revision` (stale -> 409). Cancelling and accepting a
    proposal that waits at a human gate (awaiting_human -> succeeded) are human-only and need a rationale."""
    fields = command.model_fields_set - {"actor", "expected_revision", "rationale"}
    with transaction() as connection:
        row = _task_row(connection, task_id)
        task = _task_record(connection, row)
        if task["revision"] != command.expected_revision:
            raise HTTPException(409, "Task changed; reload it and use its current revision")
        _acting_agent(connection, command.actor)
        if task["status"] == "running":
            raise HTTPException(409, "Task is running; wait for its outcome")
        if task["status"] in ("succeeded", "cancelled"):
            raise HTTPException(409, f"Task is {task['status']} and final")
        values = {name: getattr(command, name) for name in fields}
        action = "task.updated"
        if values.get("status", task["status"]) != task["status"]:
            target = values["status"]
            if target not in TRANSITIONS[task["status"]]:
                raise HTTPException(409, f"A {task['status']} task cannot move to {target}")
            if target == "cancelled" or target == "succeeded":
                require_human(command.actor, connection)
                if command.rationale is None:
                    raise HTTPException(422, "Cancelling or accepting a task needs a rationale")
            action = STATUS_ACTIONS[target]
        else:
            values.pop("status", None)
        if values.get("assigned_agent_id") is not None:
            values["assigned_agent_id"] = _assignable(connection, values["assigned_agent_id"], task["capability"])["id"]
        if "input" in values:
            if task["status"] not in ("backlog", "queued", "failed"):
                raise HTTPException(409, f"The input of a {task['status']} task is fixed")
            capability = CAPABILITIES.get(task["capability"])
            if capability is not None:
                values["input"] = _effective_input(capability, task["vehicle"], task["market"], values["input"])
            values["input"] = encode(values["input"])
        if "due_at" in values and values["due_at"] is None and task["recurrence_days"] is not None:
            raise HTTPException(422, "A recurring task needs a due_at")
        if not values:
            raise HTTPException(422, "Nothing changes")
        timestamp = now()
        assignments = ", ".join(f"{name}=?" for name in values)
        connection.execute(f"UPDATE tasks SET {assignments}, updated_by=?, updated_at=?, revision=revision+1 WHERE id=?",
                           [*values.values(), command.actor, timestamp, task_id])
        record = _task_record(connection, _task_row(connection, task_id))
        event = audit(connection, "task", task_id, action, command.actor,
                      command.rationale or f"Updated task: {', '.join(sorted(values))}", before=task, after=record)
    return {**record, "audit_event_id": event}


@tasks_router.post("/{task_id}/execute")
def execute_task(task_id: str, command: TaskExecute):
    """Run a queued (or failed, as a retry) task now through run_capability; recurring tasks run a new
    occurrence without moving their schedule. Capability failures return 200 with the task `failed`."""
    return execute(task_id, command.actor, command.expected_revision)


# Runs -----------------------------------------------------------------------------------------------

def _run_record(_connection, row) -> dict:
    run = decode(row, ("inputs", "outputs", "metrics"))
    method = run["method_version"]
    ai = method.startswith("openai:")
    run["provider"] = "openai" if ai else "deterministic"
    run["model"] = method.split(":")[1] if ai and method.count(":") >= 2 else None
    run["duration_ms"] = run["metrics"].get("duration_ms") if isinstance(run["metrics"], dict) else None
    return run


@runs_router.get("")
def list_runs(vehicle: str | None = None, market: str | None = None, capability: str | None = None,
              task_id: str | None = None, actor: str | None = None,
              status: Literal["running", "succeeded", "failed"] | None = None,
              limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    """Every capability execution, newest first, with provider/model labels for AI-generated outputs."""
    vehicle, market = scope_filters(vehicle, market)
    clauses, params = _filters(vehicle=vehicle, market=market, capability=capability, task_id=task_id, actor=actor,
                               status=status)
    with closing(connect()) as connection:
        return _page(connection, "runs", clauses, params, "rowid DESC", limit, offset, _run_record)


@runs_router.get("/{run_id}")
def get_run(run_id: str):
    with closing(connect()) as connection:
        row = connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Run not found")
        run = _run_record(connection, row)
        task = connection.execute("SELECT * FROM tasks WHERE id=?", (run["task_id"],)).fetchone() if run["task_id"] else None
        run["task"] = _card(task) if task is not None else None
        run["audit_events"] = [decode(event, ("before_state", "after_state", "metadata")) for event in connection.execute(
            "SELECT * FROM audit_events WHERE entity_type='run' AND entity_id=? ORDER BY sequence", (run_id,))]
        run["messages"] = [decode(message, ("payload",)) for message in connection.execute(
            "SELECT * FROM messages WHERE run_id=? ORDER BY created_at, rowid", (run_id,))]
    return run


# Threads and messages -------------------------------------------------------------------------------

MessageBody = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000)]


def _bounded_payload(value: dict) -> dict:
    if json_size(value) > MAX_INPUT_BYTES:
        raise ValueError("Message payload must be at most 64 KiB of JSON")
    return value


class ThreadCreate(Command):
    vehicle: Identifier | None = Field(default=None, max_length=50)
    market: Identifier | None = Field(default=None, max_length=50)
    kind: Literal["agent", "human", "request", "review"]
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    entity_type: Literal[tuple(ENTITY_TABLES)] | None = None  # type: ignore[valid-type]
    entity_id: Identifier | None = None
    created_by: Actor
    body: MessageBody | None = None
    payload: dict = Field(default_factory=dict)

    _payload = field_validator("payload")(_bounded_payload)

    @model_validator(mode="after")
    def linked_entity(self):
        if (self.entity_type is None) != (self.entity_id is None):
            raise ValueError("entity_type and entity_id are given together")
        if self.body is None and self.payload:
            raise ValueError("A payload belongs to a first message body")
        return self


class MessageCreate(Command):
    author: Actor
    role: Literal["human", "agent", "system", "tool"]
    body: MessageBody
    payload: dict = Field(default_factory=dict, description="Cited ids and tool call/result JSON")
    run_id: Identifier | None = None

    _payload = field_validator("payload")(_bounded_payload)


class ThreadUpdate(Command):
    actor: Actor
    status: Literal["open", "closed"]
    rationale: Rationale | None = None


def _role_for(author: str) -> str:
    lowered = author.lower()
    return "agent" if lowered.startswith(("ai:", "system:agent:")) else "system" if lowered.startswith("system:") else "human"


def _role_allowed(author: str, role: str) -> bool:
    """Authors cannot speak in another actor class: only humans post human messages, only agents agent ones."""
    natural = _role_for(author)
    return role == natural or (role == "tool" and natural != "human")


def _thread_row(connection, thread_id: str):
    row = connection.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Thread not found")
    return row


def _thread_record(connection, row) -> dict:
    thread = dict(row)
    count, last = connection.execute("SELECT count(*), max(created_at) FROM messages WHERE thread_id=?",
                                     (thread["id"],)).fetchone()
    thread.update(message_count=count, last_message_at=last)
    return thread


def _add_message(connection, thread: dict, command: MessageCreate) -> tuple[dict, str]:
    if thread["status"] != "open":
        raise HTTPException(409, "Thread is closed; reopen it to add messages")
    _acting_agent(connection, command.author)
    if not _role_allowed(command.author, command.role):
        raise HTTPException(422, f"{command.author} cannot post a {command.role} message")
    if command.run_id is not None and connection.execute("SELECT 1 FROM runs WHERE id=?", (command.run_id,)).fetchone() is None:
        raise HTTPException(422, "run_id does not name a recorded run")
    message_id = new_id()
    connection.execute("INSERT INTO messages (id, thread_id, author, role, body, payload, run_id, created_at) "
                       "VALUES (?,?,?,?,?,?,?,?)", (message_id, thread["id"], command.author, command.role, command.body,
                                                    encode(command.payload), command.run_id, now()))
    message = decode(connection.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone(), ("payload",))
    event = audit(connection, "thread", thread["id"], "thread.message_added", command.author,
                  f"{command.role} message added", after=message)
    return message, event


@threads_router.post("", status_code=201)
def create_thread(command: ThreadCreate):
    """An internal working thread, optionally linked to a task, requirement, request, conflict or run. Nothing
    in a thread is ever sent outside the system."""
    with transaction() as connection:
        _acting_agent(connection, command.created_by)
        vehicle, market = command.vehicle, command.market
        if vehicle is not None or market is not None:
            scope = Scope(vehicle=vehicle or "G60", market=market or "US")
            vehicle, market = scope.vehicle if vehicle else None, scope.market if market else None
        if command.entity_type is not None:
            entity = connection.execute(f"SELECT * FROM {ENTITY_TABLES[command.entity_type]} WHERE id=?",
                                        (command.entity_id,)).fetchone()
            if entity is None:
                raise HTTPException(404, f"Linked {command.entity_type} not found")
            for key in ("vehicle", "market"):
                linked = entity[key] if key in entity.keys() else None
                given = vehicle if key == "vehicle" else market
                if given is not None and linked is not None and given != linked:
                    raise HTTPException(422, f"Thread {key} {given!r} differs from the linked {command.entity_type}'s {linked!r}")
            vehicle = vehicle or (entity["vehicle"] if "vehicle" in entity.keys() else None)
            market = market or (entity["market"] if "market" in entity.keys() else None)
        thread_id = new_id()
        connection.execute("INSERT INTO threads (id, vehicle, market, kind, subject, entity_type, entity_id, created_by, "
                           "created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                           (thread_id, vehicle, market, command.kind, command.subject, command.entity_type,
                            command.entity_id, command.created_by, now()))
        thread = _thread_record(connection, _thread_row(connection, thread_id))
        event = audit(connection, "thread", thread_id, "thread.created", command.created_by, command.subject, after=thread)
        message = None
        if command.body is not None:
            message, _ = _add_message(connection, thread, MessageCreate(
                author=command.created_by, role=_role_for(command.created_by), body=command.body, payload=command.payload))
            thread = _thread_record(connection, _thread_row(connection, thread_id))
    return {**thread, "messages": [message] if message else [], "audit_event_id": event}


@threads_router.get("")
def list_threads(vehicle: str | None = None, market: str | None = None,
                 kind: Literal["agent", "human", "request", "review"] | None = None,
                 entity_type: str | None = None, entity_id: str | None = None,
                 status: Literal["open", "closed"] | None = None, created_by: str | None = None,
                 limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    vehicle, market = scope_filters(vehicle, market)
    clauses, params = _filters(vehicle=vehicle, market=market, kind=kind, entity_type=entity_type, entity_id=entity_id,
                               status=status, created_by=created_by)
    with closing(connect()) as connection:
        return _page(connection, "threads", clauses, params, "created_at DESC, rowid DESC", limit, offset, _thread_record)


@threads_router.get("/{thread_id}")
def get_thread(thread_id: str, limit: int = Query(200, ge=1, le=1000), offset: int = Query(0, ge=0)):
    with closing(connect()) as connection:
        thread = _thread_record(connection, _thread_row(connection, thread_id))
        thread["messages"] = [decode(row, ("payload",)) for row in connection.execute(
            "SELECT * FROM messages WHERE thread_id=? ORDER BY created_at, rowid LIMIT ? OFFSET ?",
            (thread_id, limit, offset))]
    return {**thread, "limit": limit, "offset": offset}


@threads_router.post("/{thread_id}/messages", status_code=201)
def post_message(thread_id: str, command: MessageCreate):
    """Append a message (append-only). Roles follow the author: human, agent (ai:/system:agent:), system, or
    tool output from an agent or system actor."""
    with transaction() as connection:
        thread = dict(_thread_row(connection, thread_id))
        message, event = _add_message(connection, thread, command)
    return {**message, "audit_event_id": event}


@threads_router.patch("/{thread_id}")
def update_thread(thread_id: str, command: ThreadUpdate):
    """Close or reopen a thread. Its messages never change."""
    with transaction() as connection:
        _acting_agent(connection, command.actor)
        row = _thread_row(connection, thread_id)
        if row["status"] == command.status:
            raise HTTPException(409, f"Thread is already {command.status}")
        before = _thread_record(connection, row)
        connection.execute("UPDATE threads SET status=? WHERE id=?", (command.status, thread_id))
        after = _thread_record(connection, _thread_row(connection, thread_id))
        event = audit(connection, "thread", thread_id, "thread.closed" if command.status == "closed" else "thread.reopened",
                      command.actor, command.rationale or f"Thread {command.status}", before=before, after=after)
    return {**after, "audit_event_id": event}


# Pipeline capabilities (existing operations wrapped with record_run) --------------------------------

Provider = Literal["openai", "deterministic"]


class AnalyzeInput(Scope):
    provider: Provider = Field(default="openai", description="'deterministic' is the labelled keyword baseline")
    source_ids: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]] | None = Field(
        default=None, min_length=1, max_length=1000, description="Restrict analysis to these sources in scope")


class GenerateInput(Command):
    analysis_id: Identifier = Field(description="analysis_id returned by pipeline.analyze")


class AssessInput(Scope):
    provider: Provider = Field(default="openai", description="'deterministic' is the labelled keyword baseline")


def _analysis_method(provider: str) -> str:
    if provider == "openai":
        return f"openai:{os.getenv('OPENAI_MODEL', '').strip() or 'unconfigured'}:{PROMPT_VERSION}"
    return REFERENCE_METHOD


def _analysis_summary(analysis: dict) -> dict:
    return {"analysis_id": analysis["id"], "provider": analysis["provider"], "model": analysis["model"],
            "prompt_version": analysis["prompt_version"], "cached": analysis["cached"],
            "evidence_count": len(analysis["evidence_ids"]),
            "analyzed_evidence_count": len(analysis["result"].get("analyzed_evidence_ids", [])),
            "finding_ids": [finding["id"] for finding in analysis["findings"]],
            "proposal_count": len(analysis["result"]["proposals"]), "warnings": analysis["warnings"]}


def _generation_summary(generation: dict) -> dict:
    requirements = []
    for requirement in generation["requirements"]:
        version = requirement["current_version"] or {}
        score = version.get("score") or {}
        requirements.append({"id": requirement["id"], "topic": requirement["topic"], "status": requirement["status"],
                             "current_version_id": requirement["current_version_id"], "score_id": score.get("id"),
                             "score_total": score.get("total"), "needs_review": requirement["needs_review"]})
    return {"analysis_id": generation["run_id"], "created": generation["created"], "updated": generation["updated"],
            "unchanged": generation["unchanged"], "unchanged_reasons": generation["unchanged_reasons"],
            "requirements": requirements}


def _analyze(command: AnalyzeInput, actor: str) -> dict:
    with record_run(None, "pipeline.analyze", actor, _analysis_method(command.provider), command.model_dump(),
                    command.vehicle, command.market) as run:
        analysis = run_analysis(AnalysisRequest(vehicle=command.vehicle, market=command.market, provider=command.provider,
                                                source_ids=command.source_ids, actor=actor))
        run.outputs.update(_analysis_summary(analysis))
        run.metrics.update(findings=len(analysis["findings"]), evidence=run.outputs["evidence_count"],
                           cached=analysis["cached"])
    return {**run.outputs, "run_id": run.id, "awaiting_human": False}


def _generate(command: GenerateInput, actor: str) -> dict:
    with closing(connect()) as connection:
        scope = connection.execute("SELECT vehicle, market FROM analysis_runs WHERE id=?", (command.analysis_id,)).fetchone()
    with record_run(None, "pipeline.generate_requirements", actor, GENERATE_METHOD, command.model_dump(),
                    *(tuple(scope) if scope else (None, None))) as run:
        run.outputs.update(_generation_summary(generate_requirements(GenerateRequest(run_id=command.analysis_id,
                                                                                     actor=actor))))
        run.metrics.update({key: len(run.outputs[key]) for key in ("created", "updated", "unchanged")})
    proposals = bool(run.outputs["created"] or run.outputs["updated"])
    return {**run.outputs, "run_id": run.id, "awaiting_human": proposals}


def _assess(command: AssessInput, actor: str) -> dict:
    with record_run(None, "pipeline.assess_updates", actor, _analysis_method(command.provider), command.model_dump(),
                    command.vehicle, command.market) as run:
        result = assess_update(AnalysisRequest(vehicle=command.vehicle, market=command.market, provider=command.provider,
                                               actor=actor))
        reviews = [review["id"] for review in result["reviews"]]
        run.outputs.update(analysis=_analysis_summary(result["analysis"]),
                           generation=_generation_summary(result["generation"]), open_review_ids=reviews)
        run.metrics.update(open_reviews=len(reviews), findings=len(result["analysis"]["findings"]))
    generation = run.outputs["generation"]
    return {**run.outputs, "run_id": run.id, "awaiting_human": bool(generation["created"] or generation["updated"] or reviews)}


PIPELINE_CAPABILITIES = (
    Capability("pipeline.analyze", "Analyze all evidence (or selected sources) in a vehicle and market scope into "
               "source-linked findings and requirement proposals. Cached by evidence and prompt version.",
               AnalyzeInput, _analyze, "A1", ("analysis_runs", "findings", "finding_evidence")),
    Capability("pipeline.generate_requirements", "Build and score requirement proposals from a persisted analysis, "
               "keeping stable requirement identities and PM edits. Proposals wait for a PM decision.",
               GenerateInput, _generate, "A1",
               ("requirements", "requirement_versions", "requirement_findings", "scores", "review_items")),
    Capability("pipeline.assess_updates", "Reanalyze all cumulative evidence in scope, propose revisions and open "
               "review items for approved decisions the changes touch. A PM accepts every revision.",
               AssessInput, _assess, "A2",
               ("analysis_runs", "findings", "finding_evidence", "requirements", "requirement_versions",
                "requirement_findings", "scores", "review_items")),
)
for _capability in PIPELINE_CAPABILITIES:
    register_capability(_capability)
