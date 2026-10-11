"""Run the multi-source evidence pipeline for one vehicle and market against a running API.

    uv run python scripts/run_multisource_pipeline.py --api-url http://127.0.0.1:8000 --vehicle G60 --market US

Steps, each a recorded run with audit events in the API's database:

1. BMW files: every supplied workbook and PDF (feedback, customer studies, sales volumes, option lists),
   then sales-share market weights, the preserve list and coverage warnings.
2. NHTSA: new owner complaints and safety recalls for the vehicle's public US models.
3. Public web research: owner forums and press reviews per topic (OpenAI web search; skipped with a
   warning when the provider is not configured, unless --require-web).
4. Analysis: the initial pipeline when the scope has no requirements yet, otherwise a cumulative update
   that proposes revisions for PM review. Approved versions stay untouched.
5. Sentiment and derived priority inputs (market demand, sentiment momentum, request pressure).

The script never decides anything: switching the scope to rubric v2 and approving requirements remain PM
actions in the workspace. Output is counts and the source mix, never verbatims.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

ACTOR = "system:multi-source-pipeline"


def call(base: str, method: str, path: str, payload: dict | None = None, timeout: int = 900) -> tuple[int, dict]:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(base.rstrip("/") + path, data=body, method=method,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.load(exc)
        except ValueError:
            detail = {"detail": exc.reason}
        return exc.code, detail


def step(name: str, status: int, result: dict, ok=(200, 201)) -> dict:
    if status not in ok:
        raise RuntimeError(f"{name}: HTTP {status}: {json.dumps(result.get('detail', result))[:600]}")
    return result


def run(args) -> dict:
    base, scope, report = args.api_url, {"vehicle": args.vehicle.upper(), "market": args.market.upper()}, {}
    started = time.monotonic()

    if not args.skip_bmw:
        result = step("BMW files", *call(base, "POST", "/market-data/import-bmw", {"actor": ACTOR}))
        report["bmw_files"] = result.get("totals")
        step("Market weights", *call(base, "POST", "/market-data/weights/derive", {"actor": ACTOR}))
        step("Preserve list", *call(base, "POST", "/market-data/preserve/derive",
                                    {"vehicle": scope["vehicle"], "provider": "deterministic", "actor": ACTOR}))
        step("Coverage", *call(base, "POST", "/market-data/coverage", {"vehicle": scope["vehicle"], "actor": ACTOR}))
        print(f"BMW files imported: {report['bmw_files']}")

    status, result = call(base, "POST", "/public-sources/nhtsa/import", {**scope, "actor": ACTOR})
    if status == 422:
        report["nhtsa"] = {"skipped": result.get("detail")}
        print(f"NHTSA skipped: {result.get('detail')}")
    else:
        result = step("NHTSA", status, result)
        report["nhtsa"] = {key: result[key] for key in ("models", "complaints_found", "recalls_found",
                                                         "new_complaints", "new_recalls", "warnings")}
        print(f"NHTSA: {result['new_complaints']} new complaints, {result['new_recalls']} new recalls "
              f"({len(result['models'])} model-years)")

    payload = {**scope, "actor": ACTOR, "max_per_topic": args.max_per_topic}
    if args.topics:
        payload["topics"] = args.topics
    status, result = call(base, "POST", "/public-sources/web-research/import", payload)
    if status == 503 and not args.require_web:
        report["web_research"] = {"skipped": result.get("detail")}
        print(f"Web research skipped: {result.get('detail')}")
    else:
        result = step("Web research", status, result)
        report["web_research"] = {"imported": result["imported"], "rejected": len(result["rejected"]),
                                  "per_topic": result["per_topic"], "model": result["model"]}
        print(f"Web research: {result['imported']} grounded pages imported, {len(result['rejected'])} rejected")

    requirements = step("Requirements", *call(base, "GET", f"/requirements?vehicle={scope['vehicle']}"
                                                          f"&market={scope['market']}&limit=1"))
    analysis = {**scope, "provider": args.provider, "actor": ACTOR}
    if requirements.get("total", len(requirements.get("items", []))):
        result = step("Update", *call(base, "POST", "/updates", analysis))
        generation = result["generation"]
        report["analysis"] = {"mode": "update", "updated": len(generation["updated"]),
                              "created": len(generation["created"]), "open_reviews": len(result.get("reviews", []))}
    else:
        result = step("Pipeline", *call(base, "POST", "/pipeline/run", analysis))
        generation = result["generation"]
        report["analysis"] = {"mode": "initial", "created": len(generation["created"])}
    print(f"Analysis ({report['analysis']['mode']}, {args.provider}): {report['analysis']}")

    created = 0
    while True:
        result = step("Sentiment", *call(base, "POST", "/signals/sentiment/score",
                                         {**scope, "provider": "deterministic", "subject_type": "evidence",
                                          "actor": ACTOR}))
        created += result["created"]
        if not result["remaining"]:
            break
    result = step("Priority inputs", *call(base, "POST", "/priorities/inputs/derive", {**scope, "actor": ACTOR}))
    report["priority_inputs"] = {"written": result.get("written"), "rubric": result.get("rubric_version"),
                                 "sentiment_scored": created}
    mix = step("Source mix", *call(base, "GET", f"/public-sources/mix?vehicle={scope['vehicle']}&market={scope['market']}"))
    report["source_mix"] = {"by_origin": mix["by_origin"], "totals": mix["totals"]}
    report["seconds"] = round(time.monotonic() - started, 1)
    return report | {"sources": mix["sources"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--vehicle", default="G60")
    parser.add_argument("--market", default="US")
    parser.add_argument("--provider", choices=("deterministic", "openai"), default="deterministic",
                        help="Analysis provider for findings and requirements")
    parser.add_argument("--topics", nargs="+", help="Web research topics (default: the connector's list)")
    parser.add_argument("--max-per-topic", type=int, default=5)
    parser.add_argument("--skip-bmw", action="store_true", help="BMW files are already imported")
    parser.add_argument("--require-web", action="store_true", help="Fail when web research is unavailable")
    parser.add_argument("--json", action="store_true", help="Print the full report as JSON")
    args = parser.parse_args()
    try:
        report = run(args)
    except RuntimeError as exc:
        sys.exit(str(exc))
    if args.json:
        print(json.dumps(report, indent=2))
        return
    print("\n| Origin | Role | Source | Records | Dated | Observed | Linked requirements |")
    print("| --- | --- | --- | ---: | ---: | --- | ---: |")
    for source in report["sources"]:
        observed = f"{source['first_observed']} – {source['last_observed']}" if source["first_observed"] else "undated"
        print(f"| {source['origin']} | {source['role']} | {source['title']} | {source['records']} | "
              f"{source['dated_records']} | {observed} | {source['linked_requirements']} |")
    totals = report["source_mix"]["totals"]
    print(f"\n{totals['sources']} sources, {totals['records']} records; {totals['requirements_with_public_evidence']} of "
          f"{totals['requirements']} requirements cite public evidence. {report['seconds']} s.")


if __name__ == "__main__":
    main()
