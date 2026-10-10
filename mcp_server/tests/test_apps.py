"""MCP Apps contracts over the real client/Streamable HTTP protocol.

The UI bundle is represented by temporary, self-contained HTML so the normal
Python suite needs neither Node nor built frontend assets. API round trips use a
temporary SQLite database and deterministic analysis; no provider is contacted.
"""

import json
from contextlib import asynccontextmanager

import httpx
import httpx2
import pytest
from fastapi.testclient import TestClient
from mcp import ClientSession, MCPError
from mcp.client.streamable_http import streamable_http_client

from mcp_server import apps
from mcp_server import main as adapter
from server.main import app as api_app

REAL_ASYNC_CLIENT = httpx.AsyncClient
APP_MIME = "text/html;profile=mcp-app"
APP_RESOURCES = {
    "ui://bmw-evidence/scoring-panel.html": "scoring-panel.html",
    "ui://bmw-evidence/trace-explorer.html": "trace-explorer.html",
}
IMPLEMENTED_TOOLS = {
    "health", "list_sources", "get_source", "import_local_file", "import_records", "import_web_source", "fetch_web_source",
    "list_evidence", "get_evidence", "analyze_evidence", "get_analysis", "list_findings", "get_finding",
    "generate_requirements", "run_pipeline", "assess_updates", "list_requirements", "get_requirement",
    "get_requirement_versions", "trace_requirement", "create_requirement", "edit_requirement",
    "score_requirement", "decide_requirement", "list_reviews", "list_audit", "get_workspace",
    "search_market_evidence", "fetch_market_evidence", "import_web_candidate",
    "list_actors", "create_pm_workflow", "list_pm_workflows", "get_pm_workflow",
    "run_pm_workflow", "complete_pm_workflow", "get_pm_workflow_brief",
}
PRIVATE_VALUES = {
    "OPENAI_API_KEY": "synthetic-openai-secret-do-not-embed",
    "EXA_API_KEY": "synthetic-exa-secret-do-not-embed",
    "API_BASE_URL": "http://private-backend.invalid:8123",
}


@pytest.fixture
def ui_files(tmp_path, monkeypatch):
    directory = tmp_path / "private-build-directory" / "dist"
    directory.mkdir(parents=True)
    contents = {}
    for uri, filename in APP_RESOURCES.items():
        # Template-looking text must stay literal, including Unicode and braces.
        html = (
            '<!doctype html><html><head><meta charset="UTF-8">'
            '<style>body{color:#123}</style></head><body>'
            f"<main>{filename} — G60 / US</main>"
            "<pre>${OPENAI_API_KEY} {{EXA_API_KEY}} ${API_BASE_URL}</pre>"
            '<script type="module">document.body.dataset.ready="true";</script>'
            "</body></html>\n"
        )
        (directory / filename).write_text(html, encoding="utf-8")
        contents[uri] = html
    monkeypatch.setattr(apps, "UI_DIR", directory)
    for name, value in PRIVATE_VALUES.items():
        monkeypatch.setenv(name, value)
    return directory, contents


@pytest.fixture
def app_session(ui_files):
    # Pytest-asyncio drives fixture setup/teardown in different tasks. Keep AnyIO
    # task-group entry/exit in each test's task by returning a context manager.
    return open_app_session


@asynccontextmanager
async def open_app_session():
    """Use SDK requests and responses, with HTTP dispatched in-process only."""
    application = adapter.mcp.streamable_http_app(json_response=True, stateless_http=True)
    async with application.router.lifespan_context(application):
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(application), trust_env=False) as client:
            async with streamable_http_client("http://127.0.0.1:8001/mcp", http_client=client) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=5) as session:
                    await session.initialize()
                    yield session


def wire(value):
    return value.model_dump(by_alias=True, exclude_none=True)


def payload(result):
    assert not result.is_error, result
    # The pinned SDK emits bare `-> dict` results as JSON text. Apps must retain
    # this fallback even if a future SDK also supplies structuredContent.
    text_blocks = [block.text for block in result.content if block.type == "text"]
    assert len(text_blocks) == 1
    value = json.loads(text_blocks[0])
    assert isinstance(value, dict)
    if result.structured_content is not None:
        assert result.structured_content == value
    return value


async def test_apps_attach_to_existing_read_tools_without_changing_tool_contracts(app_session):
    async with app_session() as session:
        tools = {tool.name: wire(tool) for tool in (await session.list_tools()).tools}
        assert len(tools) == len(IMPLEMENTED_TOOLS)
        assert set(tools) == IMPLEMENTED_TOOLS
        links = {
            name: tool["_meta"]["ui"]["resourceUri"]
            for name, tool in tools.items()
            if tool.get("_meta", {}).get("ui", {}).get("resourceUri")
        }
        assert links == {
            "get_requirement": "ui://bmw-evidence/scoring-panel.html",
            "trace_requirement": "ui://bmw-evidence/trace-explorer.html",
        }
        resources = {str(resource.uri) for resource in (await session.list_resources()).resources}
        assert set(links.values()) <= resources
        assert all(tool["inputSchema"]["additionalProperties"] is False for tool in tools.values())
        assert set(tools["get_requirement"]["inputSchema"]["properties"]) == {"requirement_id"}
        assert set(tools["trace_requirement"]["inputSchema"]["properties"]) == {
            "requirement_id", "version_id", "score_id", "limit", "offset",
        }
        assert set(tools["trace_requirement"]["inputSchema"]["required"]) == {"requirement_id"}
        assert set(tools["decide_requirement"]["inputSchema"]["required"]) == {
            "requirement_id", "version_id", "score_id", "action", "actor", "rationale",
        }
        assert "expected_score_id" in tools["score_requirement"]["inputSchema"]["properties"]
        assert "expected_version_id" in tools["score_requirement"]["inputSchema"]["required"]


async def test_resource_discovery_and_reads_preserve_html_mime_and_sandbox_metadata(app_session, ui_files):
    async with app_session() as session:
        _, expected_html = ui_files
        resources = {str(resource.uri): wire(resource) for resource in (await session.list_resources()).resources}
        assert set(resources) == set(APP_RESOURCES)
        assert not (await session.list_resource_templates()).resource_templates
        for uri, resource in resources.items():
            assert resource["mimeType"] == APP_MIME
            metadata = resource["_meta"]["ui"]
            assert metadata["prefersBorder"] is False
            assert metadata["csp"]["connectDomains"] == []
            assert metadata["csp"]["resourceDomains"] == []
            result = wire(await session.read_resource(uri))
            assert len(result["contents"]) == 1
            content = result["contents"][0]
            assert content["uri"] == uri
            assert content["mimeType"] == APP_MIME
            assert content["_meta"]["ui"] == metadata
            assert content["text"] == expected_html[uri]
            assert "blob" not in content
            assert all(value not in json.dumps(result) for value in PRIVATE_VALUES.values())


@pytest.mark.parametrize("uri", APP_RESOURCES)
async def test_missing_bundle_is_an_actionable_safe_protocol_error(app_session, ui_files, uri):
    async with app_session() as session:
        directory, _ = ui_files
        (directory / APP_RESOURCES[uri]).unlink()
        # Missing builds do not prevent tool/resource discovery or unrelated reads.
        assert len((await session.list_tools()).tools) == len(IMPLEMENTED_TOOLS)
        assert {str(resource.uri) for resource in (await session.list_resources()).resources} == set(APP_RESOURCES)
        with pytest.raises(MCPError) as caught:
            await session.read_resource(uri)
        message = caught.value.message
        assert "build" in message.lower()
        assert APP_RESOURCES[uri] in message
        assert str(directory) not in message
        assert all(value not in message for value in PRIVATE_VALUES.values())
        other_uri = next(value for value in APP_RESOURCES if value != uri)
        assert (await session.read_resource(other_uri)).contents


@pytest.mark.parametrize("uri", [
    "ui://bmw-evidence/unknown.html",
    "ui://bmw-evidence/../../private-secret.txt",
    "ui://bmw-evidence/scoring-panel.html?file=../../private-secret.txt",
])
async def test_resource_uris_cannot_select_arbitrary_files(app_session, ui_files, uri):
    async with app_session() as session:
        directory, _ = ui_files
        private_content = "synthetic-local-file-not-a-resource"
        (directory.parent / "private-secret.txt").write_text(private_content, encoding="utf-8")
        with pytest.raises(MCPError) as caught:
            await session.read_resource(uri)
        assert caught.value.code == -32602
        assert private_content not in caught.value.message
        assert str(directory) not in caught.value.message


@pytest.fixture
def api_requirement(tmp_path, monkeypatch):
    """An approved version plus a newer proposal with exact source locations."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path / "snapshots"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    with TestClient(api_app) as client:
        imported = client.post("/imports/records", json={
            "title": "Synthetic G60 customer feedback", "reference": "synthetic:app-contracts", "kind": "feedback",
            "vehicle": "G60", "market": "US", "records": [
                {"content": content, "location": {"sheet": "Feedback", "row": index + 2},
                 "metadata": {"topic": "charging", "sentiment": "problem"}, "observed_at": "2026-09-01"}
                for index, content in enumerate([
                    "Public charging is confusing and unreliable.",
                    "Public charging requires too many separate steps.",
                ])
            ],
        })
        assert imported.status_code == 201, imported.text
        generated = client.post("/pipeline/run", json={"provider": "deterministic"})
        assert generated.status_code == 201, generated.text
        requirement = next(
            item for item in generated.json()["generation"]["requirements"] if item["topic"] == "charging"
        )
        original = requirement["current_version"]
        approved = client.post(f"/requirements/{requirement['id']}/decisions", json={
            "version_id": original["id"], "score_id": original["score"]["id"], "action": "approve",
            "actor": "Fixture PM", "rationale": "Reviewed the exact synthetic evidence and score",
        })
        assert approved.status_code == 201, approved.text
        edited = client.patch(f"/requirements/{requirement['id']}", json={
            "expected_version_id": original["id"], "title": "Simplify the public charging workflow",
            "actor": "Fixture PM", "rationale": "Make the proposal title more specific",
        })
        assert edited.status_code == 200, edited.text
        monkeypatch.setattr(adapter, "API_BASE_URL", "http://api.test")
        monkeypatch.setattr(adapter.httpx, "AsyncClient", lambda **kwargs: REAL_ASYNC_CLIENT(
            transport=httpx.ASGITransport(api_app), trust_env=False, **kwargs))
        yield client, edited.json()


async def test_app_read_tools_keep_persisted_detail_and_historical_trace_shapes(app_session, api_requirement):
    async with app_session() as session:
        client, expected = api_requirement
        requirement_id = expected["id"]
        await session.list_tools()
        detail = payload(await session.call_tool("get_requirement", {"requirement_id": requirement_id}))
        assert detail == expected
        assert detail["needs_review"] is True
        assert detail["current_version"]["id"] != detail["approved_version"]["id"]
        assert detail["approved_version"]["score"]["id"] == detail["approved_score_id"]
        params = {"version_id": detail["approved_version_id"], "limit": 1, "offset": 1}
        trace = payload(await session.call_tool("trace_requirement", {"requirement_id": requirement_id, **params}))
        expected_trace = client.get(f"/requirements/{requirement_id}/trace", params=params)
        assert expected_trace.status_code == 200
        assert trace == expected_trace.json()
        assert trace["version"]["id"] == detail["approved_version_id"]
        assert trace["evidence"]["total"] == 2
        assert trace["evidence"]["limit"] == trace["evidence"]["offset"] == 1
        assert len(trace["evidence"]["items"]) == 1
        evidence = trace["evidence"]["items"][0]
        assert evidence["location"]["sheet"] == "Feedback"
        assert evidence["source_id"] in {source["id"] for source in trace["sources"]}
        assert evidence["id"] in {identifier for finding in trace["findings"] for identifier in finding["evidence_ids"]}
        assert trace["decisions"][0]["score_id"] == detail["approved_score_id"]


async def test_app_scoring_roundtrip_keeps_approval_and_rejects_stale_score(app_session, api_requirement):
    async with app_session() as session:
        _, requirement = api_requirement
        await session.list_tools()
        arguments = {
            "requirement_id": requirement["id"], "expected_version_id": requirement["current_version_id"],
            "expected_score_id": requirement["current_version"]["score"]["id"],
            "actor": "Fixture PM", "rationale": "Emphasize customer impact after explicit review",
            "weights": {"customer_impact": 1, "market_relevance": 0, "strategic_fit": 0,
                        "differentiation": 0, "feasibility": 0},
        }
        score = payload(await session.call_tool("score_requirement", arguments))
        assert score["id"] != arguments["expected_score_id"]
        assert score["weights"] == arguments["weights"]
        current = payload(await session.call_tool("get_requirement", {"requirement_id": requirement["id"]}))
        assert current["current_version"]["score"] == score
        assert current["current_version_id"] == requirement["current_version_id"]
        assert current["approved_version"] == requirement["approved_version"]
        assert current["approved_score_id"] == requirement["approved_score_id"]
        stale = await session.call_tool("score_requirement", arguments)
        assert stale.is_error is True
        assert "HTTP 409" in stale.content[0].text
        assert "reload" in stale.content[0].text
