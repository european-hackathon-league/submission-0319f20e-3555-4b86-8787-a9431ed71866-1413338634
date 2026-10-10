from pathlib import Path

import httpx
import pytest

from scripts.evaluate_pipeline import evaluate, evaluate_client


def test_labeled_change_evaluation_and_decision_metrics(client):
    report = evaluate_client(client)
    assert report["passed"]
    assert report["change_detection"] == {
        "unit": "new PM review alerts for an existing approved requirement per update",
        "scenario_count": 8, "approved_requirements": 2, "precision": 1, "recall": 1,
        "true_positive": 3, "false_positive": 0, "false_negative": 0, "true_negative": 13,
    }
    assert report["traceability"]["coverage"] == 1
    assert report["decision_time"]["sample_count"] == 2


def test_empty_scope_metrics_are_explicit(client):
    report = client.get("/metrics").json()
    assert report["traceability"]["coverage"] is None
    assert report["time_to_first_decision_seconds"] == {"sample_count": 0, "median": None}


@pytest.mark.parametrize("scope", [{"vehicle": ""}, {"market": " "}, {"vehicle": "x" * 51}, {"market": "x" * 51}])
def test_metrics_rejects_invalid_scope(client, scope):
    assert client.get("/metrics", params=scope).status_code == 422


def test_evaluation_reports_wrong_alerts_instead_of_aborting(client):
    class WrongAlertClient:
        def request(self, method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if path == "/updates":
                body = response.json()
                # Simulate both missed relevant alerts and a fresh incorrect alert
                # on the unchanged comfort decision on every update.
                comfort_id = next(r["id"] for r in body["generation"]["requirements"] if r["topic"] == "comfort")
                body["reviews"] = [{"id": "incorrect-alert", "requirement_id": comfort_id}]
                return httpx.Response(response.status_code, json=body, request=response.request)
            return response

    report = evaluate_client(WrongAlertClient())
    assert not report["passed"]
    assert report["change_detection"]["false_positive"] == 7
    assert report["change_detection"]["false_negative"] == 2
    assert report["change_detection"]["precision"] == 1 / 8
    assert report["change_detection"]["recall"] == 1 / 3


def test_evaluation_isolates_database_originals_and_restores_environment(tmp_path, monkeypatch):
    untouched = tmp_path / "existing.db"
    untouched.write_bytes(b"Existing application database must not be opened")
    monkeypatch.setenv("DB_PATH", str(untouched))
    monkeypatch.setenv("OPENAI_API_KEY", "unused")
    monkeypatch.setenv("OPENAI_MODEL", "unused")
    report = evaluate()
    assert report["provider"] == "deterministic"
    assert untouched.read_bytes() == b"Existing application database must not be opened"
    assert list(tmp_path.iterdir()) == [untouched]
    from database.store import database_path

    assert database_path() == Path(untouched)


def test_decision_metrics_count_first_action_per_decided_version(client, monkeypatch):
    client.post("/imports/records", json={"title": "Metrics evidence", "reference": "metrics", "records": [
        {"content": "Public charging is confusing", "location": {"row": 2},
         "metadata": {"topic": "charging", "sentiment": "problem"}},
        {"content": "I love the comfortable seats", "location": {"row": 3},
         "metadata": {"topic": "comfort", "sentiment": "strength"}},
    ]}).raise_for_status()
    monkeypatch.setattr("server.requirements.now", lambda: "2026-01-01T00:00:00+00:00")
    result = client.post("/pipeline/run", json={}).json()
    charging = next(r for r in result["generation"]["requirements"] if r["topic"] == "charging")

    def decide(requirement, action, second):
        monkeypatch.setattr("server.requirements.now", lambda: f"2026-01-01T00:00:{second:02}+00:00")
        version = requirement["current_version"]
        response = client.post(f"/requirements/{requirement['id']}/decisions", json={
            "version_id": version["id"], "score_id": version["score"]["id"],
            "action": action, "actor": "PM", "rationale": "Metrics fixture",
        })
        response.raise_for_status()

    decide(charging, "postpone", 10)
    decide(charging, "approve", 18)
    monkeypatch.setattr("server.requirements.now", lambda: "2026-01-01T00:00:20+00:00")
    edited = client.patch(f"/requirements/{charging['id']}", json={
        "expected_version_id": charging["current_version_id"], "actor": "PM", "rationale": "Metrics fixture",
        "title": "Updated charging requirement",
    })
    edited.raise_for_status()
    decide(edited.json(), "approve", 35)
    report = client.get("/metrics", params={"vehicle": "g60", "market": "USA"}).json()
    assert report["scope"] == {"vehicle": "G60", "market": "US"}
    assert report["counts"]["requirements"] == 2
    assert report["counts"]["decisions"] == 3
    assert report["time_to_first_decision_seconds"] == {"sample_count": 2, "median": 12.5}
