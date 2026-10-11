"""Tool contracts: preparation uses HTTP; no request decisions or curation leak into MCP."""

import json

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from mcp_server import main as adapter


@pytest.fixture
def intake_upstream(monkeypatch):
    seen = []
    real_client = httpx.AsyncClient

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(adapter, "API_BASE_URL", "http://intake.test")
    monkeypatch.setattr(adapter.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handle), **kwargs))
    return seen


async def test_intake_tools_are_discoverable_without_human_gates():
    tools = {t.name: t for t in await adapter.mcp.list_tools()}
    expected = {"create_requests", "list_requests", "get_request", "classify_requests", "cluster_requests",
                "list_request_clusters", "propose_request_evidence", "triage_requests", "draft_request_positions",
                "get_request_aggregates", "load_simulated_requests"}
    assert expected <= tools.keys()
    assert not {"decide_request", "convert_request", "edit_request", "set_request_link_status"} & tools.keys()
    assert "weights" not in tools["triage_requests"].input_schema["properties"]
    assert tools["classify_requests"].input_schema["properties"]["provider"]["default"] == "openai"
    assert all(tools[name].input_schema["additionalProperties"] is False for name in expected)


@pytest.mark.parametrize("tool,args,method,path", [
    ("create_requests", {"requests": [{"origin_type": "dealer", "origin_name": "Simulated", "title": "Cooling",
                                      "body": "Rear seat cooling", "simulated": True}]}, "POST", "/requests"),
    ("list_requests", {"market": "CN", "simulated": True, "limit": 2}, "GET", "/requests"),
    ("get_request", {"request_id": "a/b"}, "GET", "/requests/a%2Fb"),
    ("classify_requests", {"provider": "deterministic", "request_ids": ["r"]}, "POST", "/requests/classify"),
    ("cluster_requests", {"topic": "comfort"}, "POST", "/requests/cluster"),
    ("list_request_clusters", {"market": "US"}, "GET", "/requests/clusters"),
    ("propose_request_evidence", {"request_ids": ["r"]}, "POST", "/requests/links/propose"),
    ("triage_requests", {}, "POST", "/requests/triage"),
    ("draft_request_positions", {"market": "CN"}, "POST", "/requests/positions"),
    ("get_request_aggregates", {"as_of": "2026-10-11"}, "GET", "/requests/aggregates"),
    ("load_simulated_requests", {}, "POST", "/requests/fixtures/simulated"),
])
async def test_intake_tools_use_api(intake_upstream, tool, args, method, path):
    result = await adapter.mcp.call_tool(tool, args)
    assert "true" in "".join(x.text for x in result.content if hasattr(x, "text"))
    request = intake_upstream[-1]
    assert request.method == method and request.url.raw_path.split(b"?")[0].decode() == path
    if method == "POST":
        body = json.loads(request.content)
        assert body["actor"] == "ai:request-intake"
        if tool == "triage_requests":
            assert body["link_provider"] == "none" and "weights" not in body
    if tool == "list_requests":
        assert request.url.params["market"] == "CN" and request.url.params["simulated"] == "true"


async def test_mcp_cannot_smuggle_decision_or_weight_override(intake_upstream):
    with pytest.raises(ToolError, match="Unsupported arguments"):
        await adapter.mcp.call_tool("triage_requests", {"decision": "convert", "weights": {"effort": 1}})
    assert not intake_upstream
