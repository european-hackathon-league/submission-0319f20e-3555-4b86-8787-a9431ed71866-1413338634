"""Repeatable labeled workflow evaluation in a temporary database. No credentials required."""

import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from server.main import app  # noqa: E402


def evaluate():
    previous_db = os.environ.get("DB_PATH")
    try:
        with TemporaryDirectory(prefix="bmw-evaluation-") as directory:
            os.environ["DB_PATH"] = str(Path(directory) / "evaluation.db")
            with TestClient(app) as client:
                return evaluate_client(client)
    finally:
        if previous_db is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = previous_db


def classify_change(expected, predicted, eligible):
    """Compare human-authored labels with newly raised review alerts."""
    return {"true_positive": len(predicted & expected), "false_positive": len(predicted - expected),
            "false_negative": len(expected - predicted), "true_negative": len(eligible - expected - predicted)}


def evaluate_client(client):
    vehicle = "EVAL-" + uuid4().hex[:10].upper()
    market = "US"

    def request(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def ingest(reference, content, topic, sentiment, evidence_market=market):
        return request("POST", "/imports/records", json={"vehicle": vehicle, "market": evidence_market, "title": reference,
            "reference": reference, "records": [{"content": content, "location": {"row": 2},
             "metadata": {"topic": topic, "sentiment": sentiment, "provenance": reference}}]})

    scope = {"vehicle": vehicle, "market": market}
    ingest("labeled-charging", "Public charging is confusing", "charging", "problem")
    ingest("labeled-comfort", "I love the comfortable seats", "comfort", "strength")
    started = perf_counter()
    initial = request("POST", "/pipeline/run", json={**scope, "provider": "deterministic"})
    elapsed = perf_counter() - started
    requirements = initial["generation"]["requirements"]
    if {r["topic"] for r in requirements} != {"charging", "comfort"}:
        raise RuntimeError("Evaluation baseline must contain the two labeled approved themes")
    for requirement in requirements:
        version = requirement["current_version"]
        request("POST", f"/requirements/{requirement['id']}/decisions", json={"version_id": version["id"],
            "score_id": version["score"]["id"], "action": "approve", "actor": "Synthetic evaluator", "rationale": "Labeled workflow fixture"})

    eligible = {r["id"] for r in requirements}
    topic_ids = {r["topic"]: r["id"] for r in requirements}
    scenarios = []
    for name, update, expected_topics in [
        ("unchanged_baseline", None, set()),
        ("unrelated_new_theme", ("labeled-design", "Exterior design looks beautiful", "design", "strength"), set()),
        ("contrasting_charging_evidence", ("labeled-charging-positive", "Public charging is easy", "charging", "strength"), {"charging"}),
        ("identical_replay_with_pending_review", None, set()),
        ("duplicate_import", ("labeled-charging-positive", "Public charging is easy", "charging", "strength"), set()),
        ("additional_charging_support", ("labeled-charging-more", "Public charging is hard to understand", "charging", "problem"), {"charging"}),
        ("other_market_evidence", ("labeled-charging-de", "Public charging is confusing", "charging", "problem", "DE"), set()),
        ("additional_comfort_support", ("labeled-comfort-more", "I enjoy the comfortable seats", "comfort", "strength"), {"comfort"}),
    ]:
        before = {review["id"] for review in request("GET", "/reviews", params=scope)}
        if update:
            ingest(*update)
        result = request("POST", "/updates", json={**scope, "provider": "deterministic"})
        actual = {review["requirement_id"] for review in result["reviews"] if review["id"] not in before}
        expected = {topic_ids[topic] for topic in expected_topics}
        id_topics = {r["id"]: r["topic"] for r in result["generation"]["requirements"]}
        scenarios.append({"name": name, "expected_topics": sorted(expected_topics),
                          "predicted_topics": sorted(id_topics.get(rid, rid) for rid in actual),
                          "expected_affected": len(expected), "predicted_affected": len(actual),
                          **classify_change(expected, actual, eligible)})
    metrics = request("GET", "/metrics", params=scope)
    tp, fp, fn, tn = (sum(row[key] for row in scenarios) for key in
                      ("true_positive", "false_positive", "false_negative", "true_negative"))
    return {"evaluation": "Synthetic labeled reference-provider workflow; not a model quality benchmark",
            "passed": fp == fn == 0 and metrics["traceability"]["coverage"] == 1,
            "provider": "deterministic", "initial_pipeline_seconds": round(elapsed, 4), "scenarios": scenarios,
            "change_detection": {"unit": "new PM review alerts for an existing approved requirement per update",
                                 "scenario_count": len(scenarios), "approved_requirements": len(eligible),
                                 "precision": tp / (tp + fp) if tp + fp else None,
                                 "recall": tp / (tp + fn) if tp + fn else None,
                                 "true_positive": tp, "false_positive": fp, "false_negative": fn, "true_negative": tn},
            "traceability": metrics["traceability"], "decision_time": metrics["time_to_first_decision_seconds"],
            "limitations": ["Eight authored scenarios and two approved themes are a regression fixture, not a representative statistical sample or confidence estimate.",
                            "Topic/sentiment metadata labels are supplied to the reference provider; this does not evaluate AI extraction or semantic classification accuracy.",
                            "A replay with an already open review is negative for new alerts; it does not require clearing the pending review.",
                            "Fixtures have known expected affected themes. These results do not establish performance on unseen customer data.",
                            "Semantic correctness and usefulness still require independent PM review of original evidence and criteria."]}


if __name__ == "__main__":
    report = evaluate()
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
