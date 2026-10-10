import pytest


@pytest.mark.parametrize("text,topic", [
    ("I need charging route planning to warn me when the station availability information is stale. Otherwise I arrive at occupied chargers.", "charging"),
    ("I love the comfortable seats during long journeys; preserve that comfort.", "comfort"),
])
def test_pm_source_target_accepts_complete_desired_outcome_quotes(client, text, topic):
    imported = client.post("/imports/records", json={"title": "Customer request", "reference": "quoted-request",
        "records": [{"content": text, "location": {"row": 2}, "metadata": {"topic": topic, "sentiment": "need"}}]})
    assert imported.status_code == 201, imported.text
    initial = client.post("/pipeline/run", json={})
    assert initial.status_code == 201, initial.text
    requirement = next(r for r in initial.json()["generation"]["requirements"] if r["topic"] == topic)
    response = client.patch(f"/requirements/{requirement['id']}", json={
        "expected_version_id": requirement["current_version_id"], "actor": "human:jakob", "rationale": "Retain the quoted customer outcome",
        "acceptance_criteria": [{"metric": "Customer request met in representative task evaluation", "target": text,
                                 "basis": "source", "source_ids": [imported.json()["source_id"]]}],
    })
    assert response.status_code == 200, response.text
    assert response.json()["current_version"]["acceptance_criteria"][0]["target"] == text


def test_measurement_with_unrelated_desire_is_not_a_target(client):
    text = "Seat satisfaction measured 80%. I want quieter ventilation."
    imported = client.post("/imports/records", json={"title": "Customer feedback", "reference": "measurement",
        "records": [{"content": text, "location": {"row": 2}, "metadata": {"topic": "comfort", "sentiment": "need"}}]}).json()
    requirement = client.post("/pipeline/run", json={}).json()["generation"]["requirements"][0]
    response = client.patch(f"/requirements/{requirement['id']}", json={
        "expected_version_id": requirement["current_version_id"], "actor": "PM", "rationale": "Test invalid numeric attribution",
        "acceptance_criteria": [{"metric": "Seat satisfaction", "target": "80%", "basis": "source", "source_ids": [imported["source_id"]]}],
    })
    assert response.status_code == 422
    assert len(client.get(f"/requirements/{requirement['id']}/versions").json()) == 1
