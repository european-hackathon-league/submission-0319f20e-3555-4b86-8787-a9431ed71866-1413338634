import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from database.store import connect, decode, transaction
from server import analysis_engine, workflows
from server.main import app


@pytest.fixture
def client(db):
    # The engine can be reviewed independently of the integration router wiring.
    previous_routes = list(app.router.routes)
    if not any(getattr(route, "path", None) == "/workflows" for route in app.router.routes):
        app.include_router(workflows.router)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.router.routes[:] = previous_routes


def import_evidence(client, reference="baseline", topic="charging", market="US"):
    response = client.post("/imports/records", json={
        "title": reference, "reference": reference, "market": market,
        "records": [{"content": f"Charging is unreliable ({reference})", "market": market,
                     "metadata": {"topic": topic, "sentiment": "problem"}, "location": {"row": 2}}],
    })
    assert response.status_code == 201, response.text
    return response.json()


def create(client, key="test", **kwargs):
    response = client.post("/workflows", json={"request_key": key, **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


def run(client, workflow, **kwargs):
    response = client.post(f"/workflows/{workflow['id']}/run", json={
        "expected_revision": workflow["revision"], **kwargs})
    assert response.status_code == 200, response.text
    return response.json()


def ready(client, **kwargs):
    import_evidence(client)
    workflow = run(client, create(client, **kwargs))
    assert workflow["status"] == "awaiting_review", workflow
    return workflow


def decide_all(client, workflow, action="approve"):
    decisions = []
    for snapshot in workflow["requirement_snapshots"]:
        requirement = client.get(f"/requirements/{snapshot['requirement_id']}").json()
        version = requirement["current_version"]
        response = client.post(f"/requirements/{requirement['id']}/decisions", json={
            "version_id": version["id"], "score_id": version["score"]["id"], "action": action,
            "actor": "PM Alice", "rationale": "Reviewed customer evidence and acceptance assumptions",
        })
        assert response.status_code == 201, response.text
        decisions.append(response.json()["decision_id"])
    return decisions


def complete(client, workflow, **kwargs):
    return client.post(f"/workflows/{workflow['id']}/complete", json={
        "expected_revision": workflow["revision"], "actor": "PM Alice", "rationale": "Ready for development handoff", **kwargs})


def version_count():
    with connect() as connection:
        return connection.execute("SELECT count(*) FROM requirement_versions").fetchone()[0]


def test_durable_sequence_and_human_gate_complete_with_exact_trace(client):
    workflow = ready(client)
    assert [stage["key"] for stage in workflow["stages"]] == [key for key, _ in workflows.STAGES]
    assert [stage["status"] for stage in workflow["stages"]] == ["completed"] * 4 + ["awaiting_review", "pending"]
    assert complete(client, workflow).status_code == 409
    decision_ids = decide_all(client, workflow)
    response = complete(client, workflow)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "completed"
    assert all(stage["status"] == "completed" for stage in result["stages"])
    assert {snapshot["decision_id"] for snapshot in result["requirement_snapshots"]} == set(decision_ids)
    assert result["analysis_id"] and result["evidence_ids"]
    assert "lease_token" not in result
    assert client.get(f"/workflows/{result['id']}").json() == result
    assert client.get("/workflows", params={"vehicle": "g60", "market": "USA"}).json() == [result]
    events = client.get("/audit", params={"entity_id": result["id"]}).json()["items"]
    assert events[-1]["action"] == "workflow.completed"
    assert events[-1]["after_state"] == result
    assert client.post(f"/workflows/{result['id']}/run", json={"expected_revision": result["revision"]}).status_code == 409
    assert complete(client, result).status_code == 409


def test_request_key_idempotent_and_mismatched_request_rejected(client):
    workflow = create(client, vehicle="g60", market="USA")
    assert create(client) == workflow
    response = client.post("/workflows", json={"request_key": "test", "kind": "update"})
    assert response.status_code == 409
    assert len(client.get("/workflows").json()) == 1
    assert client.get("/workflows", params={"market": "CN"}).json() == []
    assert client.get("/workflows/missing").status_code == 404


def test_stale_commands_do_not_mutate_and_awaiting_retry_is_noop(client):
    import_evidence(client)
    pending = create(client)
    workflow = run(client, pending)
    assert client.post(f"/workflows/{workflow['id']}/run", json={"expected_revision": pending["revision"]}).status_code == 409
    assert complete(client, workflow, expected_revision=pending["revision"]).status_code == 409
    before = version_count()
    assert run(client, workflow) == workflow
    assert version_count() == before


def test_provider_failure_persisted_and_retry_safe(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    import_evidence(client)
    workflow = run(client, create(client, provider="openai"))
    assert workflow["status"] == "failed"
    assert workflow["error"]["code"] == "http_503"
    assert workflow["stages"][0]["status"] == "completed"
    assert workflow["stages"][1]["status"] == "failed"
    assert version_count() == 0
    original = analysis_engine.analyze_evidence
    monkeypatch.setattr(analysis_engine, "analyze_evidence", lambda records, vehicle, market, provider:
                        {**original(records, vehicle, market, "deterministic"), "provider": "openai", "model": "test"})
    workflow = run(client, workflow)
    assert workflow["status"] == "awaiting_review"
    before = version_count()
    assert run(client, workflow) == workflow
    assert version_count() == before


def test_no_evidence_fails_with_actionable_stage_then_import_recovers(client):
    workflow = run(client, create(client))
    assert workflow["status"] == "failed"
    assert "Import evidence" in workflow["error"]["message"]
    import_evidence(client)
    assert run(client, workflow)["status"] == "awaiting_review"


def test_generation_checkpoint_is_atomic_and_failed_retry_has_one_version(client, monkeypatch):
    import_evidence(client)
    original = workflows._generate

    def crash_after_generation(connection, workflow):
        original(connection, workflow)
        raise RuntimeError("crashed before checkpoint")

    monkeypatch.setattr(workflows, "_generate", crash_after_generation)
    workflow = run(client, create(client))
    assert workflow["status"] == "failed"
    assert workflow["stages"][1]["status"] == "completed"
    assert version_count() == 0
    monkeypatch.setattr(workflows, "_generate", original)
    recovered = run(client, workflow)
    assert recovered["status"] == "awaiting_review"
    assert recovered["analysis_id"] == workflow["analysis_id"]
    assert version_count() == len(recovered["requirement_snapshots"])


def test_generation_that_outlives_lease_rolls_back_and_can_retry(client, monkeypatch):
    import_evidence(client)
    original = workflows._generate
    clock = SimpleNamespace(value=time.time())
    monkeypatch.setattr(workflows, "time", SimpleNamespace(time=lambda: clock.value))

    def slow_generation(connection, workflow):
        result = original(connection, workflow)
        clock.value += workflows.LEASE_SECONDS + 1
        return result

    monkeypatch.setattr(workflows, "_generate", slow_generation)
    failed = run(client, create(client))
    assert failed["status"] == "failed"
    assert "lease expired" in failed["error"]["message"]
    assert failed["stages"][2]["status"] == "failed"
    assert version_count() == 0
    monkeypatch.setattr(workflows, "_generate", original)
    recovered = run(client, failed)
    assert recovered["status"] == "awaiting_review"
    assert recovered["analysis_id"] == failed["analysis_id"]
    assert version_count() == len(recovered["requirement_snapshots"])


def test_update_preserves_approved_baseline_pm_edits_and_records_final_current_decision(client):
    first = ready(client)
    decide_all(client, first)
    completed = complete(client, first).json()
    snapshot = first["requirement_snapshots"][0]
    approved = client.get(f"/requirements/{snapshot['requirement_id']}").json()
    edit = client.patch(f"/requirements/{approved['id']}", json={
        "expected_version_id": approved["current_version_id"], "actor": "PM Alice", "rationale": "Use agreed product language",
        "title": "Dependable charging on every journey"})
    assert edit.status_code == 200, edit.text
    decide_all(client, first)
    approved = client.get(f"/requirements/{approved['id']}").json()
    import_evidence(client, "later")
    second = run(client, create(client, key="update", kind="update"))
    current = client.get(f"/requirements/{approved['id']}").json()
    assert current["approved_version"] == approved["approved_version"]
    assert current["current_version"]["title"] == "Dependable charging on every journey"
    assert current["current_version_id"] != approved["current_version_id"]
    assert complete(client, second).status_code == 409
    decide_all(client, second)
    response = complete(client, second)
    assert response.status_code == 200, response.text
    assert client.get(f"/workflows/{first['id']}").json() == completed


def test_pm_edit_after_workflow_run_requires_redecision_and_final_snapshot_uses_edit(client):
    workflow = ready(client)
    decide_all(client, workflow)
    snapshot = workflow["requirement_snapshots"][0]
    edit = client.patch(f"/requirements/{snapshot['requirement_id']}", json={
        "expected_version_id": snapshot["version_id"], "actor": "PM Alice", "rationale": "Clarify user outcome",
        "title": "Revised PM title"}).json()
    assert complete(client, workflow).status_code == 409
    decide_all(client, workflow)
    result = complete(client, workflow)
    assert result.status_code == 200, result.text
    assert result.json()["requirement_snapshots"][0]["version_id"] == edit["current_version_id"]


@pytest.mark.parametrize("actor,role,active", [
    ("ai:assistant", None, None), ("system:worker", None, None),
    ("human:viewer", "viewer", 1), ("human:inactive", "pm", 0),
])
def test_completion_requires_active_human_pm(client, actor, role, active):
    workflow = ready(client)
    decide_all(client, workflow)
    if role:
        with transaction() as connection:
            connection.execute("INSERT INTO actors (id,kind,role,display_name,active) VALUES (?,'human',?,?,?)",
                               (actor, role, actor, active))
    response = complete(client, workflow, actor=actor)
    assert response.status_code == 403, response.text
    assert client.get(f"/workflows/{workflow['id']}").json()["status"] == "awaiting_review"


@pytest.mark.parametrize("action", ["postpone", "challenge"])
def test_unresolved_decisions_cannot_complete(client, action):
    workflow = ready(client)
    decide_all(client, workflow, action)
    assert complete(client, workflow).status_code == 409
    decide_all(client, workflow, "reject")
    assert complete(client, workflow).status_code == 200


def test_new_evidence_blocks_completion_then_reanalysis_reopens_current_decision(client):
    workflow = ready(client)
    decide_all(client, workflow)
    import_evidence(client, "new-evidence")
    response = complete(client, workflow)
    assert response.status_code == 409 and "Evidence changed" in response.text
    refreshed = run(client, workflow)
    assert refreshed["analysis_id"] != workflow["analysis_id"]
    assert len(refreshed["evidence_ids"]) == 2
    assert complete(client, refreshed).status_code == 409
    decide_all(client, refreshed)
    assert complete(client, refreshed).status_code == 200


def test_import_during_model_io_fails_closed_and_does_not_generate(client, monkeypatch):
    original = analysis_engine.analyze_evidence

    def importing_analysis(records, vehicle, market, provider):
        import_evidence(client, "arrived-during-analysis")
        return original(records, vehicle, market, provider)

    monkeypatch.setattr(analysis_engine, "analyze_evidence", importing_analysis)
    import_evidence(client)
    workflow = run(client, create(client))
    assert workflow["status"] == "failed" and "Evidence changed" in workflow["error"]["message"]
    assert version_count() == 0
    monkeypatch.setattr(analysis_engine, "analyze_evidence", original)
    assert run(client, workflow)["status"] == "awaiting_review"


def test_partial_analysis_coverage_cannot_generate_or_pass_human_gate(client, monkeypatch):
    original = analysis_engine.analyze_evidence

    def partial(records, vehicle, market, provider):
        result = original(records, vehicle, market, provider)
        result["analyzed_evidence_ids"] = []
        return result

    monkeypatch.setattr(analysis_engine, "analyze_evidence", partial)
    workflow = ready_input = create(client)
    import_evidence(client)
    workflow = run(client, ready_input)
    assert workflow["status"] == "failed"
    assert "omitted evidence" in workflow["error"]["message"]
    assert version_count() == 0
    assert complete(client, workflow).status_code == 409


def test_same_scope_runs_excluded_while_other_scope_is_allowed_and_no_model_io_lock(client, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = analysis_engine.analyze_evidence

    def slow(records, vehicle, market, provider):
        if market == "US":
            entered.set()
            assert release.wait(10)
        return original(records, vehicle, market, provider)

    monkeypatch.setattr(analysis_engine, "analyze_evidence", slow)
    import_evidence(client)
    import_evidence(client, "china", market="CN")
    first, second, other = create(client), create(client, key="second"), create(client, key="china", market="CN")
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run, client, first)
        try:
            assert entered.wait(10)
            response = client.post(f"/workflows/{second['id']}/run", json={"expected_revision": second["revision"]})
            assert response.status_code == 409
            assert run(client, other)["status"] == "awaiting_review"
            # Importing writes successfully while US analysis is waiting.
            import_evidence(client, "during-wait", market="CN")
        finally:
            release.set()
        assert future.result()["status"] == "awaiting_review"


def test_expired_lease_recovery_fences_old_worker(client, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = analysis_engine.analyze_evidence
    calls = 0

    def first_slow(records, vehicle, market, provider):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            assert release.wait(10)
        return original(records, vehicle, market, provider)

    monkeypatch.setattr(analysis_engine, "analyze_evidence", first_slow)
    import_evidence(client)
    workflow = create(client)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.post, f"/workflows/{workflow['id']}/run", json={"expected_revision": workflow["revision"]})
        try:
            assert entered.wait(10)
            with transaction() as connection:
                connection.execute("UPDATE pm_workflows SET lease_expires_at=? WHERE id=?", (time.time() - 1, workflow["id"]))
            latest = client.get(f"/workflows/{workflow['id']}").json()
            recovered = run(client, latest)
            assert recovered["status"] == "awaiting_review"
        finally:
            release.set()
        assert future.result().status_code == 409
    assert version_count() == len(recovered["requirement_snapshots"])
    assert client.get(f"/workflows/{workflow['id']}").json() == recovered
    with connect() as connection:
        failures = [decode(row, ("after_state",))["after_state"]["error"]["code"] for row in connection.execute(
            "SELECT after_state FROM audit_events WHERE entity_id=? AND action='workflow.failed'", (workflow["id"],))]
    assert "interrupted" in failures


def test_heartbeat_renews_owner_and_cannot_renew_replacement(client, monkeypatch):
    pending = create(client)
    claimed, token = workflows._claim(pending["id"], workflows.WorkflowAction(expected_revision=pending["revision"]))
    clock = claimed["lease_expires_at"] - 1
    monkeypatch.setattr(workflows, "time", SimpleNamespace(time=lambda: clock))
    heartbeat = workflows._Heartbeat(pending["id"], token)
    waits = iter((False, True))
    heartbeat.stop = SimpleNamespace(wait=lambda _: next(waits))
    heartbeat._renew()
    with transaction() as connection:
        renewed = workflows._row(connection, pending["id"])
        assert renewed["lease_expires_at"] == clock + workflows.LEASE_SECONDS
        assert renewed["revision"] == claimed["revision"]
        connection.execute("UPDATE pm_workflows SET lease_token=? WHERE id=?", ("replacement", pending["id"]))
    heartbeat.stop = SimpleNamespace(wait=lambda _: False)
    heartbeat._renew()
    with connect() as connection:
        replacement = workflows._row(connection, pending["id"])
        assert replacement["lease_token"] == "replacement"
        assert replacement["lease_expires_at"] == renewed["lease_expires_at"]
        assert connection.execute(
            "SELECT count(*) FROM audit_events WHERE entity_id=? AND action='workflow.lease_renewed'",
            (pending["id"],),
        ).fetchone()[0] == 1


def test_rescored_requirement_requires_current_score_decision(client):
    workflow = ready(client)
    decide_all(client, workflow)
    snapshot = workflow["requirement_snapshots"][0]
    response = client.post(f"/requirements/{snapshot['requirement_id']}/scores", json={
        "expected_version_id": snapshot["version_id"], "actor": "PM Alice", "rationale": "Focus on customer impact",
        "weights": {"customer_impact": 1, "market_relevance": 0, "strategic_fit": 0, "differentiation": 0, "feasibility": 0}})
    assert response.status_code == 201, response.text
    assert complete(client, workflow).status_code == 409
    decide_all(client, workflow)
    finished = complete(client, workflow).json()
    assert finished["requirement_snapshots"][0]["score_id"] == response.json()["id"]


def test_context_only_evidence_cannot_complete_vacuous_workflow(client):
    response = client.post("/imports/records", json={
        "title": "context", "reference": "context", "records": [{"content": "Survey has 250 respondents",
        "metadata": {"topic": "survey", "sentiment": "context"}, "location": {"row": 1}}]})
    assert response.status_code == 201
    workflow = run(client, create(client))
    assert workflow["status"] == "failed"
    assert "No customer requirements" in workflow["error"]["message"]
    assert complete(client, workflow).status_code == 409
