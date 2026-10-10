"""Exercise durable initial/update planning through real HTTP and Streamable HTTP MCP.

Uses a fresh, explicitly synthetic vehicle; never approves real G60 requirements.
--provider openai exercises the configured live model without a fallback.
"""

import argparse
import asyncio
import json
import sys
import uuid

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from scripts.verify_backend import decode_tool_result, feedback_payload, require


async def verify(api_url, mcp_url, provider):
    vehicle = "PM-E2E-" + uuid.uuid4().hex[:12].upper()
    scope = {"vehicle": vehicle, "market": "US"}
    actor = "PM workflow verifier"
    checks = []
    async with httpx.AsyncClient(base_url=api_url, timeout=300) as api:
        async with streamable_http_client(mcp_url) as streams:
            async with ClientSession(streams[0], streams[1], read_timeout_seconds=300) as session:
                await session.initialize()

                async def call(name, **args):
                    return decode_tool_result(await session.call_tool(name, args))

                async def request(method, path, **kwargs):
                    response = await api.request(method, path, **kwargs)
                    require(response.is_success, f"{path}: HTTP {response.status_code}: {response.text[:500]}")
                    return response.json()

                async def start(kind):
                    workflow = await call("create_pm_workflow", **scope, kind=kind, provider=provider, actor=actor,
                                          request_key=f"{vehicle}:{kind}")
                    replay = await call("create_pm_workflow", **scope, kind=kind, provider=provider, actor=actor,
                                        request_key=f"{vehicle}:{kind}")
                    require(replay["id"] == workflow["id"], "Request replay created a second run")
                    if kind == "initial":
                        workflow = await call("run_pm_workflow", workflow_id=workflow["id"],
                                              expected_revision=workflow["revision"], actor=actor)
                    else:
                        workflow = await request("POST", f"/workflows/{workflow['id']}/run", json={
                            "expected_revision": workflow["revision"], "actor": actor})
                    require(workflow["status"] == "awaiting_review", f"Autonomous stages failed: {workflow.get('error')}")
                    analysis = await call("get_analysis", run_id=workflow["analysis_id"])
                    require(analysis["provider"] == provider, "Workflow provider did not match requested provider")
                    require(set(analysis["evidence_ids"]) == set(workflow["evidence_ids"]), "Workflow input trace differs")
                    return workflow

                async def approve_all(workflow):
                    brief = await call("get_pm_workflow_brief", workflow_id=workflow["id"])
                    for item in brief["requirements"]:
                        version = item["version"]
                        await call("decide_requirement", requirement_id=item["requirement_id"], version_id=version["id"],
                                   score_id=item["score"]["id"], actor=actor, action="approve",
                                   rationale="Synthetic PM reviewed exact evidence and acceptance assumptions")
                    return await call("complete_pm_workflow", workflow_id=workflow["id"],
                                      expected_revision=workflow["revision"], actor=actor,
                                      rationale="Synthetic planning review complete")

                for label, content, topic, sentiment in [
                    ("charging", "Public charging often fails to start; I need reliable charging session initiation.", "charging", "problem"),
                    ("comfort", "I love the comfortable seats during long journeys and want that comfort preserved.", "comfort", "strength"),
                ]:
                    payload = feedback_payload(vehicle, f"{vehicle}:{label}", content, topic, sentiment)
                    await call("import_records", **payload)
                initial = await start("initial")
                initial_brief = await call("get_pm_workflow_brief", workflow_id=initial["id"])
                require(initial_brief["summary"]["requirement_count"] >= 2, "Expected customer requirements missing")
                require(initial_brief["summary"]["approved_count"] == 0, "Agent implicitly approved requirements")
                for item in initial_brief["requirements"]:
                    require(item["evidence"] and all(e["location"] for e in item["evidence"]), "Exact source trace missing")
                    trace = await request("GET", item["trace_url"])
                    require(trace["version"]["id"] == item["version"]["id"], "Brief trace points at wrong version")
                    require(trace["version"]["score"]["id"] == item["score"]["id"], "Brief trace points at wrong score")
                blocked = await api.post(f"/workflows/{initial['id']}/complete", json={
                    "expected_revision": initial["revision"], "actor": actor, "rationale": "Must not bypass review"})
                require(blocked.status_code == 409, "Undecided requirements bypassed human review")
                checks.append("Idempotent creation, persisted autonomous stages, exact source traces, mandatory PM gate")
                charging = next(item for item in initial_brief["requirements"] if item["topic"] == "charging")
                edited = await call("edit_requirement", requirement_id=charging["requirement_id"],
                                    expected_version_id=charging["version"]["id"], actor=actor,
                                    rationale="Synthetic PM clarifies customer outcome", title="Customers start charging reliably")
                require(edited["current_version_id"] != charging["version"]["id"], "PM edit did not version")
                live = await call("get_pm_workflow_brief", workflow_id=initial["id"])
                edited_item = next(item for item in live["requirements"]
                                   if item["requirement_id"] == charging["requirement_id"])
                require(edited_item["version"]["id"] == edited["current_version_id"],
                        "Live brief omitted PM edit")
                require(edited_item["decision"] is None, "Live brief reused a stale PM decision")
                completed = await approve_all(initial)
                require(completed["status"] == "completed", "Planning did not complete")
                frozen = await call("get_pm_workflow_brief", workflow_id=initial["id"])
                require(frozen["snapshot"] == "completed", "Brief is not frozen")
                baseline = {item["requirement_id"]: item["version"]["id"] for item in frozen["requirements"]}
                markdown = await api.get(f"/workflows/{initial['id']}/brief", params={"format": "markdown"})
                require(markdown.is_success and "attachment" in markdown.headers.get("content-disposition", ""),
                        "Brief export missing")
                require(all(item["key"] in markdown.text for item in frozen["requirements"]), "Export omitted requirements")
                checks.append("PM edit, current version/score approval, frozen documented brief and Markdown export")
                payload = feedback_payload(vehicle, f"{vehicle}:update", "I love the easy public charging; session initiation is now reliable.",
                                           "charging", "strength")
                await request("POST", "/imports/records", json=payload)
                update = await start("update")
                brief = await call("get_pm_workflow_brief", workflow_id=update["id"])
                changed = next(item for item in brief["requirements"] if item["topic"] == "charging")
                require(changed["version"]["id"] != baseline[changed["requirement_id"]], "Changed evidence produced no revision")
                require(changed["approved_baseline"]["id"] == baseline[changed["requirement_id"]], "Approved baseline was overwritten")
                require(changed["version"]["title"] == "Customers start charging reliably", "Workflow discarded PM edit")
                require(await call("get_pm_workflow_brief", workflow_id=initial["id"]) == frozen, "Later update rewrote completed brief")
                denied = await api.post(f"/workflows/{update['id']}/complete", json={
                    "expected_revision": update["revision"], "actor": "ai:reference:v1", "rationale": "Must not bypass PM"})
                require(denied.status_code == 403, "AI completed human gate")
                await approve_all(update)
                events = await call("list_audit", entity_id=update["id"], limit=1000)
                require(any(item["action"] == "workflow.completed" for item in events["items"]), "Completion audit missing")
                require(await call("get_pm_workflow_brief", workflow_id=initial["id"]) == frozen, "Later decisions rewrote brief")
                historical_markdown = await api.get(f"/workflows/{initial['id']}/brief", params={"format": "markdown"})
                require(historical_markdown.is_success and historical_markdown.text == markdown.text,
                        "Later evidence, versions or decisions rewrote completed Markdown")
                checks.append("Cumulative update, preserved PM edit and approved baseline, AI denial, audit and historical JSON/Markdown")
                return {"status": "passed", "vehicle": vehicle, "provider": provider, "checks": checks,
                        "workflow_ids": [initial["id"], update["id"]]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:18000")
    parser.add_argument("--mcp-url", default="http://127.0.0.1:18001/mcp")
    parser.add_argument("--provider", choices=["deterministic", "openai"], default="deterministic")
    args = parser.parse_args()
    try:
        report = asyncio.run(verify(args.api_url, args.mcp_url, args.provider))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
