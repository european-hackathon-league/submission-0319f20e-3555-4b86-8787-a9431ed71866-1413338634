"""Offline checks of the live OpenAI verifier through the real API/MCP adapter.

These tests mock the external OpenAI HTTP response and local network transports. Passing them
is not evidence of a successful paid/provider call; scripts/verify_openai.py is
the separate live command and has no reference-provider substitution.
"""
import json
from contextlib import asynccontextmanager
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
from urllib.error import HTTPError

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from mcp_server import main as adapter
from scripts import verify_openai as verifier
from scripts.verify_backend import VerificationFailure, decode_tool_result
from server import analysis_engine as engine
from server.main import app


@pytest.fixture
def offline_provider(monkeypatch):
    calls = []
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-6.1-sol")
    monkeypatch.setenv("ANALYSIS_BATCH_SIZE", "40")
    monkeypatch.setenv("ANALYSIS_MAX_BATCHES", "20")

    def request(request, timeout):
        assert request.full_url == "https://api.openai.com/v1/responses"
        assert request.method == "POST" and timeout == 90
        assert request.get_header("Authorization") == "Bearer test-only-key"
        assert request.get_header("Content-type") == "application/json"
        payload = json.loads(request.data)
        assert payload["model"] == "gpt-6.1-sol" and payload["store"] is False
        assert payload["text"]["format"]["type"] == "json_schema" and payload["text"]["format"]["strict"] is True
        records = json.loads(payload["input"])["evidence"]
        calls.append(records)
        # Reference output is solely an offline structured-response fixture.
        fixture = engine.analyze_evidence(records, records[0]["vehicle"], "US", provider="deterministic")
        analysis = {key: deepcopy(fixture[key]) for key in ("findings", "proposals", "warnings")}
        wire = {"status": "completed", "output": [{"type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(analysis)}]}]}
        return BytesIO(json.dumps(wire).encode())

    monkeypatch.setattr(engine, "urlopen", request)
    return calls


@asynccontextmanager
async def offline_api(monkeypatch, fault=None, http_fault=None):
    real_client = httpx.AsyncClient
    asgi = httpx.ASGITransport(app=app)

    class OfflineTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            response = await asgi.handle_async_request(request)
            if http_fault:
                await response.aread()
                response = http_fault(request, response)
            return response

    transport = OfflineTransport()
    monkeypatch.setattr(adapter, "API_BASE_URL", "http://api.test")
    monkeypatch.setattr(adapter.httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs))

    class AdapterSession:
        async def list_tools(self):
            return SimpleNamespace(tools=await adapter.mcp.list_tools())

        async def call_tool(self, name, arguments, read_timeout_seconds=None):
            try:
                result = await adapter.mcp.call_tool(name, arguments)
            except ToolError as exc:
                result = SimpleNamespace(is_error=True, structured_content=None, content=[SimpleNamespace(text=str(exc))])
            if fault:
                result = fault(name, arguments, result)
            return result

    async with real_client(transport=transport, base_url="http://api.test") as api:
        yield verifier.OpenAIVerification(api, AdapterSession())


async def test_actual_workflow_verifier_with_mocked_provider(db, monkeypatch, offline_provider):
    async with offline_api(monkeypatch) as verification:
        await verification.run()
        report = verification.report("passed", 1)
    assert len(offline_provider) == 2
    assert sorted(len(records) for records in offline_provider) == [3, 4]
    assert report["provider"] == "openai"
    assert report["expected_model"] == "gpt-6.1-sol"
    assert report["stage"] == "complete"
    assert report["checks_passed"] == 6
    assert report["counts"]["synthetic_sources"] == report["counts"]["synthetic_evidence"] == 4
    assert report["counts"]["synthetic_requirements"] == 2
    assert report["counts"]["charging_versions"] == 3
    assert report["counts"]["uncached_analyses"] == report["counts"]["cached_replays"] == 2
    assert report["requests"]["http"] > 10 and report["requests"]["mcp"] > 30
    assert report["vehicle"].startswith("LIVE-AI-")
    assert "Public charging often fails" not in json.dumps(report)
    assert "test-only-key" not in json.dumps(report)


@pytest.mark.parametrize(("invalid", "message"), [
    ("wrong_model", "different model"),
    ("reference_provider", "requested OpenAI provider"),
    ("wrong_analysis_scope", "Analysis crossed"),
    ("wrong_generation_run", "different analysis run"),
    ("wrong_finding_run", "findings belong"),
    ("incomplete_analysis", "every scoped evidence"),
    ("duplicate_coverage", "duplicated evidence"),
    ("missing_strength", "positive customer evidence"),
    ("broken_trace", "source.*match|Finding-to-evidence"),
    ("wrong_requirement_content", "Requirement trace differs"),
    ("wrong_analysis_audit", "audit provider or evidence provenance"),
    ("missing_analysis_audit", "completion audit event"),
    ("implicit_approval", "implicitly approved"),
    ("stale_success", "unexpectedly succeeded"),
])
async def test_verifier_rejects_broken_provider_and_workflow_invariants(db, monkeypatch, offline_provider, invalid, message):
    def fault(name, arguments, result):
        if invalid == "stale_success" and result.is_error:
            return SimpleNamespace(is_error=False, structured_content={"success": True}, content=[])
        if result.is_error:
            return result
        payload = deepcopy(decode_tool_result(result))
        if name == "run_pipeline":
            if invalid == "wrong_model":
                payload["analysis"]["model"] = "different-model"
            elif invalid == "reference_provider":
                payload["analysis"]["provider"] = "deterministic"
            elif invalid == "wrong_analysis_scope":
                payload["analysis"]["market"] = "CN"
            elif invalid == "wrong_generation_run":
                payload["generation"]["run_id"] = "different-run"
            elif invalid == "wrong_finding_run":
                payload["analysis"]["findings"][0]["run_id"] = "different-run"
            elif invalid == "incomplete_analysis":
                payload["analysis"]["result"]["analyzed_evidence_ids"].pop()
            elif invalid == "duplicate_coverage":
                payload["analysis"]["result"]["analyzed_evidence_ids"].append(payload["analysis"]["evidence_ids"][0])
            elif invalid == "wrong_requirement_content":
                payload["generation"]["requirements"][0]["current_version"]["statement"] = "Unpersisted requirement wording"
            elif invalid == "missing_strength":
                for findings in (payload["analysis"]["findings"], payload["analysis"]["result"]["findings"]):
                    for finding in findings:
                        if finding["kind"] == "strength":
                            finding["kind"] = "need"
        if name == "list_audit":
            if invalid == "wrong_analysis_audit":
                for event in payload["items"]:
                    if event["action"] == "analysis.completed":
                        event["metadata"]["source_ids"] = []
            elif invalid == "missing_analysis_audit":
                for event in payload["items"]:
                    if event["action"] == "analysis.completed":
                        event["action"] = "other.action"
        if name == "trace_requirement" and invalid == "broken_trace":
            payload["sources"] = []
        if name == "edit_requirement" and invalid == "implicit_approval":
            payload["approved_version_id"] = payload["current_version_id"]
        return SimpleNamespace(is_error=False, structured_content=payload if isinstance(payload, dict) else {"result": payload}, content=[])

    async with offline_api(monkeypatch, fault) as verification:
        with pytest.raises(VerificationFailure, match=message):
            await verification.run()
    assert len(offline_provider) == 1


@pytest.mark.parametrize(("invalid", "message"), [
    ("original_bytes", "original checksum"),
    ("evidence_location", "Evidence content, source location"),
    ("source_reference", "Source reference or kind"),
])
async def test_verifier_checks_original_bytes_and_exact_imported_record(db, monkeypatch, offline_provider, invalid, message):
    def http_fault(request, response):
        if invalid == "original_bytes" and request.url.path.endswith("/original"):
            return httpx.Response(200, content=b"tampered synthetic original")
        if invalid == "evidence_location" and request.url.path == "/evidence":
            payload = response.json()
            payload["items"][0]["location"] = {"sheet": "Wrong", "row": 999}
            return httpx.Response(200, json=payload)
        return response

    def fault(name, arguments, result):
        if invalid == "source_reference" and name == "get_source":
            payload = deepcopy(decode_tool_result(result))
            payload["reference"] = "different-source"
            return SimpleNamespace(is_error=False, structured_content=payload, content=[])
        return result

    async with offline_api(monkeypatch, fault, http_fault) as verification:
        with pytest.raises(VerificationFailure, match=message):
            await verification.run()
    assert not offline_provider


@pytest.mark.parametrize(("invalid", "message"), [
    ("cached_update", "cache state"),
    ("untargeted_update", "unrelated requirement themes"),
    ("changed_pm_title", "edited PM fields"),
    ("changed_comfort", "Unrelated comfort requirement"),
    ("wrong_baseline", "explain the evidence change"),
    ("missing_review", "Review routing"),
    ("extra_approval_audit", "extra approval audit events"),
])
async def test_verifier_rejects_update_and_acceptance_regressions(db, monkeypatch, offline_provider, invalid, message):
    changed_audit = False

    def http_fault(request, response):
        if invalid == "changed_pm_title" and request.url.path.endswith("/trace"):
            payload = response.json()
            if payload["version"]["version"] == 3:
                payload["version"]["title"] = "Lost PM wording"
            return httpx.Response(200, json=payload)
        return response

    def fault(name, arguments, result):
        nonlocal changed_audit
        if result.is_error:
            return result
        payload = deepcopy(decode_tool_result(result))
        if name == "assess_updates" and not payload["analysis"]["cached"]:
            charging = next(item for item in payload["generation"]["requirements"] if item["topic"] == "charging")
            comfort = next(item for item in payload["generation"]["requirements"] if item["topic"] == "comfort")
            if invalid == "cached_update":
                payload["analysis"]["cached"] = True
            elif invalid == "untargeted_update":
                payload["generation"]["updated"].append(comfort["id"])
            elif invalid == "changed_pm_title":
                charging["current_version"]["title"] = "Lost PM wording"
            elif invalid == "changed_comfort":
                comfort["needs_review"] = True
            elif invalid == "wrong_baseline":
                payload["reviews"][0]["changes"]["against_approved"]["baseline_version_id"] = "wrong-version"
            elif invalid == "missing_review":
                payload["reviews"] = []
        if name == "trace_requirement" and invalid == "changed_pm_title" and payload["version"]["version"] == 3:
            payload["version"]["title"] = "Lost PM wording"
        if name == "list_audit" and invalid == "extra_approval_audit":
            for event in payload["items"]:
                if event["action"] == "requirement.version_created" and not changed_audit:
                    event["action"] = "requirement.approve"
                    changed_audit = True
        return SimpleNamespace(is_error=False, structured_content=payload if isinstance(payload, dict) else {"result": payload}, content=[])

    async with offline_api(monkeypatch, fault, http_fault) as verification:
        with pytest.raises(VerificationFailure, match=message):
            await verification.run()
    assert len(offline_provider) == 2


async def test_cli_errors_are_json_metadata_without_remote_details(monkeypatch, capsys):
    @asynccontextmanager
    async def broken(*args):
        raise ConnectionError("Authorization: Bearer test-secret; confidential customer quote")
        yield

    monkeypatch.setattr(verifier, "connect_live", broken)
    code = await verifier.main_async(SimpleNamespace(api_url="http://api.test", mcp_url="http://mcp.test",
                                                    expected_model="gpt-6.1-sol"))
    output = capsys.readouterr().out
    report = json.loads(output)
    assert code == 1 and report["status"] == "failed"
    assert report["error_type"] == "ConnectionError" and report["stage"] == "connect"
    assert "test-secret" not in output and "confidential" not in output


async def test_cli_success_prints_metadata_only(db, monkeypatch, offline_provider, capsys):
    @asynccontextmanager
    async def connection(*args):
        async with offline_api(monkeypatch) as verification:
            yield verification

    monkeypatch.setattr(verifier, "connect_live", connection)
    code = await verifier.main_async(SimpleNamespace(api_url="http://api.test", mcp_url="http://mcp.test",
                                                    expected_model="gpt-6.1-sol"))
    output = capsys.readouterr().out
    assert code == 0 and json.loads(output)["status"] == "passed"
    assert "test-only-key" not in output and "Charging session initiation" not in output


@pytest.mark.parametrize("failure", ["missing_credentials", "http_error", "incomplete", "refusal", "malformed_json"])
async def test_cli_provider_failure_never_falls_back_or_leaks_remote_bodies(db, monkeypatch, offline_provider, capsys, failure):
    attempts = []
    reference_calls = []
    real_reference = engine._reference_analysis

    def reference(*args):
        reference_calls.append(args)
        return real_reference(*args)

    def failed_wire(request, timeout):
        attempts.append(request.full_url)
        if failure == "http_error":
            raise HTTPError(request.full_url, 401, "remote-secret", {}, BytesIO(b"confidential customer quote"))
        if failure == "incomplete":
            wire = {"status": "incomplete", "output": []}
        elif failure == "refusal":
            wire = {"status": "completed", "output": [{"type": "message", "role": "assistant", "status": "completed",
                    "content": [{"type": "refusal", "refusal": "confidential customer quote"}]}]}
        else:
            return BytesIO(b"remote-secret confidential customer quote")
        return BytesIO(json.dumps(wire).encode())

    monkeypatch.setattr(engine, "urlopen", failed_wire)
    monkeypatch.setattr(engine, "_reference_analysis", reference)
    if failure == "missing_credentials":
        monkeypatch.delenv("OPENAI_API_KEY")

    @asynccontextmanager
    async def connection(*args):
        async with offline_api(monkeypatch) as verification:
            try:
                yield verification
            finally:
                workspace = await verification.http("GET", "/workspace", params=verification.scope)
                assert workspace["requirements"]["total"] == 0 and not workspace["reviews"]

    monkeypatch.setattr(verifier, "connect_live", connection)
    code = await verifier.main_async(SimpleNamespace(api_url="http://api.test", mcp_url="http://mcp.test",
                                                    expected_model="gpt-6.1-sol"))
    output = capsys.readouterr().out
    report = json.loads(output)
    assert code == 1 and report["status"] == "failed" and report["stage"] == "initial-openai-analysis"
    assert report["provider"] == "openai" and report["checks_passed"] == 1
    assert len(attempts) == (0 if failure == "missing_credentials" else 1)
    assert not offline_provider
    assert not reference_calls
    assert "remote-secret" not in output and "confidential" not in output and "test-only-key" not in output
