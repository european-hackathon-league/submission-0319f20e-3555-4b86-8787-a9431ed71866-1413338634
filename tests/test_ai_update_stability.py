import pytest

from server import analysis_engine


def seed(client, monkeypatch, transform, *, import_update=True):
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
    if import_update:
        client.post("/imports/records", json={"title": "Charging update", "reference": "update", "records": [
            {"content": "Public charging information is unreliable", "location": {"row": 2}, "metadata": {"topic": "charging", "sentiment": "problem"}}
        ]}).raise_for_status()
    return initial


def import_design(client, reference):
    client.post("/imports/records", json={"title": "Unrelated update", "reference": reference, "records": [
        {"content": "I love the exterior design", "location": {"row": 2}, "metadata": {"topic": "design", "sentiment": "strength"}}
    ]}).raise_for_status()


def approve(client, requirement):
    version = requirement["current_version"]
    response = client.post(f"/requirements/{requirement['id']}/decisions", json={"version_id": version["id"],
        "score_id": version["score"]["id"], "action": "approve", "actor": "PM", "rationale": "Reviewed fixture"})
    assert response.status_code == 201, response.text
    return response.json()["requirement"]


def pin_comfort(client, initial):
    charging = next(r for r in initial["generation"]["requirements"] if r["topic"] == "charging")
    comfort = next(r for r in initial["generation"]["requirements"] if r["topic"] == "comfort")
    pinned = comfort["current_version"]["finding_ids"][0]
    response = client.patch(f"/requirements/{charging['id']}", json={
        "expected_version_id": charging["current_version_id"], "actor": "PM", "rationale": "Track comfort while charging",
        "finding_ids": [*charging["current_version"]["finding_ids"], pinned],
    })
    assert response.status_code == 200, response.text
    return approve(client, response.json()), pinned


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


@pytest.mark.parametrize("changed_field", ["model", "prompt_version"])
def test_changed_analysis_contract_still_requires_review(client, monkeypatch, changed_field):
    def upgrade(result, records):
        if len(records) > 2:
            result[changed_field] = "new-analysis-contract"
            for proposal in result["proposals"]:
                proposal["title"] = "Reconsider " + proposal["title"]
    initial = seed(client, monkeypatch, upgrade)
    response = client.post("/updates", json={"provider": "openai"})
    assert response.status_code == 201, response.text
    assert set(response.json()["generation"]["updated"]) == {r["id"] for r in initial["generation"]["requirements"]}


def test_reclassified_pm_pinned_evidence_updates_related_decision_once(client, monkeypatch):
    def reclassify(result, records):
        if len(records) > 2:
            for finding in result["findings"]:
                if finding["topic"] == "comfort":
                    finding.update(kind="need", summary="Customers need comfortable seats", confidence=0.8)

    initial = seed(client, monkeypatch, reclassify, import_update=False)
    charging, pinned = pin_comfort(client, initial)
    import_design(client, "first-design-update")
    response = client.post("/updates", json={"provider": "openai"})
    assert response.status_code == 201, response.text
    assert charging["id"] in response.json()["generation"]["updated"]
    revised = client.get(f"/requirements/{charging['id']}").json()
    assert pinned in revised["current_version"]["finding_ids"]
    assert revised["approved_version"] == charging["approved_version"]
    assert revised["needs_review"]
    interpretation = revised["reviews"][-1]["changes"]["against_approved"]["finding_interpretation"]
    assert any(f["topic"] == "comfort" and f["kind"] == "need" for f in interpretation["after"])

    approved = approve(client, revised)
    import_design(client, "second-design-update")
    response = client.post("/updates", json={"provider": "openai"})
    assert response.status_code == 201, response.text
    assert charging["id"] in response.json()["generation"]["unchanged"]
    assert not response.json()["analysis"]["cached"]
    after = client.get(f"/requirements/{charging['id']}").json()
    assert after["current_version"] == approved["current_version"]
    assert not after["needs_review"]


def test_paraphrased_pm_pinned_evidence_keeps_approved_decision(client, monkeypatch):
    def paraphrase(result, records):
        if len(records) > 2:
            for finding in result["findings"]:
                if finding["topic"] == "comfort":
                    finding.update(summary="Customers value comfortable seats", confidence=0.95)

    initial = seed(client, monkeypatch, paraphrase, import_update=False)
    charging, pinned = pin_comfort(client, initial)
    import_design(client, "paraphrased-design-update")
    response = client.post("/updates", json={"provider": "openai"})
    assert response.status_code == 201, response.text
    assert charging["id"] in response.json()["generation"]["unchanged"]
    after = client.get(f"/requirements/{charging['id']}").json()
    assert after["current_version"] == charging["current_version"]
    assert pinned in after["current_version"]["finding_ids"]
    assert not after["needs_review"]


def test_new_conflict_with_pm_pinned_evidence_requires_review(client, monkeypatch):
    def conflict(result, records):
        if len(records) > 2:
            new_evidence = next(r["id"] for r in records if r["metadata"]["topic"] == "design")
            for finding in result["findings"]:
                if finding["topic"] == "comfort":
                    finding["conflicting_evidence_ids"] = [new_evidence]

    initial = seed(client, monkeypatch, conflict, import_update=False)
    charging, pinned = pin_comfort(client, initial)
    import_design(client, "conflicting-design-update")
    response = client.post("/updates", json={"provider": "openai"})
    assert response.status_code == 201, response.text
    assert charging["id"] in response.json()["generation"]["updated"]
    revised = client.get(f"/requirements/{charging['id']}").json()
    assert pinned in revised["current_version"]["finding_ids"]
    assert revised["approved_version"] == charging["approved_version"]
    assert revised["needs_review"]
    assert revised["current_version"]["score"]["explanation"]["conflict_count"] == 1


def test_reclassified_source_target_support_requires_review(client, monkeypatch):
    def reclassify(result, records):
        if len(records) > 3:
            for finding in result["findings"]:
                if finding["topic"] == "charging" and finding["kind"] == "need":
                    finding["kind"] = "context"
            for proposal in result["proposals"]:
                if proposal["topic"] == "charging":
                    proposal["finding_indexes"] = [i for i, f in enumerate(result["findings"])
                                                    if f["topic"] == "charging" and f["kind"] == "problem"]

    seed(client, monkeypatch, reclassify, import_update=False)
    source = client.post("/imports/records", json={"title": "Charging target", "reference": "target", "records": [
        {"content": "Customers want 95% successful charging", "location": {"row": 2},
         "metadata": {"topic": "charging", "sentiment": "need"}}
    ]}).json()
    response = client.post("/updates", json={"provider": "openai"})
    assert response.status_code == 201, response.text
    charging = next(r for r in response.json()["generation"]["requirements"] if r["topic"] == "charging")
    original_findings = {f["id"] for f in response.json()["analysis"]["findings"] if f["kind"] == "need"}
    response = client.patch(f"/requirements/{charging['id']}", json={
        "expected_version_id": charging["current_version_id"], "actor": "PM", "rationale": "Adopt the source target",
        "acceptance_criteria": [{"metric": "charging success", "target": "95%", "basis": "source",
                                 "source_ids": [source["source_id"]]}],
    })
    assert response.status_code == 200, response.text
    charging = approve(client, response.json())
    import_design(client, "reclassified-target-update")
    response = client.post("/updates", json={"provider": "openai"})
    assert response.status_code == 201, response.text
    assert charging["id"] in response.json()["generation"]["updated"]
    revised = client.get(f"/requirements/{charging['id']}").json()
    assert original_findings <= set(revised["current_version"]["finding_ids"])
    assert revised["current_version"]["acceptance_criteria"] == charging["current_version"]["acceptance_criteria"]
    assert revised["needs_review"]


def test_partial_analysis_cannot_claim_unchanged_pinned_evidence(client, monkeypatch):
    def partial(result, records):
        if len(records) > 2:
            result["findings"] = [f for f in result["findings"] if f["topic"] == "charging"]
            result["proposals"] = [p for p in result["proposals"] if p["topic"] == "charging"]
            result["proposals"][0]["finding_indexes"] = [0]
            result["analyzed_evidence_ids"] = [r["id"] for r in records if r["metadata"]["topic"] != "comfort"]

    initial = seed(client, monkeypatch, partial, import_update=False)
    charging, _ = pin_comfort(client, initial)
    import_design(client, "partial-design-update")
    response = client.post("/updates", json={"provider": "openai"})
    assert response.status_code == 409, response.text
    assert "did not analyze all evidence" in response.json()["detail"]
    assert client.get(f"/requirements/{charging['id']}").json()["current_version"] == charging["current_version"]


def test_stale_analysis_cannot_claim_unchanged_newer_pinned_evidence(client, monkeypatch):
    initial = seed(client, monkeypatch, lambda result, records: None, import_update=False)
    monkeypatch.setenv("ANALYSIS_BATCH_SIZE", "1")
    newer = client.post("/analyses", json={"provider": "openai"})
    assert newer.status_code == 201, newer.text
    charging = next(r for r in initial["generation"]["requirements"] if r["topic"] == "charging")
    comfort = next(f for f in newer.json()["findings"] if f["topic"] == "comfort")
    response = client.patch(f"/requirements/{charging['id']}", json={
        "expected_version_id": charging["current_version_id"], "actor": "PM", "rationale": "Select the newer comfort analysis",
        "finding_ids": [*charging["current_version"]["finding_ids"], comfort["id"]],
    })
    assert response.status_code == 200, response.text
    charging = approve(client, response.json())
    response = client.post("/requirements/generate", json={"run_id": initial["analysis"]["id"]})
    assert response.status_code == 409, response.text
    assert "newer analysis" in response.json()["detail"]
    assert client.get(f"/requirements/{charging['id']}").json()["current_version"] == charging["current_version"]
