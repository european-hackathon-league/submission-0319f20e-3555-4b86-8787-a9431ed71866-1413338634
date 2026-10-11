"""Regression checks for the live verifier, including the full in-process workflow.

Only this test fixture substitutes transports. The CLI uses the MCP SDK's live
Streamable HTTP client and makes all database mutations through the public API.
"""

import json
from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from mcp_server import main as adapter
from scripts import verify_backend as verifier
from server.main import app


@pytest.mark.parametrize(("payload", "expected"), [({"items": [], "total": 0}, {"items": [], "total": 0}),
                                                    ({"result": [{"id": "source"}]}, [{"id": "source"}]),
                                                    ({"result": []}, [])])
def test_mcp_structured_objects_and_wrapped_lists(payload, expected):
    result = SimpleNamespace(content=[], structured_content=payload, is_error=False)
    assert verifier.decode_tool_result(result) == expected


def test_mcp_errors_cannot_look_like_success():
    result = SimpleNamespace(content=[SimpleNamespace(text="API returned HTTP 409: reload before deciding")],
                             structured_content=None, is_error=True)
    with pytest.raises(verifier.VerificationFailure, match="MCP operation failed"):
        verifier.decode_tool_result(result)
    assert "HTTP 409" in verifier.decode_tool_result(result, "HTTP 409")
    with pytest.raises(verifier.VerificationFailure, match="did not contain"):
        verifier.decode_tool_result(result, "HTTP 422")
    result.is_error = False
    with pytest.raises(verifier.VerificationFailure, match="unexpectedly succeeded"):
        verifier.decode_tool_result(result, "HTTP 409")


def test_mcp_text_fallback_rejects_malformed_and_scalar_results():
    result = SimpleNamespace(content=[SimpleNamespace(text='{"ok":true}')], structured_content=None, is_error=False)
    assert verifier.decode_tool_result(result) == {"ok": True}
    result.content[0].text = "not JSON"
    with pytest.raises(verifier.VerificationFailure, match="no structured JSON"):
        verifier.decode_tool_result(result)
    result.content[0].text = "null"
    with pytest.raises(verifier.VerificationFailure, match="scalar"):
        verifier.decode_tool_result(result)


@pytest.mark.parametrize("payload", [{"result": False}, {"result": ""}, {"result": None}, []])
def test_mcp_structured_scalar_and_malformed_results_fail(payload):
    result = SimpleNamespace(content=[], structured_content=payload, is_error=False)
    with pytest.raises(verifier.VerificationFailure, match="scalar|not an object"):
        verifier.decode_tool_result(result)


async def test_complete_verifier_exercises_api_and_mcp_adapter(db, monkeypatch):
    real_client = httpx.AsyncClient
    transport = httpx.ASGITransport(app=app)
    monkeypatch.setattr(adapter, "API_BASE_URL", "http://api.test")
    monkeypatch.setattr(adapter.httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs))

    class AdapterSession:
        async def list_tools(self):
            return SimpleNamespace(tools=await adapter.mcp.list_tools())

        async def call_tool(self, name, arguments, read_timeout_seconds=None):
            try:
                return await adapter.mcp.call_tool(name, arguments)
            except ToolError as exc:
                return SimpleNamespace(is_error=True, structured_content=None, content=[SimpleNamespace(text=str(exc))])

    async with real_client(transport=transport, base_url="http://api.test") as api:
        verification = verifier.Verification(api, AdapterSession())
        await verification.run_synthetic()
        # Exercise --real-data against local fixture files and an existing G60
        # approval. The verifier must import and analyze without approving it.
        inputs = db.parent / "inputs"
        inputs.mkdir()
        (inputs / "feedback.xlsx").write_bytes(verifier.make_workbook("G60"))
        (inputs / "new-feedback.csv").write_text(
            "Feedback,Topic,Sentiment,Vehicle,Market\n"
            "Public charging is confusing,charging,problem,G60,US\n")
        monkeypatch.setenv("DATA_DIR", str(inputs))
        monkeypatch.setattr(verifier, "REAL_FILES", (("feedback.xlsx", "feedback"), ("new-feedback.csv", "feedback")))
        await verification.http("POST", "/imports/local", json={"path": "feedback.xlsx", "kind": "feedback"})
        real_initial = await verification.http("POST", "/pipeline/run", json={"vehicle": "G60", "market": "US"})
        real_requirement = verifier.requirement_by_topic(real_initial, "comfort")
        await verification.http("POST", f"/requirements/{real_requirement['id']}/decisions",
                                json=verifier.decision_payload(real_requirement))
        await verification.run_real_data()
        report = verification.report("passed", 1)
    assert report["status"] == "passed"
    assert report["checks_passed"] == 12
    assert report["counts"]["synthetic_evidence"] == 4
    assert report["counts"]["charging_versions"] == 3
    assert report["counts"]["real_preserved_approvals"] == 1
    assert report["counts"]["real_evidence"] == report["counts"]["real_customer_evidence"] == 2
    assert report["counts"]["real_requirement_trace_evidence"] == 2
    assert report["requests"]["http"] >= 20
    assert report["requests"]["mcp"] > 30
    assert report["vehicle"].startswith("E2E-")
    assert report["latency_ms"]["http"]["max"] > 0
    json.dumps(report)  # The CLI report must remain machine readable.


async def test_main_returns_nonzero_and_json_when_connection_fails(monkeypatch, capsys):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def broken(*args):
        raise ConnectionError("test endpoint unavailable")
        yield

    monkeypatch.setattr(verifier, "connect_live", broken)
    result = await verifier.main_async(SimpleNamespace(api_url="http://api.test", mcp_url="http://mcp.test", real_data=False))
    output = json.loads(capsys.readouterr().out)
    assert result == 1
    assert output["status"] == "failed"
    assert output["checks_passed"] == 0
    assert "test endpoint unavailable" in output["error"]


@pytest.mark.parametrize("invalid", ["duplicate", "empty", "wrong_offset", "changing_total"])
async def test_http_pagination_rejects_incomplete_or_inconsistent_results(invalid, monkeypatch):
    verification = verifier.Verification(None, None)
    pages = [
        {"items": [{"id": "a"}], "total": 2, "offset": 0},
        {"items": [{"id": "b"}], "total": 2, "offset": 1},
    ]
    if invalid == "duplicate":
        pages[1]["items"][0]["id"] = "a"
    elif invalid == "empty":
        pages[1]["items"] = []
    elif invalid == "wrong_offset":
        pages[1]["offset"] = 0
    else:
        pages[1]["total"] = 3

    async def http(*args, **kwargs):
        return pages.pop(0)

    monkeypatch.setattr(verification, "http", http)
    with pytest.raises(verifier.VerificationFailure, match="pagination"):
        await verification.all_http_items("/requirements", page_size=1, vehicle="G60", market="US")


async def test_http_pagination_visits_all_pages_and_accepts_empty_scope(monkeypatch):
    verification = verifier.Verification(None, None)
    offsets = []

    async def http(method, path, *, params):
        offsets.append(params["offset"])
        assert params["vehicle"] == "G60" and params["market"] == "US"
        if path == "/empty":
            return {"items": [], "total": 0, "offset": 0}
        return {"items": [{"id": str(params["offset"])}], "total": 3, "offset": params["offset"]}

    monkeypatch.setattr(verification, "http", http)
    assert await verification.all_http_items("/requirements", page_size=1, vehicle="G60", market="US") == [
        {"id": "0"}, {"id": "1"}, {"id": "2"}]
    assert offsets == [0, 1, 2]
    assert await verification.all_http_items("/empty", vehicle="G60", market="US") == []


@pytest.mark.parametrize("invalid", ["skipped_cursor", "repeated_sequence", "wrong_entity", "empty_cursor"])
async def test_audit_pagination_rejects_bad_cursors_and_scope(invalid, monkeypatch):
    verification = verifier.Verification(None, None)
    pages = [{"items": [{"sequence": 1, "entity_id": "req"}], "next_after": 1},
             {"items": [], "next_after": 1}]
    if invalid == "skipped_cursor":
        pages[0]["next_after"] = 100
    elif invalid == "repeated_sequence":
        pages[0]["items"].append(pages[0]["items"][0])
    elif invalid == "wrong_entity":
        pages[0]["items"][0]["entity_id"] = "other"
    else:
        pages[1]["next_after"] = 2

    async def mcp(*args, **kwargs):
        return pages.pop(0)

    monkeypatch.setattr(verification, "mcp", mcp)
    with pytest.raises(verifier.VerificationFailure, match="Audit|audit"):
        await verification.audit_events("req")


@pytest.mark.parametrize("invalid", ["source_scope", "version_requirement", "decision_version", "score_source", "score_count"])
async def test_trace_rejects_disconnected_scope_priority_or_decisions(invalid, monkeypatch):
    scope = {"vehicle": "G60", "market": "US"}
    requirement = {"id": "req", "current_version_id": "version", **scope}
    trace = {
        "requirement": {"id": "req"},
        "version": {"id": "version", "requirement_id": "req", "finding_ids": ["finding"],
                    "score": {"version_id": "version", "explanation": {
                        "source_ids": ["source"], "evidence_count": 1, "source_count": 1}}},
        "sources": [{"id": "source", **scope}],
        "findings": [{"id": "finding", "evidence_ids": ["evidence"], "conflicting_evidence_ids": [], **scope}],
        "evidence": {"items": [{"id": "evidence", "source_id": "source", "location": {"row": 2}, **scope}],
                     "total": 1, "offset": 0},
        "decisions": [{"version_id": "version", "requirement_id": "req", "actor": "PM", "rationale": "Reviewed"}],
    }
    verification = verifier.Verification(None, None)

    async def mcp(*args, **kwargs):
        return trace

    monkeypatch.setattr(verification, "mcp", mcp)
    assert await verification.trace(requirement) == trace
    trace = deepcopy(trace)
    if invalid == "source_scope":
        trace["sources"][0]["market"] = "CN"
    elif invalid == "version_requirement":
        trace["version"]["requirement_id"] = "other"
    elif invalid == "decision_version":
        trace["decisions"][0]["version_id"] = "other"
    elif invalid == "score_source":
        trace["version"]["score"]["explanation"]["source_ids"] = ["other"]
    else:
        trace["version"]["score"]["explanation"]["evidence_count"] = 0
    with pytest.raises(verifier.VerificationFailure, match="Trace"):
        await verification.trace(requirement)


@asynccontextmanager
async def in_process(monkeypatch, **options):
    real_client = httpx.AsyncClient
    transport = httpx.ASGITransport(app=app)
    monkeypatch.setattr(adapter, "API_BASE_URL", "http://api.test")
    monkeypatch.setattr(adapter.httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs))

    class AdapterSession:
        async def list_tools(self):
            return SimpleNamespace(tools=await adapter.mcp.list_tools())

        async def call_tool(self, name, arguments, read_timeout_seconds=None):
            try:
                return await adapter.mcp.call_tool(name, arguments)
            except ToolError as exc:
                return SimpleNamespace(is_error=True, structured_content=None, content=[SimpleNamespace(text=str(exc))])

    async with real_client(transport=transport, base_url="http://api.test") as api:
        yield verifier.Verification(api, AdapterSession(), **options)


@pytest.fixture
def no_exa(tmp_path, monkeypatch):
    from server import exa_research

    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.setenv("EXA_CACHE_DIR", str(tmp_path / "exa-cache"))
    exa_research.exa_client.cache_clear()
    yield
    exa_research.exa_client.cache_clear()


async def test_platform_journey_runs_every_step_in_process(db, monkeypatch, no_exa):
    async with in_process(monkeypatch) as verification:
        await verification.run_platform()
        report = verification.report("passed", 1)
    assert report["status"] == "passed" and report["provider"] == "deterministic"
    assert [check.split(":")[0] for check in report["checks"]] == [f"Platform {step}" for step in range(1, 9)]
    counts = report["counts"]
    assert counts["platform_weights"] == 6 and counts["platform_requirements"] >= 7
    assert counts["platform_conflict_markets"] == {"exhaust": ["CN", "US"], "rear": ["CN", "EU"]}
    assert counts["platform_task_status"] == "failed" and counts["exa_configured"] is False
    assert counts["audit_chain"]["events"] > 100 and counts["audit_chain"]["head_sequence"]
    assert counts["platform_reviews_opened"] >= 1
    assert report["platform_vehicle"].startswith("E2E-") and report["platform_label"] == "simulated"
    assert "llm_usage" not in counts
    json.dumps(report)


async def test_platform_real_data_imports_bmw_layout_without_g60_decisions(db, monkeypatch, tmp_path):
    from tests.test_market_data import feedback_rows, sales_sheets, workbook_bytes

    folder = tmp_path / "data" / "BMW-Data"
    folder.mkdir(parents=True)
    (folder / "G60_feedback_simulated.xlsx").write_bytes(workbook_bytes({"Feedback_Explorer": feedback_rows()}))
    (folder / "sales_volumes_simulated.xlsx").write_bytes(workbook_bytes(sales_sheets()))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    async with in_process(monkeypatch) as verification:
        await verification.run_platform_real_data()
        decisions = await verification.http("GET", "/audit", params={"after": 0, "limit": 1000})
    counts = verification.counts
    assert counts["real_platform_import"]["files"] == 2 and counts["real_g60_simulated_requests"] == 6
    assert counts["real_g60_weight_periods"] == ["2024", "2025", "2030"] and counts["real_g60_us_preserve"] >= 1
    assert "single_source_dominance" in counts["real_g60_coverage_warnings"]["US"]
    assert not {event["action"] for event in decisions["items"]} & {
        "requirement.approve", "priorities.rubric_switched", "market_conflict.selectable_mode"}


def test_audit_chain_check_matches_the_database_verifier(client, db):
    import sqlite3

    from database.integrity import verify_audit_chain as database_chain
    from database.store import pre_chain_digest

    assert verifier.AUDIT_HASH_FIELDS == __import__("database.store").store.AUDIT_HASH_FIELDS
    assert verifier.pre_chain_digest([]) == pre_chain_digest([])
    for index in range(3):
        client.post("/imports/records", json=verifier.feedback_payload(
            "G60", f"chain-{index}", f"Simulated: quiet cabin {index}", "quietness", "strength"))
    events = client.get("/audit", params={"limit": 1000}).json()["items"]
    assert len(events) >= 3
    with sqlite3.connect(db) as connection:
        expected = database_chain(connection)
    assert verifier.verify_audit_chain(events) == {"events": expected["events"], "head_sequence": expected["head"]["sequence"]}
    tampered = deepcopy(events)
    tampered[-1]["after_state"] = {"changed": True}
    with pytest.raises(verifier.VerificationFailure, match="content changed"):
        verifier.verify_audit_chain(tampered)
    with pytest.raises(verifier.VerificationFailure, match="link broken"):
        verifier.verify_audit_chain(events[:-2] + events[-1:])


@pytest.mark.parametrize(("change", "message"), [
    ({"status": "failed"}, "not a succeeded OpenAI run"), ({"provider": "deterministic"}, "not a succeeded OpenAI run"),
    ({"metrics": {}}, "no OpenAI calls"), ({"llm": {"total_tokens": 0, "cache_hits": 0}}, "no OpenAI token usage"),
    ({"llm": {"requests": [{"model": "m", "prompt_version": "", "input_hash": "h"}]}}, "lack model, prompt version"),
    ({"expected": "other-model"}, "model other than other-model")])
def test_openai_runs_must_record_provider_model_prompt_and_usage(change, message):
    llm = {"calls": 1, "cache_hits": 0, "input_tokens": 5, "output_tokens": 3, "total_tokens": 8,
           "requests": [{"kind": "structured", "model": "m", "prompt_version": "p-v1", "input_hash": "h"}]}
    run = {"id": "run", "status": "succeeded", "provider": "openai", "model": "m", "method_version": "openai:m:p-v1",
           "metrics": {"llm": llm}}
    assert verifier.llm_usage(run, "step", "m")["total_tokens"] == 8
    expected = change.pop("expected", "m")
    llm.update(change.pop("llm", {}))
    run.update(change)
    with pytest.raises(verifier.VerificationFailure, match=message):
        verifier.llm_usage(run, "step", expected)
