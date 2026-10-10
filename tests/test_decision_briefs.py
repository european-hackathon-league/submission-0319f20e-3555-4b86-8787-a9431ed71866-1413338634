from test_workflow import decision, import_feedback

from database.store import connect


def run_workflow(client, key="brief-test", **overrides):
    response = client.post("/workflows", json={"request_key": key, "actor": "PM", **overrides})
    assert response.status_code == 201, response.text
    workflow = response.json()
    response = client.post(f"/workflows/{workflow['id']}/run", json={
        "expected_revision": workflow["revision"], "actor": "PM"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "awaiting_review", response.text
    return response.json()


def initial_brief(client):
    import_feedback(client, [("Public charging is unreliable", "charging", "problem"),
                             ("Public charging is easy", "charging", "strength")])
    workflow = run_workflow(client)
    response = client.get(f"/workflows/{workflow['id']}/brief")
    assert response.status_code == 200, response.text
    return workflow, response.json()


def test_brief_prepares_decision_with_source_locations_and_honest_checks(client):
    workflow, brief = initial_brief(client)
    assert brief["snapshot"] == "live"
    assert brief["summary"]["needs_decision_count"] == 1
    requirement = brief["requirements"][0]
    checks = {item["code"]: item for item in requirement["checks"]}
    assert {"conflicting_evidence", "undated_evidence", "assumed_targets", "limited_provenance", "human_decision"} <= checks.keys()
    evidence_ids = {item["id"] for item in requirement["evidence"]}
    assert all(set(item["evidence_ids"]) <= evidence_ids for item in requirement["checks"])
    assert {item["location"]["row"] for item in requirement["evidence"]} == {2, 3}
    assert requirement["score"]["id"] == requirement["version"]["score"]["id"]
    assert requirement["decision"] is None
    assert all(item["next_action"] for item in checks.values())
    assert client.get(requirement["trace_url"]).status_code == 200
    assert brief["warnings"] == []
    audit = client.get("/audit", params={"entity_id": workflow["id"]}).json()["items"]
    assert any(item["action"] == "workflow.brief_viewed" for item in audit)


def test_completed_brief_stays_frozen_after_edits_rescores_decisions_and_evidence(client):
    workflow, before = initial_brief(client)
    requirement_id = before["requirements"][0]["requirement_id"]
    approved = decision(client, client.get(f"/requirements/{requirement_id}").json())
    completed = client.post(f"/workflows/{workflow['id']}/complete", json={
        "expected_revision": workflow["revision"], "actor": "PM", "rationale": "Reviewed customer planning evidence"})
    assert completed.status_code == 200, completed.text
    endpoint = f"/workflows/{workflow['id']}/brief"
    frozen = client.get(endpoint).json()
    assert frozen["snapshot"] == "completed"
    assert frozen["summary"]["approved_count"] == 1
    assert frozen["requirements"][0]["decision"]["action"] == "approve"
    markdown = client.get(endpoint, params={"format": "markdown"}).text
    rescored = client.post(f"/requirements/{requirement_id}/scores", json={
        "expected_version_id": approved["current_version_id"], "actor": "PM", "rationale": "Reweight customers",
        "weights": {"customer_impact": 1, "market_relevance": 0, "strategic_fit": 0,
                    "differentiation": 0, "feasibility": 0}})
    assert rescored.status_code == 201, rescored.text
    assert rescored.json()["id"] != frozen["requirements"][0]["score"]["id"]
    assert client.get(endpoint).json() == frozen
    trace = client.get(frozen["requirements"][0]["trace_url"])
    assert trace.status_code == 200, trace.text
    assert trace.json()["version"]["score"] == frozen["requirements"][0]["score"]
    import_feedback(client, [("Charging requires improvement", "charging", "problem")], reference="new")
    edited = client.patch(f"/requirements/{requirement_id}", json={
        "expected_version_id": approved["current_version_id"], "actor": "PM", "rationale": "New wording",
        "title": "A newer requirement"}).json()
    decision(client, edited, "reject")
    assert client.get(endpoint).json() == frozen
    assert client.get(endpoint, params={"format": "markdown"}).text == markdown


def test_live_brief_tracks_pm_edits_without_reusing_old_decision(client):
    workflow, brief = initial_brief(client)
    rid = brief["requirements"][0]["requirement_id"]
    approved = decision(client, client.get(f"/requirements/{rid}").json())
    edited = client.patch(f"/requirements/{rid}", json={
        "expected_version_id": approved["current_version_id"], "actor": "PM", "rationale": "Review wording",
        "title": "Improve customer charging"}).json()
    item = client.get(f"/workflows/{workflow['id']}/brief").json()["requirements"][0]
    assert item["version"]["id"] == edited["current_version_id"]
    assert item["decision"] is None
    assert item["approved_baseline"]["id"] == approved["current_version_id"]
    import_feedback(client, [("New customer feedback", "charging", "problem")], reference="newer")
    assert client.get(f"/workflows/{workflow['id']}/brief").json()["warnings"]


def test_markdown_export_has_exact_citations_and_escapes_untrusted_text(client):
    import_feedback(client, [("<script>alert(1)</script> [go](https://evil.test) Charging is slow", "charging", "problem")])
    workflow = run_workflow(client)
    response = client.get(f"/workflows/{workflow['id']}/brief?format=markdown")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in response.headers["content-disposition"]
    assert "\\<script\\>" in response.text
    assert "\\[go\\]\\(https://evil.test\\)" in response.text
    assert "'row': 2" in response.text
    assert "PM assumption" in response.text
    assert "Customer need:" in response.text
    assert client.get(f"/workflows/{workflow['id']}/brief?format=html").status_code == 422
    assert client.get("/workflows/missing/brief").status_code == 404


def test_actor_discovery_reports_actual_roles_and_active_flags(client):
    with connect() as connection:
        connection.execute("UPDATE actors SET active=0 WHERE id='human:jakob'")
    actors = {item["id"]: item for item in client.get("/actors").json()}
    assert actors["human:jakob"]["active"] == 0
    assert actors["human:troy"]["role"] == "lead_pm"
    assert actors["ai:reference:v1"]["kind"] == "ai"


def test_live_brief_includes_pm_requirements_added_after_generation(client):
    workflow, brief = initial_brief(client)
    version = brief["requirements"][0]["version"]
    content = {key: version[key] for key in (
        "title", "statement", "customer_need", "acceptance_criteria", "assumptions", "factors", "finding_ids")}
    response = client.post("/requirements", json={
        **content, "topic": "pm-added-charging", "actor": "PM", "rationale": "Separate PM planning outcome"})
    assert response.status_code == 201, response.text
    added = response.json()
    live = client.get(f"/workflows/{workflow['id']}/brief").json()
    assert live["summary"]["requirement_count"] == 2
    assert live["summary"]["needs_decision_count"] == 2
    assert added["id"] in {item["requirement_id"] for item in live["requirements"]}
