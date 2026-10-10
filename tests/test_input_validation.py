import json

import pytest


@pytest.mark.parametrize("path,payload", [
    ("/analyses", {"actor": "bad\ud800"}),
    ("/requirements/generate", {"run_id": "bad\ud800"}),
    ("/requirements/unknown/decisions", {"version_id": "v", "score_id": "s", "action": "approve", "actor": "bad\ud800", "rationale": "test"}),
    ("/requirements/unknown/scores", {"expected_version_id": "v", "actor": "PM", "rationale": "test", "weights": {"customer_impact": float("nan")}}),
])
def test_invalid_json_values_are_clean_validation_errors(client, path, payload):
    response = client.post(path, content=json.dumps(payload), headers={"Content-Type": "application/json"})
    assert response.status_code == 422, response.text
    assert response.json()["detail"]
