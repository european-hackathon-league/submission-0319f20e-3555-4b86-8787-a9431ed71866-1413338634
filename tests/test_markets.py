"""Synthetic market scenarios, explicitly simulated; no BMW inputs or network calls."""

import json
from contextlib import closing

import pytest

from database.integrity import verify
from database.store import connect, transaction
from server.markets import scan_directions
from server.platform import record_run
from tests.test_workflow import import_feedback

SCOPE = {"vehicle": "G60", "markets": ["CN", "EU", "US"]}
DETECT = {**SCOPE, "provider": "deterministic", "actor": "system:test"}
FACTORS = ("customer_impact", "market_relevance", "strategic_fit", "differentiation", "feasibility")


def post(client, path, payload, code=200):
    response = client.post(path, json=payload)
    assert response.status_code == code, response.text
    return response.json()


def run_pipeline(client, market):
    return post(client, "/pipeline/run", {"vehicle": "G60", "market": market, "provider": "deterministic"}, 201)


def load_market(client, market, rows):
    imported = import_feedback(client, [(text, topic, "problem") for text, topic in rows],
                               reference=f"simulated-{market}", market=market)
    return imported, run_pipeline(client, market)


@pytest.fixture
def scenario(client):
    rows = {
        "CN": [("Simulated: customers want more rear legroom", "comfort"),
               ("Simulated: customers want a quieter cabin", "quietness"),
               ("Simulated: storage access needs improvement", "access-storage"),
               ("Simulated: driving controls need improvement", "driving-experience")],
        "US": [("Simulated: customers want a louder exhaust", "driving-experience"),
               ("Simulated: storage access needs improvement", "access-storage"),
               ("Simulated: comfortable seats need improvement", "comfort"),
               ("Simulated: noise insulation needs improvement", "quietness")],
        "EU": [("Simulated: customers want a smaller car", "access-storage"),
               ("Simulated: comfortable seats need improvement", "comfort"),
               ("Simulated: noise insulation needs improvement", "quietness"),
               ("Simulated: driving controls need improvement", "driving-experience")],
    }
    loaded = {market: load_market(client, market, records) for market, records in rows.items()}
    # Deterministic equal scores isolate exactly the two intended direction tensions.
    for _, pipeline in loaded.values():
        for req in pipeline["generation"]["requirements"]:
            response = client.patch(f"/requirements/{req['id']}", json={
                "expected_version_id": req["current_version_id"], "actor": "human:test",
                "rationale": "simulated equal priorities", "factors": {factor: 3 for factor in FACTORS}})
            assert response.status_code == 200, response.text
    with record_run(None, "simulated.weights", "system:test", "sales-share-v1", {"simulated": True}) as run:
        with transaction() as connection:
            for market, share in (("CN", .45), ("US", .45), ("EU", .10)):
                connection.execute(
                    "INSERT INTO market_weights VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (f"weight-{market}", "G60", market, "2025", share * 100, share, "[]", "sales-share-v1", run.id,
                     "2026-01-01",))
    return loaded


def test_three_markets_exact_conflicts_recommendations_trace_and_idempotence(client, scenario, db):
    first = post(client, "/markets/conflicts/detect", DETECT, 201)
    assert {(item["conflict_type"], item["topic"], item["related_topic"], item["recommendation"])
            for item in first["items"]} == {
        ("direction_conflict", "driving-experience", "quietness", "selectable_mode"),
        ("direction_conflict", "comfort", "access-storage", "market_variant")}
    assert len(first["items"]) == 2 and first["awaiting_human"]
    second = post(client, "/markets/conflicts/detect", DETECT, 201)
    assert second["created"] == [] and second["superseded"] == []
    assert set(second["unchanged"]) == set(first["created"])
    for item in first["items"]:
        detail = client.get(f"/markets/conflicts/{item['id']}").json()
        assert detail["run_id"] == first["run_id"]
        assert all(detail["evidence_ids"][market] for market in detail["markets"])
        for records in detail["evidence"].values():
            for evidence in records:
                assert evidence["source_id"] and evidence["location"]
                for mention in evidence["mentions"]:
                    assert evidence["content"][slice(*mention["span"])] == mention["quote"]
    assert verify(db)["ok"]


def test_missing_data_is_visible_and_weights_are_explicit(client):
    matrix = post(client, "/markets/compare", {**SCOPE, "topics": ["comfort"]})
    assert matrix["weights"]["basis"] == "equal_fallback"
    assert "equal weights" in matrix["warnings"][0]
    assert matrix["audit_event_id"]
    assert matrix["topics"][0]["demand_index"] is None
    for cell in matrix["topics"][0]["cells"].values():
        assert cell["requirement"] is cell["score"] is cell["sentiment"] is cell["request_pressure"] is None
        assert cell["targets"] is None
        assert set(cell["missing"]) >= {"evidence", "requirement", "sentiment", "request_pressure"}


@pytest.mark.parametrize("actor", ["ai:agent:market-balancer", "system:scheduler", "AI:robot"])
def test_resolution_human_gate(client, scenario, actor):
    conflict = post(client, "/markets/conflicts/detect", DETECT, 201)["items"][0]
    post(client, f"/markets/conflicts/{conflict['id']}/resolve",
         {"actor": actor, "decision": "adopt_global", "rationale": "simulated review"}, 403)
    assert client.get(f"/markets/conflicts/{conflict['id']}").json()["status"] == "open"


@pytest.mark.parametrize("decision,status", [("selectable_mode", "resolved"), ("dismiss", "dismissed"), ("defer", "open")])
def test_resolution_is_idempotent_on_unchanged_detection(client, scenario, decision, status):
    first = post(client, "/markets/conflicts/detect", DETECT, 201)
    for conflict in first["items"]:
        resolution = post(client, f"/markets/conflicts/{conflict['id']}/resolve", {
            "actor": "human:test", "decision": decision, "rationale": "simulated customer review",
            "requirement_ids": conflict["requirement_ids"]}, 201)
        assert resolution["conflict"]["status"] == status and resolution["audit_event_id"]
    rerun = post(client, "/markets/conflicts/detect", DETECT, 201)
    assert rerun["created"] == [] and set(rerun["unchanged"]) == set(first["created"])
    assert rerun["awaiting_human"] is (status == "open")


def test_changed_evidence_supersedes_but_retains_history(client, scenario):
    first = post(client, "/markets/conflicts/detect", DETECT, 201)
    original = next(item for item in first["items"] if item["recommendation"] == "selectable_mode")
    import_feedback(client, [("Simulated: more US customers request a louder exhaust", "driving-experience", "problem")],
                    reference="simulated-US-new")
    run_pipeline(client, "US")
    rerun = post(client, "/markets/conflicts/detect", DETECT, 201)
    assert original["id"] in rerun["superseded"]
    current = next(item for item in rerun["items"] if item["fingerprint"] == original["fingerprint"])
    assert current["id"] != original["id"]
    detail = client.get(f"/markets/conflicts/{original['id']}").json()
    assert detail["status"] == "superseded" and detail["superseded_by"] == current["id"]
    assert len(detail["history"]) == 2
    post(client, f"/markets/conflicts/{original['id']}/resolve",
         {"actor": "human:test", "decision": "dismiss", "rationale": "old"}, 409)


def test_direction_terms_negation_and_longest_match():
    assert scan_directions("We do not want a louder exhaust")[0] == []
    matches, _ = scan_directions("We want a quieter exhaust and more rear legroom")
    assert [(m["attribute"], m["direction"]) for m in matches] == [
        ("driving-experience/exhaust-sound", "decrease"), ("comfort/rear-space", "increase")]


def test_openai_direction_grounding_cache_and_provenance(client, scenario, fake_llm):
    def respond(request):
        inputs = json.loads(request["input"])
        result = []
        for text in inputs["texts"]:
            for match in scan_directions(text["text"])[0]:
                result.append({"text_id": text["text_id"], **{k: match[k] for k in ("attribute", "direction", "quote")}})
        return {"mentions": result}
    fake_llm.responder = respond
    result = post(client, "/markets/directions", {**SCOPE, "provider": "openai"})
    assert result["provider"] == "openai" and result["model"] == "fake-model"
    assert result["mentions"] and result["audit_event_id"]
    calls = len(fake_llm.requests)
    post(client, "/markets/directions", {**SCOPE, "provider": "openai"})
    assert len(fake_llm.requests) == calls
    with closing(connect()) as connection:
        metrics = json.loads(connection.execute("SELECT metrics FROM runs WHERE id=?", (result["run_id"],)).fetchone()[0])
    assert metrics["llm"]["total_tokens"] > 0


def test_openai_ungrounded_direction_rejected_with_failed_run(client, scenario, fake_llm):
    fake_llm.responder = lambda request: {"mentions": [{"text_id": "outside-scope", "attribute": "quietness",
                                                       "direction": "increase", "quote": "invented"}]}
    post(client, "/markets/directions", {**SCOPE, "provider": "openai"}, 502)
    with closing(connect()) as connection:
        assert connection.execute("SELECT status FROM runs WHERE capability='markets.extract_directions'").fetchone()[0] == "failed"
        assert connection.execute("SELECT count(*) FROM market_conflicts").fetchone()[0] == 0


def test_openai_unconfigured_does_not_fallback(client, scenario, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    post(client, "/markets/conflicts/detect", SCOPE, 503)


def test_lists_rules_weights_and_pagination(client, scenario):
    created = post(client, "/markets/conflicts/detect", DETECT, 201)
    listing = client.get("/markets/conflicts", params={"vehicle": "g60", "market": "china", "limit": 1, "offset": 1}).json()
    assert listing["total"] == 2 and len(listing["items"]) == 1
    assert listing["items"][0]["id"] in created["created"]
    weights = client.get("/markets/weights?vehicle=g60&limit=1&offset=1").json()
    assert weights["total"] == 3 and len(weights["items"]) == 1
    assert weights["selected"]["period"] == "2025"
    assert client.get("/markets/rules").json()["thresholds"]["score_gap"] == 20


def test_priorities_target_rules_and_gap_thresholds(client, scenario):
    comparison = post(client, "/markets/compare", SCOPE)
    ids = {code: next(t for t in comparison["topics"] if t["topic"] == "comfort")["cells"][code]["requirement"]["id"]
           for code in ("CN", "US", "EU")}
    for code, factor, target in (("CN", 5, 100), ("US", 1, 50), ("EU", 3, 100)):
        req = client.get(f"/requirements/{ids[code]}").json()
        response = client.patch(f"/requirements/{req['id']}", json={
            "expected_version_id": req["current_version_id"], "actor": "human:test", "rationale": "simulated targets",
            "factors": {name: factor for name in FACTORS},
            "acceptance_criteria": [{"metric": "Customer comfort success", "target": target, "unit": "%",
                                     "basis": "PM assumption"}]})
        assert response.status_code == 200
    result = post(client, "/markets/conflicts/detect", DETECT, 201)
    by_type = {item["conflict_type"]: item for item in result["items"] if item["topic"] == "comfort"}
    assert by_type["priority_divergence"]["recommendation"] == "market_variant"
    assert by_type["priority_divergence"]["metrics"]["demand"]["demand_index"] == .60
    assert by_type["target_incompatible"]["recommendation"] == "market_variant"
    assert by_type["target_incompatible"]["metrics"]["groups"][0]["relative_difference"] == .5
    # A new top-ranked topic in one market exposes significant missing markets only.
    import_feedback(client, [("Simulated: public charging is unreliable", "charging", "problem")],
                    reference="simulated-charging", market="CN")
    run_pipeline(client, "CN")
    result = post(client, "/markets/conflicts/detect", {**DETECT, "topics": ["charging"]}, 201)
    gap = next(item for item in result["items"] if item["conflict_type"] == "evidence_gap")
    assert set(gap["metrics"]["gap_markets"]) == {"US"}
    assert gap["recommendation"] == "needs_research" and gap["evidence_ids"]["US"] == []
    # A restricted scan cannot supersede open conflicts outside its scope.
    comfort = client.get("/markets/conflicts?status=open&topic=comfort").json()
    assert comfort["total"] >= 2


def test_openai_brief_is_grounded_and_keeps_authoritative_rationale(client, scenario, fake_llm):
    conflict = post(client, "/markets/conflicts/detect", DETECT, 201)["items"][0]
    def respond(request):
        evidence = json.loads(request["input"])["evidence"][0]
        return {"summary": "Simulated market tension", "trade_off": "Customer preferences differ",
                "options": [{"option": "selectable_mode", "summary": "Offer selectable customer experiences",
                             "benefits": ["Choice"], "risks": ["Requires customer validation"]}], "open_questions": [],
                "citations": [{"evidence_id": evidence["evidence_id"], "quote": evidence["text"]}]}
    fake_llm.responder = respond
    result = post(client, f"/markets/conflicts/{conflict['id']}/brief", {"actor": "ai:test"})
    assert result["rationale"] == conflict["rationale"] and result["status"] == "open"
    brief = result["metrics"]["ai_brief"]
    assert brief["provider"] == "openai" and brief["model"] == "fake-model"
    assert brief["run_id"] == result["run_id"] and brief["citations"][0]["span"]
    rerun = post(client, "/markets/conflicts/detect", DETECT, 201)
    assert rerun["created"] == [] and conflict["id"] in rerun["unchanged"]


def test_detection_rejects_concurrent_input_change(client, scenario, fake_llm):
    def respond(request):
        req = scenario["US"][1]["generation"]["requirements"][0]
        current = client.get(f"/requirements/{req['id']}").json()
        response = client.patch(f"/requirements/{req['id']}", json={
            "expected_version_id": current["current_version_id"], "title": f"Simulated concurrent edit {len(fake_llm.requests)}",
            "actor": "human:test", "rationale": "simulated race"})
        assert response.status_code == 200
        return {"mentions": []}
    fake_llm.responder = respond
    post(client, "/markets/conflicts/detect", {**SCOPE, "provider": "openai"}, 409)
    with closing(connect()) as connection:
        assert connection.execute("SELECT count(*) FROM market_conflicts").fetchone()[0] == 0
        assert connection.execute("SELECT status FROM runs WHERE capability='markets.detect_conflicts'").fetchone()[0] == "failed"


def test_resolution_proposals_create_traceable_requirements_atomically(client):
    # Analyse the synthetic text without generating requirements, leaving room for market proposals.
    findings = {}
    for code, text, topic in (("CN", "Simulated: want a quieter cabin", "quietness"),
                              ("US", "Simulated: want a louder exhaust", "driving-experience")):
        import_feedback(client, [(text, topic, "problem")], reference=f"simulated-proposal-{code}", market=code)
        findings[code] = post(client, "/analyses", {"market": code}, 201)["findings"][0]["id"]
    conflict = post(client, "/markets/conflicts/detect", {**DETECT, "markets": ["CN", "US"]}, 201)["items"][0]
    proposal = {"market": "US", "topic": "driving-experience", "title": "Selectable driving sound",
                "statement": "Allow the driver to select the preferred sound experience",
                "customer_need": "Simulated customers want choice", "finding_ids": [findings["US"]],
                "acceptance_criteria": [{"metric": "Driver satisfaction", "target": 80, "unit": "%",
                                         "basis": "PM assumption"}], "factors": {name: 3 for name in FACTORS}}
    # A second invalid proposal rolls back the valid proposal and the resolution together.
    invalid = {**proposal, "market": "CN", "topic": "quietness"}
    post(client, f"/markets/conflicts/{conflict['id']}/resolve", {
        "actor": "human:test", "decision": "selectable_mode", "rationale": "reviewed synthetic evidence",
        "proposals": [proposal, invalid]}, 422)
    assert client.get("/requirements").json()["total"] == 0
    resolved = post(client, f"/markets/conflicts/{conflict['id']}/resolve", {
        "actor": "human:test", "decision": "selectable_mode", "rationale": "reviewed synthetic evidence",
        "proposals": [proposal]}, 201)
    requirement_id = resolved["created_requirement_ids"][0]
    trace = client.get(f"/requirements/{requirement_id}/trace").json()
    assert trace["findings"][0]["id"] == findings["US"]
    assert trace["evidence"]["items"]
    assert client.get(f"/requirements/{requirement_id}").json()["status"] == "proposed"
    events = client.get("/audit", params={"entity_id": requirement_id}).json()["items"]
    assert any(e["action"] == "requirement.market_resolution" and e["metadata"]["conflict_id"] == conflict["id"] for e in events)


def test_context_inputs_request_pressure_sentiment_methods_and_coverage(client, scenario):
    from database.store import encode
    with record_run(None, "simulated.context", "system:test", "simulated-v1", {"simulated": True}) as run:
        with transaction() as connection:
            connection.execute(
                "INSERT INTO intake_requests (id,key,vehicle,market,origin_type,origin_name,title,body,topic,requested_at,"
                "simulated,scope_flags,status,created_by,created_at,updated_at) VALUES "
                "('request','MR-G60-US-0001','G60','US','market_org','simulated','Louder exhaust',"
                "'Simulated: customers request a louder exhaust','driving-experience','2026-01-01',1,'[]','new',"
                "'human:test','t','t')")
            connection.execute("INSERT INTO request_triage VALUES ('triage','request','request-triage-v1','{}','{}',75,'{}',?,'t')",
                               (run.id,))
            connection.execute("INSERT INTO coverage_reports VALUES ('coverage','G60','US','{}',?, 'coverage-v1',?,'t')",
                               (encode(["Simulated single-source dominance"]), run.id))
            evidence = connection.execute("SELECT id FROM evidence WHERE market='US' ORDER BY id").fetchall()
            for index, row in enumerate(evidence):
                connection.execute(
                    "INSERT INTO sentiment_scores VALUES (?, 'evidence', ?, 'driving-experience', 'lexicon-v1',"
                    "-.5,'negative','[]','h',?,'t')", (f"sentiment-{index}", row[0], run.id))
            connection.execute(
                "INSERT INTO sentiment_scores VALUES ('openai-score','evidence',?,'driving-experience',"
                "'openai:fake:v1',1,'positive','[]','h',?,'t')", (evidence[0][0], run.id))
    comparison = post(client, "/markets/compare", SCOPE)
    assert comparison["sentiment_method_version"] == "lexicon-v1"
    assert any("not mixed" in text for text in comparison["warnings"])
    assert any("single-source dominance" in text for text in comparison["warnings"])
    cell = next(t for t in comparison["topics"] if t["topic"] == "driving-experience")["cells"]["US"]
    assert cell["request_pressure"]["count"] == cell["request_pressure"]["simulated"] == 1
    assert cell["request_pressure"]["mean_triage"] == 75
    assert cell["request_pressure"]["request_ids"] == ["request"]
    assert cell["sentiment"]["mean_polarity"] == -.5


def test_resolved_conflict_reopens_only_after_new_evidence(client, scenario):
    original = next(item for item in post(client, "/markets/conflicts/detect", DETECT, 201)["items"]
                    if item["recommendation"] == "selectable_mode")
    post(client, f"/markets/conflicts/{original['id']}/resolve",
         {"actor": "human:test", "decision": "dismiss", "rationale": "simulated decision"}, 201)
    import_feedback(client, [("Simulated: additional customers want a louder exhaust", "driving-experience", "problem")],
                    reference="simulated-more-US")
    run_pipeline(client, "US")
    result = post(client, "/markets/conflicts/detect", DETECT, 201)
    current = next(item for item in result["items"] if item["fingerprint"] == original["fingerprint"])
    assert current["id"] != original["id"] and current["status"] == "open"
    assert client.get(f"/markets/conflicts/{original['id']}").json()["status"] == "dismissed"


async def test_markets_mcp_tools_are_adapter_only_and_do_not_expose_resolution():
    from urllib.parse import quote

    from mcp_server.markets_tools import register_markets_tools
    calls, functions = [], {}
    class Recorder:
        def tool(self):
            def add(function):
                functions[function.__name__] = function
                return function
            return add
    async def api_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"ok": True}
    register_markets_tools(Recorder(), api_request, lambda value: quote(value, safe=""))
    assert len(functions) == 8 and not any("resolve" in name for name in functions)
    for name, function in functions.items():
        args = {"conflict_id": "id/with space"} if name in ("get_market_conflict", "draft_market_conflict_brief") else {}
        assert await function(**args) == {"ok": True}
    assert any(path == "/markets/conflicts/id%2Fwith%20space" for _, path, _ in calls)
    detect = next(call for call in calls if call[1] == "/markets/conflicts/detect")
    assert detect[2]["payload"]["provider"] == "openai" and detect[2]["payload"]["actor"] == "ai:mcp"


def test_openai_includes_chinese_evidence_without_english_keyword_filter(client, fake_llm):
    load_market(client, "CN", [("模拟：希望后排腿部空间更大。", "comfort")])
    seen = []
    def respond(request):
        texts = json.loads(request["input"])["texts"]
        seen.extend(texts)
        return {"mentions": [{"text_id": text["text_id"], "attribute": "comfort/rear-space",
                               "direction": "increase", "quote": "后排腿部空间更大"}
                              for text in texts if "后排腿部空间更大" in text["text"]]}
    fake_llm.responder = respond
    result = post(client, "/markets/directions", {**SCOPE, "topics": ["comfort"], "provider": "openai"})
    assert any("模拟" in text["text"] for text in seen)
    assert any(mention["subject_type"] == "evidence" for mention in result["mentions"])


def test_narrow_topics_actually_bound_openai_inputs(client, scenario, fake_llm):
    seen = []
    def respond(request):
        seen.extend(json.loads(request["input"])["texts"])
        return {"mentions": []}
    fake_llm.responder = respond
    result = post(client, "/markets/directions", {**SCOPE, "topics": ["access-storage"], "provider": "openai"})
    assert result["texts_scanned"] == 12
    assert not any("louder exhaust" in text["text"] or "more rear legroom" in text["text"] for text in seen)
