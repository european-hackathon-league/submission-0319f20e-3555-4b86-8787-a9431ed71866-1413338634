"""Verify the live BMW PM pipeline through HTTP and a real Streamable HTTP MCP client.

Run from the repository: uv run python scripts/verify_backend.py --api-url
http://127.0.0.1:18000 --mcp-url http://127.0.0.1:18001/mcp

Every run uses a fresh E2E vehicle. It leaves that auditable fixture in place;
there is no database access, cleanup, server lifecycle management, or approval of
real G60 requirements. --real-data additionally imports the mounted BMW files
and checks G60/US analysis and trace coverage, preserving prior approvals.

--platform additionally runs the platform journey (PLATFORM_BUILD_PLAN.md §11 step 3) on a second
fresh, explicitly simulated E2E vehicle in US, CN and EU: market data, pipeline, request triage,
sentiment, market conflicts and their human gate, rubric v2, and a recurring signals task with
runs, board, audit and hash-chain checks. --provider openai runs its AI steps on the server's
configured OpenAI model and requires recorded model, prompt version and token usage per run; a
missing key fails, it never falls back. The signals watchlist and task use the public G60/US
template (the only scopes Exa monitoring accepts); the verifier pauses and cancels them at the end.
With --real-data the platform journey also imports every BMW file through /market-data/import-bmw and
derives G60 weights, preserve list and coverage; human decisions still happen only on the simulated vehicle.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import logging
import math
import sys
import time
import uuid
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from openpyxl import Workbook

ACTOR = "E2E verification PM"
REAL_FILES = (
    ("BMW-Data/G60_feedback_hackathon.xlsx", "feedback"),
    ("BMW-Data/F70_G60_G68_G70_customer_studies.xlsx", "study"),
    ("BMW-Data/sales_volumes.xlsx", "sales"),
    ("BMW-Data/G60_OptionList.PDF", "document"),
)
FACTOR_NAMES = {"customer_impact", "market_relevance", "strategic_fit", "differentiation", "feasibility"}

# Platform journey ---------------------------------------------------------------------------------
PLATFORM_MARKETS = ("US", "CN", "EU")
PUBLIC_SCOPE = {"vehicle": "G60", "market": "US"}   # Exa monitoring accepts only public model/market templates
AI_ACTOR = "ai:agent:e2e-verifier"
REQUEST_FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "simulated_requests.json"
DERIVED_FACTORS = ("market_demand", "sentiment_momentum", "request_pressure")
TRIAGE_FACTORS = {"market_weight", "evidence_support", "evidence_conflict", "recurrence", "alignment", "effort"}
PLATFORM_CAPABILITIES = {"market_data.derive_weights", "market_data.derive_preserve", "market_data.coverage",
                         "requests.intake", "requests.classify", "requests.cluster", "requests.link_evidence",
                         "requests.triage", "signals.score_sentiment", "markets.extract_directions",
                         "markets.detect_conflicts", "priorities.derive_inputs", "priorities.sensitivity",
                         "priorities.explain"}
PLATFORM_TOOLS = {"list_sales_weights", "list_coverage_reports", "list_preserve_attributes", "get_request_aggregates",
                  "list_request_clusters", "get_sentiment_timeseries", "list_market_conflicts", "get_market_conflict",
                  "run_priority_sensitivity", "get_priority_ranking", "get_task_board", "get_task", "get_run"}
# Human gates are API-only; MCP may prepare proposals but never decide them.
GATE_TOOLS = {"resolve_market_conflict", "decide_request", "switch_priority_rubric", "create_signal_watchlist",
              "update_signal_watchlist", "pause_agent", "resume_agent"}
EXHAUST_TENSION, REAR_TENSION = {"driving-experience", "quietness"}, {"comfort", "access-storage"}
# Explicitly simulated customer feedback, never BMW data: (text, topic, sentiment, weeks before today).
PLATFORM_FEEDBACK = {
    "US": (("Simulated: customers want a louder exhaust; the engine sound is too subdued for a sporty sedan.",
            "driving-experience", "problem", 6),
           ("Simulated: dealers hear that buyers ask for a sportier exhaust note.", "driving-experience", "problem", 2),
           ("Simulated: I love the comfortable seats on long journeys.", "comfort", "strength", 5),
           ("Simulated: the comfortable seats are my favourite part of the car.", "comfort", "strength", 4),
           ("Simulated: I love how comfortable the seats feel after hours of driving.", "comfort", "strength", 3),
           ("Simulated: excellent seat comfort for the whole family.", "comfort", "strength", 2),
           ("Simulated: the comfortable seats make every commute relaxing.", "comfort", "strength", 1),
           ("Simulated: public charging is confusing and unreliable.", "charging", "problem", 1)),
    "CN": (("Simulated: customers want more rear legroom; the rear seat space is too tight for chauffeur-driven "
            "passengers.", "comfort", "problem", 5),
           ("Simulated: families compare rear knee room with long-wheelbase competitors.", "comfort", "problem", 3),
           ("Simulated: customers want a quieter cabin at highway speeds.", "quietness", "problem", 4),
           ("Simulated: road noise is too high on rough surfaces.", "quietness", "problem", 2)),
    "EU": (("Simulated: customers want a smaller car that fits city parking garages.", "access-storage", "problem", 5),
           ("Simulated: the car is too long to park in older city garages.", "access-storage", "problem", 3),
           ("Simulated: noise insulation needs improvement.", "quietness", "problem", 4)),
}
SALES_ROWS = (("Europe", "EU", 380, 390), ("China", "CN", 250, 255), ("USA", "US", 260, 265))
AUDIT_HASH_FIELDS = ("id", "entity_type", "entity_id", "action", "actor", "rationale", "before_state",
                     "after_state", "metadata", "created_at", "prev_hash")   # database.store.AUDIT_HASH_FIELDS


class VerificationFailure(RuntimeError):
    """An observable backend invariant did not hold."""


def require(condition: Any, message: str) -> None:
    # Unlike assert, verification must still run under python -O.
    if not condition:
        raise VerificationFailure(message)


def decode_tool_result(result: Any, expected_error: str | None = None) -> dict | list | str:
    text = "\n".join(item.text for item in result.content if hasattr(item, "text"))
    if expected_error is not None:
        require(result.is_error, f"MCP operation unexpectedly succeeded; expected {expected_error}")
        require(expected_error in text, f"MCP error did not contain {expected_error}: {text[:1000]}")
        return text
    require(not result.is_error, f"MCP operation failed: {text[:2000]}")
    structured = result.structured_content
    if structured is not None:
        # MCP wraps list-valued tool returns in an object for structuredContent.
        require(isinstance(structured, dict), "MCP structured content is not an object")
        payload = structured["result"] if set(structured) == {"result"} else structured
        require(isinstance(payload, (dict, list)), "MCP returned a scalar instead of an object/list")
        return payload
    try:
        payload = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise VerificationFailure(f"MCP returned no structured JSON: {text[:1000]}") from exc
    require(isinstance(payload, (dict, list)), "MCP returned a scalar instead of an object/list")
    return payload


def make_workbook(vehicle: str) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Drivers"
    sheet.append(["Feedback", "Topic", "Sentiment", "Vehicle", "Market", "Date", "Source"])
    sheet.append(["I love the comfortable seats", "comfort", "strength", vehicle, "US", "2026-09-01", "seat-survey"])
    # This row proves the importer respects explicit market scope.
    sheet.append(["Public charging is slow", "charging", "problem", vehicle, "CN", "2026-09-01", "other-market"])
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def feedback_payload(vehicle: str, reference: str, content: str, topic: str, sentiment: str, market: str = "US") -> dict:
    return {"title": reference, "reference": reference, "vehicle": vehicle, "market": market, "kind": "feedback",
            "actor": ACTOR, "records": [{"content": content, "location": {"sheet": "Drivers", "row": 2},
                                         "observed_at": "2026-09-01",
                                         "metadata": {"topic": topic, "sentiment": sentiment, "provenance": reference}}]}


def requirement_by_topic(result: dict, topic: str) -> dict:
    matches = [item for item in result["generation"]["requirements"] if item["topic"] == topic]
    require(len(matches) == 1, f"Expected exactly one requirement for {topic}, received {len(matches)}")
    return matches[0]


def decision_payload(requirement: dict, action: str = "approve") -> dict:
    version = requirement["current_version"]
    return {"version_id": version["id"], "score_id": version["score"]["id"], "action": action,
            "actor": ACTOR, "rationale": f"Synthetic customer evidence reviewed: {action}"}


def verify_priority(requirement: dict) -> None:
    version = requirement["current_version"]
    score = version["score"]
    require(version["requirement_id"] == requirement["id"], "Version belongs to a different requirement")
    require(score["version_id"] == version["id"], "Priority belongs to a different requirement version")
    require(score["factors"] == version["factors"], "Priority does not reflect the current requirement")
    require(set(score["factors"]) == set(score["weights"]) == FACTOR_NAMES, "Priority rubric has missing/extra factors")
    require(all(math.isfinite(value) and 0 <= value <= 5 for value in score["factors"].values()),
            "Priority factors are outside the recorded 0–5 rubric")
    require(all(math.isfinite(value) and 0 <= value <= 1 for value in score["weights"].values())
            and math.isclose(sum(score["weights"].values()), 1, abs_tol=1e-6), "Priority weights are not normalized")
    require(math.isfinite(score["total"]) and 0 <= score["total"] <= 100, "Priority is outside 0–100")
    expected = round(sum(score["factors"][key] * weight * 20 for key, weight in score["weights"].items()), 4)
    require(score["total"] == expected, f"Priority formula mismatch: {score['total']} != {expected}")
    require(bool(score["explanation"]["source_ids"]), "Priority is missing evidence provenance")
    require(bool(version["acceptance_criteria"]), "Requirement lacks acceptance criteria")
    require(all(criterion["metric"] and criterion["target"] is not None and criterion["basis"] in {"source", "PM assumption"}
                for criterion in version["acceptance_criteria"]), "Requirement targets lack a metric, target or stated basis")


def make_sales_workbook() -> bytes:
    """One simulated sales file; uploaded unchanged per market so every scope shares its content hash."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Simulated sales"
    sheet.append(["market", "market_code", "volume_2024", "volume_2025"])
    for row in SALES_ROWS:
        sheet.append(list(row))
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def platform_feedback_payload(vehicle: str, market: str, today: date) -> dict:
    records = [{"content": text, "location": {"sheet": "Simulated feedback", "row": row},
                "observed_at": (today - timedelta(weeks=weeks)).isoformat(),
                "metadata": {"record_type": "customer_feedback", "feedback_id": f"{vehicle}-{market}-{row}",
                             "topic": topic, "sentiment": sentiment, "provenance": f"simulated-{market.lower()}-panel",
                             "simulated": True}}
               for row, (text, topic, sentiment, weeks) in enumerate(PLATFORM_FEEDBACK[market], 2)]
    return {"title": f"Simulated {market} customer feedback", "reference": f"{vehicle}:{market}:simulated-feedback",
            "vehicle": vehicle, "market": market, "kind": "feedback", "actor": ACTOR, "metadata": {"simulated": True},
            "records": records}


def simulated_requests(vehicle: str) -> list[dict]:
    """The labelled G60 request fixture, re-scoped to the simulated vehicle (the fixture endpoint loads G60 only)."""
    fixture = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    require(fixture["label"] == "simulated", "Request fixture is not labelled simulated")
    return [{**item, "vehicle": vehicle, "simulated": True, "external_ref": f"{vehicle}:{item['external_ref']}"}
            for item in fixture["requests"]]


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def audit_event_hash(row: dict) -> str:
    """database.store.audit_event_hash over the stored row (JSON columns as their canonical text)."""
    return hashlib.sha256(canonical({key: row[key] for key in AUDIT_HASH_FIELDS}).encode()).hexdigest()


def pre_chain_digest(rows: list[dict]) -> str:
    digest = hashlib.sha256(b"audit.pre-chain").hexdigest()
    for row in rows:
        fields = {key: row[key] for key in AUDIT_HASH_FIELDS if key != "prev_hash"}
        digest = hashlib.sha256((digest + canonical({**fields, "sequence": row["sequence"]})).encode()).hexdigest()
    return digest


def verify_audit_chain(events: list[dict]) -> dict:
    """database.integrity.verify_audit_chain over GET /audit items, so the check needs no database access."""
    previous, pre_chain = None, []
    for item in events:
        event = {**item, **{key: None if item[key] is None else canonical(item[key])
                            for key in ("before_state", "after_state", "metadata")}}
        if previous is None and event["event_hash"] is None:
            pre_chain.append(event)
            continue
        require(event["event_hash"], f"Audit event {event['sequence']} is not hashed")
        if previous is None:
            require(not pre_chain or event["action"] == "audit.chain.started",
                    "Pre-chain audit events are not sealed by a genesis event")
            expected = pre_chain_digest(pre_chain)
        else:
            expected = previous["event_hash"]
        require(event["prev_hash"] == expected, f"Audit hash chain link broken at sequence {event['sequence']}")
        require(audit_event_hash(event) == event["event_hash"], f"Audit event content changed at sequence {event['sequence']}")
        previous = event
    require(previous is not None or not pre_chain, "Pre-chain audit events are not sealed by a genesis event")
    return {"events": len(events), "head_sequence": previous["sequence"] if previous else None}


def llm_usage(run: dict, label: str, expected_model: str | None = None) -> dict:
    """Require a stored OpenAI run with provider, model, prompt versions and token usage in metrics.llm."""
    llm = (run.get("metrics") or {}).get("llm") or {}
    calls = llm.get("requests") or []
    require(run["status"] == "succeeded" and run["provider"] == "openai" and run["model"],
            f"{label} is not a succeeded OpenAI run")
    require(llm.get("calls", 0) >= 1 and calls, f"{label} recorded no OpenAI calls in metrics.llm")
    require(all(call.get("model") and call.get("prompt_version") and call.get("input_hash") for call in calls),
            f"{label} OpenAI calls lack model, prompt version or input hash")
    require(llm.get("total_tokens", 0) > 0 or llm.get("cache_hits") == llm["calls"],
            f"{label} recorded no OpenAI token usage")
    if expected_model:
        require(all(call["model"] == expected_model for call in calls if call.get("kind") != "embedding"),
                f"{label} used a model other than {expected_model}")
    return {"run_id": run["id"], "model": run["model"], "method_version": run["method_version"],
            "prompt_versions": sorted({call["prompt_version"] for call in calls}), "calls": llm["calls"],
            "cache_hits": llm.get("cache_hits", 0), **{key: llm.get(key, 0) for key in
                                                       ("input_tokens", "output_tokens", "total_tokens")}}


@dataclass
class Verification:
    api: httpx.AsyncClient
    session: Any
    vehicle: str = field(default_factory=lambda: "E2E-" + uuid.uuid4().hex[:16].upper())
    checks: list[str] = field(default_factory=list)
    timings: list[dict] = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    provider: str = "deterministic"
    llm_model: str | None = None
    platform_vehicle: str = field(default_factory=lambda: "E2E-" + uuid.uuid4().hex[:16].upper())
    llm_runs: dict = field(default_factory=dict)

    @property
    def scope(self) -> dict:
        return {"vehicle": self.vehicle, "market": "US"}

    def passed(self, label: str) -> None:
        self.checks.append(label)

    async def http(self, method: str, path: str, *, expected_status: int | None = None, raw: bool = False, **kwargs):
        started = time.perf_counter()
        response = await self.api.request(method, path, **kwargs)
        self.timings.append({"transport": "http", "operation": f"{method} {path}",
                             "ms": round((time.perf_counter() - started) * 1000, 2)})
        valid = response.status_code == expected_status if expected_status is not None else response.is_success
        require(valid, f"{method} {path} returned {response.status_code}: {response.text[:2000]}")
        return response.content if raw else response.json()

    async def mcp(self, name: str, *, expected_error: str | None = None, **arguments):
        started = time.perf_counter()
        result = await self.session.call_tool(name, arguments, read_timeout_seconds=180)
        self.timings.append({"transport": "mcp", "operation": name,
                             "ms": round((time.perf_counter() - started) * 1000, 2)})
        return decode_tool_result(result, expected_error)

    async def approve(self, requirement: dict) -> dict:
        result = await self.mcp("decide_requirement", requirement_id=requirement["id"], **decision_payload(requirement))
        approved = result["requirement"]
        require(approved["approved_version_id"] == requirement["current_version_id"], "Approval points to wrong version")
        require(approved["approved_score_id"] == requirement["current_version"]["score"]["id"], "Approval points to wrong score")
        require(approved["status"] == "approved" and not approved["needs_review"], "Approval did not resolve reviews")
        trace = await self.trace(approved)
        decisions = [decision for decision in trace["decisions"] if decision["id"] == result["decision_id"]]
        require(len(decisions) == 1 and decisions[0]["action"] == "approve"
                and decisions[0]["score_id"] == approved["approved_score_id"] and decisions[0]["actor"] == ACTOR,
                "Approval is not linked to its exact persisted PM decision and score")
        return approved

    async def all_http_items(self, path: str, *, page_size: int = 1000, **params) -> list[dict]:
        items, total = [], None
        while total is None or len(items) < total:
            page = await self.http("GET", path, params={**params, "limit": page_size, "offset": len(items)})
            if total is None:
                total = page["total"]
                require(isinstance(total, int) and total >= 0, f"{path} pagination total is invalid")
            require(page["total"] == total and page["offset"] == len(items), f"{path} pagination metadata changed")
            require(page["items"] or len(items) == total, f"{path} pagination ended before its reported total")
            items.extend(page["items"])
        require(len(items) == total and len({item["id"] for item in items}) == total,
                f"{path} pagination lost/duplicated records")
        return items

    async def audit_events(self, entity_id: str, page_size: int = 3) -> list[dict]:
        events, cursor = [], 0
        while True:
            page = await self.mcp("list_audit", entity_id=entity_id, after=cursor, limit=page_size)
            if not page["items"]:
                require(page["next_after"] == cursor, "Empty audit page changed the cursor")
                break
            sequences = [event["sequence"] for event in page["items"]]
            require(sequences == sorted(set(sequences)) and sequences[0] > cursor
                    and page["next_after"] == sequences[-1], "Audit pagination skipped/repeated events or has an invalid cursor")
            require(all(event["entity_id"] == entity_id for event in page["items"]), "Audit crossed entity boundaries")
            events.extend(page["items"])
            cursor = page["next_after"]
        return events

    async def trace(self, requirement: dict, version_id: str | None = None, page_size: int = 1) -> dict:
        version_id = version_id or requirement["current_version_id"]
        first = await self.mcp("trace_requirement", requirement_id=requirement["id"], version_id=version_id, limit=page_size)
        require(first["version"]["id"] == version_id, "Trace returned the wrong requirement version")
        require(first["requirement"]["id"] == first["version"]["requirement_id"] == requirement["id"],
                "Trace returned a different requirement")
        evidence = list(first["evidence"]["items"])
        total = first["evidence"]["total"]
        require(isinstance(total, int) and total > 0, "Trace has no evidence or an invalid evidence total")
        require(first["evidence"]["offset"] == 0, "Trace first page has the wrong offset")
        while len(evidence) < total:
            page = await self.http("GET", f"/requirements/{requirement['id']}/trace",
                                   params={"version_id": version_id, "offset": len(evidence), "limit": page_size})
            require(page["evidence"]["total"] == total, "Trace pagination total changed")
            require(page["evidence"]["offset"] == len(evidence) and page["version"] == first["version"],
                    "Trace pagination switched offset or version")
            require(bool(page["evidence"]["items"]), "Trace pagination ended before its reported total")
            evidence.extend(page["evidence"]["items"])
        require(len(evidence) == total and len({row["id"] for row in evidence}) == total, "Trace pagination lost/duplicated evidence")
        source_ids = {source["id"] for source in first["sources"]}
        require(source_ids == {row["source_id"] for row in evidence}, "Trace sources do not exactly match linked evidence")
        finding_evidence = {eid for finding in first["findings"]
                            for eid in finding["evidence_ids"] + finding["conflicting_evidence_ids"]}
        require({row["id"] for row in evidence} == finding_evidence, "Finding-to-evidence trace is incomplete")
        require(set(first["version"]["finding_ids"]) == {finding["id"] for finding in first["findings"]},
                "Requirement-to-finding trace is incomplete")
        require(all(row["source_id"] in source_ids and row["location"] for row in evidence), "Evidence lacks source/location")
        require(all((row["vehicle"], row["market"]) == (requirement["vehicle"], requirement["market"])
                    for row in evidence + first["sources"] + first["findings"]), "Trace crosses vehicle/market scope")
        score = first["version"]["score"]
        require(score["version_id"] == version_id and set(score["explanation"]["source_ids"]) == source_ids
                and score["explanation"]["evidence_count"] == total
                and score["explanation"]["source_count"] == len(source_ids), "Trace priority provenance is incomplete")
        require(all(decision["version_id"] == version_id and decision["requirement_id"] == requirement["id"]
                    and decision["actor"] and decision["rationale"] for decision in first["decisions"]),
                "Trace decision points to a different requirement/version or lacks PM attribution")
        return {**first, "evidence": {**first["evidence"], "items": evidence}}

    async def run_synthetic(self) -> None:
        require((await self.http("GET", "/health"))["status"] == "ok", "API health check failed")
        require((await self.mcp("health"))["status"] == "ok", "MCP upstream health check failed")
        tool_definitions = {tool.name: tool for tool in (await self.session.list_tools()).tools}
        discovered = set(tool_definitions)
        required_tools = {"health", "import_records", "get_source", "list_sources", "list_evidence", "get_evidence",
                          "run_pipeline", "edit_requirement", "score_requirement", "get_requirement", "decide_requirement",
                          "assess_updates", "trace_requirement", "get_requirement_versions", "list_audit", "get_workspace",
                          "list_requirements", "list_reviews"}
        require(required_tools <= discovered, f"MCP tools missing: {sorted(required_tools - discovered)}")
        require((await self.http("GET", "/workspace", params=self.scope))["evidence_count"] == 0,
                "Fresh synthetic scope already has evidence")
        self.passed("HTTP and MCP health, protocol initialization and tool discovery")

        feedback = feedback_payload(self.vehicle, f"{self.vehicle}:initial", "Public charging is confusing and unreliable",
                                    "charging", "problem")
        imported = await self.mcp("import_records", **feedback)
        repeated = await self.http("POST", "/imports/records", expected_status=201, json=feedback)
        require(not imported["deduplicated"] and repeated["deduplicated"], "Repeated evidence import was not deduplicated")
        require(imported["source_id"] == repeated["source_id"] and imported["record_count"] == 1, "Deduplication changed source identity")
        original = await self.http("GET", f"/sources/{imported['source_id']}/original", raw=True)
        require(hashlib.sha256(original).hexdigest() == imported["sha256"], "Preserved record original checksum differs")
        require(json.loads(original)["records"][0]["content"] == feedback["records"][0]["content"], "Original record text changed")
        source = await self.mcp("get_source", source_id=imported["source_id"])
        require(source["reference"] == feedback["reference"] and source["content_hash"] == imported["sha256"]
                and (source["vehicle"], source["market"]) == (self.vehicle, "US"), "Source provenance changed")
        self.passed("Record import, cross-transport deduplication and preserved original")

        workbook = make_workbook(self.vehicle)
        file_args = {"files": {"file": ("verification.xlsx", workbook,
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                     "data": {**self.scope, "kind": "feedback", "actor": ACTOR}}
        uploaded = await self.http("POST", "/imports/files", expected_status=201, **file_args)
        duplicated_file = await self.http("POST", "/imports/files", expected_status=201, **file_args)
        require(uploaded["record_count"] == 1, "Workbook import included a different market or dropped matching evidence")
        require(duplicated_file["deduplicated"] and duplicated_file["source_id"] == uploaded["source_id"], "File deduplication failed")
        require(await self.http("GET", f"/sources/{uploaded['source_id']}/original", raw=True) == workbook,
                "Downloaded workbook bytes differ from upload")
        self.passed("XLSX upload, scope filtering, deduplication and exact original download")

        first_page = await self.mcp("list_evidence", **self.scope, limit=1, offset=0)
        second_page = await self.http("GET", "/evidence", params={**self.scope, "limit": 1, "offset": 1})
        require(first_page["total"] == second_page["total"] == 2, "Evidence counts do not match imports")
        require(first_page["items"][0]["id"] != second_page["items"][0]["id"], "Evidence pagination repeated a row")
        evidence = {row["source_id"]: row for row in first_page["items"] + second_page["items"]}
        require(evidence[imported["source_id"]]["location"] == feedback["records"][0]["location"], "Record location lost")
        require(evidence[uploaded["source_id"]]["location"] == {"sheet": "Drivers", "row": 2, "header_row": 1},
                "Workbook row location lost")
        read = await self.mcp("get_evidence", evidence_id=evidence[imported["source_id"]]["id"])
        require(read["content"] == feedback["records"][0]["content"], "Evidence detail changed source text")
        search = await self.http("GET", "/evidence", params={**self.scope, "q": "comfortable seats"})
        require(search["total"] == 1 and search["items"][0]["source_id"] == uploaded["source_id"], "Evidence text search failed")
        self.passed("Evidence pagination, search and exact source locations")

        pipeline = await self.mcp("run_pipeline", **self.scope, provider="deterministic", actor=ACTOR)
        require(pipeline["analysis"]["provider"] == "deterministic" and not pipeline["analysis"]["cached"], "Initial analysis provenance is wrong")
        charging, comfort = (requirement_by_topic(pipeline, topic) for topic in ("charging", "comfort"))
        for requirement in (charging, comfort):
            verify_priority(requirement)
            traced = await self.trace(requirement)
            require(traced["evidence"]["total"] == 1, "Initial requirement contains unrelated evidence")
        require(comfort["current_version"]["title"].startswith("Preserve"), "Positive customer attribute was not preserved")
        require(any(finding["kind"] == "strength" and evidence[uploaded["source_id"]]["id"] in finding["evidence_ids"]
                    for finding in pipeline["analysis"]["findings"]), "Positive evidence was lost during analysis")
        ranked = await self.mcp("list_requirements", **self.scope, limit=1)
        next_rank = await self.http("GET", "/requirements", params={**self.scope, "limit": 1, "offset": 1})
        require(ranked["total"] == next_rank["total"] == 2 and ranked["items"][0]["id"] != next_rank["items"][0]["id"],
                "Requirement pagination failed")
        require(ranked["items"][0]["priority"] >= next_rank["items"][0]["priority"], "Priority list is not ranked")
        self.passed("Initial analysis, positive preservation, measurable requirements, priority formula and complete traces")

        original_version = charging["current_version"]
        pm_title = "Customers complete charging trip planning confidently"
        pm_target = [{"metric": "Charging trip planning task success", "target": 95, "unit": "%",
                      "basis": "PM assumption", "source_ids": []}]
        charging = await self.mcp("edit_requirement", requirement_id=charging["id"], expected_version_id=original_version["id"],
                                  actor=ACTOR, rationale="Set customer evaluation target", title=pm_title,
                                  acceptance_criteria=pm_target,
                                  factors={**original_version["factors"], "customer_impact": 5})
        verify_priority(charging)
        require(charging["current_version"]["score"]["total"] > original_version["score"]["total"], "PM edit was not rescored")
        require(charging["current_version"]["version"] == 2, "PM edit did not create a new version")
        await self.http("PATCH", f"/requirements/{charging['id']}", expected_status=409,
                        json={"expected_version_id": original_version["id"], "actor": ACTOR, "rationale": "Stale edit check", "title": "Stale title"})
        await self.mcp("decide_requirement", requirement_id=charging["id"], version_id=original_version["id"],
                       score_id=original_version["score"]["id"], action="approve", actor=ACTOR,
                       rationale="Stale version check", expected_error="HTTP 409")
        prior_score = charging["current_version"]["score"]
        await self.mcp("score_requirement", requirement_id=charging["id"], expected_version_id=original_version["id"],
                       actor=ACTOR, rationale="Stale scoring version check", expected_error="HTTP 409")
        # Newer API/MCP versions also guard competing rescoring within one immutable
        # requirement version. Discover this optional argument instead of sending it
        # to older adapters whose tool schemas reject unknown fields.
        score_guard = "expected_score_id" in tool_definitions["score_requirement"].input_schema["properties"]
        score_arguments = {"expected_score_id": prior_score["id"]} if score_guard else {}
        revised_weights = {key: float(key == "customer_impact") for key in prior_score["weights"]}
        revised_score = await self.mcp("score_requirement", requirement_id=charging["id"], expected_version_id=charging["current_version_id"],
                       actor=ACTOR, rationale="Emphasize customer impact", weights=revised_weights, **score_arguments)
        require(revised_score["id"] != prior_score["id"], "Changed rubric did not record a new score")
        if score_guard:
            await self.mcp("score_requirement", requirement_id=charging["id"], expected_version_id=charging["current_version_id"],
                           actor=ACTOR, rationale="Stale scoring rubric check", weights=prior_score["weights"],
                           expected_score_id=prior_score["id"], expected_error="HTTP 409")
        self.counts["optimistic_score_concurrency"] = score_guard
        await self.mcp("decide_requirement", requirement_id=charging["id"], **decision_payload(charging), expected_error="HTTP 409")
        charging = await self.mcp("get_requirement", requirement_id=charging["id"])
        charging, comfort = await self.approve(charging), await self.approve(comfort)
        baseline = charging["approved_version"]
        self.passed("PM edit and rescore, stale version/score rejection, explicit versioned approval")

        unchanged = await self.mcp("assess_updates", **self.scope, actor=ACTOR)
        require(unchanged["analysis"]["cached"] and not unchanged["generation"]["updated"] and not unchanged["reviews"],
                "Unchanged evidence unnecessarily reopened approved decisions")
        unrelated = feedback_payload(self.vehicle, f"{self.vehicle}:unrelated", "Exterior design looks beautiful", "design", "strength")
        await self.mcp("import_records", **unrelated)
        unrelated_update = await self.http("POST", "/updates", expected_status=201, json={**self.scope, "actor": ACTOR})
        require(not unrelated_update["generation"]["updated"] and not unrelated_update["reviews"],
                "Unrelated evidence reopened an approved decision")
        require(requirement_by_topic(unrelated_update, "charging")["approved_version"] == baseline, "Unrelated update changed approval")
        self.passed("Unchanged and unrelated evidence do not create review noise")

        other_vehicle = self.vehicle + "-OTHER"
        foreign = feedback_payload(other_vehicle, f"{self.vehicle}:other-vehicle", "Public charging is confusing", "charging", "problem")
        foreign_source = await self.http("POST", "/imports/records", expected_status=201, json=foreign)
        await self.http("POST", "/analyses", expected_status=422,
                        json={**self.scope, "source_ids": [foreign_source["source_id"]]})
        foreign_pipeline = await self.http("POST", "/pipeline/run", expected_status=201, json={"vehicle": other_vehicle, "market": "US"})
        foreign_requirement = requirement_by_topic(foreign_pipeline, "charging")
        await self.mcp("edit_requirement", requirement_id=charging["id"], expected_version_id=charging["current_version_id"],
                       actor=ACTOR, rationale="Cross-vehicle findings must fail", finding_ids=foreign_requirement["current_version"]["finding_ids"],
                       expected_error="HTTP 422")
        require((await self.mcp("list_evidence", **self.scope))["total"] == 3, "Another vehicle leaked into evidence list")
        require((await self.http("GET", "/requirements", params={"vehicle": other_vehicle, "market": "US"}))["total"] == 1,
                "Other vehicle requirements include main-scope data")
        self.passed("Vehicle/market isolation and rejection of cross-scope evidence references")

        new_feedback = feedback_payload(self.vehicle, f"{self.vehicle}:new-evidence", "I love the easy public charging", "charging", "strength")
        new_source = await self.mcp("import_records", **new_feedback)
        updated = await self.mcp("assess_updates", **self.scope, actor=ACTOR)
        revised = requirement_by_topic(updated, "charging")
        verify_priority(revised)
        require(updated["generation"]["updated"] == [charging["id"]], "Update did not target only the affected requirement")
        require({review["requirement_id"] for review in updated["reviews"]} == {charging["id"]}, "Review routing is not targeted")
        require(len(updated["reviews"]) == 1, "New evidence created duplicate review items")
        require(revised["approved_version"] == baseline, "New evidence changed the approved snapshot")
        require(revised["current_version_id"] != baseline["id"] and revised["needs_review"], "New evidence did not produce a reviewable proposal")
        require(revised["current_version"]["title"] == pm_title and revised["current_version"]["acceptance_criteria"] == pm_target,
                "New analysis overwrote PM acceptance targets/title")
        require(revised["current_version"]["score"]["explanation"]["conflict_flag"], "Contrasting customer evidence was not highlighted")
        require(requirement_by_topic(updated, "comfort")["approved_version"] == comfort["approved_version"], "Unrelated approval changed")
        review = updated["reviews"][0]
        require(review["reason"] and review["suggested_action"], "Review lacks rationale or suggested response")
        comparison = review["changes"]["against_approved"]
        require(comparison["baseline_version_id"] == baseline["id"] and len(comparison["added_evidence_ids"]) == 1,
                "Review does not explain changes against the approved baseline")
        require(comparison["approved_score"] == baseline["score"], "Review lost the approved priority snapshot")
        needs_review = await self.mcp("list_requirements", **self.scope, needs_review=True)
        require([row["id"] for row in needs_review["items"]] == [charging["id"]], "Needs review filter is inaccurate")
        traced = await self.trace(revised)
        require({source["id"] for source in traced["sources"]} == {imported["source_id"], new_source["source_id"]},
                "Updated trace lost old or new evidence")
        old_trace = await self.trace(charging, baseline["id"])
        require(old_trace["version"] == baseline and old_trace["evidence"]["total"] == 1 and len(old_trace["decisions"]) == 1,
                "Historical approved trace changed after new evidence")
        await self.http("POST", "/requirements/generate", expected_status=409, json={"run_id": pipeline["analysis"]["id"]})
        await self.mcp("decide_requirement", requirement_id=charging["id"], **decision_payload(charging), expected_error="HTTP 409")
        repeated_update = await self.mcp("assess_updates", **self.scope, actor=ACTOR)
        require(not repeated_update["generation"]["updated"] and repeated_update["reviews"] == updated["reviews"]
                and requirement_by_topic(repeated_update, "charging")["current_version_id"] == revised["current_version_id"],
                "Repeated update duplicated revisions or review items")
        self.passed("New evidence creates targeted review, preserves PM fields and approvals, and retains complete historical traces")

        accepted = await self.approve(revised)
        require(accepted["approved_version_id"] != baseline["id"], "Accepted update failed to advance approval")
        require(not await self.mcp("list_reviews", **self.scope), "Accepted review remains open")
        versions = await self.mcp("get_requirement_versions", requirement_id=charging["id"])
        require([version["version"] for version in versions] == [1, 2, 3], "Version history is incomplete or duplicated")
        require(next(version for version in versions if version["id"] == baseline["id"])["title"] == pm_title,
                "Historical PM version content changed")
        approved_trace = await self.trace(accepted)
        require(len(approved_trace["decisions"]) == 1 and approved_trace["decisions"][0]["actor"] == ACTOR,
                "Accepted proposal is not connected to its PM decision")
        design = await self.approve(requirement_by_topic(updated, "design"))
        design_baseline = design["approved_version"]
        design = await self.http("PATCH", f"/requirements/{design['id']}", json={
            "expected_version_id": design["current_version_id"], "actor": ACTOR, "rationale": "Alternative design proposal",
            "title": "Preserve distinctive exterior design through customer validation"})
        for action, expected_status in (("postpone", "postponed"), ("challenge", "needs_review"), ("reject", "rejected")):
            result = await self.mcp("decide_requirement", requirement_id=design["id"], **decision_payload(design, action))
            design = result["requirement"]
            require(design["status"] == expected_status and design["approved_version"] == design_baseline,
                    f"{action} changed approval or failed to record PM disposition")
            require(design["needs_review"] == (action != "reject"), f"{action} left the wrong review state")
        self.passed("Postpone, challenge and reject preserve the last approved decision")
        events = await self.audit_events(charging["id"])
        sequences = [event["sequence"] for event in events]
        require(sequences == sorted(set(sequences)), "Audit pagination lost order or repeated events")
        require({event["action"] for event in events} >= {"requirement.version_created", "requirement.scored", "requirement.approve", "review.opened"},
                "Audit trail lacks required workflow events")
        require(sum(event["action"] == "requirement.approve" for event in events) == 2, "Stale attempts created extra decisions")
        workspace = await self.mcp("get_workspace", **self.scope)
        require(workspace["scope"] == self.scope and workspace["evidence_count"] == 4 and not workspace["reviews"]
                and workspace["requirements"]["total"] == 3,
                "Final PM workspace counts/reviews are incorrect")
        self.counts.update(synthetic_sources=len(await self.mcp("list_sources", **self.scope)),
                           synthetic_evidence=workspace["evidence_count"], synthetic_requirements=workspace["requirements"]["total"],
                           charging_versions=len(versions), charging_audit_events=len(events), discovered_mcp_tools=len(discovered))
        self.passed("Accept revision, resolve review, retain immutable versions/decisions, paginate audit, and expose PM workspace")

    async def run_real_data(self) -> None:
        scope = {"vehicle": "G60", "market": "US"}
        before = await self.all_http_items("/requirements", **scope)
        approvals = {}
        for row in before:
            if row["approved_version_id"]:
                detail = await self.http("GET", f"/requirements/{row['id']}")
                approvals[row["id"]] = (detail["approved_version_id"], detail["approved_score_id"], detail["approved_version"])
        imported = []
        for path, kind in REAL_FILES:
            result = await self.http("POST", "/imports/local", expected_status=201,
                                     json={**scope, "path": path, "kind": kind, "actor": ACTOR})
            require(result["record_count"] > 0, f"BMW import returned no records: {path}")
            imported.append(result)
        records = await self.all_http_items("/evidence", **scope)
        by_source = Counter(row["source_id"] for row in records)
        for source in imported:
            require(by_source[source["source_id"]] == source["record_count"], "BMW import record count differs from persisted evidence")
        pipeline = await self.http("POST", "/pipeline/run", expected_status=201,
                                   json={**scope, "provider": "deterministic", "actor": ACTOR})
        findings = pipeline["analysis"]["findings"]
        require(bool(findings) and bool(pipeline["generation"]["requirements"]), "BMW analysis produced no findings/requirements")
        evidence_ids = set(pipeline["analysis"]["evidence_ids"])
        require(evidence_ids == {row["id"] for row in records}, "BMW analysis omitted persisted scope evidence")
        finding_evidence = {eid for finding in findings for eid in finding["evidence_ids"] + finding["conflicting_evidence_ids"]}
        require(finding_evidence == evidence_ids, "BMW evidence-to-finding coverage is incomplete")
        traced_ids = set()
        for requirement in pipeline["generation"]["requirements"]:
            verify_priority(requirement)
            traced = await self.trace(requirement, page_size=1000)
            traced_ids.update(row["id"] for row in traced["evidence"]["items"])
        # Context-only sales/document findings intentionally need not generate customer requirements.
        customer_evidence = {eid for finding in findings if finding["kind"] != "context"
                             for eid in finding["evidence_ids"] + finding["conflicting_evidence_ids"]}
        require(customer_evidence <= traced_ids, "BMW customer findings were lost before requirement generation")
        after = await self.all_http_items("/requirements", **scope)
        require({row["id"] for row in after if row["approved_version_id"]} == set(approvals),
                "Real-data evaluation added or removed PM approvals")
        for row in after:
            if row["id"] in approvals:
                current = await self.http("GET", f"/requirements/{row['id']}")
                require((current["approved_version_id"], current["approved_score_id"], current["approved_version"]) == approvals[row["id"]],
                        "Real-data evaluation altered an existing PM approval or priority snapshot")
        self.counts.update(real_import_records=sum(item["record_count"] for item in imported), real_evidence=len(evidence_ids),
                           real_findings=len(findings), real_requirements=len(pipeline["generation"]["requirements"]),
                           real_customer_evidence=len(customer_evidence), real_requirement_trace_evidence=len(traced_ids),
                           real_preserved_approvals=len(approvals))
        self.passed("Mounted G60/US BMW imports, complete finding/customer trace coverage, and preservation of real approvals")

    # Platform journey (PLATFORM_BUILD_PLAN.md §11 step 3) -------------------------------------------------

    async def ai(self, method: str, path: str, **kwargs):
        """An AI-interpretation call: an unconfigured OpenAI provider is a clear failure, never a fallback."""
        try:
            return await self.http(method, path, **kwargs)
        except VerificationFailure as exc:
            if self.provider == "openai" and " returned 503:" in str(exc):
                raise VerificationFailure(
                    f"OpenAI provider unavailable for {method} {path}: the API service needs OPENAI_API_KEY and "
                    f"OPENAI_MODEL; the journey never falls back to the deterministic provider ({exc})") from None
            raise

    async def ai_run(self, label: str, run_id: str | None) -> None:
        if self.provider == "openai":
            require(run_id, f"{label} returned no run id")
            self.llm_runs[label] = llm_usage(await self.http("GET", f"/runs/{run_id}"), label, self.llm_model)

    async def all_audit(self) -> list[dict]:
        events, cursor = [], 0
        while page := (await self.http("GET", "/audit", params={"after": cursor, "limit": 1000}))["items"]:
            events.extend(page)
            cursor = page[-1]["sequence"]
        sequences = [event["sequence"] for event in events]
        require(sequences == sorted(set(sequences)), "Audit pagination lost order or repeated events")
        return events

    async def run_platform_real_data(self) -> None:
        """Every BMW file through Pod E, then G60 context layers. Derivations only: no G60 decisions."""
        scope = {"vehicle": "G60"}
        imported = await self.http("POST", "/market-data/import-bmw", expected_status=201, json={"actor": ACTOR})
        require(imported["totals"]["files"] > 0 and imported["totals"]["sources"] > 0, "BMW import found no files")
        weights = await self.http("POST", "/market-data/weights/derive", expected_status=201, json={**scope, "actor": ACTOR})
        totals = defaultdict(float)
        for item in weights["items"]:
            totals[item["period"]] += item["share"]
        require(totals and all(math.isclose(total, 1, abs_tol=1e-9) for total in totals.values()),
                "BMW G60 sales shares do not sum to 1 per period")
        preserve = await self.http("POST", "/market-data/preserve/derive", expected_status=201,
                                   json={**scope, "market": "US", "provider": "deterministic", "actor": ACTOR})
        coverage = await self.http("POST", "/market-data/coverage", expected_status=201, json={**scope, "actor": ACTOR})
        require(any(report["warnings"] for report in coverage["items"]), "BMW G60 coverage reports carry no warnings")
        fixture = await self.http("POST", "/requests/fixtures/simulated", expected_status=201, json={"actor": ACTOR})
        require(fixture["label"] == "simulated" and fixture["items"] and all(item["simulated"] for item in fixture["items"]),
                "G60 request fixture is not entirely labelled simulated")
        self.counts.update(real_platform_import=imported["totals"], real_g60_weight_periods=sorted(totals),
                           real_g60_us_preserve=len(preserve["items"]),
                           real_g60_coverage_warnings={item["market"]: [w["code"] for w in item["warnings"]]
                                                       for item in coverage["items"]},
                           real_g60_simulated_requests=fixture["total"])
        self.passed("Platform real data: every BMW file imported, G60 weights sum to 1, preserve list, coverage warnings, "
                    "simulated G60 request fixture")

    async def run_platform(self) -> None:
        vehicle, today = self.platform_vehicle, date.today()
        scope = {"vehicle": vehicle, "market": "US"}
        tools = {tool.name for tool in (await self.session.list_tools()).tools}
        require(PLATFORM_TOOLS <= tools, f"Platform MCP tools missing: {sorted(PLATFORM_TOOLS - tools)}")
        require(not tools & GATE_TOOLS, f"Human-gate operations exposed over MCP: {sorted(tools & GATE_TOOLS)}")
        audit_start = (await self.http("GET", "/audit", params={"after": 0, "limit": 1}))["items"]
        require((await self.http("GET", "/workspace", params=scope))["evidence_count"] == 0,
                "Fresh platform scope already has evidence")

        # 1. Market data: simulated feedback and one sales file per market, weights, preserve list, coverage.
        sales = make_sales_workbook()
        for market in PLATFORM_MARKETS:
            feedback = await self.http("POST", "/imports/records", expected_status=201,
                                       json=platform_feedback_payload(vehicle, market, today))
            require(feedback["record_count"] == len(PLATFORM_FEEDBACK[market]), f"{market} feedback import lost records")
            upload = await self.http("POST", "/imports/files", expected_status=201, files={"file": (
                "simulated_sales.xlsx", sales, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"vehicle": vehicle, "market": market, "kind": "sales", "actor": ACTOR,
                      "title": "Simulated sales volumes"})
            require(upload["record_count"] == 1 and upload["sha256"] == hashlib.sha256(sales).hexdigest(),
                    f"{market} sales import did not keep exactly its own row of the shared file")
        weights = await self.http("POST", "/market-data/weights/derive", expected_status=201,
                                  json={"vehicle": vehicle, "actor": ACTOR})
        listed = await self.mcp("list_sales_weights", vehicle=vehicle)
        require({item["id"] for item in listed["items"]} == {item["id"] for item in weights["items"]},
                "MCP weight list differs from the derivation")
        totals = defaultdict(float)
        for item in weights["items"]:
            totals[item["period"]] += item["share"]
            require(item["evidence_ids"] and item["run_id"] == weights["run_id"], "Weight lacks evidence or run provenance")
        require(sorted(totals) == ["2024", "2025"] and all(math.isclose(t, 1, abs_tol=1e-9) for t in totals.values()),
                f"Market weights do not sum to 1 per period: {dict(totals)}")
        require({item["market"] for item in weights["items"]} == set(PLATFORM_MARKETS), "Weights do not cover US, CN and EU")
        share_2025 = {item["market"]: item["share"] for item in weights["items"] if item["period"] == "2025"}
        require(math.isclose(share_2025["US"], 265 / 910), "US 2025 sales share differs from the simulated file")
        preserve = await self.ai("POST", "/market-data/preserve/derive", expected_status=201,
                                 json={"vehicle": vehicle, "provider": self.provider, "actor": ACTOR})
        await self.ai_run("market_data.derive_preserve (naming)", preserve.get("naming_run_id"))
        preserved = await self.mcp("list_preserve_attributes", vehicle=vehicle, market="US")
        require(any(item["topic"] == "comfort" and len(item["evidence_ids"]) >= 5 for item in preserved["items"]),
                "Five explicit comfort likes did not become a preserve attribute")
        coverage = await self.http("POST", "/market-data/coverage", expected_status=201,
                                   json={"vehicle": vehicle, "actor": ACTOR})
        reports = {item["market"]: item for item in (await self.mcp("list_coverage_reports", vehicle=vehicle))["items"]}
        require({item["id"] for item in coverage["items"]} >= {reports[m]["id"] for m in PLATFORM_MARKETS},
                "Coverage reports for US, CN and EU are not current")
        require(all("small_sample" in {w["code"] for w in reports[m]["warnings"]} for m in PLATFORM_MARKETS),
                "Coverage reports omit the small-sample warning for simulated markets")
        self.counts.update(platform_weights=len(weights["items"]), platform_preserve=len(preserved["items"]),
                           platform_coverage_warnings={m: sorted({w["code"] for w in reports[m]["warnings"]})
                                                       for m in PLATFORM_MARKETS})
        self.passed("Platform 1: simulated market data, sales weights sum to 1 per period, preserve list and coverage warnings")

        # 2. The existing pipeline per market.
        requirements = {}
        for market in PLATFORM_MARKETS:
            result = await self.http("POST", "/pipeline/run", expected_status=201,
                                     json={"vehicle": vehicle, "market": market, "provider": "deterministic", "actor": ACTOR})
            for requirement in result["generation"]["requirements"]:
                verify_priority(requirement)
                requirements[market, requirement["topic"]] = requirement
        expected_topics = {("US", "driving-experience"), ("US", "comfort"), ("US", "charging"), ("CN", "comfort"),
                           ("CN", "quietness"), ("EU", "access-storage"), ("EU", "quietness")}
        require(expected_topics <= set(requirements), f"Pipeline omitted requirements: {sorted(expected_topics - set(requirements))}")
        self.counts["platform_requirements"] = len(requirements)
        self.passed("Platform 2: pipeline in US, CN and EU with measurable, scored requirements")

        # 3. Simulated requests: intake, classification, clustering and triage with linked evidence.
        created = await self.http("POST", "/requests", expected_status=201,
                                  json={"requests": simulated_requests(vehicle), "actor": ACTOR})
        require(created["created"] == created["total"] == 6 and all(item["simulated"] for item in created["items"]),
                "Simulated requests were not all created and labelled simulated")
        by_ref = {item["external_ref"].split(":", 1)[1]: item for item in created["items"]}
        rear, exhaust = by_ref["sim-cn-rear-legroom"], by_ref["sim-us-exhaust-note"]
        classified = await self.ai("POST", "/requests/classify", expected_status=201,
                                   json={"vehicle": vehicle, "provider": self.provider, "actor": ACTOR})
        await self.ai_run("requests.classify", classified["run_id"])
        topics = {item["id"]: item for item in classified["items"]}
        require(topics[rear["id"]]["topic"] == "comfort" and topics[exhaust["id"]]["topic"] == "driving-experience",
                "Rear-space or exhaust request was classified into the wrong topic")
        clustered = await self.ai("POST", "/requests/cluster", expected_status=201,
                                  json={"vehicle": vehicle, "provider": self.provider, "actor": ACTOR})
        await self.ai_run("requests.cluster", clustered["run_id"])
        clusters = await self.mcp("list_request_clusters", vehicle=vehicle)
        triage = await self.ai("POST", "/requests/triage", expected_status=201,
                               json={"vehicle": vehicle, "link_provider": self.provider, "actor": ACTOR})
        require(triage["link_run_id"], "Triage did not link evidence for never-linked requests")
        await self.ai_run("requests.link_evidence", triage["link_run_id"])
        ranked = {item["id"]: item for item in triage["items"]}
        flagged = [item for item in triage["items"] if item["scope_flags"]]
        for request in (rear, exhaust):
            item = ranked[request["id"]]
            detail = await self.http("GET", f"/requests/{request['id']}", params={"actor": ACTOR})
            explanation = detail["triage_history"][0]["explanation"]
            require(item["rank"] and item["triage"]["total"] == explanation["total"]
                    and set(explanation["factors"]) == TRIAGE_FACTORS
                    and all(factor["formula"] and "contribution" in factor for factor in explanation["factors"].values())
                    and explanation["suggested_action"]["reason"], f"{request['key']} triage lacks an explained rank")
            supports = [link for link in detail["links"] if link["status"] == "active" and link["entity_type"] == "evidence"
                        and link["relation"] == "supports"]
            require(supports and explanation["factors"]["evidence_support"]["measured"],
                    f"{request['key']} has no linked supporting evidence")
            require(all(link["entity"]["vehicle"] == vehicle and link["basis"]["quote"]
                        and link["entity"]["content"][slice(*link["basis"]["span"])] == link["basis"]["quote"]
                        for link in supports), f"{request['key']} evidence links are ungrounded or cross vehicle scope")
            require(all(item["rank"] < other["rank"] for other in flagged), f"{request['key']} ranks below an out-of-scope ask")
        if self.provider == "deterministic":
            require(by_ref["sim-eu-package-pricing"]["id"] in {item["id"] for item in flagged}
                    and all(item["triage"]["total"] <= 20 for item in flagged), "Pricing request was not flagged and capped")
            require(any(link["relation"] == "conflicts" and link["status"] == "active" for link in (
                await self.http("GET", f"/requests/{exhaust['id']}", params={"actor": ACTOR}))["links"]),
                "Exhaust request lacks the conflicting quietness evidence")
        aggregates = await self.mcp("get_request_aggregates", vehicle=vehicle)
        self.counts.update(platform_requests=len(ranked), platform_flagged_requests=len(flagged),
                           platform_request_clusters=clusters["total"],
                           platform_request_ranks={"CN rear space": ranked[rear["id"]]["rank"],
                                                   "US exhaust": ranked[exhaust["id"]]["rank"]},
                           platform_request_aggregate_keys=sorted(aggregates))
        self.passed("Platform 3: simulated requests classified, clustered and triaged; CN rear-space and US exhaust rank "
                    "with factor explanations and grounded evidence links")

        # 4. Sentiment for imported evidence and weekly series.
        sentiment_method = None
        for market in PLATFORM_MARKETS:
            remaining = True
            while remaining:
                scored = await self.ai("POST", "/signals/sentiment/score", json={
                    "vehicle": vehicle, "market": market, "provider": self.provider, "subject_type": "evidence",
                    "actor": ACTOR})
                if scored["created"]:
                    await self.ai_run(f"signals.score_sentiment {market}", scored["run_id"])
                sentiment_method, remaining = scored["method_version"], scored["remaining"]
        require(self.provider != "deterministic" or sentiment_method == "lexicon-v1", "Deterministic sentiment method changed")
        series = await self.mcp("get_sentiment_timeseries", vehicle=vehicle, market="US", source_class="bmw_evidence",
                                method_version=sentiment_method)
        weeks = {point["week_start"] for point in series["items"] if point["n"] > 0}
        require(len(weeks) >= 3 and all(point["subject_ids"] for point in series["items"]),
                "Weekly sentiment series for the simulated US evidence is missing")
        summary = await self.http("GET", "/signals/summary", params={**scope, "source_class": "bmw_evidence"})
        require(any(row["momentum"] is not None for row in summary["items"]), "No topic has a weekly sentiment momentum")
        self.counts.update(platform_sentiment_method=sentiment_method, platform_sentiment_weeks_us=len(weeks))
        self.passed("Platform 4: sentiment scored for imported evidence; weekly series and momentum exist")

        # 5. Market conflicts with recommendations and per-market evidence.
        detection = await self.ai("POST", "/markets/conflicts/detect", expected_status=201, json={
            "vehicle": vehicle, "markets": list(PLATFORM_MARKETS), "provider": self.provider, "actor": ACTOR})
        await self.ai_run("markets.extract_directions", detection["direction_run_id"])
        conflicts = {}
        for name, tension, recommendation in (("exhaust", EXHAUST_TENSION, "selectable_mode"),
                                              ("rear", REAR_TENSION, "market_variant")):
            matches = [item for item in detection["items"] if item["conflict_type"] == "direction_conflict"
                       and {item["topic"], item["related_topic"]} == tension]
            require(len(matches) == 1 and matches[0]["recommendation"] == recommendation and matches[0]["rationale"],
                    f"The {name} tension did not appear once with recommendation {recommendation}")
            detail = await self.mcp("get_market_conflict", conflict_id=matches[0]["id"])
            require(len(detail["markets"]) >= 2 and all(detail["evidence"].get(m) for m in detail["markets"]),
                    f"The {name} conflict lacks evidence in each market")
            require(all(row["source_id"] and row["location"] and row["content"][slice(*mention["span"])] == mention["quote"]
                        for rows in detail["evidence"].values() for row in rows for mention in row["mentions"]),
                    f"The {name} conflict evidence lacks provenance or exact quotes")
            conflicts[name] = detail
        if self.provider == "openai":
            brief = await self.ai("POST", f"/markets/conflicts/{conflicts['exhaust']['id']}/brief",
                                  json={"provider": "openai", "actor": ACTOR})
            require(brief["metrics"]["ai_brief"]["citations"] and brief["recommendation"] == "selectable_mode",
                    "AI conflict brief lacks citations or changed the recommendation")
            await self.ai_run("markets.draft_conflict_brief", brief["run_id"])
        self.counts.update(platform_conflicts=detection["total"],
                           platform_conflict_markets={name: c["markets"] for name, c in conflicts.items()})
        self.passed("Platform 5: rear-space and exhaust/quietness tensions with recommendations and per-market evidence")

        # 6. Human gate: an AI actor is refused, the PM resolves, re-detection keeps the decision.
        exhaust_conflict = conflicts["exhaust"]
        resolution = {"decision": "selectable_mode", "requirement_ids": exhaust_conflict["requirement_ids"],
                      "rationale": "Simulated PM review: offer a selectable sound mode per market"}
        await self.http("POST", f"/markets/conflicts/{exhaust_conflict['id']}/resolve", expected_status=403,
                        json={**resolution, "actor": AI_ACTOR})
        require((await self.http("GET", f"/markets/conflicts/{exhaust_conflict['id']}"))["status"] == "open",
                "Refused AI resolution changed the conflict")
        resolved = await self.http("POST", f"/markets/conflicts/{exhaust_conflict['id']}/resolve", expected_status=201,
                                   json={**resolution, "actor": ACTOR})
        require(resolved["conflict"]["status"] == "resolved" and resolved["actor"] == ACTOR and resolved["audit_event_id"],
                "PM resolution was not recorded")
        again = await self.ai("POST", "/markets/conflicts/detect", expected_status=201, json={
            "vehicle": vehicle, "markets": list(PLATFORM_MARKETS), "provider": self.provider, "actor": ACTOR})
        require({exhaust_conflict["id"], conflicts["rear"]["id"]} <= set(again["unchanged"]) and not again["created"],
                "Re-detection on unchanged inputs reopened or duplicated conflicts")
        listed = await self.mcp("list_market_conflicts", vehicle=vehicle, status="resolved")
        require([item["id"] for item in listed["items"]] == [exhaust_conflict["id"]], "Resolved conflict list is wrong")
        self.passed("Platform 6: AI resolution refused (403); PM resolution recorded and kept by re-detection")

        # 7. Rubric v2: approved requirement, human switch, derived factors, sensitivity, reviews, explanation.
        approved = await self.approve(requirements["US", "driving-experience"])
        switch = {"vehicle": vehicle, "market": "US", "rubric_version": "customer-priority-v2",
                  "rationale": "Simulated PM review: rank with recorded market demand, sentiment and requests"}
        await self.http("POST", "/priorities/rubric", expected_status=403, json={**switch, "actor": AI_ACTOR})
        switched = await self.http("POST", "/priorities/rubric", expected_status=201, json={**switch, "actor": ACTOR})
        require(switched["changed"] and switched["run_id"] and switched["rescored"], "Rubric switch did not rescore")
        reviewed = {entry["requirement_id"]: entry for entry in switched["rescored"] if entry["review_id"]}
        require(approved["id"] in reviewed and set(switched["reviews_opened"]) == {e["review_id"] for e in reviewed.values()},
                "Approved requirement whose score changed got no review item")
        reviews = await self.http("GET", "/reviews", params=scope)
        require(approved["id"] in {review["requirement_id"] for review in reviews}, "Rubric review is not open")
        sensitivity = await self.mcp("run_priority_sensitivity", **scope, actor=ACTOR)
        ranking = await self.mcp("get_priority_ranking", **scope)
        require(ranking["rubric"]["rubric_version"] == "customer-priority-v2" and ranking["items"]
                and all(item["rubric_version"] == "customer-priority-v2" for item in ranking["items"]),
                "Ranking does not use rubric v2")
        for item in ranking["items"]:
            derived = {factor["factor"]: factor for factor in item["factors"] if factor["source"] == "derived"}
            require(set(derived) == set(DERIVED_FACTORS)
                    and all(factor["priority_input_id"] and isinstance(factor["derivation"], dict) for factor in derived.values()),
                    f"{item['key']} lacks derived factors with derivations")
            require(derived["market_demand"]["measured"] and derived["request_pressure"]["measured"],
                    f"{item['key']} did not measure market demand or request pressure")
            require(item["stability"]["current"] and item["stability"]["sensitivity_id"] == sensitivity["id"],
                    f"{item['key']} stability is not from the current sensitivity run")
        require(any(item["stability"]["stable"] for item in ranking["items"]), "Sensitivity marked no item stable")
        require(any(item["preserve_warnings"] for item in ranking["items"]), "Preserve guard warned on no requirement")
        explained = await self.ai("POST", "/priorities/explain", expected_status=201,
                                  json={**scope, "provider": self.provider, "actor": ACTOR})
        require(explained["ai_generated"] is (self.provider == "openai")
                and {item["requirement_id"] for item in explained["items"]} == {i["requirement_id"] for i in ranking["items"]}
                and all(item["explanation"] and item["score_id"] in item["cited_ids"] for item in explained["items"]),
                "Ranking explanation is incomplete or does not cite the recorded scores")
        await self.ai_run("priorities.explain", explained["run_id"])
        self.counts.update(platform_v2_ranking=[{key: item[key] for key in ("key", "topic", "rank", "total")}
                                                | {"stable": item["stability"]["stable"],
                                                   "sentiment_measured": next(f["measured"] for f in item["factors"]
                                                                              if f["factor"] == "sentiment_momentum")}
                                                for item in ranking["items"]],
                           platform_reviews_opened=len(switched["reviews_opened"]))
        self.passed("Platform 7: AI rubric switch refused; PM switch to v2 shows derived factors with derivations, "
                    "stable items, preserve warnings, explanations and review items for changed approvals")

        # 8. Recurring signals task through run-due, runs, board, audit and the hash chain.
        exa = await self.http("GET", "/research/exa/status")
        watch = {**PUBLIC_SCOPE, "topic": "driving-experience", "label": f"Simulated E2E journey {vehicle}",
                 "rationale": "Simulated verification: weekly public-signal refresh"}
        await self.http("POST", "/signals/watchlists", expected_status=403, json={**watch, "actor": AI_ACTOR})
        watchlist = await self.http("POST", "/signals/watchlists", expected_status=201, json={**watch, "actor": ACTOR})
        task = await self.http("POST", "/tasks", expected_status=201, json={
            **PUBLIC_SCOPE, "topic": "driving-experience", "capability": "signals.refresh_watchlist",
            "title": f"Simulated E2E weekly refresh {vehicle}", "input": {"watchlist_id": watchlist["id"]},
            "requested_by": ACTOR, "recurrence_days": 7})
        require(task["recurring"] and task["status"] == "queued" and task["due_at"], "Recurring task is not due")
        due = await self.http("POST", "/tasks/run-due", json={})
        runs = [item for item in due["executed"] if item["occurrence_of"] == task["id"]]
        require(len(runs) == 1, f"run-due did not execute the recurring task once: {due['skipped']}")
        occurrence = await self.mcp("get_task", task_id=runs[0]["task_id"])
        template = await self.http("GET", f"/tasks/{task['id']}")
        require(occurrence["parent_task_id"] == task["id"] and occurrence["status"] in ("succeeded", "failed")
                and template["status"] == "queued" and template["due_at"] > task["due_at"]
                and occurrence["id"] in {child["id"] for child in template["children"]},
                "Recurring task did not spawn one occurrence and advance its schedule")
        run = await self.mcp("get_run", run_id=occurrence["last_run_id"])
        require(run["capability"] == "signals.refresh_watchlist" and run["task_id"] == occurrence["id"]
                and run["status"] == occurrence["status"] and run["audit_events"], "Task run is not recorded")
        if not exa["configured"] and occurrence["status"] == "failed":
            require("exa" in (occurrence["error"] or "").lower() and "exa" in (run["error"] or "").lower(),
                    "Unconfigured Exa did not fail visibly with a clear error")
        board = await self.mcp("get_task_board", **PUBLIC_SCOPE, limit=500)
        columns = {column["key"]: {card["id"] for card in column["items"]} for column in board["columns"]}
        require(task["id"] in columns["queued"] and occurrence["id"] in columns[occurrence["status"]],
                "Task board does not show the schedule and its occurrence")
        cancelled = await self.http("PATCH", f"/tasks/{task['id']}", json={
            "actor": ACTOR, "expected_revision": template["revision"], "status": "cancelled",
            "rationale": "Simulated verification complete; stop the schedule"})
        paused = await self.http("PATCH", f"/signals/watchlists/{watchlist['id']}", json={
            "actor": ACTOR, "status": "paused", "rationale": "Simulated verification complete"})
        require(cancelled["status"] == "cancelled" and paused["status"] == "paused", "Verification schedule was not stopped")
        platform_runs = await self.all_http_items("/runs", page_size=500, vehicle=vehicle)
        capabilities = {item["capability"] for item in platform_runs}
        require(PLATFORM_CAPABILITIES <= capabilities, f"Runs missing for {sorted(PLATFORM_CAPABILITIES - capabilities)}")
        require(all(item["status"] == "succeeded" for item in platform_runs), "A platform journey run did not succeed")
        expected_audit = {
            exhaust_conflict["id"]: {"market_conflict.detected", "market_conflict.selectable_mode"},
            switched["id"]: {"priorities.rubric_switched"}, rear["id"]: {"request.created", "request.triaged"},
            task["id"]: {"task.created", "task.rescheduled", "task.cancelled"},
            occurrence["id"]: {"task.created", "task.started", f"task.{occurrence['status']}"},
            watchlist["id"]: {"watchlist.created", "watchlist.updated"}}
        for entity_id, actions in expected_audit.items():
            found = {event["action"] for event in await self.audit_events(entity_id, page_size=100)}
            require(actions <= found, f"Audit for {entity_id} lacks {sorted(actions - found)}")
        events = await self.all_audit()
        chain = verify_audit_chain(events)
        require(not audit_start or events[0]["sequence"] == audit_start[0]["sequence"], "Audit history start changed")
        self.counts.update(platform_runs=len(platform_runs), platform_run_capabilities=sorted(capabilities),
                           platform_task_status=occurrence["status"], exa_configured=exa["configured"],
                           audit_chain=chain)
        self.passed("Platform 8: recurring signals task via run-due (Exa outcome recorded), runs, board and audit for "
                    "every step, and a verified audit hash chain")
        if self.provider == "openai":
            self.counts["llm_usage"] = self.llm_runs
            self.counts["llm_total_tokens"] = sum(item["total_tokens"] for item in self.llm_runs.values())

    def report(self, status: str, elapsed: float, error: str | None = None) -> dict:
        totals = Counter()
        for operation in self.timings:
            totals[operation["transport"]] += 1
        result = {"status": status, "vehicle": self.vehicle, "market": "US", "provider": self.provider,
                  "elapsed_seconds": round(elapsed, 3), "checks_passed": len(self.checks), "checks": self.checks,
                  "counts": self.counts, "requests": dict(totals),
                  "latency_ms": {transport: {"total": round(sum(item["ms"] for item in self.timings if item["transport"] == transport), 2),
                                             "max": max(item["ms"] for item in self.timings if item["transport"] == transport)}
                                 for transport in totals}}
        if any(check.startswith("Platform") for check in self.checks) or self.llm_runs:
            result.update(platform_vehicle=self.platform_vehicle, platform_markets=list(PLATFORM_MARKETS),
                          platform_label="simulated")
        if error:
            result["error"] = error
        return result


@asynccontextmanager
async def connect_live(api_url: str, mcp_url: str):
    async with httpx.AsyncClient(base_url=api_url.rstrip("/"), timeout=180, follow_redirects=False) as api:
        async with streamable_http_client(mcp_url) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=180) as session:
                await session.initialize()
                yield Verification(api, session)


async def main_async(args) -> int:
    started = time.perf_counter()
    verification = None
    try:
        platform = getattr(args, "platform", False)
        async with connect_live(args.api_url, args.mcp_url) as verification:
            verification.provider = getattr(args, "provider", "deterministic")
            verification.llm_model = getattr(args, "expected_model", None)
            await verification.run_synthetic()
            if args.real_data:
                await verification.run_real_data()
            if platform and args.real_data:
                await verification.run_platform_real_data()
            if platform:
                await verification.run_platform()
        report = verification.report("passed", time.perf_counter() - started)
    except Exception as exc:
        # Preserve nested transport failure details instead of only ExceptionGroup's title.
        error = repr(exc)
        report = (verification.report("failed", time.perf_counter() - started, error) if verification else
                  {"status": "failed", "checks_passed": 0, "error": error,
                   "elapsed_seconds": round(time.perf_counter() - started, 3)})
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--mcp-url", default="http://127.0.0.1:8001/mcp")
    parser.add_argument("--real-data", action="store_true", help="Also import mounted BMW files and check G60/US trace coverage")
    parser.add_argument("--platform", action="store_true",
                        help="Also run the simulated platform journey (market data, requests, sentiment, conflicts, "
                             "rubric v2, recurring task, audit chain)")
    parser.add_argument("--provider", choices=("deterministic", "openai"), default="deterministic",
                        help="Provider for the platform journey's AI steps; openai needs the key on the API service")
    parser.add_argument("--expected-model", help="With --provider openai: require this OPENAI_MODEL in every AI run")
    args = parser.parse_args()
    if args.provider == "openai" and not args.platform:
        parser.error("--provider openai applies to the platform journey; add --platform")
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
