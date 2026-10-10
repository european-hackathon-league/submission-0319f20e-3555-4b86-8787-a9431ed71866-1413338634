"""Verify the live BMW PM pipeline through HTTP and a real Streamable HTTP MCP client.

Run from the repository: uv run python scripts/verify_backend.py --api-url
http://127.0.0.1:18000 --mcp-url http://127.0.0.1:18001/mcp

Every run uses a fresh E2E vehicle. It leaves that auditable fixture in place;
there is no database access, cleanup, server lifecycle management, or approval of
real G60 requirements. --real-data additionally imports the mounted BMW files
and checks G60/US analysis and trace coverage, preserving prior approvals.
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
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
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


@dataclass
class Verification:
    api: httpx.AsyncClient
    session: Any
    vehicle: str = field(default_factory=lambda: "E2E-" + uuid.uuid4().hex[:16].upper())
    checks: list[str] = field(default_factory=list)
    timings: list[dict] = field(default_factory=list)
    counts: dict = field(default_factory=dict)

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

    def report(self, status: str, elapsed: float, error: str | None = None) -> dict:
        totals = Counter()
        for operation in self.timings:
            totals[operation["transport"]] += 1
        result = {"status": status, "vehicle": self.vehicle, "market": "US", "provider": "deterministic",
                  "elapsed_seconds": round(elapsed, 3), "checks_passed": len(self.checks), "checks": self.checks,
                  "counts": self.counts, "requests": dict(totals),
                  "latency_ms": {transport: {"total": round(sum(item["ms"] for item in self.timings if item["transport"] == transport), 2),
                                             "max": max(item["ms"] for item in self.timings if item["transport"] == transport)}
                                 for transport in totals}}
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
        async with connect_live(args.api_url, args.mcp_url) as verification:
            await verification.run_synthetic()
            if args.real_data:
                await verification.run_real_data()
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
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
