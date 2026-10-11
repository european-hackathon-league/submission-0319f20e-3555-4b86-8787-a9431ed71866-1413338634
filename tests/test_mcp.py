"""Adapter contract checks and a real Streamable HTTP protocol round trip."""

import json

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from mcp_server import main as adapter

REAL_ASYNC_CLIENT = httpx.AsyncClient
FACTORS = {name: 3 for name in (
    "customer_impact", "market_relevance", "strategic_fit", "differentiation", "feasibility")}
CRITERION = {"metric": "task completion", "target": 95, "unit": "%", "basis": "PM assumption", "source_ids": []}


@pytest.fixture
def upstream(monkeypatch):
    requests = []
    behavior = {"status": 200, "json": {"ok": True}}

    def handle(request):
        requests.append(request)
        if "error" in behavior:
            raise behavior["error"]("simulated transport failure", request=request)
        if "text" in behavior:
            return httpx.Response(behavior["status"], text=behavior["text"])
        return httpx.Response(behavior["status"], json=behavior["json"])

    monkeypatch.setattr(adapter, "API_BASE_URL", "http://api.test")
    monkeypatch.setattr(adapter.httpx, "AsyncClient", lambda **kwargs: REAL_ASYNC_CLIENT(
        transport=httpx.MockTransport(handle), **kwargs))
    return requests, behavior


def body(request):
    return json.loads(request.content)


def text_result(result):
    return "\n".join(item.text for item in result.content if hasattr(item, "text"))


class _ToolRecorder:
    """Collects the tool names a platform registrar adds, without an MCP server or API."""

    def __init__(self):
        self.names = set()

    def tool(self, *args, **kwargs):
        def decorator(function):
            self.names.add(kwargs.get("name") or function.__name__)
            return function
        return decorator

    def __getattr__(self, name):
        return lambda *args, **kwargs: (lambda function: function)


def platform_tool_names() -> set[str]:
    recorder = _ToolRecorder()
    for register in adapter.PLATFORM_TOOL_REGISTRARS:
        register(recorder, None, None)
    return recorder.names


async def test_every_pipeline_operation_is_discoverable():
    tools = {tool.name: tool for tool in await adapter.mcp.list_tools()}
    platform = platform_tool_names()
    assert platform <= set(tools)
    assert set(tools) - platform == {
        "health", "list_sources", "get_source", "import_local_file", "import_records", "import_web_source", "fetch_web_source",
        "list_evidence", "get_evidence", "analyze_evidence", "get_analysis", "list_findings", "get_finding",
        "generate_requirements", "run_pipeline", "assess_updates", "list_requirements", "get_requirement",
        "get_requirement_versions", "trace_requirement", "create_requirement", "edit_requirement",
        "score_requirement", "decide_requirement", "list_reviews", "list_audit", "get_workspace",
        "search_market_evidence", "fetch_market_evidence", "import_web_candidate",
        "list_actors", "create_pm_workflow", "list_pm_workflows", "get_pm_workflow",
        "run_pm_workflow", "complete_pm_workflow", "get_pm_workflow_brief",
    }
    # Clients can discover required optimistic-lock tokens and nested target/factor schemas.
    assert set(tools["decide_requirement"].input_schema["required"]) == {
        "requirement_id", "version_id", "score_id", "action", "actor", "rationale"}
    assert "source_ids" not in tools["assess_updates"].input_schema["properties"]
    assert all(tool.input_schema["additionalProperties"] is False for tool in tools.values())
    assert tools["create_requirement"].input_schema["properties"]["factors"]
    assert "additionalProperties" in tools["create_requirement"].input_schema["$defs"]["FactorInputs"]


@pytest.mark.parametrize(("name", "arguments"), [
    ("assess_updates", {"source_ids": ["new-source"]}),
    ("run_pipeline", {"market_id": "UK"}),
    ("decide_requirement", {"requirement_id": "r1", "version_id": "v1", "score_id": "s1", "action": "approve",
                            "actor": "PM", "rationale": "Reviewed", "auto_approve": True}),
])
async def test_unsupported_arguments_never_execute_api_commands(upstream, name, arguments):
    requests, _ = upstream
    with pytest.raises(ToolError, match="Unsupported arguments"):
        await adapter.mcp.call_tool(name, arguments)
    assert requests == []


@pytest.mark.parametrize(("name", "arguments", "path", "query", "response"), [
    ("health", {}, "/health", {}, {"status": "ok"}),
    ("list_sources", {"vehicle": "G60", "market": "US"}, "/sources", {"vehicle": "G60", "market": "US"}, [{"id": "source"}]),
    ("get_source", {"source_id": "source"}, "/sources/source", {}, {}),
    ("list_evidence", {"source_id": "source", "q": "charging & range", "limit": 12, "offset": 2}, "/evidence",
     {"source_id": "source", "q": "charging & range", "limit": "12", "offset": "2"}, {"items": []}),
    ("get_evidence", {"evidence_id": "e1"}, "/evidence/e1", {}, {}),
    ("get_analysis", {"run_id": "r1"}, "/analyses/r1", {}, {}),
    ("list_findings", {"vehicle": "G60", "market": "US", "run_id": "r1", "limit": 12, "offset": 2}, "/findings",
     {"vehicle": "G60", "market": "US", "run_id": "r1", "limit": "12", "offset": "2"}, {"items": []}),
    ("get_finding", {"finding_id": "f1"}, "/findings/f1", {}, {}),
    ("list_requirements", {"vehicle": "G60", "market": "US", "status": "approved", "needs_review": True},
     "/requirements", {"vehicle": "G60", "market": "US", "status": "approved", "needs_review": "true", "limit": "100", "offset": "0"}, {"items": []}),
    ("get_requirement", {"requirement_id": "req1"}, "/requirements/req1", {}, {}),
    ("get_requirement_versions", {"requirement_id": "req1"}, "/requirements/req1/versions", {}, []),
    ("trace_requirement", {"requirement_id": "req1", "version_id": "v1", "limit": 10, "offset": 5}, "/requirements/req1/trace",
     {"version_id": "v1", "limit": "10", "offset": "5"}, {}),
    ("trace_requirement", {"requirement_id": "req1", "version_id": "v1", "score_id": "s1"},
     "/requirements/req1/trace", {"version_id": "v1", "score_id": "s1", "limit": "100", "offset": "0"}, {}),
    ("list_reviews", {"vehicle": "G60", "market": "US", "status": "resolved"}, "/reviews",
     {"vehicle": "G60", "market": "US", "status": "resolved"}, []),
    ("list_audit", {"entity_id": "req1", "after": 15, "limit": 4}, "/audit",
     {"entity_id": "req1", "after": "15", "limit": "4"}, {}),
    ("get_workspace", {}, "/workspace", {"vehicle": "G60", "market": "US"}, {}),
])
async def test_read_tools_preserve_api_paths_queries_and_shapes(upstream, name, arguments, path, query, response):
    requests, behavior = upstream
    behavior["json"] = response
    result = await adapter.mcp.call_tool(name, arguments)
    assert not result.is_error
    if isinstance(response, list):
        assert result.structured_content == {"result": response}
    else:
        assert json.loads(text_result(result)) == response
    request = requests[-1]
    assert request.method == "GET"
    assert request.url.path == path
    assert dict(request.url.params) == query


@pytest.mark.parametrize(("tool", "key", "prefix", "suffix"), [
    ("get_source", "source_id", "/sources/", ""),
    ("get_evidence", "evidence_id", "/evidence/", ""),
    ("get_analysis", "run_id", "/analyses/", ""),
    ("get_finding", "finding_id", "/findings/", ""),
    ("get_requirement", "requirement_id", "/requirements/", ""),
    ("get_requirement_versions", "requirement_id", "/requirements/", "/versions"),
    ("trace_requirement", "requirement_id", "/requirements/", "/trace"),
])
async def test_path_ids_cannot_inject_routes_or_query_parameters(upstream, tool, key, prefix, suffix):
    requests, behavior = upstream
    behavior["json"] = [] if tool == "get_requirement_versions" else {}
    await adapter.mcp.call_tool(tool, {key: "a/b ?#ü"})
    encoded_path = requests[-1].url.raw_path.split(b"?")[0].decode()
    assert encoded_path == prefix + "a%2Fb%20%3F%23%C3%BC" + suffix


@pytest.mark.parametrize("identifier", [".", ".."])
async def test_dot_segment_ids_cannot_be_normalized_into_other_routes(upstream, identifier):
    requests, _ = upstream
    await adapter.mcp.call_tool("decide_requirement", {
        "requirement_id": identifier, "version_id": "v1", "score_id": "s1", "action": "approve",
        "actor": "PM", "rationale": "Reviewed",
    })
    assert requests[-1].url.raw_path == b"/requirements/" + b"%2E" * len(identifier) + b"/decisions"


async def test_record_import_inherits_scope_without_losing_locations_or_metadata(upstream):
    requests, _ = upstream
    await adapter.mcp.call_tool("import_records", {
        "title": "UK study", "reference": "study:2026", "vehicle": "G61", "market": "UK", "actor": "Alex",
        "metadata": {"provenance": "survey"}, "records": [
            {"content": "Rear space is tight", "location": {"sheet": "Drivers", "row": 18},
             "metadata": {"respondent": "42"}, "observed_at": "2026-09-10"},
            {"content": "explicit scope", "location": {"row": 19}, "vehicle": "G60", "market": "US"},
        ],
    })
    request = requests[-1]
    assert (request.method, request.url.path) == ("POST", "/imports/records")
    payload = body(request)
    assert payload["actor"] == "Alex"
    assert payload["metadata"] == {"provenance": "survey"}
    assert payload["records"][0] == {
        "content": "Rear space is tight", "location": {"sheet": "Drivers", "row": 18},
        "metadata": {"respondent": "42"}, "observed_at": "2026-09-10", "vehicle": "G61", "market": "UK"}
    # A caller's mismatched scope is left intact for the API to reject, not silently rewritten.
    assert payload["records"][1]["vehicle"] == "G60"


@pytest.mark.parametrize(("name", "args", "path", "expected"), [
    ("import_local_file", {"path": "bmw/study.xlsx"}, "/imports/local",
     {"path": "bmw/study.xlsx", "vehicle": "G60", "market": "US", "kind": "document", "actor": "PM"}),
    ("import_web_source", {"url": "https://example.com/study", "title": "Study", "content": "Source text", "observed_at": "2026-10-01"},
     "/imports/web", {"url": "https://example.com/study", "title": "Study", "content": "Source text", "observed_at": "2026-10-01",
                      "vehicle": "G60", "market": "US", "actor": "PM"}),
    ("analyze_evidence", {"source_ids": ["s1"], "provider": "openai"}, "/analyses",
     {"vehicle": "G60", "market": "US", "provider": "openai", "source_ids": ["s1"], "actor": "PM"}),
    ("generate_requirements", {"run_id": "r1", "actor": "Alex"}, "/requirements/generate", {"run_id": "r1", "actor": "Alex"}),
    ("run_pipeline", {}, "/pipeline/run", {"vehicle": "G60", "market": "US", "provider": "deterministic", "actor": "PM"}),
    ("assess_updates", {}, "/updates", {"vehicle": "G60", "market": "US", "provider": "deterministic", "actor": "PM"}),
    ("score_requirement", {"requirement_id": "r1", "expected_version_id": "v2", "actor": "Alex", "rationale": "New rubric"},
     "/requirements/r1/scores", {"expected_version_id": "v2", "actor": "Alex", "rationale": "New rubric"}),
    ("decide_requirement", {"requirement_id": "r1", "version_id": "v2", "score_id": "sc3", "action": "approve", "actor": "Alex", "rationale": "Accept evidence"},
     "/requirements/r1/decisions", {"version_id": "v2", "score_id": "sc3", "action": "approve", "actor": "Alex", "rationale": "Accept evidence"}),
])
async def test_write_tools_preserve_api_commands(upstream, name, args, path, expected):
    requests, _ = upstream
    result = await adapter.mcp.call_tool(name, args)
    assert not result.is_error
    assert (requests[-1].method, requests[-1].url.path) == ("POST", path)
    assert body(requests[-1]) == expected


async def test_manual_requirement_sends_typed_content(upstream):
    requests, _ = upstream
    args = {"topic": "usability", "title": "Improve controls", "statement": "Drivers can operate climate controls",
            "customer_need": "Adjust temperature quickly", "acceptance_criteria": [CRITERION], "factors": FACTORS,
            "finding_ids": ["f1"], "rationale": "Customer feedback", "assumptions": ["Target requires validation"]}
    await adapter.mcp.call_tool("create_requirement", args)
    assert body(requests[-1]) == {**args, "vehicle": "G60", "market": "US", "actor": "PM"}


async def test_edit_omits_unspecified_fields_but_keeps_empty_lists_and_current_version(upstream):
    requests, _ = upstream
    await adapter.mcp.call_tool("edit_requirement", {
        "requirement_id": "r/1", "expected_version_id": "v1", "actor": "Alex", "rationale": "Clarify",
        "title": "Revised title", "assumptions": [], "factors": FACTORS,
    })
    assert requests[-1].method == "PATCH"
    assert requests[-1].url.raw_path == b"/requirements/r%2F1"
    assert body(requests[-1]) == {"expected_version_id": "v1", "actor": "Alex", "rationale": "Clarify",
                                  "title": "Revised title", "assumptions": [], "factors": FACTORS}


async def test_custom_weights_are_passed_intact(upstream):
    requests, _ = upstream
    weights = {name: 0.2 for name in FACTORS}
    await adapter.mcp.call_tool("score_requirement", {
        "requirement_id": "r1", "expected_version_id": "v1", "actor": "Alex", "rationale": "Equal weighting", "weights": weights})
    assert body(requests[-1])["weights"] == weights


@pytest.mark.parametrize(("status", "detail"), [
    (409, "Requirement or score changed; reload before deciding"),
    (422, [{"loc": ["body", "weights"], "msg": "Scoring weights must sum to 1", "type": "value_error"}]),
    (404, "Requirement version not found"),
])
async def test_expected_http_errors_preserve_detail_for_mcp_clients(upstream, status, detail):
    _, behavior = upstream
    behavior.update(status=status, json={"detail": detail})
    with pytest.raises(ToolError) as caught:
        await adapter.mcp.call_tool("get_requirement", {"requirement_id": "r1"})
    assert f"HTTP {status}" in str(caught.value)
    assert (detail if isinstance(detail, str) else "Scoring weights must sum to 1") in str(caught.value)


@pytest.mark.parametrize(("status", "content", "message"), [
    (502, "Upstream unavailable", "HTTP 502: Upstream unavailable"),
    (200, "broken JSON", "invalid JSON"),
    (200, '"scalar response"', "unexpected JSON"),
    (302, "", "HTTP 302"),
])
async def test_non_json_and_unexpected_responses_are_errors(upstream, status, content, message):
    _, behavior = upstream
    behavior.update(status=status, text=content)
    with pytest.raises(ToolError, match=message):
        await adapter.mcp.call_tool("health", {})


@pytest.mark.parametrize(("error", "message"), [
    (httpx.ConnectError, "Cannot reach API"), (httpx.ReadTimeout, "timed out"),
])
async def test_transport_failures_are_actionable(upstream, error, message):
    requests, behavior = upstream
    behavior["error"] = error
    with pytest.raises(ToolError, match=message):
        await adapter.mcp.call_tool("health", {})
    assert requests[-1].extensions["timeout"]["connect"] <= 10
    assert requests[-1].extensions["timeout"]["read"] == adapter.API_TIMEOUT_SECONDS


async def test_streamable_http_protocol_reports_success_and_errors(upstream):
    """Exercise initialization, discovery, typed tools/call, and isError on the wire."""
    requests, behavior = upstream
    app = adapter.mcp.streamable_http_app(json_response=True, stateless_http=True)
    headers = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-03-26"}
    async with app.router.lifespan_context(app):
        async with REAL_ASYNC_CLIENT(transport=httpx.ASGITransport(app), base_url="http://127.0.0.1:8001", headers=headers) as client:
            async def rpc(method, params, sequence):
                response = await client.post("/mcp", json={"jsonrpc": "2.0", "id": sequence, "method": method, "params": params})
                assert response.status_code == 200, response.text
                return response.json()

            initialized = await rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                                    "clientInfo": {"name": "adapter-test", "version": "1"}}, 1)
            assert "serverInfo" in initialized["result"]
            tools = await rpc("tools/list", {}, 2)
            assert any(tool["name"] == "decide_requirement" for tool in tools["result"]["tools"])
            assert all(tool["inputSchema"]["additionalProperties"] is False for tool in tools["result"]["tools"])
            success = await rpc("tools/call", {"name": "run_pipeline", "arguments": {}}, 3)
            assert not success["result"].get("isError", False)
            assert requests[-1].url.path == "/pipeline/run"
            behavior.update(status=409, json={"detail": "Requirement or score changed; reload before deciding"})
            failure = await rpc("tools/call", {"name": "decide_requirement", "arguments": {
                "requirement_id": "r1", "version_id": "v1", "score_id": "s1", "action": "approve", "actor": "PM", "rationale": "Reviewed"}}, 4)
            assert failure["result"]["isError"] is True
            assert "HTTP 409" in failure["result"]["content"][0]["text"]
            assert "reload before deciding" in failure["result"]["content"][0]["text"]
            request_count = len(requests)
            unsupported = await rpc("tools/call", {"name": "assess_updates", "arguments": {"source_ids": ["s1"]}}, 5)
            assert unsupported["result"]["isError"] is True
            assert "Unsupported arguments" in unsupported["result"]["content"][0]["text"]
            assert len(requests) == request_count


async def test_fetch_source_and_score_guard_reach_api(upstream):
    requests, _ = upstream
    await adapter.fetch_web_source("https://example.org/research", "Research")
    assert requests[-1].url.path == "/imports/web-fetch"
    assert body(requests[-1])["url"] == "https://example.org/research"
    await adapter.score_requirement("r", "v", "PM", "Changed rubric", expected_score_id="s")
    assert body(requests[-1])["expected_score_id"] == "s"
