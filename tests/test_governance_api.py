"""Database decision gates must survive the HTTP and MCP boundary."""

import sqlite3
from contextlib import closing

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from database.integrity import verify_audit_chain
from database.store import connect, transaction
from mcp_server import main as adapter
from server import main as api
from server.main import app

REAL_ASYNC_CLIENT = httpx.AsyncClient


def persisted_state():
    # Include catalog discovery, key/sequence allocation, and every history row.
    # Reading through HTTP would itself create detail-access audit events.
    with closing(connect()) as connection:
        names = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        state = {name: [tuple(row) for row in connection.execute(f'SELECT * FROM "{name}" ORDER BY rowid')]
                 for name in names}
        assert verify_audit_chain(connection)["ok"]
        return state


def decision_payload(requirement, actor="PM", action="approve"):
    return {"version_id": requirement["current_version_id"],
            "score_id": requirement["current_version"]["score"]["id"],
            "actor": actor, "action": action, "rationale": "Reviewed the source evidence"}


@pytest.fixture
def proposal(client):
    response = client.post("/imports/records", json={
        "title": "Governance fixture", "reference": "governance", "kind": "feedback",
        "records": [{"content": "Public charging is confusing and unreliable", "location": {"row": 2},
                     "metadata": {"topic": "charging", "sentiment": "problem"}}],
    })
    assert response.status_code == 201, response.text
    response = client.post("/pipeline/run", json={"provider": "deterministic"})
    assert response.status_code == 201, response.text
    return response.json()["generation"]["requirements"][0]


@pytest.fixture
def revision(client, proposal):
    path = f"/requirements/{proposal['id']}"
    approved = client.post(path + "/decisions", json=decision_payload(proposal))
    assert approved.status_code == 201, approved.text
    response = client.patch(path, json={
        "expected_version_id": proposal["current_version_id"], "actor": "PM",
        "rationale": "Clarify the customer need", "title": "Make public charging easier",
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["approved_version_id"] == proposal["current_version_id"]
    assert result["needs_review"]
    return result


@pytest.mark.parametrize("actor", ["ai:reference:v1", "AI:openai", "system:scoring", "System:reference"])
@pytest.mark.parametrize("action", ["approve", "reject", "postpone", "challenge"])
def test_nonhuman_decisions_return_forbidden_without_changes(client, revision, actor, action):
    before = persisted_state()
    response = client.post(f"/requirements/{revision['id']}/decisions",
                           json=decision_payload(revision, actor, action))
    assert response.status_code == 403, response.text
    assert response.json() == {"detail": "decisions require a human actor"}
    assert persisted_state() == before


@pytest.mark.parametrize("role", ["analyst", "engineering", "viewer"])
@pytest.mark.parametrize("action", ["approve", "reject"])
def test_non_pm_decisions_return_forbidden_without_changes(client, revision, role, action):
    actor = f"human:{role}"
    with transaction() as connection:
        connection.execute("INSERT INTO actors (id,kind,display_name,role) VALUES (?,'human',?,?)",
                           (actor, role, role))
    before = persisted_state()
    response = client.post(f"/requirements/{revision['id']}/decisions",
                           json=decision_payload(revision, actor, action))
    assert response.status_code == 403, response.text
    assert response.json() == {"detail": "approve and reject require a PM role"}
    assert persisted_state() == before


@pytest.mark.parametrize("action", ["postpone", "challenge"])
def test_any_active_human_can_postpone_or_challenge(client, revision, action):
    with transaction() as connection:
        connection.execute("INSERT INTO actors (id,kind,display_name,role) "
                           "VALUES ('human:viewer','human','Viewer','viewer')")
    response = client.post(f"/requirements/{revision['id']}/decisions",
                           json=decision_payload(revision, "human:viewer", action))
    assert response.status_code == 201, response.text
    result = response.json()["requirement"]
    assert result["status"] == ("postponed" if action == "postpone" else "needs_review")
    assert result["approved_version"] == revision["approved_version"]
    assert result["needs_review"]
    with closing(connect()) as connection:
        decision = connection.execute("SELECT actor,action FROM decisions ORDER BY rowid DESC LIMIT 1").fetchone()
        assert tuple(decision) == ("human:viewer", action)
        assert verify_audit_chain(connection)["ok"]


@pytest.mark.parametrize("operation", ["decision", "edit", "score", "import", "create", "generate"])
def test_inactive_actor_denials_roll_back_complete_operation(client, revision, operation):
    actor = "human:jakob"
    with transaction() as connection:
        connection.execute("UPDATE actors SET active=0 WHERE id=?", (actor,))
    before = persisted_state()
    path = f"/requirements/{revision['id']}"
    common = {"actor": actor, "rationale": "Governance regression"}
    if operation == "decision":
        response = client.post(path + "/decisions", json=decision_payload(revision, actor))
    elif operation == "edit":
        response = client.patch(path, json={**common, "expected_version_id": revision["current_version_id"],
                                            "title": "Improve charging usability"})
    elif operation == "score":
        response = client.post(path + "/scores", json={**common,
            "expected_version_id": revision["current_version_id"],
            "weights": {name: 0.2 for name in revision["current_version"]["score"]["weights"]}})
    elif operation == "import":
        response = client.post("/imports/records", json={
            "actor": actor, "title": "New source", "reference": "new-governance-source", "kind": "feedback",
            "records": [{"content": "Seats are comfortable", "location": {"row": 3}}],
        })
    elif operation == "create":
        version = revision["current_version"]
        fields = ("title", "statement", "customer_need", "acceptance_criteria", "assumptions", "factors", "finding_ids")
        response = client.post("/requirements", json={**common, "topic": "new-charging-topic",
                                                      **{name: version[name] for name in fields}})
    else:
        with closing(connect()) as connection:
            run_id = connection.execute("SELECT id FROM analysis_runs ORDER BY rowid DESC LIMIT 1").fetchone()[0]
        response = client.post("/requirements/generate", json={"actor": actor, "run_id": run_id})
    assert response.status_code == 403, response.text
    assert response.json() == {"detail": "inactive actor"}
    assert persisted_state() == before


def test_inactive_analysis_actor_rolls_back_findings_and_audit(client, proposal):
    # A fresh evidence batch prevents an idempotent cached read from skipping writes.
    response = client.post("/imports/records", json={
        "title": "New evidence", "reference": "new-evidence", "kind": "feedback",
        "records": [{"content": "Charging remains unreliable", "location": {"row": 3},
                     "metadata": {"topic": "charging", "sentiment": "problem"}}],
    })
    assert response.status_code == 201, response.text
    with transaction() as connection:
        connection.execute("UPDATE actors SET active=0 WHERE id='human:jakob'")
    before = persisted_state()
    response = client.post("/analyses", json={"actor": "human:jakob", "provider": "deterministic"})
    assert response.status_code == 403, response.text
    assert response.json() == {"detail": "inactive actor"}
    assert persisted_state() == before


@pytest.mark.parametrize("actor", ["PM", "human:troy", "human:jakob", "New PM"])
def test_pm_approval_uses_exact_version_and_score_and_preserves_key(client, revision, actor):
    response = client.post(f"/requirements/{revision['id']}/decisions",
                           json=decision_payload(revision, actor))
    assert response.status_code == 201, response.text
    result = response.json()["requirement"]
    assert result["key"] == revision["key"] == "REQ-G60-US-001"
    assert result["approved_version_id"] == revision["current_version_id"]
    assert result["approved_score_id"] == revision["current_version"]["score"]["id"]
    assert result["status"] == "approved"
    assert not result["needs_review"]
    with closing(connect()) as connection:
        registered = connection.execute("SELECT kind,role,active FROM actors WHERE id=?", (actor,)).fetchone()
        assert registered["kind"] == "human" and registered["role"] in ("pm", "lead_pm") and registered["active"]
        assert verify_audit_chain(connection)["ok"]


async def test_mcp_preserves_database_actor_denial_and_rolls_back(client, revision, monkeypatch):
    monkeypatch.setattr(adapter, "API_BASE_URL", "http://api.test")
    monkeypatch.setattr(adapter.httpx, "AsyncClient", lambda **kwargs: REAL_ASYNC_CLIENT(
        transport=httpx.ASGITransport(app=app), **kwargs))
    before = persisted_state()
    with pytest.raises(ToolError, match="API returned HTTP 403: decisions require a human actor"):
        await adapter.mcp.call_tool("decide_requirement", {
            "requirement_id": revision["id"], **decision_payload(revision, "ai:openai:test")})
    assert persisted_state() == before


@pytest.mark.parametrize("message", ["FOREIGN KEY constraint failed", "audit event does not continue the hash chain"])
def test_unexpected_integrity_errors_remain_server_failures(client, monkeypatch, message):
    def fail(data):
        raise sqlite3.IntegrityError(message)

    monkeypatch.setattr(api, "create_source", fail)
    # A broken write or audit chain must still reach server error reporting,
    # rather than disguising it as a permission denial attributable to the PM.
    with pytest.raises(sqlite3.IntegrityError, match=message):
        client.post("/sources", json={"title": "Source", "kind": "feedback", "reference": "fixture"})
