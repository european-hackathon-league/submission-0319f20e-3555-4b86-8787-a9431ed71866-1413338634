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


def evaluate_client(client):
    vehicle = "EVAL-" + uuid4().hex[:10].upper()
    market = "US"

    def request(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def ingest(reference, content, topic, sentiment):
        return request("POST", "/imports/records", json={"vehicle": vehicle, "market": market, "title": reference,
            "reference": reference, "records": [{"content": content, "location": {"row": 2},
             "metadata": {"topic": topic, "sentiment": sentiment, "provenance": reference}}]})

    scope = {"vehicle": vehicle, "market": market}
    ingest("labeled-charging", "Public charging is confusing", "charging", "problem")
    ingest("labeled-comfort", "I love the comfortable seats", "comfort", "strength")
    started = perf_counter()
    initial = request("POST", "/pipeline/run", json=scope)
    elapsed = perf_counter() - started
    requirements = initial["generation"]["requirements"]
    assert {r["topic"] for r in requirements} == {"charging", "comfort"}
    for requirement in requirements:
        version = requirement["current_version"]
        request("POST", f"/requirements/{requirement['id']}/decisions", json={"version_id": version["id"],
            "score_id": version["score"]["id"], "action": "approve", "actor": "Synthetic evaluator", "rationale": "Labeled workflow fixture"})

    charging_id = next(r["id"] for r in requirements if r["topic"] == "charging")
    scenarios = []
    for name, update, expected in [
        ("unrelated_new_theme", ("labeled-design", "Exterior design looks beautiful", "design", "strength"), set()),
        ("contrasting_charging_evidence", ("labeled-charging-positive", "Public charging is easy", "charging", "strength"), {charging_id}),
        ("identical_replay", None, set()),
    ]:
        if update:
            ingest(*update)
        result = request("POST", "/updates", json=scope)
        actual = set(result["generation"]["updated"])
        tp, fp, fn = len(actual & expected), len(actual - expected), len(expected - actual)
        scenarios.append({"name": name, "expected_affected": len(expected), "predicted_affected": len(actual),
                          "true_positive": tp, "false_positive": fp, "false_negative": fn})
        assert actual == expected, f"Incorrect change assessment for {name}"
    metrics = request("GET", "/metrics", params=scope)
    tp, fp, fn = (sum(row[key] for row in scenarios) for key in ("true_positive", "false_positive", "false_negative"))
    assert metrics["traceability"]["coverage"] == 1
    return {"evaluation": "Synthetic labeled reference-provider workflow; not a model quality benchmark",
            "provider": "deterministic", "initial_pipeline_seconds": round(elapsed, 4), "scenarios": scenarios,
            "change_detection": {"precision": tp / (tp + fp) if tp + fp else None,
                                 "recall": tp / (tp + fn) if tp + fn else None,
                                 "false_positive": fp, "false_negative": fn},
            "traceability": metrics["traceability"], "decision_time": metrics["time_to_first_decision_seconds"],
            "limitations": ["Fixtures have known expected affected themes. These results do not establish performance on unseen customer data.",
                            "Semantic correctness and usefulness still require independent PM review of original evidence and criteria."]}


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
