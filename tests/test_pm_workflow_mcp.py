import json

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from test_decision_briefs import initial_brief

import mcp_server.main as adapter
from server.main import app

REAL_ASYNC_CLIENT = httpx.AsyncClient


@pytest.mark.parametrize(("name", "args", "method", "path", "payload"), [
    ("list_actors", {}, "GET", "/actors", None),
    ("list_pm_workflows", {}, "GET", "/workflows", None),
    ("get_pm_workflow", {"workflow_id": "a/b"}, "GET", "/workflows/a%2Fb", None),
    ("get_pm_workflow_brief", {"workflow_id": ".."}, "GET", "/workflows/%2E%2E/brief", None),
    ("create_pm_workflow", {"request_key": "key", "actor": "PM"}, "POST", "/workflows",
     {"request_key": "key", "actor": "PM", "vehicle": "G60", "market": "US", "kind": "initial", "provider": "deterministic"}),
    ("run_pm_workflow", {"workflow_id": "w", "expected_revision": 3, "actor": "PM"}, "POST", "/workflows/w/run",
     {"expected_revision": 3, "actor": "PM"}),
    ("complete_pm_workflow", {"workflow_id": "w", "expected_revision": 5, "actor": "PM", "rationale": "Reviewed"},
     "POST", "/workflows/w/complete", {"expected_revision": 5, "actor": "PM", "rationale": "Reviewed"}),
])
async def test_workflow_tools_use_shared_http_contract(monkeypatch, name, args, method, path, payload):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=[] if name.startswith("list_") else {"status": "awaiting_review"})

    monkeypatch.setattr(adapter.httpx, "AsyncClient", lambda **kwargs: REAL_ASYNC_CLIENT(
        transport=httpx.MockTransport(handle), **kwargs))
    result = await adapter.mcp.call_tool(name, args)
    assert not result.is_error
    request = requests[0]
    assert request.method == method
    assert request.url.raw_path.split(b"?")[0].decode() == path
    if payload:
        assert json.loads(request.content) == payload
    if name == "list_pm_workflows":
        assert dict(request.url.params) == {"vehicle": "G60", "market": "US"}


async def test_mcp_workflow_completion_obeys_actual_api_gates(client, monkeypatch):
    workflow, _ = initial_brief(client)
    monkeypatch.setattr(adapter.httpx, "AsyncClient", lambda **kwargs: REAL_ASYNC_CLIENT(
        transport=httpx.ASGITransport(app=app), **kwargs))
    for actor, status, detail in (
        ("ai:reference:v1", 403, "active human PM"),
        ("PM", 409, "approval or rejection"),
    ):
        with pytest.raises(ToolError, match=f"HTTP {status}.*{detail}"):
            await adapter.mcp.call_tool("complete_pm_workflow", {
                "workflow_id": workflow["id"], "expected_revision": workflow["revision"],
                "actor": actor, "rationale": "Cannot bypass API review gate"})
    unchanged = client.get(f"/workflows/{workflow['id']}").json()
    assert unchanged["status"] == "awaiting_review"
    assert unchanged["revision"] == workflow["revision"]
