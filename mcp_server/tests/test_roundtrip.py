"""Real MCP client -> HTTP MCP server -> FastAPI -> temporary SQLite checks.

Subprocesses bind only ephemeral loopback ports, use a fresh database, and are
terminated by the fixture. No existing Compose stack or BMW input is touched.
"""

import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from mcp_server.cache import FileCache
from mcp_server.exa_client import ExaClient
from mcp_server.models import FetchRequest

ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTED_TOOLS = {
    "list_sources", "get_source", "search_market_evidence", "fetch_web_source", "import_web_candidate",
}
PUBLIC_QUERY = "BMW 5 Series cabin controls US public product information"
PUBLIC_URL = "https://example.com/research/bmw-five-series"


def unused_loopback_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


@contextmanager
def running_process(command, env, log_path):
    with log_path.open("w+") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            yield process
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def wait_for_http(process, url, log_path, *, health=False):
    deadline = time.monotonic() + 20
    with httpx.Client(timeout=0.5, trust_env=False) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(f"Service exited with {process.returncode}: {log_path.read_text()[-6000:]}")
            try:
                # MCP GET can open an SSE stream indefinitely; headers prove readiness.
                with client.stream("GET", url) as response:
                    if not health:
                        return
                    response.read()
                    if response.status_code == 200 and response.json() == {"status": "ok"}:
                        return
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(0.05)
    pytest.fail(f"Service did not become ready: {log_path.read_text()[-6000:]}")


def seed_fetched_cache(directory):
    """Generate the real candidate/cache envelope with a mocked Exa response."""
    requests = []

    def handle(request):
        requests.append(request)
        assert request.url == "https://api.exa.ai/contents"
        return httpx.Response(200, json={
            "requestId": "fixture-exa-request-17",
            "results": [{
                "id": "fixture-exa-result-17", "url": PUBLIC_URL + "?utm_source=fixture",
                "title": "Synthetic public BMW product information",
                "text": "Public product information describes the BMW 5 Series cabin controls. Verify market applicability.",
                "publishedDate": None,
            }],
            "statuses": [{"id": PUBLIC_URL, "status": "success"}],
        })

    with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
        client = ExaClient(api_key="fixture-only-not-a-secret", client=transport, cache=FileCache(directory))
        response = client.fetch(FetchRequest(identifier=PUBLIC_URL, query=PUBLIC_QUERY, public_data_confirmed=True))
    assert len(requests) == 1
    return response["candidates"][0]


@pytest.fixture
def live_stack(tmp_path_factory):
    directory = tmp_path_factory.mktemp("mcp-roundtrip")
    api_port = unused_loopback_port()
    api_url = f"http://127.0.0.1:{api_port}"
    database = directory / "app.db"
    cache_directory = directory / "public-cache"
    candidate = seed_fetched_cache(cache_directory)
    env = os.environ.copy()
    env.update({
        "DB_PATH": str(database), "PYTHONUNBUFFERED": "1", "API_BASE_URL": api_url,
        "EXA_CACHE_DIR": str(cache_directory),
    })
    # Schema/read tests never need a provider credential or access to a user's cache.
    env.pop("EXA_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)
    api_log = directory / "api.log"
    command = [sys.executable, "-m", "uvicorn", "server.main:app", "--host", "127.0.0.1", "--port", str(api_port)]
    with running_process(command, env, api_log) as api:
        wait_for_http(api, f"{api_url}/health", api_log, health=True)
        with httpx.Client(base_url=api_url, timeout=5, trust_env=False) as client:
            records = []
            for title, vehicle, market in [
                ("US G60 source", "G60", "US"),
                ("DE G60 source", "G60", "DE"),
                ("US G68 source", "G68", "US"),
            ]:
                response = client.post("/sources", json={
                    "title": title, "kind": "document", "reference": f"https://example.com/{vehicle}/{market}",
                    "vehicle": vehicle, "market": market,
                })
                assert response.status_code == 201, response.text
                records.append(response.json())

        mcp_port = unused_loopback_port()
        mcp_url = f"http://127.0.0.1:{mcp_port}/mcp"
        env.update({"MCP_HOST": "127.0.0.1", "MCP_PORT": str(mcp_port), "MCP_TRANSPORT": "streamable-http"})
        mcp_log = directory / "mcp.log"
        with running_process([sys.executable, "-m", "mcp_server.main"], env, mcp_log) as mcp:
            wait_for_http(mcp, mcp_url, mcp_log)
            yield {"url": mcp_url, "records": records, "database": database, "candidate": candidate}


def result_payload(result):
    assert not result.is_error, result
    if result.structured_content is not None:
        payload = result.structured_content
        return payload["result"] if isinstance(payload, dict) and set(payload) == {"result"} else payload
    assert len(result.content) == 1 and result.content[0].type == "text"
    return json.loads(result.content[0].text)


@pytest.mark.asyncio
async def test_source_reads_roundtrip_to_persisted_backend_records(live_stack):
    async with streamable_http_client(live_stack["url"]) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=10) as session:
            await session.initialize()
            await session.list_tools()
            all_sources = result_payload(await session.call_tool("list_sources", {}))
            assert {source["id"] for source in all_sources} == {record["id"] for record in live_stack["records"]}
            sources = result_payload(await session.call_tool("list_sources", {"vehicle": "G60", "market": "US"}))
            assert sources == [live_stack["records"][0]]
            empty = result_payload(await session.call_tool("list_sources", {"vehicle": "G60", "market": "JP"}))
            assert empty == []
            source = result_payload(await session.call_tool("get_source", {"source_id": sources[0]["id"]}))
            assert source == live_stack["records"][0]
            missing = await session.call_tool("get_source", {"source_id": "00000000-0000-0000-0000-000000000000"})
            assert missing.is_error
            assert missing.content and missing.content[0].type == "text"

    with sqlite3.connect(live_stack["database"]) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 3
        # Reads must not fabricate findings, requirements, decisions, or research audit events.
        for table in ("evidence", "analysis_runs", "findings", "requirements", "decisions"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        assert connection.execute("SELECT action FROM audit_events").fetchall() == [("source.created",)] * 3


@pytest.mark.asyncio
async def test_only_real_tools_and_explicit_public_query_schemas_are_advertised(live_stack):
    async with streamable_http_client(live_stack["url"]) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=10) as session:
            await session.initialize()
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}

    assert set(tools) == IMPLEMENTED_TOOLS
    for tool in tools.values():
        Draft202012Validator.check_schema(tool.input_schema)
    assert "source_id" in tools["get_source"].input_schema["required"]

    import_schema = tools["import_web_candidate"].input_schema
    import_validator = Draft202012Validator(import_schema)
    selection = {
        "candidate_id": "candidate-fixture", "actor": "Test PM", "rationale": "Selected public market context",
        "selection_confirmed": True,
    }
    assert import_validator.is_valid(selection), list(import_validator.iter_errors(selection))
    for required in selection:
        assert not import_validator.is_valid({key: value for key, value in selection.items() if key != required})
    assert not import_validator.is_valid({**selection, "selection_confirmed": False})

    for name in ("search_market_evidence", "fetch_web_source"):
        schema = tools[name].input_schema
        validator = Draft202012Validator(schema)
        base = {"query": "BMW 5 Series US public product specifications", "public_data_confirmed": True}
        if name == "fetch_web_source":
            base["identifier"] = "https://www.bmwusa.com/vehicles/5-series/sedan/overview.html"
        assert validator.is_valid(base), list(validator.iter_errors(base))
        assert not validator.is_valid({key: value for key, value in base.items() if key != "public_data_confirmed"})
        assert not validator.is_valid({**base, "public_data_confirmed": False})
        assert not validator.is_valid({key: value for key, value in base.items() if key != "query"})
        assert schema["properties"]["vehicle"]["default"] == "G60"
        assert schema["properties"]["market"]["default"] == "US"
        if name == "search_market_evidence":
            assert schema["properties"]["max_results"]["default"] == 5
            assert validator.is_valid({**base, "max_results": 1})
            assert validator.is_valid({**base, "max_results": 10})
            assert not validator.is_valid({**base, "max_results": 0})
            assert not validator.is_valid({**base, "max_results": 11})
            assert validator.is_valid({**base, "trusted_domains": ["bmwusa.com"]})
        else:
            assert "cache_only" in schema["properties"]


@pytest.mark.asyncio
async def test_cached_fetch_import_preserves_provenance_and_deduplicates_without_provider_key(live_stack):
    actor = "Alex fixture PM"
    rationale = "Selected public product context for G60 US; verify claims before approval."
    async with streamable_http_client(live_stack["url"]) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=10) as session:
            await session.initialize()
            await session.list_tools()
            fetched = result_payload(await session.call_tool("fetch_web_source", {
                "identifier": PUBLIC_URL, "query": PUBLIC_QUERY, "public_data_confirmed": True,
                "vehicle": "G60", "market": "US", "cache_only": True,
            }))
            assert fetched["cache"]["hit"] is True
            assert fetched["persistence_status"] == "not_persisted"
            candidate = fetched["candidates"][0]
            assert candidate == live_stack["candidate"]
            assert candidate["publication_date"] is None
            assert candidate["review_status"] == "unreviewed"
            selection = {
                "candidate_id": candidate["candidate_id"], "actor": actor,
                "rationale": rationale, "selection_confirmed": True,
            }
            imported = result_payload(await session.call_tool("import_web_candidate", selection))
            assert imported["persisted"] is True
            assert imported["provenance_verified"] is True
            assert imported["review_status"] == "unreviewed"
            assert imported["deduplicated"] is False
            assert imported["record_count"] == 1
            assert "audit_id" not in imported and "audit_event_id" not in imported
            repeated = result_payload(await session.call_tool("import_web_candidate", selection))
            assert repeated["source_id"] == imported["source_id"]
            assert repeated["import_id"] == imported["import_id"]
            assert repeated["deduplicated"] is True
            source = result_payload(await session.call_tool("get_source", {"source_id": imported["source_id"]}))
            assert source["kind"] == "web"
            assert source["reference"] == candidate["canonical_url"]
            assert source["observed_at"] is None
            assert source["content_hash"] == imported["sha256"]
            assert source["metadata"]["web_evidence"] == candidate
            assert source["metadata"]["selection"] == {"actor": actor, "rationale": rationale}

    with sqlite3.connect(live_stack["database"]) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT * FROM evidence WHERE source_id=?", (imported["source_id"],)).fetchall()
        assert len(rows) == 1
        evidence = dict(rows[0])
        metadata = json.loads(evidence["metadata"])
        assert metadata["web_evidence"] == candidate
        assert metadata["record_type"] == "document_context"
        assert metadata["review_status"] == "unreviewed"
        assert evidence["content"] == candidate["content"]
        assert evidence["observed_at"] is None
        assert connection.execute("SELECT COUNT(*) FROM imports").fetchone()[0] == 1
        audits = connection.execute(
            "SELECT * FROM audit_events WHERE entity_id=?", (imported["source_id"],)
        ).fetchall()
        assert len(audits) == 1
        assert audits[0]["action"] == "source.imported"
        assert audits[0]["actor"] == actor
        # Importing source context must not approve a claim or construct a PM decision.
        for table in ("findings", "requirements", "scores", "decisions"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
