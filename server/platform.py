"""Shared platform substrate: recorded runs, the capability registry and human gates.

LLMs interpret and draft, deterministic code counts and scores, humans decide. Every capability
execution is a `runs` row with its method version, input hash, inputs, outputs and metrics, and an
audit event for success and for failure, so any number shown to a PM traces to the code or recorded
model call that produced it. Pods register capabilities at import; tasks and the next phase's agents
run them through `run_capability`, so nothing changes when agents arrive.
"""

import contextvars
import hashlib
import re
import sqlite3
import time
from collections.abc import Callable
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError

from database.store import audit, encode, new_id, now, transaction

METHOD = str  # method_version label, e.g. 'market-balance-v1' or 'openai:<model>:<prompt_version>'
AUTONOMY_LEVELS = ("A0", "A1", "A2", "A3")  # A0 autonomous, A1 proposes, A2 needs human accept, A3 human only
HUMAN_REQUIRED = "this action requires a human actor"
MAX_ERROR_CHARS = 2000
# Sales shares other pods read (Pod E, 0014): current rows only, and only reported periods by default,
# because sales periods after the import year are planning projections (metrics.period_type).
CURRENT_MARKET_WEIGHTS = "v_market_weights_current"
REPORTED_MARKET_WEIGHTS = ("(SELECT * FROM v_market_weights_current "
                           "WHERE coalesce(json_extract(metrics, '$.period_type'), 'reported') != 'projection')")
_CAPABILITY_NAME = re.compile(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*")
_TASK_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar("platform_task_id", default=None)
_RUN_IDS: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar("platform_run_ids", default=None)


def input_hash(payload) -> str:
    """SHA-256 of the canonical JSON (store.encode: sorted keys, no NaN)."""
    return hashlib.sha256(encode(payload).encode()).hexdigest()


class HumanActorRequired(HTTPException, ValueError):
    """403: an ai:/system: actor attempted a human decision. Mirrors the database gate triggers."""

    def __init__(self, detail: str = HUMAN_REQUIRED):
        super().__init__(status_code=403, detail=detail)


def is_automated(actor: str) -> bool:
    return actor.strip().lower().startswith(("ai:", "system:"))


def require_human(actor: str, connection: sqlite3.Connection | None = None) -> None:
    """Reject ai:/system: actors (and, given a connection, registered non-human or inactive actors)."""
    if not isinstance(actor, str) or not actor.strip() or is_automated(actor):
        raise HumanActorRequired()
    if connection is not None:
        row = connection.execute("SELECT kind, active FROM actors WHERE id=?", (actor,)).fetchone()
        if row is not None and row[0] != "human":
            raise HumanActorRequired()
        if row is not None and not row[1]:
            raise HTTPException(403, "inactive actor")


@dataclass
class RunHandle:
    """The open run. Capabilities fill `outputs` and `metrics`; server/llm.py adds `metrics['llm']`."""

    id: str
    capability: str
    actor: str
    method_version: str
    input_hash: str
    task_id: str | None = None
    metrics: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)


def _error_text(exc: BaseException) -> str:
    detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
    text = f"{type(exc).__name__}: {detail if isinstance(detail, str) else encode(detail)}"
    return text[:MAX_ERROR_CHARS]


def _finish(connection, run: RunHandle, status: str, error: str | None, started: float) -> tuple[str, str | None]:
    run.metrics.setdefault("duration_ms", round((time.monotonic() - started) * 1000, 1))
    try:
        outputs, metrics = encode(run.outputs), encode(run.metrics)
    except (TypeError, ValueError):
        status, error = "failed", "RunOutputError: outputs and metrics must be finite JSON"
        outputs, metrics = None, encode({"duration_ms": run.metrics.get("duration_ms")})
    connection.execute("UPDATE runs SET status=?, outputs=?, metrics=?, error=?, finished_at=? WHERE id=?",
                       (status, outputs if status == "succeeded" else None, metrics, error, now(), run.id))
    summary = {"status": status, "capability": run.capability, "method_version": run.method_version,
               "input_hash": run.input_hash, "error": error}
    llm = run.metrics.get("llm")
    if isinstance(llm, dict):
        summary["llm"] = {key: llm.get(key) for key in ("calls", "cache_hits", "total_tokens", "models")}
    audit(connection, "run", run.id, f"run.{status}", run.actor, f"{run.capability} {status}", after=summary,
          metadata={"task_id": run.task_id})
    return status, error


@contextmanager
def record_run(connection: sqlite3.Connection | None, capability: str, actor: str, method_version: str,
               inputs: dict, vehicle: str | None = None, market: str | None = None, task_id: str | None = None):
    """Insert a 'running' run, yield a RunHandle, mark it succeeded/failed on exit and audit both outcomes.

    With connection=None (the normal case) the start and the outcome commit in their own short
    transactions, so a failure stays visible and model calls inside the block hold no write lock; write
    results in your own `transaction()` referencing `run.id`. Never call it with connection=None while
    holding another write transaction (SQLite would wait on itself). Passing an open transaction makes
    the run atomic with the caller's writes instead; a failure then rolls back with that transaction.
    The task id defaults to the task being executed by run_capability.
    """
    run = RunHandle(new_id(), capability, actor, method_version, input_hash(inputs),
                    task_id if task_id is not None else _TASK_ID.get())
    started = time.monotonic()
    with (transaction() if connection is None else nullcontext(connection)) as db:
        db.execute("INSERT INTO runs (id, capability, task_id, actor, vehicle, market, method_version, input_hash, "
                   "inputs, metrics, status, started_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (run.id, capability, run.task_id, actor, vehicle, market, method_version, run.input_hash,
                    encode(inputs), "{}", "running", now()))
    collected = _RUN_IDS.get()
    if collected is not None:
        collected.append(run.id)
    try:
        yield run
    except BaseException as exc:
        with (transaction() if connection is None else nullcontext(connection)) as db:
            _finish(db, run, "failed", _error_text(exc), started)
        raise
    with (transaction() if connection is None else nullcontext(connection)) as db:
        status, error = _finish(db, run, "succeeded", None, started)
    if status == "failed":
        raise ValueError(error)


@dataclass(frozen=True)
class Capability:
    name: str                                   # 'signals.refresh_watchlist'
    description: str
    input_model: type[BaseModel]
    handler: Callable[[BaseModel, str], dict]   # (validated input, actor) -> outputs; owns its transactions
    autonomy_level: str                         # see AUTONOMY_LEVELS
    writes: tuple[str, ...]                     # tables it writes, for the agent permission view

    def __post_init__(self):
        if not _CAPABILITY_NAME.fullmatch(self.name):
            raise ValueError(f"Capability names are '<module>.<operation>': {self.name}")
        if self.autonomy_level not in AUTONOMY_LEVELS:
            raise ValueError(f"Unknown autonomy level for {self.name}: {self.autonomy_level}")
        if not (isinstance(self.input_model, type) and issubclass(self.input_model, BaseModel)):
            raise ValueError(f"Capability {self.name} needs a pydantic input model")
        if not self.description.strip() or not isinstance(self.writes, tuple):
            raise ValueError(f"Capability {self.name} needs a description and a writes tuple")


CAPABILITIES: dict[str, Capability] = {}


def register_capability(capability: Capability) -> None:
    if capability.name in CAPABILITIES:
        raise ValueError(f"Capability already registered: {capability.name}")
    CAPABILITIES[capability.name] = capability


def describe_capability(capability: Capability) -> dict:
    return {"name": capability.name, "description": capability.description,
            "autonomy_level": capability.autonomy_level, "writes": list(capability.writes),
            "input_schema": capability.input_model.model_json_schema()}


def run_capability(name: str, payload: dict, actor: str, task_id: str | None = None) -> dict:
    """Validate the payload and run a registered capability as `actor`.

    Returns {capability, actor, task_id, run_ids, awaiting_human, outputs}. run_ids lists every run the
    handler recorded (the last is the task's last_run_id). A handler signals a proposal that needs a
    human gate with outputs['awaiting_human'] = True.
    """
    capability = CAPABILITIES.get(name)
    if capability is None:
        raise HTTPException(404, f"Unknown capability: {name}")
    if not isinstance(actor, str) or not actor.strip():
        raise HTTPException(422, "Capabilities run as a named actor")
    try:
        command = capability.input_model.model_validate(payload)
    except ValidationError as exc:
        errors = [{"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]} for error in exc.errors()]
        raise HTTPException(422, {"capability": name, "errors": errors}) from None
    run_ids: list[str] = []
    task_token, runs_token = _TASK_ID.set(task_id), _RUN_IDS.set(run_ids)
    try:
        outputs = capability.handler(command, actor)
    finally:
        _TASK_ID.reset(task_token)
        _RUN_IDS.reset(runs_token)
    if not isinstance(outputs, dict):
        raise TypeError(f"Capability {name} must return a dict")
    return {"capability": name, "actor": actor, "task_id": task_id, "run_ids": run_ids,
            "awaiting_human": bool(outputs.get("awaiting_human")), "outputs": outputs}
