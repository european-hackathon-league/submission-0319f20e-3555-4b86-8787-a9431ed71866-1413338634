
from database.store import connect


def import_feedback(client, records, reference="sample", vehicle="G60", market="US"):
    response = client.post("/imports/records", json={
        "title": reference, "reference": reference, "kind": "feedback", "vehicle": vehicle, "market": market,
        "records": [{"content": record[0], "metadata": {"topic": record[1], "sentiment": record[2], "provenance": reference},
                     "location": {"row": index + 2}, "vehicle": vehicle, "market": market}
                    for index, record in enumerate(records)],
    })
    assert response.status_code == 201, response.text
    return response.json()


def initial(client):
    import_feedback(client, [("Public charging is confusing and unreliable", "charging", "problem"),
                             ("I love the comfortable seats", "comfort", "strength")])
    response = client.post("/pipeline/run", json={})
    assert response.status_code == 201, response.text
    return response.json()


def by_topic(result, topic):
    return next(item for item in result["generation"]["requirements"] if item["topic"] == topic)


def decision(client, requirement, action="approve"):
    version = requirement["current_version"]
    response = client.post(f"/requirements/{requirement['id']}/decisions", json={
        "version_id": version["id"], "score_id": version["score"]["id"], "action": action,
        "actor": "PM Alice", "rationale": f"Customer evidence reviewed: {action}",
    })
    assert response.status_code == 201, response.text
    return response.json()["requirement"]


def test_evidence_to_scoring_to_pm_approval_trace_and_history(client):
    result = initial(client)
    assert result["analysis"]["provider"] == "deterministic"
    assert result["analysis"]["cached"] is False
    requirement = by_topic(result, "charging")
    assert requirement["status"] == "proposed"
    version = requirement["current_version"]
    score = version["score"]
    assert score["total"] == round(sum(score["factors"][key] * value * 20 for key, value in score["weights"].items()), 4)
    assert score["evidence_grade"] == "C"
    assert version["acceptance_criteria"][0]["basis"] == "PM assumption"
    approved = decision(client, requirement)
    assert approved["approved_version_id"] == version["id"]
    assert approved["approved_score_id"] == score["id"]
    assert approved["status"] == "approved"
    trace = client.get(f"/requirements/{requirement['id']}/trace").json()
    assert trace["evidence"]["items"][0]["location"] == {"row": 2}
    assert trace["sources"][0]["reference"] == "sample"
    assert trace["findings"][0]["evidence_ids"]
    assert trace["decisions"][0]["actor"] == "PM Alice"
    events = client.get("/audit", params={"entity_id": requirement["id"]}).json()["items"]
    assert {event["action"] for event in events} >= {"requirement.scored", "requirement.version_created", "requirement.approve"}
    assert [event["sequence"] for event in events] == sorted(event["sequence"] for event in events)
    assert any(f["kind"] == "strength" for f in result["analysis"]["findings"])
    workspace = client.get("/workspace").json()
    assert workspace["evidence_count"] == 2
    assert workspace["requirements"]["total"] >= 2


def test_repeated_pipeline_is_cached_and_does_not_create_versions(client):
    first = initial(client)
    second = client.post("/pipeline/run", json={}).json()
    assert second["analysis"]["id"] == first["analysis"]["id"]
    assert second["analysis"]["cached"]
    assert second["generation"]["created"] == []
    assert second["generation"]["updated"] == []
    assert len(second["generation"]["unchanged"]) == len(first["generation"]["created"])


def test_pm_edit_is_versioned_rescored_and_stale_actions_rejected(client):
    requirement = by_topic(initial(client), "charging")
    approved = decision(client, requirement)
    original = approved["current_version"]
    changed_factors = {**original["factors"], "customer_impact": 5.0}
    response = client.patch(f"/requirements/{requirement['id']}", json={
        "expected_version_id": original["id"], "actor": "PM Alice", "rationale": "Raise customer impact",
        "factors": changed_factors, "acceptance_criteria": [{"metric": "Trip planning task success", "target": 95,
                                                             "unit": "%", "basis": "PM assumption"}],
    })
    assert response.status_code == 200, response.text
    edited = response.json()
    assert edited["approved_version"] == approved["approved_version"]
    assert edited["current_version"]["version"] == 2
    assert edited["current_version"]["score"]["id"] != original["score"]["id"]
    assert edited["current_version"]["score"]["total"] > original["score"]["total"]
    assert edited["needs_review"]
    assert client.patch(f"/requirements/{requirement['id']}", json={"expected_version_id": original["id"], "title": "Stale title", "actor": "Bob", "rationale": "old"}).status_code == 409
    assert client.post(f"/requirements/{requirement['id']}/decisions", json={"version_id": original["id"], "score_id": original["score"]["id"], "action": "approve", "actor": "Bob", "rationale": "old"}).status_code == 409
    assert len(client.get(f"/requirements/{requirement['id']}/versions").json()) == 2


def test_cross_scope_findings_and_unlinked_target_sources_rejected(client):
    requirement = by_topic(initial(client), "charging")
    version = requirement["current_version"]
    common = {"expected_version_id": version["id"], "actor": "PM", "rationale": "check"}
    response = client.patch(f"/requirements/{requirement['id']}", json={**common,
        "acceptance_criteria": [{"metric": "task success", "target": "90%", "basis": "source", "source_ids": ["imaginary"]}]})
    assert response.status_code == 422
    import_feedback(client, [("Seat is uncomfortable", "comfort", "problem")], reference="China", market="CN")
    analysis = client.post("/analyses", json={"market": "CN"}).json()
    response = client.patch(f"/requirements/{requirement['id']}", json={**common, "finding_ids": [analysis["findings"][0]["id"]]})
    assert response.status_code == 422
    assert len(client.get(f"/requirements/{requirement['id']}/versions").json()) == 1
    assert client.get("/requirements?market=CN").json()["total"] == 0


def test_score_reweight_preserves_approved_snapshot_and_requires_current_score(client):
    requirement = decision(client, by_topic(initial(client), "charging"))
    approved_score = requirement["approved_version"]["score"]
    response = client.post(f"/requirements/{requirement['id']}/scores", json={
        "expected_version_id": requirement["current_version_id"], "actor": "PM", "rationale": "Emphasize customers",
        "weights": {"customer_impact": 1, "market_relevance": 0, "strategic_fit": 0, "differentiation": 0, "feasibility": 0},
    })
    assert response.status_code == 201, response.text
    current = client.get(f"/requirements/{requirement['id']}").json()
    assert current["approved_version"]["score"] == approved_score
    assert current["needs_review"]
    assert client.post(f"/requirements/{requirement['id']}/decisions", json={"version_id": current["current_version_id"],
        "score_id": approved_score["id"], "actor": "PM", "rationale": "stale score", "action": "approve"}).status_code == 409
    approved = decision(client, current)
    assert approved["approved_score_id"] == response.json()["id"]
    assert not approved["needs_review"]


def test_new_evidence_reviews_only_affected_approved_requirements(client):
    result = initial(client)
    charging = decision(client, by_topic(result, "charging"))
    comfort = decision(client, by_topic(result, "comfort"))
    import_feedback(client, [("I love the easy public charging", "charging", "strength")], reference="new-batch")
    response = client.post("/updates", json={})
    assert response.status_code == 201, response.text
    update = response.json()
    revised = by_topic(update, "charging")
    assert revised["approved_version"] == charging["approved_version"]
    assert revised["current_version_id"] != charging["current_version_id"]
    assert revised["current_version"]["score"]["explanation"]["conflict_flag"]
    assert revised["needs_review"]
    assert by_topic(update, "comfort")["current_version_id"] == comfort["current_version_id"]
    assert {r["requirement_id"] for r in update["reviews"]} == {charging["id"]}
    assert client.get("/requirements?needs_review=true").json()["total"] == 1
    second = client.post("/updates", json={}).json()
    assert second["generation"]["updated"] == []
    accepted = decision(client, revised)
    assert accepted["approved_version_id"] == revised["current_version_id"]
    assert not accepted["needs_review"]


def test_unrelated_evidence_does_not_reopen_decisions(client):
    result = initial(client)
    approved = [decision(client, r) for r in result["generation"]["requirements"]]
    import_feedback(client, [("Exterior design looks beautiful", "design", "strength")], reference="design-batch")
    update = client.post("/updates", json={}).json()
    assert update["generation"]["updated"] == []
    assert update["reviews"] == []
    for requirement in approved:
        assert client.get(f"/requirements/{requirement['id']}").json()["approved_version_id"] == requirement["approved_version_id"]


def test_multiple_updates_show_complete_difference_from_last_approval(client):
    requirement = decision(client, by_topic(initial(client), "charging"))
    for index in range(2):
        import_feedback(client, [(f"Public charging is confusing for user {index}", "charging", "problem")], reference=f"batch-{index}")
        response = client.post("/updates", json={})
        assert response.status_code == 201, response.text
    reviews = client.get("/reviews").json()
    assert len(reviews) == 1
    comparison = reviews[0]["changes"]["against_approved"]
    assert comparison["baseline_version_id"] == requirement["approved_version_id"]
    assert len(comparison["added_evidence_ids"]) == 2
    assert comparison["approved_score"]["id"] == requirement["approved_score_id"]


def test_updates_preserve_pm_targets_and_reject_stale_analysis(client):
    first = initial(client)
    requirement = decision(client, by_topic(first, "charging"))
    target = [{"metric": "Planning success", "target": 95, "unit": "%", "basis": "PM assumption"}]
    edited = client.patch(f"/requirements/{requirement['id']}", json={
        "expected_version_id": requirement["current_version_id"], "actor": "PM Alice", "rationale": "Define acceptance",
        "acceptance_criteria": target, "title": "Our agreed charging outcome",
    }).json()
    approved = decision(client, edited)
    import_feedback(client, [("Public charging is slow", "charging", "problem")], reference="second-batch")
    response = client.post("/updates", json={})
    assert response.status_code == 201, response.text
    revised = by_topic(response.json(), "charging")
    assert revised["current_version"]["title"] == "Our agreed charging outcome"
    assert revised["current_version"]["acceptance_criteria"] == approved["current_version"]["acceptance_criteria"]
    assert revised["approved_version"] == approved["approved_version"]
    stale = client.post("/requirements/generate", json={"run_id": first["analysis"]["id"]})
    assert stale.status_code == 409
    assert client.post("/updates", json={"source_ids": ["anything"]}).status_code == 422


def test_reject_postpone_challenge_record_decisions_without_overwriting_approval(client):
    original = decision(client, by_topic(initial(client), "charging"))
    current = client.patch(f"/requirements/{original['id']}", json={"expected_version_id": original["current_version_id"],
        "actor": "Alice", "rationale": "Proposal", "title": "New charging title"}).json()
    postponed = decision(client, current, "postpone")
    assert postponed["status"] == "postponed" and postponed["needs_review"]
    challenged = decision(client, postponed, "challenge")
    assert challenged["status"] == "needs_review"
    rejected = decision(client, challenged, "reject")
    assert rejected["status"] == "rejected" and not rejected["needs_review"]
    assert rejected["approved_version"] == original["approved_version"]


def test_missing_evidence_and_unavailable_ai_are_explicit(client, monkeypatch):
    assert client.post("/pipeline/run", json={}).status_code == 422
    import_feedback(client, [("Seat uncomfortable", "comfort", "problem")])
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    response = client.post("/pipeline/run", json={"provider": "openai"})
    assert response.status_code == 503, response.text
    assert client.get("/requirements").json()["total"] == 0
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM analysis_runs").fetchone()[0] == 0


def test_invalid_scoring_and_null_edit_do_not_mutate(client):
    requirement = by_topic(initial(client), "charging")
    common = {"expected_version_id": requirement["current_version_id"], "actor": "PM", "rationale": "test"}
    assert client.patch(f"/requirements/{requirement['id']}", json={**common, "title": None}).status_code == 422
    assert client.post(f"/requirements/{requirement['id']}/scores", json={**common, "weights": {"customer_impact": 0}}).status_code == 422
    assert client.patch(f"/requirements/{requirement['id']}", json={**common, "factors": {**requirement["current_version"]["factors"], "feasibility": 10}}).status_code == 422
    assert len(client.get(f"/requirements/{requirement['id']}/versions").json()) == 1


def test_sqlite_enforces_immutable_approved_versions(client):
    import sqlite3

    import pytest

    from database.store import transaction

    approved = decision(client, by_topic(initial(client), "charging"))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"), transaction() as connection:
        connection.execute("UPDATE requirement_versions SET title='tampered' WHERE id=?", (approved["approved_version_id"],))
    assert client.get(f"/requirements/{approved['id']}").json()["approved_version"] == approved["approved_version"]
