from scripts.evaluate_pipeline import evaluate_client


def test_labeled_change_evaluation_and_decision_metrics(client):
    report = evaluate_client(client)
    assert report["change_detection"] == {"precision": 1, "recall": 1, "false_positive": 0, "false_negative": 0}
    assert report["traceability"]["coverage"] == 1
    assert report["decision_time"]["sample_count"] == 2


def test_empty_scope_metrics_are_explicit(client):
    report = client.get("/metrics").json()
    assert report["traceability"]["coverage"] is None
    assert report["time_to_first_decision_seconds"] == {"sample_count": 0, "median": None}
