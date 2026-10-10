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
    "health", "list_sources", "get_source", "import_local_file", "import_records", "import_web_source", "fetch_web_source",
    "list_evidence", "get_evidence", "analyze_evidence", "get_analysis", "list_findings", "get_finding",
    "generate_requirements", "run_pipeline", "assess_updates", "list_requirements", "get_requirement",
    "get_requirement_versions", "trace_requirement", "create_requirement", "edit_requirement",
    "score_requirement", "decide_requirement", "list_reviews", "list_audit", "get_workspace",
    "search_market_evidence", "fetch_market_evidence", "import_web_candidate",
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
        assert tool.input_schema["additionalProperties"] is False
    assert "source_id" in tools["get_source"].input_schema["required"]
    decision_schema = tools["decide_requirement"].input_schema
    assert set(decision_schema["required"]) == {
        "requirement_id", "version_id", "score_id", "action", "actor", "rationale",
    }
    decision = {
        "requirement_id": "requirement-fixture", "version_id": "version-fixture", "score_id": "score-fixture",
        "action": "approve", "actor": "Fixture PM", "rationale": "Reviewed supporting and conflicting evidence",
    }
    decision_validator = Draft202012Validator(decision_schema)
    assert decision_validator.is_valid(decision)
    for field in ("version_id", "score_id"):
        assert not decision_validator.is_valid({key: value for key, value in decision.items() if key != field})
    assert "source_ids" not in tools["assess_updates"].input_schema["properties"]
    assert "expected_version_id" in tools["edit_requirement"].input_schema["required"]

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

    for name in ("search_market_evidence", "fetch_market_evidence"):
        schema = tools[name].input_schema
        validator = Draft202012Validator(schema)
        base = {"query": "BMW 5 Series US public product specifications", "public_data_confirmed": True}
        if name == "fetch_market_evidence":
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
            fetched = result_payload(await session.call_tool("fetch_market_evidence", {
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


@pytest.mark.asyncio
async def test_pm_pipeline_updates_and_historical_trace_roundtrip(live_stack):
    actor = "Fixture PM Alice"

    async with streamable_http_client(live_stack["url"]) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=15) as session:
            await session.initialize()
            await session.list_tools()

            async def call(name, **arguments):
                return result_payload(await session.call_tool(name, arguments))

            async def import_feedback(reference, records):
                return await call("import_records", title=reference, reference=reference, kind="feedback",
                                  vehicle="G60", market="US", actor=actor, records=[
                                      {"content": text, "location": {"row": row},
                                       "metadata": {"topic": topic, "sentiment": sentiment, "synthetic_fixture": True}}
                                      for row, (text, topic, sentiment) in enumerate(records, 2)
                                  ])

            async def approve(requirement):
                version = requirement["current_version"]
                return await call("decide_requirement", requirement_id=requirement["id"],
                                  version_id=version["id"], score_id=version["score"]["id"], action="approve",
                                  actor=actor, rationale="Fixture PM reviewed evidence, uncertainty, and proposed targets.")

            initial_import = await import_feedback("synthetic-initial-feedback", [
                ("Public charging is confusing and unreliable", "charging", "problem"),
                ("I love the comfortable seats", "comfort", "strength"),
            ])
            initial = await call("run_pipeline", vehicle="G60", market="US", provider="deterministic", actor=actor)
            assert initial["analysis"]["provider"] == "deterministic"
            assert any(finding["kind"] == "strength" for finding in initial["analysis"]["findings"])
            requirements = {item["topic"]: item for item in initial["generation"]["requirements"]}
            assert {"charging", "comfort"} <= requirements.keys()
            charging_decision = await approve(requirements["charging"])
            charging = charging_decision["requirement"]
            comfort = (await approve(requirements["comfort"]))["requirement"]
            original_version = charging["approved_version"]
            assert charging["status"] == "approved"
            assert charging["approved_version_id"] == original_version["id"]
            assert charging["approved_score_id"] == original_version["score"]["id"]

            newer_import = await import_feedback("synthetic-followup-feedback", [
                ("I love the easy public charging", "charging", "strength"),
            ])
            update = await call("assess_updates", vehicle="G60", market="US", provider="deterministic", actor=actor)
            updated = {item["topic"]: item for item in update["generation"]["requirements"]}
            revised = updated["charging"]
            current_version = revised["current_version"]
            assert revised["approved_version"] == original_version
            assert current_version["id"] != original_version["id"]
            assert current_version["version"] == original_version["version"] + 1
            assert current_version["score"]["explanation"]["conflict_flag"] is True
            assert revised["needs_review"] is True
            assert updated["comfort"]["current_version_id"] == comfort["current_version_id"]
            assert {review["requirement_id"] for review in update["reviews"]} == {charging["id"]}

            # Prove score and version locks independently on the real MCP wire.
            for version_id, score_id in (
                (original_version["id"], current_version["score"]["id"]),
                (current_version["id"], original_version["score"]["id"]),
            ):
                failure = await session.call_tool("decide_requirement", {
                    "requirement_id": charging["id"], "version_id": version_id, "score_id": score_id,
                    "action": "approve", "actor": actor, "rationale": "Fixture stale decision must be rejected",
                })
                assert failure.is_error
                assert "409" in " ".join(item.text for item in failure.content if item.type == "text")

            trace = await call("trace_requirement", requirement_id=charging["id"], version_id=current_version["id"])
            assert {source["id"] for source in trace["sources"]} == {
                initial_import["source_id"], newer_import["source_id"],
            }
            assert trace["evidence"]["total"] == 2
            assert all(evidence["location"] == {"row": 2} for evidence in trace["evidence"]["items"])
            assert any(finding["conflicting_evidence_ids"] for finding in trace["findings"])
            accepted_decision = await approve(revised)
            accepted = accepted_decision["requirement"]
            assert accepted["approved_version_id"] == current_version["id"]
            assert accepted["status"] == "approved" and not accepted["needs_review"]
            assert await call("list_reviews", vehicle="G60", market="US") == []

            old_trace = await call("trace_requirement", requirement_id=charging["id"], version_id=original_version["id"])
            assert old_trace["version"] == original_version
            assert {source["id"] for source in old_trace["sources"]} == {initial_import["source_id"]}
            assert old_trace["decisions"][0]["id"] == charging_decision["decision_id"]
            assert old_trace["decisions"][0]["actor"] == actor
            versions = await call("get_requirement_versions", requirement_id=charging["id"])
            assert [version["id"] for version in versions] == [original_version["id"], current_version["id"]]
            audit = await call("list_audit", entity_id=charging["id"], limit=100)
            events = audit["items"]
            assert [event["sequence"] for event in events] == sorted(event["sequence"] for event in events)
            approvals = [event for event in events if event["action"] == "requirement.approve"]
            assert [event["metadata"]["decision_id"] for event in approvals] == [
                charging_decision["decision_id"], accepted_decision["decision_id"],
            ]
            assert all(event["actor"] == actor for event in approvals)

    with sqlite3.connect(live_stack["database"]) as connection:
        # Stale calls created no decisions; the two charging approvals and one comfort approval persisted.
        assert connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 3
