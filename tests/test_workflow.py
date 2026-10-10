
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


def fake_ai(monkeypatch, transform=lambda result, records: None):
    """Exercise persisted AI workflows using the validated reference output."""
    import os

    from server import analysis_engine

    reference = analysis_engine.analyze_evidence

    def analyze(records, vehicle, market, provider):
        result = reference(records, vehicle, market, "deterministic")
        result.update(provider=provider, model=os.getenv("OPENAI_MODEL", "test-model"))
        transform(result, records)
        return result

    monkeypatch.setattr(analysis_engine, "analyze_evidence", analyze)
    monkeypatch.setenv("OPENAI_MODEL", "test-model")


def test_old_analysis_cannot_revert_newer_interpretation_of_same_evidence(client, monkeypatch):
    first = initial(client)

    def revised_title(result, records):
        for proposal in result["proposals"]:
            proposal["title"] = "New interpretation: " + proposal["title"]

    fake_ai(monkeypatch, revised_title)
    newer = client.post("/pipeline/run", json={"provider": "openai"})
    assert newer.status_code == 201, newer.text
    current = by_topic(newer.json(), "charging")
    stale = client.post("/requirements/generate", json={"run_id": first["analysis"]["id"]})
    assert stale.status_code == 409, stale.text
    assert client.get(f"/requirements/{current['id']}").json()["current_version_id"] == current["current_version_id"]


def test_partial_ai_input_snapshot_cannot_drop_previously_linked_evidence(client, monkeypatch):
    approved = decision(client, by_topic(initial(client), "charging"))
    trace = client.get(f"/requirements/{approved['id']}/trace").json()
    original_ids = {e["id"] for e in trace["evidence"]["items"]}
    import_feedback(client, [("Charging stations keep failing", "charging", "problem")], reference="new")

    def partial(result, records):
        result["analyzed_evidence_ids"] = [r["id"] for r in records if r["id"] not in original_ids]
        for finding in result["findings"]:
            finding["evidence_ids"] = [eid for eid in finding["evidence_ids"] if eid not in original_ids]
        result["warnings"].append("Partial AI source coverage")

    fake_ai(monkeypatch, partial)
    response = client.post("/updates", json={"provider": "openai"})
    assert response.status_code == 409, response.text
    current = client.get(f"/requirements/{approved['id']}").json()
    assert current["current_version_id"] == approved["current_version_id"]
    assert current["approved_version"] == approved["approved_version"]
    assert not current["needs_review"]


def test_ai_cache_is_invalidated_when_batch_coverage_changes(client, monkeypatch):
    initial(client)
    fake_ai(monkeypatch)
    monkeypatch.setenv("ANALYSIS_MAX_BATCHES", "1")
    first = client.post("/analyses", json={"provider": "openai"}).json()
    assert not first["cached"]
    assert client.post("/analyses", json={"provider": "openai"}).json()["cached"]
    monkeypatch.setenv("ANALYSIS_MAX_BATCHES", "2")
    second = client.post("/analyses", json={"provider": "openai"}).json()
    assert not second["cached"] and second["id"] != first["id"]
    monkeypatch.setenv("ANALYSIS_BATCH_SIZE", "10")
    third = client.post("/analyses", json={"provider": "openai"}).json()
    assert not third["cached"] and third["id"] != second["id"]


def test_pm_override_survives_a_coinciding_generator_proposal(client, monkeypatch):
    approved = decision(client, by_topic(initial(client), "charging"))
    pm_title = "Agreed charging experience"
    edited = client.patch(f"/requirements/{approved['id']}", json={
        "expected_version_id": approved["current_version_id"], "actor": "Alice", "rationale": "Choose product language",
        "title": pm_title,
    }).json()
    approved = decision(client, edited)

    def matching_title(result, records):
        for proposal in result["proposals"]:
            if proposal["topic"] == "charging":
                proposal["title"] = pm_title

    fake_ai(monkeypatch, matching_title)
    import_feedback(client, [("Charging is unreliable", "charging", "problem")], reference="coinciding")
    aligned = client.post("/updates", json={"provider": "openai"})
    assert aligned.status_code == 201, aligned.text
    import_feedback(client, [("Charging is too slow", "charging", "problem")], reference="later")
    later = client.post("/updates", json={})
    assert later.status_code == 201, later.text
    revised = by_topic(later.json(), "charging")
    assert revised["current_version"]["title"] == pm_title
    assert revised["approved_version"] == approved["approved_version"]


def test_rescore_checks_current_score_and_noop_does_not_invalidate_approval(client):
    approved = decision(client, by_topic(initial(client), "charging"))
    original = approved["current_version"]["score"]
    common = {"expected_version_id": approved["current_version_id"], "expected_score_id": original["id"],
              "actor": "Alice", "rationale": "Reconsider priority"}
    noop = client.post(f"/requirements/{approved['id']}/scores", json={**common, "weights": original["weights"]})
    assert noop.status_code == 201, noop.text
    assert noop.json()["id"] == original["id"]
    assert not client.get(f"/requirements/{approved['id']}").json()["needs_review"]
    weights = {"customer_impact": 1, "market_relevance": 0, "strategic_fit": 0, "differentiation": 0, "feasibility": 0}
    revised = client.post(f"/requirements/{approved['id']}/scores", json={**common, "weights": weights})
    assert revised.status_code == 201, revised.text
    stale = client.post(f"/requirements/{approved['id']}/scores", json={**common, "weights": original["weights"]})
    assert stale.status_code == 409, stale.text
    current = client.get(f"/requirements/{approved['id']}").json()
    assert current["current_version"]["score"]["id"] == revised.json()["id"]
    assert current["approved_version"]["score"] == original


def test_pm_assumed_targets_cannot_claim_source_citations(client):
    requirement = by_topic(initial(client), "charging")
    source_id = client.get(f"/requirements/{requirement['id']}/trace").json()["sources"][0]["id"]
    response = client.patch(f"/requirements/{requirement['id']}", json={
        "expected_version_id": requirement["current_version_id"], "actor": "PM", "rationale": "Define target",
        "acceptance_criteria": [{"metric": "success", "target": "95%", "basis": "PM assumption", "source_ids": [source_id]}],
    })
    assert response.status_code == 422, response.text


def test_context_alone_cannot_be_the_basis_of_a_pm_requirement(client):
    import_feedback(client, [("Charging survey has 250 respondents", "charging", "context")])
    run = client.post("/analyses", json={}).json()
    assert run["findings"][0]["kind"] == "context"
    response = client.post("/requirements", json={
        "topic": "charging", "title": "Improve charging", "statement": "Customers can charge confidently",
        "customer_need": "Charge confidently", "acceptance_criteria": [{"metric": "success", "target": "90%", "basis": "PM assumption"}],
        "factors": {"customer_impact": 3, "market_relevance": 3, "strategic_fit": 3, "differentiation": 3, "feasibility": 3},
        "finding_ids": [run["findings"][0]["id"]], "rationale": "Review context",
    })
    assert response.status_code == 422, response.text
    assert client.get("/requirements").json()["total"] == 0


def test_interpretation_only_updates_compare_against_complete_approved_baseline(client, monkeypatch):
    approved = decision(client, by_topic(initial(client), "charging"))

    def reinterpret(result, records):
        for finding in result["findings"]:
            if finding["topic"] == "charging":
                finding["summary"] = "Same customer report now assessed with additional uncertainty"
                finding["confidence"] = 0.25

    fake_ai(monkeypatch, reinterpret)
    response = client.post("/updates", json={"provider": "openai"})
    assert response.status_code == 201, response.text
    revised = by_topic(response.json(), "charging")
    comparison = revised["reviews"][-1]["changes"]["against_approved"]
    assert comparison["added_evidence_ids"] == comparison["removed_evidence_ids"] == []
    assert comparison["fields"] == {}
    interpretation = comparison["finding_interpretation"]
    assert interpretation["before"][0]["confidence"] != interpretation["after"][0]["confidence"]
    assert interpretation["after"][0]["confidence"] == 0.25
    assert revised["approved_version"] == approved["approved_version"]


def test_conflict_counts_unique_evidence_instead_of_repeated_links(client):
    import_feedback(client, [("Charging is unreliable", "charging", "problem"),
                             ("I need easy charging", "charging", "need"),
                             ("I love easy charging", "charging", "strength")])
    result = client.post("/pipeline/run", json={}).json()
    explanation = by_topic(result, "charging")["current_version"]["score"]["explanation"]
    assert explanation["conflict_count"] == 3
    assert explanation["evidence_count"] == 3


def test_conflicting_source_alone_cannot_support_a_source_based_target(client, monkeypatch):
    first = import_feedback(client, [("Charging is unreliable", "charging", "problem")], reference="support")
    contrary = import_feedback(client, [("Customers want 95% charging success", "charging", "strength")], reference="contrary")

    def use_only_problem(result, records):
        for proposal in result["proposals"]:
            if proposal["topic"] == "charging":
                proposal["finding_indexes"] = [i for i, f in enumerate(result["findings"]) if f["kind"] == "problem"]

    fake_ai(monkeypatch, use_only_problem)
    response = client.post("/pipeline/run", json={"provider": "openai"})
    assert response.status_code == 201, response.text
    requirement = by_topic(response.json(), "charging")
    response = client.patch(f"/requirements/{requirement['id']}", json={
        "expected_version_id": requirement["current_version_id"], "actor": "PM", "rationale": "Define source target",
        "acceptance_criteria": [{"metric": "charging success", "target": "95%", "basis": "source", "source_ids": [contrary["source_id"]]}],
    })
    assert first["source_id"] != contrary["source_id"]
    assert response.status_code == 422, response.text


def test_concurrent_import_during_analysis_cannot_apply_an_outdated_cumulative_snapshot(client, monkeypatch):
    approved = decision(client, by_topic(initial(client), "charging"))

    def concurrent_import(result, records):
        import_feedback(client, [("Charging failed today", "charging", "problem")], reference="arrived-during-analysis")

    fake_ai(monkeypatch, concurrent_import)
    response = client.post("/updates", json={"provider": "openai"})
    assert response.status_code == 409, response.text
    current = client.get(f"/requirements/{approved['id']}").json()
    assert current["current_version_id"] == approved["current_version_id"]
    assert not current["needs_review"]
    retry = client.post("/updates", json={})
    assert retry.status_code == 201, retry.text
    assert by_topic(retry.json(), "charging")["needs_review"]


def test_generated_whitespace_is_normalized_before_noop_comparison(client, monkeypatch):
    initial(client)

    def padding(result, records):
        for proposal in result["proposals"]:
            for key in ("title", "statement", "customer_need"):
                proposal[key] = "  " + proposal[key] + "  "
            proposal["assumptions"] = ["  " + item + "  " for item in proposal["assumptions"]]
            for criterion in proposal["acceptance_criteria"]:
                criterion["metric"] = "  " + criterion["metric"] + "  "

    fake_ai(monkeypatch, padding)
    response = client.post("/updates", json={"provider": "openai"})
    assert response.status_code == 201, response.text
    assert response.json()["generation"]["updated"] == []
    assert response.json()["reviews"] == []


def test_explicit_pm_added_findings_remain_linked_in_future_updates(client):
    result = initial(client)
    approved = decision(client, by_topic(result, "charging"))
    extra_finding = by_topic(result, "comfort")["current_version"]["finding_ids"][0]
    selected = [*approved["current_version"]["finding_ids"], extra_finding]
    edited = client.patch(f"/requirements/{approved['id']}", json={
        "expected_version_id": approved["current_version_id"], "actor": "Alice", "rationale": "Track cabin comfort while charging",
        "finding_ids": selected,
    })
    assert edited.status_code == 200, edited.text
    approved = decision(client, edited.json())
    import_feedback(client, [("Public charging is slow", "charging", "problem")], reference="later")
    response = client.post("/updates", json={})
    assert response.status_code == 201, response.text
    revised = by_topic(response.json(), "charging")
    assert extra_finding in revised["current_version"]["finding_ids"]
    assert revised["approved_version"] == approved["approved_version"]


def test_preserved_pm_source_target_keeps_its_support_after_model_omits_it(client, monkeypatch):
    original_source = import_feedback(client, [("Customers want 95% successful charging", "charging", "need")])
    approved = decision(client, by_topic(client.post("/pipeline/run", json={}).json(), "charging"))
    edited = client.patch(f"/requirements/{approved['id']}", json={
        "expected_version_id": approved["current_version_id"], "actor": "Alice", "rationale": "Adopt the requested target",
        "acceptance_criteria": [{"metric": "charging success", "target": "95%", "basis": "source",
                                 "source_ids": [original_source["source_id"]]}],
    })
    assert edited.status_code == 200, edited.text
    approved = decision(client, edited.json())
    import_feedback(client, [("Charging fails", "charging", "problem")], reference="new")

    def omit_need(result, records):
        for proposal in result["proposals"]:
            proposal["finding_indexes"] = [i for i, f in enumerate(result["findings"]) if f["kind"] == "problem"]

    fake_ai(monkeypatch, omit_need)
    response = client.post("/updates", json={"provider": "openai"})
    assert response.status_code == 201, response.text
    revised = by_topic(response.json(), "charging")
    assert revised["current_version"]["acceptance_criteria"] == approved["current_version"]["acceptance_criteria"]
    assert set(approved["current_version"]["finding_ids"]) <= set(revised["current_version"]["finding_ids"])
    assert revised["current_version"]["score"]["explanation"]["evidence_count"] == 2


def test_linked_customer_text_cannot_be_misrepresented_as_a_source_target(client):
    source = import_feedback(client, [("Charging satisfaction measured 95%", "charging", "problem")])
    requirement = by_topic(client.post("/pipeline/run", json={}).json(), "charging")
    response = client.patch(f"/requirements/{requirement['id']}", json={
        "expected_version_id": requirement["current_version_id"], "actor": "Alice", "rationale": "Set target",
        "acceptance_criteria": [{"metric": "charging satisfaction", "target": "95%", "basis": "source", "source_ids": [source["source_id"]]}],
    })
    assert response.status_code == 422, response.text
    assert len(client.get(f"/requirements/{requirement['id']}/versions").json()) == 1


def test_new_evidence_preserves_pm_scoring_weights(client):
    approved = decision(client, by_topic(initial(client), "charging"))
    weights = {"customer_impact": 1, "market_relevance": 0, "strategic_fit": 0, "differentiation": 0, "feasibility": 0}
    score = client.post(f"/requirements/{approved['id']}/scores", json={
        "expected_version_id": approved["current_version_id"], "actor": "Alice", "rationale": "Prioritize impact", "weights": weights,
    })
    assert score.status_code == 201, score.text
    import_feedback(client, [("Charging stations are hard to find", "charging", "problem")], reference="new")
    response = client.post("/updates", json={})
    assert response.status_code == 201, response.text
    revised = by_topic(response.json(), "charging")
    assert revised["current_version"]["score"]["weights"] == weights
    assert revised["approved_version"] == approved["approved_version"]


def test_oversized_model_proposal_returns_validation_error_without_mutating_requirements(client, monkeypatch):
    approved = decision(client, by_topic(initial(client), "charging"))

    def too_many_criteria(result, records):
        result["proposals"][0]["acceptance_criteria"] *= 31

    fake_ai(monkeypatch, too_many_criteria)
    response = client.post("/updates", json={"provider": "openai"})
    assert response.status_code == 422, response.text
    current = client.get(f"/requirements/{approved['id']}").json()
    assert current["current_version_id"] == approved["current_version_id"]


def test_trace_can_pin_exact_score_and_rejects_mismatched_scores(client):
    result = initial(client)
    requirement = decision(client, by_topic(result, "charging"))
    version = requirement["current_version"]
    original_score = version["score"]
    other_requirement = by_topic(result, "comfort")
    endpoint = f"/requirements/{requirement['id']}/trace"
    rescored = client.post(f"/requirements/{requirement['id']}/scores", json={
        "expected_version_id": version["id"], "actor": "PM", "rationale": "Emphasize customers",
        "weights": {"customer_impact": 1, "market_relevance": 0, "strategic_fit": 0,
                    "differentiation": 0, "feasibility": 0}})
    assert rescored.status_code == 201, rescored.text
    current = client.get(f"/requirements/{requirement['id']}").json()
    decision(client, current, "reject")
    latest = client.get(endpoint).json()
    assert latest["version"]["score"]["id"] == rescored.json()["id"]
    assert {item["action"] for item in latest["decisions"]} == {"approve", "reject"}
    pinned = client.get(endpoint, params={"version_id": version["id"], "score_id": original_score["id"]})
    assert pinned.status_code == 200, pinned.text
    assert pinned.json()["version"]["score"] == original_score
    assert [item["action"] for item in pinned.json()["decisions"]] == ["approve"]
    for score_id in ("missing", "", other_requirement["current_version"]["score"]["id"]):
        assert client.get(endpoint, params={"version_id": version["id"], "score_id": score_id}).status_code == 404
    edited = client.patch(f"/requirements/{requirement['id']}", json={
        "expected_version_id": version["id"], "actor": "PM", "rationale": "Clarify outcome",
        "title": "A revised charging outcome"})
    assert edited.status_code == 200, edited.text
    assert client.get(endpoint, params={"score_id": original_score["id"]}).status_code == 404
    assert client.get(endpoint, params={"version_id": edited.json()["current_version_id"],
                                        "score_id": original_score["id"]}).status_code == 404
    assert client.get(endpoint, params={"version_id": other_requirement["current_version_id"],
                                        "score_id": original_score["id"]}).status_code == 404
