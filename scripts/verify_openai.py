"""Verify actual OpenAI analysis and the PM workflow over live HTTP and MCP.

Run: uv run python scripts/verify_openai.py --expected-model gpt-6.1-sol
The server must already have OPENAI_API_KEY and OPENAI_MODEL configured. This
command never reads credentials, substitutes a provider, or manages services.
It makes two uncached analyses in a unique LIVE-AI vehicle, leaves the auditable
synthetic fixture in place, and prints only a JSON metadata report. This tests
provider integration and workflow invariants, not general AI semantic quality.

--platform adds one cheap call per platform AI capability that fits this fixture (sentiment,
request classification, market directions, priority explanation) and requires each stored run to
record the model, prompt version and token usage. Conflict briefs, preserve naming, evidence links
and embeddings need the larger simulated scenario of verify_backend.py --platform --provider openai.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

# Support both `python scripts/verify_openai.py` and package imports in tests.
try:
    from scripts.verify_backend import (
        ACTOR,
        Verification,
        decision_payload,
        feedback_payload,
        llm_usage,
        require,
        requirement_by_topic,
        verify_priority,
    )
except ModuleNotFoundError:
    from verify_backend import (
        ACTOR,
        Verification,
        decision_payload,
        feedback_payload,
        llm_usage,
        require,
        requirement_by_topic,
        verify_priority,
    )


@dataclass
class OpenAIVerification(Verification):
    vehicle: str = field(default_factory=lambda: "LIVE-AI-" + uuid.uuid4().hex[:16].upper())
    expected_model: str = "gpt-6.1-sol"
    stage: str = "connect"
    imported_payloads: dict[str, dict] = field(default_factory=dict, repr=False)

    async def check_analysis(self, result: dict, evidence: list[dict], *, cached: bool) -> None:
        analysis = result["analysis"]
        expected = {row["id"] for row in evidence}
        require((analysis["vehicle"], analysis["market"]) == (self.vehicle, "US"), "Analysis crossed the requested scope")
        require(result["generation"]["run_id"] == analysis["id"], "Requirements came from a different analysis run")
        for recorded in (analysis, analysis["result"]):
            require(recorded["provider"] == "openai", "Analysis did not use the requested OpenAI provider")
            require(recorded["model"] == self.expected_model, "Analysis used a different model")
        require(analysis["cached"] is cached, "Analysis cache state does not match the requested workflow")
        require(set(analysis["evidence_ids"]) == expected, "Analysis input omitted scoped evidence")
        require(set(analysis["result"]["analyzed_evidence_ids"]) == expected,
                "OpenAI analysis did not analyze every scoped evidence record")
        require(len(analysis["evidence_ids"]) == len(analysis["result"]["analyzed_evidence_ids"]) == len(expected),
                "Analysis input or coverage duplicated evidence records")
        require(analysis["prompt_version"] == analysis["result"]["prompt_version"], "Analysis prompt provenance differs")
        findings = analysis["findings"]
        referenced = {eid for finding in findings
                      for eid in finding["evidence_ids"] + finding["conflicting_evidence_ids"]}
        require(referenced == expected, "OpenAI findings omitted or invented evidence references")
        require(all((finding["vehicle"], finding["market"]) == (self.vehicle, "US") for finding in findings),
                "OpenAI findings crossed the requested scope")
        require(all(finding["run_id"] == analysis["id"] for finding in findings),
                "OpenAI findings belong to a different analysis run")
        finding_fields = ("topic", "kind", "summary", "confidence", "evidence_ids", "conflicting_evidence_ids")
        require([{key: finding[key] for key in finding_fields} for finding in findings]
                == [{key: finding[key] for key in finding_fields} for finding in analysis["result"]["findings"]],
                "Persisted findings differ from the OpenAI analysis output")
        for row in evidence:
            if row["metadata"]["sentiment"] == "strength":
                require(any(finding["kind"] == "strength" and row["id"] in finding["evidence_ids"]
                            for finding in findings), "Explicit positive customer evidence was lost")
        persisted = await self.mcp("get_analysis", run_id=analysis["id"])
        require(all(persisted[key] == analysis[key] for key in (
            "id", "vehicle", "market", "result", "findings", "provider", "model", "prompt_version", "input_hash", "evidence_ids")),
                "Persisted analysis differs from the pipeline response")
        events = await self.audit_events(analysis["id"])
        completions = [event for event in events if event["action"] == "analysis.completed"]
        require(len(completions) == 1, "Analysis lacks exactly one persisted completion audit event")
        completion = completions[0]
        metadata = completion["metadata"]
        require(completion["entity_type"] == "analysis" and completion["actor"] == ACTOR and completion["rationale"]
                and metadata["provider"] == "openai" and metadata["model"] == self.expected_model
                and metadata["prompt_version"] == analysis["prompt_version"]
                and set(metadata["source_ids"]) == {row["source_id"] for row in evidence}
                and metadata["evidence_count"] == len(evidence)
                and completion["after_state"]["input_hash"] == analysis["input_hash"]
                and completion["after_state"]["finding_count"] == len(findings)
                and completion["after_state"]["proposal_count"] == len(analysis["result"]["proposals"]),
                "Analysis audit provider or evidence provenance is incomplete")
        traced_evidence = set()
        for requirement in result["generation"]["requirements"]:
            require((requirement["vehicle"], requirement["market"]) == (self.vehicle, "US"),
                    "Generated requirements crossed the requested scope")
            verify_priority(requirement)
            trace = await self.trace(requirement)
            require(trace["version"] == requirement["current_version"],
                    "Requirement trace differs from the pipeline's current version or score")
            traced_evidence.update(row["id"] for row in trace["evidence"]["items"])
        require(traced_evidence == expected, "Customer evidence was lost before requirement trace generation")

    async def check_sources(self, imports: list[dict], evidence: list[dict]) -> None:
        require({row["source_id"] for row in evidence} == {item["source_id"] for item in imports},
                "Persisted evidence does not cover exactly the imported sources")
        for imported in imports:
            payload = self.imported_payloads[imported["source_id"]]
            source = await self.mcp("get_source", source_id=imported["source_id"])
            require(source["id"] == imported["source_id"] and source["content_hash"] == imported["sha256"],
                    "Source reference does not resolve to the imported original")
            require((source["vehicle"], source["market"]) == (self.vehicle, "US"), "Source reference crosses scope")
            require(source["reference"] == payload["reference"] and source["kind"] == payload["kind"],
                    "Source reference or kind changed during import")
            original = await self.http("GET", f"/sources/{source['id']}/original", raw=True)
            require(hashlib.sha256(original).hexdigest() == imported["sha256"], "Preserved source original checksum differs")
            expected_records = [{**record, **self.scope} for record in payload["records"]]
            require(json.loads(original) == {"reference": payload["reference"], "records": expected_records},
                    "Preserved source original differs from the synthetic input")
            rows = [row for row in evidence if row["source_id"] == source["id"]]
            require(len(rows) == imported["record_count"] == 1, "Source record count differs from its persisted evidence")
            fields = ("content", "location", "observed_at", "metadata", "vehicle", "market")
            require({key: rows[0][key] for key in fields} == expected_records[0],
                    "Evidence content, source location, date, metadata or scope changed during import")

    async def import_fixture(self, payload: dict, *, use_http: bool = False) -> dict:
        imported = (await self.http("POST", "/imports/records", expected_status=201, json=payload) if use_http
                    else await self.mcp("import_records", **payload))
        require(not imported["deduplicated"] and imported["record_count"] == 1, "Fixture import was not fresh")
        require(imported["source_id"] not in self.imported_payloads, "Fixture reused another source identity")
        self.imported_payloads[imported["source_id"]] = payload
        return imported

    async def run(self) -> None:
        self.stage = "health-and-import"
        require((await self.http("GET", "/health"))["status"] == "ok", "API health check failed")
        require((await self.mcp("health"))["status"] == "ok", "MCP upstream health check failed")
        workspace = await self.http("GET", "/workspace", params=self.scope)
        require(workspace["evidence_count"] == workspace["requirements"]["total"] == 0 and not workspace["reviews"],
                "Synthetic scope already contains evidence, requirements or reviews")
        definitions = {tool.name: tool for tool in (await self.session.list_tools()).tools}
        required = {"health", "run_pipeline", "assess_updates", "get_analysis", "get_source", "import_records",
                    "trace_requirement", "edit_requirement", "score_requirement", "decide_requirement", "get_requirement",
                    "get_requirement_versions", "list_audit", "list_reviews", "get_workspace"}
        require(required <= set(definitions), "MCP is missing required workflow tools")
        require("expected_score_id" in definitions["score_requirement"].input_schema["properties"],
                "MCP scoring lacks optimistic score concurrency")
        imports = []
        records = [
            ("charging-problem", "Public charging often fails to start; I need reliable charging session initiation.",
             "charging", "problem"),
            ("charging-strength", "I love the clear charging progress display and want it preserved.", "charging", "strength"),
            ("comfort-strength", "I love the comfortable seats during long journeys and want that comfort preserved.",
             "comfort", "strength"),
        ]
        for index, (label, content, topic, sentiment) in enumerate(records):
            payload = feedback_payload(self.vehicle, f"{self.vehicle}:{label}", content, topic, sentiment)
            imports.append(await self.import_fixture(payload, use_http=index == 1))
        evidence = await self.all_http_items("/evidence", **self.scope)
        require(len(evidence) == 3, "Initial fixture evidence count differs")
        await self.check_sources(imports, evidence)
        self.passed("HTTP/MCP connectivity, unique synthetic scope, and complete source provenance")

        self.stage = "initial-openai-analysis"
        pipeline = await self.mcp("run_pipeline", **self.scope, provider="openai", actor=ACTOR)
        await self.check_analysis(pipeline, evidence, cached=False)
        charging, comfort = (requirement_by_topic(pipeline, topic) for topic in ("charging", "comfort"))
        require(len(pipeline["generation"]["requirements"]) == 2, "Initial evidence produced unexpected requirement themes")
        self.passed("Actual OpenAI initial analysis, expected model, complete evidence coverage, strengths, and priority traces")

        self.stage = "pm-edits-and-approval"
        original = charging["current_version"]
        pm_title = "Customers confidently start charging and retain a clear progress display"
        pm_target = [{"metric": "Charging session initiation task success", "target": 95, "unit": "%",
                      "basis": "PM assumption", "source_ids": []}]
        charging = await self.mcp("edit_requirement", requirement_id=charging["id"], expected_version_id=original["id"],
                                  title=pm_title, acceptance_criteria=pm_target, actor=ACTOR,
                                  rationale="Synthetic PM sets an explicit customer validation target")
        verify_priority(charging)
        require(charging["approved_version_id"] is None, "PM edit implicitly approved a proposal")
        await self.mcp("decide_requirement", requirement_id=charging["id"], version_id=original["id"],
                       score_id=original["score"]["id"], action="approve", actor=ACTOR,
                       rationale="Stale version must fail", expected_error="HTTP 409")
        await self.mcp("score_requirement", requirement_id=charging["id"], expected_version_id=original["id"],
                       actor=ACTOR, rationale="Stale version must fail", expected_error="HTTP 409")
        prior_score = charging["current_version"]["score"]
        weights = {key: float(key == "customer_impact") for key in prior_score["weights"]}
        scored = await self.mcp("score_requirement", requirement_id=charging["id"],
                                expected_version_id=charging["current_version_id"], expected_score_id=prior_score["id"],
                                weights=weights, actor=ACTOR, rationale="Synthetic PM emphasizes customer impact")
        require(scored["id"] != prior_score["id"], "Rescoring did not create a new priority snapshot")
        await self.mcp("score_requirement", requirement_id=charging["id"],
                       expected_version_id=charging["current_version_id"], expected_score_id=prior_score["id"],
                       weights=prior_score["weights"], actor=ACTOR, rationale="Stale score must fail", expected_error="HTTP 409")
        await self.mcp("decide_requirement", requirement_id=charging["id"], **decision_payload(charging),
                       expected_error="HTTP 409")
        charging = await self.mcp("get_requirement", requirement_id=charging["id"])
        verify_priority(charging)
        require(charging["current_version"]["score"] == scored and scored["weights"] == weights,
                "Explicit rescore was not persisted with the requested weights")
        charging, comfort = await self.approve(charging), await self.approve(comfort)
        baseline, comfort_baseline = charging["approved_version"], comfort["approved_version"]
        self.passed("PM edit and explicit rescore, stale version/score rejection, and persisted versioned approvals")

        self.stage = "unchanged-replay"
        unchanged = await self.mcp("assess_updates", **self.scope, provider="openai", actor=ACTOR)
        require(unchanged["analysis"]["cached"] and unchanged["analysis"]["id"] == pipeline["analysis"]["id"],
                "Unchanged evidence did not reuse the OpenAI analysis")
        require(not unchanged["generation"]["created"] and not unchanged["generation"]["updated"] and not unchanged["reviews"],
                "Unchanged evidence reopened an approved decision")
        self.passed("Unchanged OpenAI replay is cached and leaves approved decisions intact")

        self.stage = "updated-openai-analysis"
        payload = feedback_payload(self.vehicle, f"{self.vehicle}:charging-update",
                                   "Charging failed to start at two public stations; the clear charging progress display is helpful, "
                                   "but I need reliable session initiation before a journey.", "charging", "problem")
        imports.append(await self.import_fixture(payload, use_http=True))
        updated = await self.mcp("assess_updates", **self.scope, provider="openai", actor=ACTOR)
        evidence = await self.all_http_items("/evidence", **self.scope)
        require(len(evidence) == 4, "Updated fixture evidence count differs")
        await self.check_sources(imports, evidence)
        await self.check_analysis(updated, evidence, cached=False)
        require(updated["analysis"]["id"] != pipeline["analysis"]["id"], "New evidence reused the old analysis")
        revised = requirement_by_topic(updated, "charging")
        require(updated["generation"]["updated"] == [charging["id"]] and not updated["generation"]["created"],
                "Charging evidence revised unrelated requirement themes")
        require(revised["approved_version"] == baseline and revised["needs_review"],
                "New analysis changed the approved version or omitted PM review")
        require(revised["current_version_id"] != baseline["id"], "New evidence has no proposed requirement version")
        require(revised["current_version"]["title"] == pm_title and revised["current_version"]["acceptance_criteria"] == pm_target,
                "New AI analysis overwrote explicitly edited PM fields")
        current_comfort = requirement_by_topic(updated, "comfort")
        require(current_comfort["current_version"] == comfort_baseline and current_comfort["approved_version"] == comfort_baseline
                and not current_comfort["needs_review"], "Unrelated comfort requirement was changed or reopened")
        require(len(updated["reviews"]) == 1 and updated["reviews"][0]["requirement_id"] == charging["id"],
                "Review routing is not specific to charging")
        review = updated["reviews"][0]
        comparison = review["changes"]["against_approved"]
        require(review["reason"] and review["suggested_action"] and comparison["baseline_version_id"] == baseline["id"]
                and comparison["approved_score"] == baseline["score"] and len(comparison["added_evidence_ids"]) == 1,
                "Review does not explain the evidence change against its approved baseline")
        historical = await self.trace(charging, baseline["id"])
        require(historical["version"] == baseline and historical["evidence"]["total"] == 2
                and len(historical["decisions"]) == 1, "Approved historical source-to-decision trace changed")
        self.passed("Actual OpenAI update targets charging, preserves PM fields and approved history, and leaves comfort unchanged")

        self.stage = "review-replay-and-acceptance"
        repeat = await self.mcp("assess_updates", **self.scope, provider="openai", actor=ACTOR)
        require(repeat["analysis"]["cached"] and repeat["analysis"]["id"] == updated["analysis"]["id"]
                and not repeat["generation"]["updated"] and not repeat["generation"]["created"]
                and repeat["reviews"] == updated["reviews"]
                and requirement_by_topic(repeat, "charging")["current_version_id"] == revised["current_version_id"],
                "Repeated OpenAI update duplicated review items or requirement revisions")
        await self.mcp("decide_requirement", requirement_id=charging["id"], **decision_payload(charging),
                       expected_error="HTTP 409")
        accepted = await self.approve(revised)
        require(accepted["approved_version_id"] == revised["current_version_id"]
                and accepted["approved_version_id"] != baseline["id"], "Accepting revision did not advance approval")
        require(not await self.mcp("list_reviews", **self.scope), "Accepted review remains open")
        versions = await self.mcp("get_requirement_versions", requirement_id=charging["id"])
        require([version["version"] for version in versions] == [1, 2, 3], "Immutable requirement version history differs")
        require(next(version for version in versions if version["id"] == baseline["id"]) == baseline,
                "Historical approved requirement or score changed")
        trace = await self.trace(accepted)
        require(trace["evidence"]["total"] == 3 and len(trace["decisions"]) == 1, "Accepted revision trace is incomplete")
        events = await self.audit_events(charging["id"])
        require({event["action"] for event in events} >= {
            "requirement.version_created", "requirement.edited", "requirement.scored", "requirement.approve", "review.opened"},
            "Audit history omitted required workflow events")
        require(sum(event["action"] == "requirement.approve" for event in events) == 2,
                "Stale attempts created extra approval audit events")
        require(all(event["actor"] == ACTOR and event["rationale"] for event in events
                    if event["action"] in {"requirement.edited", "requirement.approve", "review.opened"}),
                "PM workflow audit events lack the exact actor or rationale")
        require(any(event["action"] == "requirement.scored" and event["actor"] == ACTOR
                    and event["after_state"]["id"] == scored["id"] and event["rationale"] for event in events),
                "Explicit PM rescore has no exact persisted audit event")
        workspace = await self.mcp("get_workspace", **self.scope)
        require(workspace["evidence_count"] == 4 and workspace["requirements"]["total"] == 2 and not workspace["reviews"],
                "Final PM workspace does not reflect accepted decisions")
        self.counts.update(synthetic_sources=len(imports), synthetic_evidence=len(evidence), synthetic_requirements=2,
                           charging_versions=len(versions), charging_audit_events=len(events), uncached_analyses=2,
                           cached_replays=2, discovered_mcp_tools=len(definitions))
        self.passed("Cached review replay, explicit revision acceptance, immutable decisions, complete audit history, and PM workspace")
        self.stage = "complete"

    async def platform_ai_run(self, label: str, run_id: str) -> None:
        run = await self.http("GET", f"/runs/{run_id}")
        require((run["vehicle"], run["status"]) == (self.vehicle, "succeeded"), f"{label} run crossed scope or failed")
        self.llm_runs[label] = {key: value for key, value in llm_usage(run, label, self.expected_model).items()
                                if key != "run_id"}

    async def run_platform(self) -> None:
        """One small OpenAI call per platform AI capability, in this verifier's LIVE-AI scope."""
        self.stage = "platform-sentiment"
        scored = await self.http("POST", "/signals/sentiment/score", json={
            **self.scope, "provider": "openai", "subject_type": "evidence", "actor": ACTOR})
        require(scored["created"] == 4 and not scored["remaining"]
                and scored["method_version"] == f"openai:{self.expected_model}:aspect-sentiment-v1",
                "OpenAI sentiment did not score every fixture record with the expected model")
        await self.platform_ai_run("signals.score_sentiment", scored["run_id"])
        self.stage = "platform-request-classification"
        request = await self.http("POST", "/requests", expected_status=201, json={
            **self.scope, "origin_type": "dealer", "origin_name": "Simulated dealer", "simulated": True,
            "external_ref": f"{self.vehicle}:charging-request", "title": "Reliable public charging start",
            "body": "Simulated: customers ask that public charging sessions start reliably on the first attempt.",
            "actor": ACTOR})
        classified = await self.http("POST", "/requests/classify", expected_status=201, json={
            "vehicle": self.vehicle, "request_ids": [request["id"]], "provider": "openai", "actor": ACTOR})
        require(classified["model"] == self.expected_model and classified["items"][0]["simulated"],
                "OpenAI request classification used another model or lost the simulated label")
        await self.platform_ai_run("requests.classify", classified["run_id"])
        self.stage = "platform-market-directions"
        directions = await self.http("POST", "/markets/directions", json={
            "vehicle": self.vehicle, "markets": ["US", "CN"], "provider": "openai", "actor": ACTOR})
        await self.platform_ai_run("markets.extract_directions", directions["run_id"])
        self.stage = "platform-priority-explanation"
        explained = await self.http("POST", "/priorities/explain", expected_status=201,
                                    json={**self.scope, "provider": "openai", "actor": ACTOR})
        require(explained["ai_generated"] and explained["model"] == self.expected_model and len(explained["items"]) == 2
                and all(item["score_id"] in item["cited_ids"] for item in explained["items"]),
                "OpenAI priority explanation is incomplete or does not cite the recorded scores")
        await self.platform_ai_run("priorities.explain", explained["run_id"])
        self.counts.update(platform_llm_usage=self.llm_runs,
                           platform_llm_total_tokens=sum(item["total_tokens"] for item in self.llm_runs.values()))
        self.passed("Platform OpenAI capabilities: sentiment, request classification, market directions and priority "
                    "explanation record model, prompt version and token usage")
        self.stage = "complete"

    def report(self, status: str, elapsed: float, error: str | None = None) -> dict:
        result = super().report(status, elapsed)
        for key in ("platform_vehicle", "platform_markets", "platform_label"):
            result.pop(key, None)   # this verifier's platform calls run in its own LIVE-AI scope
        result.update(provider="openai", expected_model=self.expected_model, stage=self.stage,
                      verification_scope="Synthetic provider integration and workflow invariants; not general AI semantic quality")
        if error:
            # Do not echo API bodies, exception strings, source text, or credentials.
            result["error_type"] = error
        return result


@asynccontextmanager
async def connect_live(api_url: str, mcp_url: str, expected_model: str):
    async with httpx.AsyncClient(base_url=api_url.rstrip("/"), timeout=180, follow_redirects=False) as api:
        async with streamable_http_client(mcp_url) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=180) as session:
                await session.initialize()
                yield OpenAIVerification(api, session, expected_model=expected_model)


async def main_async(args) -> int:
    started = time.perf_counter()
    verification = None
    try:
        async with connect_live(args.api_url, args.mcp_url, args.expected_model) as verification:
            await verification.run()
            if getattr(args, "platform", False):
                await verification.run_platform()
        report = verification.report("passed", time.perf_counter() - started)
    except Exception as exc:
        report = (verification.report("failed", time.perf_counter() - started, type(exc).__name__) if verification else
                  {"status": "failed", "provider": "openai", "expected_model": args.expected_model,
                   "stage": "connect", "checks_passed": 0, "error_type": type(exc).__name__,
                   "elapsed_seconds": round(time.perf_counter() - started, 3)})
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--mcp-url", default="http://127.0.0.1:8001/mcp")
    parser.add_argument("--expected-model", default="gpt-6.1-sol")
    parser.add_argument("--platform", action="store_true",
                        help="Also make one OpenAI call per platform AI capability (sentiment, request classification, "
                             "market directions, priority explanation)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
