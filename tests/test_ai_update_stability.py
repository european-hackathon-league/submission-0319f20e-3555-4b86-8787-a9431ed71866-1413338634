from server import analysis_engine


def seed(client, monkeypatch, transform):
    reference = analysis_engine.analyze_evidence

    def model(records, vehicle, market, provider):
        result = reference(records, vehicle, market, "deterministic")
        result.update(provider="openai", model="gpt-6.1-sol")
        transform(result, records)
        return result

    monkeypatch.setattr(analysis_engine, "analyze_evidence", model)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-6.1-sol")
    response = client.post("/imports/records", json={"title": "Initial feedback", "reference": "initial", "records": [
        {"content": "Public charging is confusing", "location": {"row": 2}, "metadata": {"topic": "charging", "sentiment": "problem"}},
        {"content": "I love the comfortable seats", "location": {"row": 3}, "metadata": {"topic": "comfort", "sentiment": "strength"}},
    ]})
    assert response.status_code == 201
    response = client.post("/pipeline/run", json={"provider": "openai"})
    assert response.status_code == 201, response.text
    initial = response.json()
    for requirement in initial["generation"]["requirements"]:
        version = requirement["current_version"]
        response = client.post(f"/requirements/{requirement['id']}/decisions", json={"version_id": version["id"],
            "score_id": version["score"]["id"], "action": "approve", "actor": "PM", "rationale": "Reviewed fixture"})
        assert response.status_code == 201, response.text
    client.post("/imports/records", json={"title": "Charging update", "reference": "update", "records": [
        {"content": "Public charging information is unreliable", "location": {"row": 2}, "metadata": {"topic": "charging", "sentiment": "problem"}}
    ]}).raise_for_status()
    return initial


def test_ai_variation_does_not_reopen_unchanged_topic(client, monkeypatch):
    def paraphrase(result, records):
        if len(records) > 2:
            for proposal in result["proposals"]:
                if proposal["topic"] == "comfort":
                    proposal["title"] = "Maintain comfortable seating for long journeys"
                    proposal["factors"]["strategic_fit"] = 4.0
                    proposal["acceptance_criteria"][0]["target"] = "At least 90%"
            for finding in result["findings"]:
                if finding["topic"] == "comfort":
                    finding.update(summary="Customers value seat comfort on long journeys.", confidence=0.95)
    initial = seed(client, monkeypatch, paraphrase)
    comfort = next(r for r in initial["generation"]["requirements"] if r["topic"] == "comfort")
    result = client.post("/updates", json={"provider": "openai"})
    assert result.status_code == 201, result.text
    update = result.json()
    assert {r["topic"] for r in update["generation"]["requirements"] if r["id"] in update["generation"]["updated"]} == {"charging"}
    after = client.get(f"/requirements/{comfort['id']}").json()
    assert after["current_version"] == comfort["current_version"]
    assert not after["needs_review"]
    assert comfort["id"] in update["generation"]["unchanged_reasons"]


def test_changed_evidence_classification_still_requires_review(client, monkeypatch):
    def reclassify(result, records):
        if len(records) > 2:
            for finding in result["findings"]:
                if finding["topic"] == "comfort":
                    finding["kind"] = "need"
    initial = seed(client, monkeypatch, reclassify)
    comfort = next(r for r in initial["generation"]["requirements"] if r["topic"] == "comfort")
    result = client.post("/updates", json={"provider": "openai"})
    assert result.status_code == 201, result.text
    assert comfort["id"] in result.json()["generation"]["updated"]
    assert client.get(f"/requirements/{comfort['id']}").json()["needs_review"]


def test_changed_prompt_contract_still_requires_review(client, monkeypatch):
    def upgrade(result, records):
        if len(records) > 2:
            result["prompt_version"] = "new-prompt-contract"
            for proposal in result["proposals"]:
                proposal["title"] = "Reconsider " + proposal["title"]
    initial = seed(client, monkeypatch, upgrade)
    response = client.post("/updates", json={"provider": "openai"})
    assert response.status_code == 201, response.text
    assert set(response.json()["generation"]["updated"]) == {r["id"] for r in initial["generation"]["requirements"]}
