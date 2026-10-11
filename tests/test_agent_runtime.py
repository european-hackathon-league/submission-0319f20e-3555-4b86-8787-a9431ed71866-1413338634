"""Runtime behavior on synthetic capability executions; no provider/network calls."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException

from database.store import connect, transaction
from server import agent_runtime as runtime
from server.models import Scope
from server.platform import CAPABILITIES, Capability, record_run
from tests.test_workflow import import_feedback


@pytest.fixture
def capability(monkeypatch):
    def install(handler=lambda command, actor: {"vehicle": command.vehicle, "actor": actor}, name="test.execute"):
        monkeypatch.setitem(CAPABILITIES, name, Capability(name, "Synthetic runtime test", Scope, handler, "A0", ()))
        return name
    return install


def task(client, capability="test.execute", **overrides):
    result = client.post("/tasks", json={"vehicle": "G60", "market": "US", "capability": capability,
                                       "title": "Simulated task", "requested_by": "human:pm", **overrides})
    assert result.status_code == 201, result.text
    return result.json()


def execute(client, item, **overrides):
    return client.post(f"/tasks/{item['id']}/execute", json={"actor": "human:pm", **overrides})


def test_execution_records_outcome_run_audit_and_board(client, capability):
    capability()
    item = task(client)
    result = execute(client, item).json()
    assert result["status"] == "succeeded"
    assert result["outputs"]["vehicle"] == "G60"
    run = client.get(f"/runs/{result['run_id']}").json()
    assert run["status"] == "succeeded" and run["task_id"] == item["id"]
    assert run["method_version"] == "agent-runtime-v1"
    assert run["outputs"]["actor"] == "human:pm"
    assert execute(client, item).status_code == 409
    board = client.get("/tasks/board", params={"vehicle": "G60", "market": "US"})
    assert board.status_code == 200
    with connect() as connection:
        actions = {r[0] for r in connection.execute("SELECT action FROM audit_events WHERE entity_id=?", (item["id"],))}
    assert actions >= {"task.created", "task.started", "task.succeeded"}


@pytest.mark.parametrize("record_success_first", [False, True])
def test_failure_remains_visible_even_after_successful_subrun(client, capability, record_success_first):
    def fail(command, actor):
        if record_success_first:
            with record_run(None, "test.execute", actor, "simulated-v1", {}, command.vehicle, command.market):
                pass
        raise ValueError("Simulated failure")
    capability(fail)
    item = task(client)
    result = execute(client, item).json()
    assert result["status"] == "failed" and "Simulated failure" in result["error"]
    run = client.get(f"/runs/{result['run_id']}").json()
    assert run["status"] == "failed" and "Simulated failure" in run["error"]
    capability()
    retry = execute(client, result).json()
    assert retry["status"] == "succeeded" and retry["error"] is None
    assert retry["run_id"] != result["run_id"]


def test_unknown_capability_records_failed_run(client):
    result = execute(client, task(client, "not_installed.capability")).json()
    assert result["status"] == "failed" and result["last_run_id"]
    assert "not registered" in result["error"]


def test_state_machine_revision_and_human_proposal_gate(client, capability):
    capability(lambda command, actor: {"awaiting_human": True})
    item = task(client, status="backlog")
    assert execute(client, item).status_code == 409
    path = f"/tasks/{item['id']}"
    move = {"actor": "human:pm", "expected_revision": item["revision"], "status": "queued"}
    queued = client.patch(path, json=move).json()
    assert client.patch(path, json=move).status_code == 409
    result = execute(client, queued).json()
    assert result["status"] == "awaiting_human"
    decision = {"expected_revision": result["revision"], "status": "succeeded", "rationale": "Reviewed proposal"}
    assert client.patch(path, json={**decision, "actor": "ai:agent:orchestrator"}).status_code == 403
    assert client.patch(path, json={**decision, "actor": "human:pm"}).status_code == 200


def test_paused_agent_cannot_execute_or_create_tasks(client, capability):
    capability(name="pipeline.analyze")
    item = task(client, "pipeline.analyze", assigned_agent_id="ai:agent:feedback-analyst")
    pause = {"actor": "human:pm", "rationale": "Review model"}
    assert client.post("/agents/feedback-analyst/pause", json=pause).status_code == 200
    assert execute(client, item).status_code == 409
    assert client.post("/tasks", json={"capability": "pipeline.analyze", "title": "Simulated",
                                      "requested_by": "ai:agent:feedback-analyst"}).status_code == 409
    assert client.post("/agents/feedback-analyst/resume", json=pause).status_code == 200
    assert execute(client, item).json()["outputs"]["actor"] == "ai:agent:feedback-analyst"
    assert client.post("/agents/feedback-analyst/pause", json={**pause, "actor": "system:scheduler"}).status_code == 403


def test_capability_permissions_and_scope_cannot_be_overridden(client, capability):
    capability()
    item = task(client)
    result = execute(client, item, actor="ai:agent:feedback-analyst").json()
    assert result["status"] == "failed" and "may not run" in result["error"]
    for payload in ({"actor": "human:pm"}, {"vehicle": "G70"}, {"market": "CN"}):
        response = client.post("/tasks", json={"capability": "test.execute", "title": "Simulated",
                                               "requested_by": "human:pm", "input": payload})
        assert response.status_code == 422
    assert client.post("/tasks", json={"capability": "test.execute", "title": "Simulated",
                                      "market": "CN", "requested_by": "human:pm",
                                      "parent_task_id": item["id"]}).status_code == 422


def test_analysis_id_does_not_cross_task_scope(client):
    import_feedback(client, [("Seats are uncomfortable", "comfort", "problem")], market="CN")
    analysis = client.post("/analyses", json={"vehicle": "G60", "market": "CN", "provider": "deterministic"})
    assert analysis.status_code == 201, analysis.text
    result = client.post("/tasks", json={"capability": "pipeline.generate_requirements", "title": "Simulated",
                                        "requested_by": "human:pm", "input": {"analysis_id": analysis.json()["id"]}})
    assert result.status_code == 422


def test_scheduler_once_per_due_slot_and_pause(client, capability):
    calls = []
    capability(lambda command, actor: calls.append(actor) or {})
    template = task(client, recurrence_days=1, due_at="2020-01-01T00:00:00Z")
    first = client.post("/tasks/run-due", json={}).json()
    assert first["count"] == 1 and first["executed"][0]["status"] == "succeeded"
    occurrence = first["executed"][0]
    assert occurrence["occurrence_of"] == template["id"] and occurrence["task_id"] != template["id"]
    assert client.post("/tasks/run-due", json={}).json()["count"] == 0
    assert len(calls) == 1
    current = client.get(f"/tasks/{template['id']}").json()
    assert current["status"] == "queued" and current["revision"] > template["revision"]


def test_concurrent_execute_claims_exactly_once(client, capability):
    entered, finish = threading.Event(), threading.Event()
    def handler(command, actor):
        entered.set()
        assert finish.wait(5)
        return {}
    capability(handler)
    item = task(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(runtime.execute, item["id"], "human:pm")
        assert entered.wait(5)
        try:
            with pytest.raises(HTTPException) as error:
                runtime.execute(item["id"], "human:pm")
            assert error.value.status_code == 409
        finally:
            finish.set()
        assert first.result()["status"] == "succeeded"
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM runs WHERE task_id=?", (item["id"],)).fetchone()[0] == 1


def test_interrupted_task_can_be_retried(client, capability):
    capability()
    item = task(client)
    with transaction() as connection:
        connection.execute("UPDATE tasks SET status='running', started_at='2020-01-01T00:00:00Z', revision=revision+1 "
                           "WHERE id=?", (item["id"],))
    assert runtime.recover_stale_tasks()[0]["task_id"] == item["id"]
    recovered = client.get(f"/tasks/{item['id']}").json()
    assert recovered["status"] == "failed" and "Interrupted" in recovered["error"]
    assert client.get(f"/runs/{recovered['last_run_id']}").json()["status"] == "failed"
    assert execute(client, recovered).json()["status"] == "succeeded"


def test_internal_messages_are_append_only_and_scoped(client, capability):
    capability()
    item = task(client)
    response = client.post("/threads", json={"kind": "agent", "subject": "Simulated discussion",
                                            "entity_type": "task", "entity_id": item["id"], "created_by": "human:pm",
                                            "body": "Investigate comfort"})
    assert response.status_code == 201, response.text
    thread = response.json()
    assert (thread["vehicle"], thread["market"]) == ("G60", "US")
    path = f"/threads/{thread['id']}"
    message = {"author": "ai:agent:feedback-analyst", "role": "agent", "body": "Evidence review pending"}
    assert client.post(path + "/messages", json={**message, "role": "human"}).status_code == 422
    assert client.post(path + "/messages", json=message).status_code == 201
    assert client.patch(path, json={"actor": "human:pm", "status": "closed"}).status_code == 200
    assert client.post(path + "/messages", json=message).status_code == 409
    assert len(client.get(path).json()["messages"]) == 2


def test_tool_export_and_model_configuration(client):
    exported = client.get("/capabilities", params={"format": "openai-tools"})
    assert exported.status_code == 200
    response = client.patch("/agents/feedback-analyst", json={"actor": "human:pm", "rationale": "Selected model",
                                                            "model": "example-model"})
    assert response.status_code == 200 and response.json()["effective_model"] == "example-model"
    assert client.patch("/agents/scorer", json={"actor": "human:pm", "rationale": "Invalid", "model": "example"}).status_code == 422
