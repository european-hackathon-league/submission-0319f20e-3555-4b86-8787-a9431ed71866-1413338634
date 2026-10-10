"""Checkpointed BMW PM process; autonomous preparation stops at a human gate.

Model calls happen outside SQLite write transactions. A renewable, fenced lease
serializes workflows per scope. Requirement generation and its checkpoint share
one transaction so retries never replay a partially committed generation.
"""

import logging
import threading
import time
from contextlib import closing
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from database.store import audit, connect, decode, encode, new_id, now, transaction
from server.models import AnalysisRequest, Command, GenerateRequest, Scope, Text, normalize_market
from server.pipeline import generate_requirements, run_analysis, run_detail
from server.requirements import latest_score

router = APIRouter()
logger = logging.getLogger(__name__)
LEASE_SECONDS = 120
LEASE_HEARTBEAT_SECONDS = 30
STAGES = (
    ("situation_analysis", "Situation analysis"),
    ("structure_context", "Structure and contextualize"),
    ("requirements_definition", "Define requirements"),
    ("prioritization", "Prioritize requirements"),
    ("human_review", "PM review and decision"),
    ("documentation", "Document decisions"),
)
JSON_FIELDS = ("stages", "evidence_ids", "requirement_snapshots", "error")


class WorkflowCreate(Scope):
    kind: Literal["initial", "update"] = "initial"
    provider: Literal["deterministic", "openai"] = "deterministic"
    actor: Text = Field(default="PM", max_length=200)
    request_key: Text = Field(max_length=200)


class WorkflowAction(Command):
    expected_revision: int = Field(ge=0, strict=True)
    actor: Text = Field(default="PM", max_length=200)


class WorkflowComplete(WorkflowAction):
    rationale: Text = Field(max_length=4000)


def _stages():
    return [{"key": key, "label": label, "status": "pending", "output": None, "error": None}
            for key, label in STAGES]


def _row(connection, workflow_id):
    result = decode(connection.execute("SELECT * FROM pm_workflows WHERE id=?", (workflow_id,)).fetchone(), JSON_FIELDS)
    if result is None:
        raise HTTPException(404, "Workflow not found")
    return result


def workflow_detail(connection, workflow_id):
    """Public projection, including immutable snapshot IDs after completion."""
    result = _row(connection, workflow_id)
    result.pop("lease_token")
    result.pop("lease_expires_at")
    return result


def _stage(workflow, key):
    return next(stage for stage in workflow["stages"] if stage["key"] == key)


def _evidence_ids(connection, workflow):
    return [row[0] for row in connection.execute(
        "SELECT id FROM evidence WHERE vehicle=? AND market=? ORDER BY id", (workflow["vehicle"], workflow["market"]))]


def _assert_fresh(connection, workflow):
    if _evidence_ids(connection, workflow) != workflow["evidence_ids"]:
        raise HTTPException(409, "Evidence changed; rerun this workflow to assess all current evidence before continuing")


def _assert_revision(workflow, expected_revision):
    if workflow["revision"] != expected_revision:
        raise HTTPException(409, "Workflow changed; reload it and use its current revision")


def _assert_lease(workflow, token):
    if workflow["status"] != "running" or workflow["lease_token"] != token or workflow["lease_expires_at"] <= time.time():
        raise HTTPException(409, "Workflow lease expired or was replaced; reload before retrying")


def _save(connection, workflow, action, actor, rationale, metadata=None):
    before = workflow_detail(connection, workflow["id"])
    workflow["revision"] += 1
    workflow["updated_at"] = now()
    connection.execute(
        "UPDATE pm_workflows SET status=?,revision=?,stages=?,evidence_ids=?,analysis_id=?,"
        "requirement_snapshots=?,error=?,lease_token=?,lease_expires_at=?,updated_at=? WHERE id=?",
        (workflow["status"], workflow["revision"], encode(workflow["stages"]), encode(workflow["evidence_ids"]),
         workflow["analysis_id"], encode(workflow["requirement_snapshots"]),
         encode(workflow["error"]) if workflow["error"] is not None else None,
         workflow["lease_token"], workflow["lease_expires_at"], workflow["updated_at"], workflow["id"]),
    )
    audit(connection, "workflow", workflow["id"], action, actor, rationale,
          before=before, after=workflow_detail(connection, workflow["id"]), metadata=metadata)


def _error(code, message):
    return {"code": code, "message": message, "retryable": True}


def _fail(connection, workflow, error, actor="system:workflow"):
    for stage in workflow["stages"]:
        if stage["status"] == "running":
            stage.update(status="failed", error=error)
    workflow.update(status="failed", error=error, lease_token=None, lease_expires_at=None)
    _save(connection, workflow, "workflow.failed", actor, error["message"])


class _Heartbeat:
    """Keep model IO alive without holding a database transaction across it."""

    def __init__(self, workflow_id, token):
        self.workflow_id, self.token = workflow_id, token
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._renew, daemon=True)

    def _renew(self):
        while not self.stop.wait(LEASE_HEARTBEAT_SECONDS):
            try:
                with transaction() as connection:
                    workflow = _row(connection, self.workflow_id)
                    _assert_lease(workflow, self.token)
                    connection.execute("UPDATE pm_workflows SET lease_expires_at=? WHERE id=? AND lease_token=?",
                                       (time.time() + LEASE_SECONDS, self.workflow_id, self.token))
                    audit(connection, "workflow", self.workflow_id, "workflow.lease_renewed", "system:workflow",
                          "Active worker renewed its bounded lease")
            except Exception:
                # Failure to renew is fenced by the next checkpoint. A stale
                # worker cannot regain ownership or write requirement versions.
                logger.exception("Could not renew workflow lease %s", self.workflow_id)
                return

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=11)


def _snapshots(connection, workflow, require_decisions=False):
    snapshots = []
    for requirement in connection.execute("SELECT * FROM requirements WHERE vehicle=? AND market=? ORDER BY key,id",
                                          (workflow["vehicle"], workflow["market"])).fetchall():
        score = latest_score(connection, requirement["current_version_id"])
        if score is None:
            raise HTTPException(409, "Every scoped requirement needs a current priority score")
        snapshot = {"requirement_id": requirement["id"], "version_id": requirement["current_version_id"], "score_id": score["id"]}
        if require_decisions:
            decision = connection.execute("SELECT * FROM decisions WHERE requirement_id=? ORDER BY rowid DESC LIMIT 1",
                                          (requirement["id"],)).fetchone()
            open_review = connection.execute("SELECT 1 FROM review_items WHERE requirement_id=? AND status='open' LIMIT 1",
                                             (requirement["id"],)).fetchone()
            if (decision is None or decision["action"] not in ("approve", "reject")
                    or decision["version_id"] != snapshot["version_id"] or decision["score_id"] != snapshot["score_id"]
                    or requirement["status"] not in ("approved", "rejected") or open_review is not None):
                raise HTTPException(409, "Every scoped requirement needs a PM approval or rejection of its current version and score")
            snapshot["decision_id"] = decision["id"]
        snapshots.append(snapshot)
    if not snapshots:
        raise HTTPException(409, "No customer requirements were generated; import actionable customer evidence and rerun")
    return snapshots


def _require_pm(connection, actor):
    record = connection.execute("SELECT kind,role,active FROM actors WHERE id=?", (actor,)).fetchone()
    # Same demo trust boundary as decisions_actor: previously unseen labels
    # without AI/system prefixes become discovered PMs when audited.
    if record is None:
        allowed = not actor.lower().startswith(("ai:", "system:"))
    else:
        allowed = record["kind"] == "human" and record["role"] in ("pm", "lead_pm") and record["active"] == 1
    if not allowed:
        raise HTTPException(403, "Workflow completion requires an active human PM")


@router.post("/workflows", status_code=201)
def create_workflow(command: WorkflowCreate):
    with transaction() as connection:
        existing = connection.execute("SELECT id FROM pm_workflows WHERE request_key=?", (command.request_key,)).fetchone()
        if existing:
            result = workflow_detail(connection, existing[0])
            if any(result[key] != value for key, value in command.model_dump().items()):
                raise HTTPException(409, "request_key is already used for a different workflow request")
            return result
        workflow_id, timestamp = new_id(), now()
        connection.execute(
            "INSERT INTO pm_workflows (id,vehicle,market,kind,provider,actor,request_key,status,stages,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,'pending',?,?,?)",
            (workflow_id, command.vehicle, command.market, command.kind, command.provider, command.actor,
             command.request_key, encode(_stages()), timestamp, timestamp),
        )
        result = workflow_detail(connection, workflow_id)
        audit(connection, "workflow", workflow_id, "workflow.created", command.actor,
              "Prepared a BMW PM workflow", after=result)
        return result


@router.get("/workflows")
def list_workflows(vehicle: str | None = None, market: str | None = None,
                   limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    clauses, params = [], []
    for key, value in (("vehicle", vehicle.strip().upper() if vehicle is not None else None),
                       ("market", normalize_market(market) if market is not None else None)):
        if value is not None:
            clauses.append(f"{key}=?")
            params.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with closing(connect()) as connection:
        return [workflow_detail(connection, row[0]) for row in connection.execute(
            "SELECT id FROM pm_workflows" + where + " ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset]).fetchall()]


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str):
    with closing(connect()) as connection:
        return workflow_detail(connection, workflow_id)


def _claim(workflow_id, command):
    with transaction() as connection:
        workflow = _row(connection, workflow_id)
        _assert_revision(workflow, command.expected_revision)
        if workflow["status"] == "completed":
            raise HTTPException(409, "Completed workflows are immutable; create an update workflow")
        active = connection.execute("SELECT id FROM pm_workflows WHERE vehicle=? AND market=? AND status='running'",
                                    (workflow["vehicle"], workflow["market"])).fetchone()
        if active:
            other = _row(connection, active[0])
            if other["lease_expires_at"] > time.time():
                raise HTTPException(409, "A workflow is already running for this vehicle and market; wait for it or retry after its lease expires")
            _fail(connection, other, _error("interrupted", "The previous worker stopped responding; retry the workflow"))
            workflow = _row(connection, workflow_id)
        current = _evidence_ids(connection, workflow)
        if workflow["evidence_ids"] != current:
            # Changed inputs invalidate all downstream checkpoints, never the
            # append-only analysis, approved version, or PM decision history.
            workflow.update(stages=_stages(), evidence_ids=current, analysis_id=None, requirement_snapshots=[])
        elif workflow["status"] == "awaiting_review":
            # A retry with unchanged input does not create versions or reopen
            # already reviewed requirements.
            return workflow, None
        for stage in workflow["stages"]:
            if stage["status"] in ("running", "failed"):
                stage.update(status="pending", error=None)
        token = new_id()
        workflow.update(status="running", error=None, lease_token=token, lease_expires_at=time.time() + LEASE_SECONDS)
        _save(connection, workflow, "workflow.started", command.actor, "Started or resumed autonomous PM preparation")
        return workflow, token


def _checkpoint(workflow_id, token, key, operation):
    with transaction() as connection:
        workflow = _row(connection, workflow_id)
        _assert_lease(workflow, token)
        _assert_fresh(connection, workflow)
        stage = _stage(workflow, key)
        if stage["status"] == "completed":
            return workflow
        stage.update(status="running", error=None)
        # operation only does local database work; external analysis is separate.
        output = operation(connection, workflow)
        # A long local stage holds the write lock, so the heartbeat cannot
        # renew while it runs. Expiry still fences its writes: roll back the
        # operation instead of reviving an expired lease at this checkpoint.
        _assert_lease(workflow, token)
        stage.update(status="completed", output=output)
        workflow["lease_expires_at"] = time.time() + LEASE_SECONDS
        _save(connection, workflow, "workflow.stage_completed", "system:workflow", f"Completed {stage['label']}",
              metadata={"stage": key})
        return workflow


def _situation(connection, workflow):
    if not workflow["evidence_ids"]:
        raise HTTPException(422, "Import evidence for this vehicle and market before running the workflow")
    sources = [dict(row) for row in connection.execute(
        "SELECT s.id,s.title,s.kind,s.reference,count(e.id) AS evidence_count FROM sources s "
        "JOIN evidence e ON e.source_id=s.id WHERE e.vehicle=? AND e.market=? GROUP BY s.id ORDER BY s.id",
        (workflow["vehicle"], workflow["market"]))]
    return {"source_count": len(sources), "evidence_count": len(workflow["evidence_ids"]), "sources": sources,
            "purpose": "Understand customer needs, strengths, problems, and market context before defining requirements"}


def _structure(workflow_id, token, workflow):
    if _stage(workflow, "structure_context")["status"] == "completed":
        return workflow
    with transaction() as connection:
        current = _row(connection, workflow_id)
        _assert_lease(current, token)
        _assert_fresh(connection, current)
        _stage(current, "structure_context").update(status="running", error=None)
        _save(connection, current, "workflow.stage_started", "system:workflow", "Analyzing and contextualizing evidence",
              metadata={"stage": "structure_context"})
    analysis = run_analysis(AnalysisRequest(vehicle=workflow["vehicle"], market=workflow["market"],
                                            provider=workflow["provider"], actor="system:workflow"))

    def finish(connection, current):
        if set(analysis["evidence_ids"]) != set(current["evidence_ids"]):
            raise HTTPException(409, "Analysis input changed; rerun this workflow with current evidence")
        if set(analysis["result"].get("analyzed_evidence_ids", [])) != set(current["evidence_ids"]):
            raise HTTPException(409, "Analysis omitted evidence; increase AI batch coverage and retry before generating requirements")
        current["analysis_id"] = analysis["id"]
        return {"analysis_id": analysis["id"], "provider": analysis["provider"], "model": analysis["model"],
                "finding_count": len(analysis["findings"]), "proposal_count": len(analysis["result"]["proposals"]),
                "analyzed_evidence_count": len(current["evidence_ids"]), "warnings": analysis["warnings"],
                "findings": [{"id": finding["id"], "topic": finding["topic"], "kind": finding["kind"],
                              "summary": finding["summary"], "evidence_ids": finding["evidence_ids"],
                              "conflicting_evidence_ids": finding["conflicting_evidence_ids"]}
                             for finding in analysis["findings"]]}

    return _checkpoint(workflow_id, token, "structure_context", finish)


def _generate(connection, workflow):
    result = generate_requirements(GenerateRequest(run_id=workflow["analysis_id"], actor="system:workflow"),
                                   require_cumulative=True, connection=connection)
    workflow["requirement_snapshots"] = _snapshots(connection, workflow)
    return {key: result[key] for key in ("run_id", "created", "updated", "unchanged", "unchanged_reasons")}


def _prioritize(connection, workflow):
    workflow["requirement_snapshots"] = _snapshots(connection, workflow)
    return {"requirements": [{**snapshot, "score": latest_score(connection, snapshot["version_id"])}
                             for snapshot in workflow["requirement_snapshots"]],
            "rubric": "Customer impact, market relevance, strategic fit, differentiation, and feasibility",
            "note": "Priorities are proposals. Assumed acceptance targets and conflicting evidence require PM review."}


@router.post("/workflows/{workflow_id}/run")
def run_workflow(workflow_id: str, command: WorkflowAction):
    workflow, token = _claim(workflow_id, command)
    if token is None:
        return get_workflow(workflow_id)
    key = "situation_analysis"
    with _Heartbeat(workflow_id, token):
        try:
            workflow = _checkpoint(workflow_id, token, key, _situation)
            key = "structure_context"
            workflow = _structure(workflow_id, token, workflow)
            key = "requirements_definition"
            workflow = _checkpoint(workflow_id, token, key, _generate)
            key = "prioritization"
            _checkpoint(workflow_id, token, key, _prioritize)
            with transaction() as connection:
                workflow = _row(connection, workflow_id)
                _assert_lease(workflow, token)
                _assert_fresh(connection, workflow)
                _stage(workflow, "human_review").update(status="awaiting_review", output={
                    "requirement_count": len(workflow["requirement_snapshots"]),
                    "instruction": "Review evidence and assumptions, edit as needed, and approve or reject every current scoped requirement."})
                workflow.update(status="awaiting_review", lease_token=None, lease_expires_at=None)
                _save(connection, workflow, "workflow.awaiting_review", "system:workflow", "Autonomous work stopped at the human decision gate")
        except Exception as exc:
            if isinstance(exc, HTTPException):
                error = _error(f"http_{exc.status_code}", str(exc.detail))
            else:
                logger.exception("Workflow %s failed at %s", workflow_id, key)
                error = _error("stage_failed", "The workflow stage failed unexpectedly; retry or inspect the server logs")
            with transaction() as connection:
                current = _row(connection, workflow_id)
                # A worker whose lease was replaced cannot mark its successor
                # failed, overwrite checkpoints, or mutate requirements.
                if current["status"] == "running" and current["lease_token"] == token:
                    _stage(current, key).update(status="failed", error=error)
                    _fail(connection, current, error)
                else:
                    raise HTTPException(409, "Workflow was resumed by another worker; reload its current state") from exc
    return get_workflow(workflow_id)


@router.post("/workflows/{workflow_id}/complete")
def complete_workflow(workflow_id: str, command: WorkflowComplete):
    with transaction() as connection:
        workflow = _row(connection, workflow_id)
        _assert_revision(workflow, command.expected_revision)
        _require_pm(connection, command.actor)
        if workflow["status"] != "awaiting_review":
            raise HTTPException(409, "Only a workflow awaiting PM review can be completed")
        active = connection.execute("SELECT 1 FROM pm_workflows WHERE vehicle=? AND market=? AND status='running'",
                                    (workflow["vehicle"], workflow["market"])).fetchone()
        if active:
            raise HTTPException(409, "A workflow is running for this scope; wait for it before completing the PM gate")
        _assert_fresh(connection, workflow)
        analysis = run_detail(connection, workflow["analysis_id"])
        if set(analysis["result"].get("analyzed_evidence_ids", [])) != set(workflow["evidence_ids"]):
            raise HTTPException(409, "Current evidence has not been fully assessed; rerun analysis with complete coverage")
        workflow["requirement_snapshots"] = _snapshots(connection, workflow, require_decisions=True)
        gate = {"actor": command.actor, "rationale": command.rationale,
                "requirement_snapshots": workflow["requirement_snapshots"]}
        _stage(workflow, "human_review").update(status="completed", output=gate)
        _stage(workflow, "documentation").update(status="completed", output={
            **gate, "analysis_id": workflow["analysis_id"], "evidence_ids": workflow["evidence_ids"],
            "note": "Recorded exact evidence, analysis, requirement version, score, and PM decision IDs for handoff."})
        workflow.update(status="completed", error=None)
        _save(connection, workflow, "workflow.completed", command.actor, command.rationale)
        return workflow_detail(connection, workflow_id)
