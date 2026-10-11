"""Import every BMW input and derive market weights, preserve attributes and coverage (Pod E).

Runs in-process against DB_PATH (default: the repository's database) with BMW files from DATA_DIR, through
the same registered capabilities as POST /market-data/*, so every step is a recorded run with audit events.
Re-running is idempotent. Output is counts only, never verbatims:

    DATA_DIR=/path/to/data DB_PATH=database/local/app.db uv run python scripts/import_bmw_data.py --markdown

--provider openai names preserve attributes through the configured OpenAI provider (OPENAI_API_KEY,
OPENAI_MODEL) and fails clearly when it is not configured; deterministic is the labelled offline baseline.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run(directory: str, provider: str, actor: str, vehicles: list[str] | None) -> dict:
    from database.store import init_database
    from server import market_data
    from server.platform import run_capability

    init_database()
    steps = {"import": run_capability("market_data.import_bmw", {"directory": directory}, actor)["outputs"]}
    steps["weights"] = run_capability("market_data.derive_weights", {}, actor)["outputs"]
    scopes = market_data.list_scopes()["items"]
    customer = sorted({s["vehicle"] for s in scopes
                       if {"customer_feedback", "study_aggregate"} & set(s["by_record_type"])})
    selected = [v.upper() for v in vehicles] if vehicles else sorted({s["vehicle"] for s in scopes})
    steps["preserve"], steps["coverage"] = {}, {}
    for vehicle in selected:
        if vehicle in customer:
            steps["preserve"][vehicle] = run_capability("market_data.derive_preserve",
                                                        {"vehicle": vehicle, "provider": provider}, actor)["outputs"]
        steps["coverage"][vehicle] = run_capability("market_data.coverage", {"vehicle": vehicle}, actor)["outputs"]
    return {"steps": steps, "scopes": [s for s in scopes if s["vehicle"] in selected]}


def summary(result: dict) -> dict:
    steps = result["steps"]
    return {"import": steps["import"]["totals"], "weights": steps["weights"]["changes"],
            "weight_warnings": sorted({w["code"] for w in steps["weights"]["warnings"]}),
            "preserve": {v: {"changes": o["changes"], "items": len(o["items"]), "provider": o["provider"]}
                         for v, o in steps["preserve"].items()},
            "coverage": {v: o["changes"] for v, o in steps["coverage"].items()}}


def markdown(result: dict, period: str) -> str:
    steps = result["steps"]
    weights = {(w["vehicle"], w["market"]): w["share"] for w in steps["weights"]["items"] if w["period"] == period}
    preserve = defaultdict(int)
    for output in steps["preserve"].values():
        for item in output["items"]:
            preserve[item["vehicle"], item["market"]] += 1
    warnings = {(r["vehicle"], r["market"]): [w["code"] for w in r["warnings"]]
                for output in steps["coverage"].values() for r in output["items"]}
    lines = [f"| Vehicle | Market | Region | Sources | Evidence | Feedback rows | Feedback IDs | Study cells | "
             f"Sales rows | Document pages | Share {period} | Preserve | Coverage warnings |",
             "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    keys = sorted({(s["vehicle"], s["market"]) for s in result["scopes"]} | set(warnings))
    scopes = {(s["vehicle"], s["market"]): s for s in result["scopes"]}
    for key in keys:
        scope = scopes.get(key, {"sales_region": "", "sources": 0, "evidence_total": 0, "by_record_type": {},
                                 "unique_feedback_ids": 0})
        types = scope["by_record_type"]
        share = weights.get(key)
        lines.append("| " + " | ".join(str(value) for value in (
            *key, scope["sales_region"] or "", scope["sources"], scope["evidence_total"],
            types.get("customer_feedback", 0), scope["unique_feedback_ids"], types.get("study_aggregate", 0),
            types.get("sales_aggregate", 0), types.get("document_context", 0),
            "" if share is None else f"{share:.1%}", preserve.get(key, 0),
            ", ".join(warnings.get(key, [])) or "–")) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", help="Directory containing BMW-Data/ (default: DATA_DIR or ./data)")
    parser.add_argument("--db", help="SQLite database path (default: DB_PATH)")
    parser.add_argument("--directory", default="BMW-Data", help="Folder inside the data directory")
    parser.add_argument("--provider", choices=("deterministic", "openai"), default="deterministic",
                        help="Preserve-attribute naming provider")
    parser.add_argument("--vehicle", action="append", help="Derive preserve/coverage only for these vehicles")
    parser.add_argument("--actor", default="system:bmw-import")
    parser.add_argument("--markdown", action="store_true", help="Print a counts table per vehicle × market")
    parser.add_argument("--period", default="2025", help="Sales period shown in the markdown table")
    args = parser.parse_args()
    if args.data_dir:
        os.environ["DATA_DIR"] = str(Path(args.data_dir).resolve())
    if args.db:
        os.environ["DB_PATH"] = str(Path(args.db).resolve())
    result = run(args.directory, args.provider, args.actor, args.vehicle)
    print(markdown(result, args.period) if args.markdown else json.dumps(summary(result), indent=2))


if __name__ == "__main__":
    main()
