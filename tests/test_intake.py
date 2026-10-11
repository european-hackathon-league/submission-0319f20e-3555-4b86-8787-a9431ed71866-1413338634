"""Request intake behavior against a real SQLite database; all examples are synthetic."""

import json
import sqlite3
from contextlib import closing

import pytest

from database.integrity import verify
from database.store import audit, connect, new_id, now, transaction
from server import intake
from server.platform import CAPABILITIES, record_run, run_capability
from tests.test_workflow import decision, import_feedback

BASE = {"vehicle": "G60", "market": "US", "origin_type": "dealer", "origin_name": "Simulated dealer",
        "title": "Ventilated rear seats", "body": "Rear passengers request ventilated rear seats for summer comfort.",
        "simulated": True, "actor": "human:pm"}


def create(client, **changes):
    response = client.post("/requests", json={**BASE, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def post(client, path, **payload):
    response = client.post(path, json={"actor": "human:pm", **payload})
    assert response.status_code == 201, response.text
    return response.json()


def detail(client, request):
    return client.get(f"/requests/{request['id']}").json()


def analyse(client, records=None, market="US", reference="simulated"):
    import_feedback(client, records or [
        ("Ventilated rear seats are missing; summer rear seat comfort is poor.", "comfort", "problem"),
        ("We love the comfortable rear seats and seat ventilation.", "comfort", "strength"),
    ], reference=reference, market=market)
    return post(client, "/analyses", vehicle="G60", market=market, provider="deterministic")


def scalar(query, args=()):
    with closing(connect()) as connection:
        return connection.execute(query, args).fetchone()[0]


def weights(shares):
    with record_run(None, "test.weights", "system:test", "test-v1", {}) as run:
        with transaction() as connection:
            for market, share in shares.items():
                connection.execute("INSERT INTO market_weights (id,vehicle,market,period,units,share,evidence_ids,"
                                   "method_version,run_id,created_at) VALUES (?,'G60',?,'2026',?,?,'[]','test-v1',?,?)",
                                   (new_id(), market, share * 1000, share, run.id, now()))
            audit(connection, "run", run.id, "test.weights", "system:test", "Synthetic weights")


def test_fixture_idempotence_and_all_topics(client):
    first = post(client, "/requests/fixtures/simulated")
    second = post(client, "/requests/fixtures/simulated")
    assert first["label"] == "simulated" and first["created"] == 6
    assert second["created"] == 0 and second["deduplicated"] == 6
    by_ref = {r["external_ref"]: r for r in first["items"]}
    assert by_ref["sim-cn-rear-legroom"]["topic"] == "comfort"
    assert by_ref["sim-us-exhaust-note"]["topic"] == "driving-experience"
    assert by_ref["sim-de-climate-buttons"]["topic"] == "controls"
    assert by_ref["sim-eng-fast-charging-target"]["topic"] == "charging"
    assert by_ref["sim-eu-package-pricing"]["scope_flags"] == ["pricing"]
    assert all(r["simulated"] and r["key"].startswith("MR-G60-") for r in first["items"])
    assert first["audit_event_id"]


def test_batch_atomicity_key_sequence_and_identity_conflict(client, db):
    r = create(client, external_ref="sim-first")
    assert r["key"] == "MR-G60-US-0001"
    retry = create(client, external_ref="sim-first")
    assert retry["id"] == r["id"] and retry["deduplicated"]
    payload = {"requests": [{k: v for k, v in BASE.items() if k != "actor"},
                             {**{k: v for k, v in BASE.items() if k != "actor"},
                              "external_ref": "sim-first", "title": "Different"}], "actor": "human:pm"}
    assert client.post("/requests", json=payload).status_code == 409
    assert scalar("SELECT count(*) FROM intake_requests") == 1
    assert create(client)["key"] == "MR-G60-US-0002"
    assert scalar("SELECT count(*) FROM runs WHERE status='failed'") == 1
    assert verify(db)["ok"]


@pytest.mark.parametrize("body,flag", [
    ("Reduce package pricing", "pricing"), ("Make a business case and ROI", "business_case"),
    ("Request homologation certification", "homologation"), ("Define the wiring harness part number", "engineering_spec"),
    ("Select a supplier", "supplier"),
])
def test_scope_flags_cap_score_and_refuse_conversion(client, body, flag):
    request = create(client, body=body)
    assert flag in request["scope_flags"]
    triage = post(client, "/requests/triage", request_ids=[request["id"]], link_provider="none")
    assert triage["items"][0]["triage"]["total"] <= intake.OUT_OF_SCOPE_CAP
    assert triage["items"][0]["triage"]["suggested_action"]["decision"] == "decline"
    response = client.post(f"/requests/{request['id']}/decide", json={
        "decision": "convert", "actor": "human:pm", "rationale": "Try"})
    assert response.status_code == 422
    assert scalar("SELECT count(*) FROM request_decisions") == 0


def test_scope_requests_do_not_cluster_or_link_or_draft(client, fake_llm):
    flagged = create(client, body="Reduce package pricing")
    good = create(client)
    clustered = post(client, "/requests/cluster", provider="deterministic")
    assert {rid for c in clustered["clusters"] for rid in c["request_ids"]} == {good["id"]}
    proposed = post(client, "/requests/links/propose", provider="openai")
    assert set(proposed["per_request"]) == {good["id"]}
    post(client, "/requests/triage")
    assert client.post("/requests/positions", json={"request_ids": [flagged["id"]],
                                                   "provider": "openai"}).status_code == 422
    assert not fake_llm.calls("/responses")


@pytest.mark.parametrize("provider", ["deterministic", "openai"])
def test_cluster_cross_market_similar_requests_and_stable_identity(client, fake_llm, provider):
    a = create(client)
    b = create(client, market="CN", body=BASE["body"] + " Please.")
    c = create(client, title="Rear legroom", body="More rear legroom and knee room for long wheelbase comfort")
    other = create(client, vehicle="G70")
    fake_llm.embedder = lambda text: [1.0, 0.0] if "Ventilated" in text else [0.0, 1.0]
    result = post(client, "/requests/cluster", provider=provider)
    first = detail(client, a)["cluster_id"]
    assert first == detail(client, b)["cluster_id"] != detail(client, c)["cluster_id"]
    assert detail(client, other)["cluster_id"] is None
    repeated = post(client, "/requests/cluster", provider=provider)
    assert repeated["created_clusters"] == repeated["moved"] == 0
    assert detail(client, a)["cluster_id"] == first
    assert result["threshold"] == (0.5 if provider == "deterministic" else 0.82)
    if provider == "openai":
        assert "openai:" in result["method_version"] and len(fake_llm.calls("/embeddings")) == 1


def test_pm_cluster_moves_are_pinned_and_scoped(client):
    a = create(client)
    b = create(client, title="Rear legroom", body="Rear legroom and knee room")
    post(client, "/requests/cluster", provider="deterministic")
    target = detail(client, b)["cluster_id"]
    response = client.patch(f"/requests/{a['id']}", json={"cluster_id": target, "actor": "human:pm", "rationale": "Same ask"})
    assert response.status_code == 200, response.text
    post(client, "/requests/cluster", provider="deterministic")
    assert detail(client, a)["cluster_id"] == target
    assert "cluster_id" in detail(client, a)["pm_pinned"]
    assert client.patch(f"/requests/{a['id']}", json={"topic": "charging", "cluster_id": target,
                                                    "actor": "human:pm", "rationale": "Invalid"}).status_code == 422


def test_deterministic_triage_neutral_unknowns_weights_and_input_trace(client):
    request = create(client)
    first = post(client, "/requests/triage")
    row = detail(client, request)["triage_history"][0]
    assert row["total"] == 50 and all(value == 2.5 for value in row["factors"].values())
    assert set(row["explanation"]["factors"]) == set(intake.TRIAGE_FACTORS)
    assert all(f["formula"] and "inputs" in f and f["flags"] for f in row["explanation"]["factors"].values())
    assert row["explanation"]["factors"]["effort"]["flags"] == ["effort_unknown"]
    assert first["link_run_id"] is None
    repeat = post(client, "/requests/triage")
    assert repeat["created"] == 0 and repeat["items"][0]["triage"]["id"] == row["id"]
    assert client.post("/requests/triage", json={"weights": {"effort": .5}}).status_code == 422
    custom = {name: 0 for name in intake.TRIAGE_FACTORS} | {"effort": 1}
    assert client.post("/requests/triage", json={"weights": custom, "actor": "ai:test"}).status_code == 403
    assert client.patch(f"/requests/{request['id']}", json={"effort": "low", "actor": "human:pm",
                                                          "rationale": "PM estimate"}).status_code == 200
    assert post(client, "/requests/triage", weights=custom)["items"][0]["triage"]["total"] == 100


def test_sales_weights_recurrence_and_changed_provenance_retriage(client):
    a = create(client)
    create(client, market="CN")
    weights({"US": .6, "CN": .4})
    post(client, "/requests/cluster", provider="deterministic")
    post(client, "/requests/triage")
    before = detail(client, a)["triage_history"][0]
    inputs = before["explanation"]["factors"]
    assert inputs["market_weight"]["value"] == 5
    assert inputs["market_weight"]["inputs"]["market_weight_id"]
    assert inputs["recurrence"]["value"] == 1.875
    # Different origin evidence/run must create a new explanation even if values are unchanged.
    with record_run(None, "test.weights", "system:test", "test-v2", {}) as run:
        with transaction() as connection:
            connection.execute("INSERT INTO market_weights (id,vehicle,market,period,units,share,evidence_ids,"
                               "method_version,run_id,created_at) VALUES (?,'G60','US','2027',600,.6,'[]','test-v2',?,?)",
                               (new_id(), run.id, now()))
    post(client, "/requests/triage")
    after = detail(client, a)["triage_history"][0]
    assert after["id"] != before["id"] and after["factors"] == before["factors"]


def test_evidence_links_grounded_idempotent_and_removed_links_stay_removed(client):
    request = create(client)
    analyse(client)
    first = post(client, "/requests/links/propose", provider="deterministic")
    assert first["created"] == 2
    links = detail(client, request)["links"]
    assert {link["relation"] for link in links} == {"supports", "conflicts"}
    for link in links:
        start, end = link["basis"]["span"]
        assert link["entity"]["content"][start:end] == link["basis"]["quote"]
        assert link["created_by"].startswith("system:") and link["run_id"]
    assert post(client, "/requests/links/propose", provider="deterministic")["created"] == 0
    link = links[0]
    url = f"/requests/{request['id']}/links/{link['id']}"
    assert client.patch(url, json={"status": "removed", "actor": "ai:agent", "rationale": "No"}).status_code == 403
    assert client.patch(url, json={"status": "removed", "actor": "human:pm", "rationale": "Not relevant"}).status_code == 200
    post(client, "/requests/links/propose", provider="deterministic")
    assert next(x for x in detail(client, request)["links"] if x["id"] == link["id"])["status"] == "removed"
    with transaction() as connection, pytest.raises(sqlite3.IntegrityError, match="human actor"):
        connection.execute("UPDATE request_links SET status='active',status_changed_by='system:test',"
                           "status_changed_at=? WHERE id=?", (now(), link["id"]))


def test_same_evidence_linked_as_finding_counts_only_once(client):
    request = create(client)
    analyse(client)
    post(client, "/requests/links/propose", provider="deterministic")
    support = next(link for link in detail(client, request)["links"] if link["relation"] == "supports")
    post(client, f"/requests/{request['id']}/links", entity_type="finding", entity_id=support["basis"]["finding_id"],
         relation="supports", rationale="Also link finding")
    post(client, "/requests/triage")
    support = detail(client, request)["triage_history"][0]["explanation"]["factors"]["evidence_support"]["inputs"]
    assert support["count"] == support["weighted_count"] == 1
    assert len(support["evidence"][0]["link_ids"]) == 2 and support["evidence_grade"] == "C"


def test_manual_links_validate_quote_scope_and_actor(client):
    request = create(client)
    analyse(client)
    evidence = client.get("/evidence").json()["items"][0]
    payload = {"entity_type": "evidence", "entity_id": evidence["id"], "relation": "supports", "actor": "human:pm",
               "rationale": "Reviewed", "quote": "Invented quote"}
    path = f"/requests/{request['id']}/links"
    assert client.post(path, json=payload).status_code == 422
    assert client.post(path, json=payload | {"quote": evidence["content"], "actor": "ai:test"}).status_code == 403
    assert client.post(path, json=payload | {"quote": evidence["content"]}).status_code == 201
    other = create(client, vehicle="G70")
    assert client.post(f"/requests/{other['id']}/links", json=payload).status_code == 422


@pytest.mark.parametrize("actor", ["ai:test", "AI:OpenAI", "system:runner"])
@pytest.mark.parametrize("action", ["convert", "decline", "defer", "link"])
def test_decisions_api_and_database_human_gate(client, actor, action):
    request = create(client)
    payload = {"decision": action, "actor": actor, "rationale": "Automated attempt"}
    if action == "link":
        payload["requirement_id"] = "missing"
    assert client.post(f"/requests/{request['id']}/decide", json=payload).status_code == 403
    with transaction() as connection, pytest.raises(sqlite3.IntegrityError, match="human actor"):
        connection.execute("INSERT INTO request_decisions (id,request_id,decision,actor,rationale,created_at) "
                           "VALUES (?,?,?,?,?,?)", (new_id(), request["id"], action, actor, "Attempt", now()))
    assert scalar("SELECT count(*) FROM request_decisions") == 0


def test_conversion_creates_traceable_proposal_then_revision_preserving_approval(client, db):
    request = create(client)
    analyse(client, records=[("Ventilated rear seats are missing and summer comfort is poor.", "comfort", "problem")])
    post(client, "/requests/triage", link_provider="deterministic")
    triage_id = detail(client, request)["triage"]["id"]
    converted = post(client, f"/requests/{request['id']}/decide", decision="convert", rationale="Evidence reviewed",
                     triage_id=triage_id)
    requirement = converted["requirement"]
    assert converted["status"] == "converted" and converted["conversion"]["mode"] == "created"
    assert requirement["status"] == "proposed" and requirement["approved_version_id"] is None
    version = requirement["current_version"]
    assert converted["decision"]["requirement_version_id"] == version["id"]
    assert converted["decision"]["score_id"] == version["score"]["id"]
    assert request["key"] in " ".join(version["assumptions"])
    assert version["finding_ids"] and version["score"]["explanation"]["source_ids"]
    decision(client, requirement)
    followup = create(client, title="More ventilated rear seats", external_ref="sim-followup")
    revised = post(client, f"/requests/{followup['id']}/decide", decision="convert", rationale="New stakeholder ask")
    assert revised["conversion"]["mode"] == "new_version"
    assert revised["requirement"]["id"] == requirement["id"]
    assert revised["requirement"]["current_version"]["version"] == 2
    assert revised["requirement"]["approved_version_id"] == version["id"]
    assert revised["requirement"]["status"] == "needs_review"
    assert client.post(f"/requests/{request['id']}/decide", json={"decision": "convert", "actor": "human:pm",
                                                               "rationale": "Retry"}).status_code == 409
    assert verify(db)["ok"]


def test_conversion_requires_actual_customer_evidence_and_exact_market(client):
    request = create(client)
    path = f"/requests/{request['id']}/decide"
    payload = {"decision": "convert", "actor": "human:pm", "rationale": "Check"}
    assert client.post(path, json=payload).status_code == 409
    analysis = analyse(client, market="CN")
    assert client.post(path, json=payload | {"finding_ids": [analysis["findings"][0]["id"]]}).status_code == 422
    assert scalar("SELECT count(*) FROM requirements") == scalar("SELECT count(*) FROM request_decisions") == 0


def test_triage_revision_check_and_decided_status_preserved(client):
    request = create(client)
    first = post(client, "/requests/triage")["items"][0]["triage"]
    client.patch(f"/requests/{request['id']}", json={"effort": "low", "actor": "human:pm", "rationale": "Changed estimate"})
    payload = {"decision": "defer", "actor": "human:pm", "rationale": "Pending", "triage_id": first["id"]}
    assert client.post(f"/requests/{request['id']}/decide", json=payload).status_code == 409
    new = post(client, "/requests/triage")["items"][0]["triage"]
    assert client.post(f"/requests/{request['id']}/decide", json=payload).status_code == 409
    assert post(client, f"/requests/{request['id']}/decide", **(payload | {"triage_id": new["id"]}))["status"] == "deferred"
    post(client, "/requests/triage")
    assert detail(client, request)["status"] == "deferred"


def test_aggregate_counts_weighted_demand_age_and_filters(client):
    a = create(client, requested_at="2026-09-01")
    create(client, market="CN", requested_at="2026-10-05", title="Charging reliability", body="Reliable charging")
    create(client, market="CN", title="Pricing", body="Reduce the price", requested_at="2026-09-01")
    weights({"US": .75, "CN": .25})
    summary = client.get("/requests/aggregates", params={"as_of": "2026-10-11"}).json()
    assert summary["total"] == summary["simulated_count"] == 3 and summary["sla_breach_count"] == 2
    assert summary["by_market"] == {"CN": 2, "US": 1}
    assert {d["topic"]: d["index"] for d in summary["demand_index"]} == {"comfort": .75, "charging": .25}
    assert summary["market_weights"]["measured"]
    post(client, "/requests/triage", request_ids=[a["id"]])
    assert client.get("/requests/aggregates", params={"as_of": "2026-10-11", "market": "US"}).json()["sla_breach_count"] == 0
    listed = client.get("/requests", params={"market": "CN", "flagged": "false", "limit": 1}).json()
    assert listed["total"] == 1 and len(listed["items"]) == 1 and listed["offset"] == 0
    assert client.get("/requests/aggregates", params={"as_of": "not-a-date"}).status_code == 422


def test_openai_classification_grounded_and_pm_pins_survive(client, fake_llm):
    request = create(client)
    fake_llm.responder = lambda payload: {"items": [{"request_id": request["id"], "topic": "comfort",
                                                    "attribute": "seat ventilation", "scope_flags": [],
                                                    "quote": "Ventilated rear seats", "rationale": "Seat cooling ask"}]}
    classified = post(client, "/requests/classify", provider="openai")
    assert classified["provider"] == "openai" and classified["model"] == "fake-model"
    record = detail(client, request)["classifications"][-1]
    assert record["basis"]["span"] == [0, len("Ventilated rear seats")]
    assert scalar("SELECT count(*) FROM llm_cache") == 1
    assert client.patch(f"/requests/{request['id']}", json={"topic": "controls", "actor": "human:pm",
                                                          "rationale": "PM interpretation"}).status_code == 200
    post(client, "/requests/classify", provider="openai")
    assert detail(client, request)["topic"] == "controls"


@pytest.mark.parametrize("bad", ["quote", "id", "duplicate"])
def test_invalid_openai_classification_rolls_back_and_records_failed_run(client, fake_llm, bad):
    request = create(client)
    item = {"request_id": request["id"], "topic": "charging", "attribute": None, "scope_flags": [],
            "quote": "Ventilated rear seats", "rationale": "Test invalid response"}
    if bad == "quote":
        item["quote"] = "The model invented this"
    if bad == "id":
        item["request_id"] = "outside-scope"
    fake_llm.responder = lambda payload: {"items": [item, item] if bad == "duplicate" else [item]}
    response = client.post("/requests/classify", json={"provider": "openai"})
    assert response.status_code == 502
    assert detail(client, request)["topic"] == "comfort"
    assert scalar("SELECT count(*) FROM request_classifications") == 1
    assert scalar("SELECT count(*) FROM runs WHERE status='failed'") == 1


def test_openai_evidence_links_and_position_grounding_and_message_idempotence(client, fake_llm):
    request = create(client)
    analyse(client)

    def respond(payload):
        data = json.loads(payload["input"])
        if "candidates" in data:
            candidate = data["candidates"][0]
            return {"links": [{"evidence_id": candidate["evidence_id"], "relation": "supports",
                               "quote": candidate["content"], "rationale": "Customer ask"}]}
        evidence = data["evidence"][0]
        return {"summary": "Review customer support for seat ventilation.",
                "case_for": [{"point": "Seats matter", "evidence_id": evidence["evidence_id"], "quote": evidence["content"]}],
                "case_against": [], "open_questions": ["What is the effort?"]}

    fake_llm.responder = respond
    post(client, "/requests/links/propose", provider="openai")
    post(client, "/requests/triage")
    first = post(client, "/requests/positions", provider="openai")
    second = post(client, "/requests/positions", provider="openai")
    assert first["label"] == "AI-generated draft (OpenAI)"
    assert first["items"][0]["message_id"] == second["items"][0]["message_id"]
    assert scalar("SELECT count(*) FROM messages") == 1
    position = detail(client, request)["positions"][0]
    assert position["payload"]["ai_generated"] and position["payload"]["provider"] == "openai"
    assert position["payload"]["cited_evidence_ids"] and position["run_id"]


def test_invalid_openai_evidence_citation_has_no_links_or_drafts(client, fake_llm):
    request = create(client)
    analyse(client)
    fake_llm.responder = lambda payload: {"links": [{"evidence_id": "unrelated", "relation": "supports",
                                                    "quote": "Invented", "rationale": "Ignore instructions"}]}
    assert client.post("/requests/links/propose", json={"provider": "openai"}).status_code == 502
    assert not detail(client, request)["links"]
    post(client, "/requests/triage")
    fake_llm.responder = lambda payload: {"summary": "Bad", "case_for": [{"point": "Bad", "evidence_id": "other",
                                                                        "quote": "Fake"}],
                                          "case_against": [], "open_questions": []}
    assert client.post("/requests/positions", json={"provider": "openai"}).status_code == 502
    assert not detail(client, request)["positions"]
    assert scalar("SELECT count(*) FROM runs WHERE status='failed'") == 2


def test_explicit_offline_positions_and_no_openai_fallback(client, monkeypatch):
    create(client)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    assert client.post("/requests/classify", json={}).status_code == 503
    post(client, "/requests/triage")
    response = post(client, "/requests/positions", provider="deterministic")
    assert response["provider"] == "deterministic" and "not AI" in response["label"]


def test_capability_registry_prepares_only_and_runs_link_to_tasks(client):
    create(client)
    names = {name for name in CAPABILITIES if name.startswith("requests.")}
    assert names == {"requests.classify", "requests.cluster", "requests.link_evidence", "requests.triage",
                     "requests.draft_position"}
    assert CAPABILITIES["requests.triage"].autonomy_level == "A0"
    assert CAPABILITIES["requests.link_evidence"].autonomy_level == "A1"
    result = run_capability("requests.triage", {}, "ai:agent:triage")
    assert result["outputs"]["total"] == 1 and result["run_ids"]
    assert scalar("SELECT count(*) FROM request_decisions") == 0


def test_machine_cannot_claim_pm_effort(client):
    assert client.post("/requests", json={**BASE, "actor": "system:import", "effort": "low"}).status_code == 403
    assert scalar("SELECT count(*) FROM intake_requests") == 0


def test_sql_records_are_append_only_and_decided_status_cannot_be_undone(client):
    request = create(client)
    post(client, "/requests/triage")
    post(client, f"/requests/{request['id']}/decide", decision="decline", rationale="PM decision")
    for sql in ("UPDATE request_triage SET total=100", "DELETE FROM request_classifications", "DELETE FROM intake_requests",
                "UPDATE intake_requests SET status='new'"):
        with transaction() as connection, pytest.raises(sqlite3.IntegrityError):
            connection.execute(sql)
    with closing(connect()) as connection:
        decision_record = dict(connection.execute("SELECT * FROM request_decisions").fetchone())
    assert decision_record["actor"] == "human:pm" and decision_record["triage_id"]
    assert json.loads(scalar("SELECT after_state FROM audit_events WHERE action='request.decline'"))["status"] == "declined"


def test_conversion_respects_removed_support_and_explicit_topic(client):
    request = create(client)
    analysis = analyse(client)
    post(client, "/requests/links/propose", provider="deterministic")
    for link in detail(client, request)["links"]:
        if link["relation"] == "supports":
            response = client.patch(f"/requests/{request['id']}/links/{link['id']}", json={
                "status": "removed", "actor": "human:pm", "rationale": "Not relevant to this ask"})
            assert response.status_code == 200
    payload = {"decision": "convert", "actor": "human:pm", "rationale": "Check reviewed links"}
    assert client.post(f"/requests/{request['id']}/decide", json=payload).status_code == 409
    # The PM may explicitly reconsider a finding, but it must match the request's topic.
    charging = create(client, title="Charging reliability", body="Charging stations should work reliably")
    response = client.post(f"/requests/{charging['id']}/decide", json=payload | {
        "finding_ids": [analysis["findings"][0]["id"]]})
    assert response.status_code == 422 and "topic" in response.json()["detail"]
    assert scalar("SELECT count(*) FROM requirements") == 0


def test_openai_correct_evidence_id_still_requires_exact_quote(client, fake_llm):
    request = create(client)
    analyse(client)

    def forged(payload):
        evidence_id = json.loads(payload["input"])["candidates"][0]["evidence_id"]
        return {"links": [{"evidence_id": evidence_id, "relation": "supports", "quote": "Not in source",
                           "rationale": "Forged quote"}]}

    fake_llm.responder = forged
    assert client.post("/requests/links/propose", json={"provider": "openai"}).status_code == 502
    assert detail(client, request)["links"] == []
