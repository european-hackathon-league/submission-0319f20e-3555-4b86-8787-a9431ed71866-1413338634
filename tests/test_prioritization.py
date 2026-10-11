"""Prioritization v2 on synthetic, explicitly simulated scenarios; no BMW inputs and no network calls."""

import json
import sqlite3
from contextlib import closing

import pytest

from database.store import connect, encode, transaction
from server import prioritization as prio
from server.analysis_engine import TOPICS
from server.models import RUBRIC_V1, RUBRIC_V2, V2_DEFAULT_WEIGHTS, Weights
from server.platform import CAPABILITIES, record_run, run_capability
from tests.test_workflow import import_feedback

FACTORS = ("customer_impact", "market_relevance", "strategic_fit", "differentiation", "feasibility")
AS_OF = "2026-03-04"  # a Wednesday: the sentiment window is the Monday weeks 2026-01-12 … 2026-03-02
US = {"comfort": 4, "quietness": 2.5, "driving-experience": 2}  # all v1 factors equal per requirement
CN = {"comfort": 5, "quietness": 2, "range": 5}
EU = {"quietness": 4, "driving-experience": 4}
TEXT = {"range": "battery range anxiety on long trips"}  # "driving range" would also match driving-experience


def post(client, path, payload, code=201):
    response = client.post(path, json=payload)
    assert response.status_code == code, response.text
    return response.json()


def load_market(client, market, topics):
    import_feedback(client, [(f"Simulated: {TEXT.get(topic, TOPICS[topic][0].lower())} needs improvement", topic, "problem")
                             for topic in topics],
                    reference=f"simulated-{market}", market=market)
    result = post(client, "/pipeline/run", {"vehicle": "G60", "market": market, "provider": "deterministic"})
    return {req["topic"]: req for req in result["generation"]["requirements"]}


def set_factors(client, requirement, factors):
    response = client.patch(f"/requirements/{requirement['id']}", json={
        "expected_version_id": requirement["current_version_id"], "actor": "human:test",
        "rationale": "simulated factors", "factors": factors})
    assert response.status_code == 200, response.text
    return response.json()


def equal(value):
    return {factor: value for factor in FACTORS}


@pytest.fixture
def us(client):
    requirements = load_market(client, "US", US)
    return {topic: set_factors(client, requirements[topic], equal(value)) for topic, value in US.items()}


def approve(client, requirement):
    version = requirement["current_version"]
    return post(client, f"/requirements/{requirement['id']}/decisions", {
        "version_id": version["id"], "score_id": version["score"]["id"], "actor": "PM", "action": "approve",
        "rationale": "Reviewed"})["requirement"]


def insert_weights(shares):
    with record_run(None, "simulated.weights", "system:test", "sales-share-v1", {"simulated": True}) as run:
        with transaction() as connection:
            for market, share in shares.items():
                connection.execute("INSERT INTO market_weights (id,vehicle,market,period,units,share,evidence_ids,method_version,run_id,created_at) "
                                   "VALUES (?,?,?,?,?,?,?,?,?,?)",
                                   (f"weight-{market}", "G60", market, "2025", share * 100, share, '["sales-1"]',
                                    "sales-share-v1", run.id, "2026-01-01"))


def requirement_rows(market="US"):
    with closing(connect()) as connection:
        return {row["topic"]: dict(row) for row in connection.execute(
            "SELECT * FROM requirements WHERE vehicle='G60' AND market=?", (market,))}


def switch(client, rubric=RUBRIC_V2, actor="PM", code=201, **extra):
    return post(client, "/priorities/rubric", {"vehicle": "G60", "market": "US", "rubric_version": rubric, "actor": actor,
                                               "rationale": "Use data-derived factors", "as_of": AS_OF, **extra}, code)



def scored_import(client, kind, rows, reference):
    """Import simulated records with observation dates and record sentiment scores for them (driving-experience)."""
    post(client, "/imports/records", {
        "title": reference, "reference": reference, "kind": kind, "vehicle": "G60", "market": "US",
        "records": [{"content": f"Simulated {reference} {index}: driving feel", "observed_at": observed,
                     "location": {"row": index + 2}, "metadata": {"topic": "driving-experience", "provenance": reference}}
                    for index, (observed, *_rest) in enumerate(rows)]})
    with record_run(None, "simulated.sentiment", "system:test", "simulated-v1", {"reference": reference}) as run:
        with transaction() as connection:
            for index, (_observed, polarity, label, *method) in enumerate(rows):
                evidence_id = connection.execute("SELECT id FROM evidence WHERE content=?",
                                                 (f"Simulated {reference} {index}: driving feel",)).fetchone()[0]
                connection.execute("INSERT INTO sentiment_scores (id,subject_type,subject_id,topic,method_version,polarity,"
                                   "label,aspects,input_hash,run_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                   (f"{reference}-{index}", "evidence", evidence_id, "driving-experience",
                                    method[0] if method else "lexicon-v1", polarity, label, "[]", "h", run.id, "t"))


BMW_SENTIMENT = [("2026-01-05", -1.0, "negative"),                                   # before the 8-week window
                 ("2026-02-16", .04, "positive"), ("2026-02-17", .04, "positive"),
                 ("2026-02-23", 0.0, "neutral"), ("2026-02-24", 0.0, "neutral"),
                 ("2026-03-02", -.04, "negative"), ("2026-03-03", -.04, "negative"),
                 ("2026-03-03", .9, "positive", "openai:other:v1")]                     # another method, not mixed
PUBLIC_SENTIMENT = [("2026-03-02", -.5, "negative")] * 5


def insert_requests(rows):
    """rows: (id, market, topic, status, scope_flags, triage) with triage = None | total | (factors, weights)."""
    with record_run(None, "simulated.requests", "system:test", "simulated-v1", {"simulated": True}) as run:
        with transaction() as connection:
            for number, (request_id, market, topic, status, flags, triage) in enumerate(rows, 1):
                connection.execute(
                    "INSERT INTO intake_requests (id,key,vehicle,market,origin_type,origin_name,title,body,topic,requested_at,"
                    "simulated,scope_flags,status,created_by,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (request_id, f"MR-G60-{market}-{number:04d}", "G60", market, "market_org", "simulated", request_id,
                     f"Simulated request {request_id}", topic, "2026-02-01", 1, encode(flags), status, "human:test", "t", "t"))
                if triage is not None:
                    factors, weights = triage if isinstance(triage, tuple) else ({}, {})
                    total = triage if not isinstance(triage, tuple) else 0
                    connection.execute("INSERT INTO request_triage VALUES (?,?,?,?,?,?,?,?,?)",
                                       (f"triage-{request_id}", request_id, "request-triage-v1", encode(factors),
                                        encode(weights), total, "{}", run.id, "t"))


REQUESTS = [("r-us", "US", "driving-experience", "triaged", [], 80),                       # 0–100 total → 4.0
            ("r-cn", "CN", "driving-experience", "triaged", [], ({"a": 4, "b": 2}, {"a": .5, "b": .5})),  # → 3.0
            ("r-declined", "US", "driving-experience", "declined", [], 90),
            ("r-pricing", "US", "driving-experience", "triaged", ["pricing"], 90),
            ("r-new", "US", "driving-experience", "new", [], None),
            ("r-comfort", "US", "comfort", "triaged", [], 3)]


def derive(client, **extra):
    return post(client, "/priorities/inputs/derive", {"vehicle": "G60", "market": "US", "as_of": AS_OF,
                                                      "actor": "ai:agent:prioritizer", **extra})


def by_topic(result):
    return {item["topic"]: item for item in result["items"]}


# Weights and pure formulas ------------------------------------------------------------------------

def test_weights_keep_v1_payloads_and_add_v2():
    assert Weights().model_dump() == {"customer_impact": .35, "market_relevance": .25, "strategic_fit": .2,
                                      "differentiation": .1, "feasibility": .1}
    assert Weights().rubric_version == RUBRIC_V1
    assert Weights(**V2_DEFAULT_WEIGHTS).rubric_version == RUBRIC_V2
    assert Weights(**V2_DEFAULT_WEIGHTS).model_dump() == V2_DEFAULT_WEIGHTS
    assert abs(sum(V2_DEFAULT_WEIGHTS.values()) - 1) < 1e-9
    with pytest.raises(ValueError, match="need market_demand"):
        Weights(**{**Weights().model_dump(), "customer_impact": .25, "market_demand": .1})
    with pytest.raises(ValueError, match="sum to 1"):
        Weights(**{**V2_DEFAULT_WEIGHTS, "market_demand": .5})


def test_weekly_momentum_is_n_weighted_least_squares():
    assert prio.weekly_momentum([(0, 1, 0.0), (1, 1, 1.0)]) == pytest.approx(1.0)
    # n-weighting pulls the line toward the heavy week: unweighted slope 0.5, weighted 1.25 / 2.75.
    assert prio.weekly_momentum([(0, 1, 0.0), (1, 1, 1.0), (2, 2, 1.0)]) == pytest.approx(1.25 / 2.75)
    assert prio.weekly_momentum([(3, 5, -.2)]) is None
    assert prio.weekly_momentum([(0, 0, 1.0), (1, 4, .1)]) is None


def test_week_labels_match_sqlite_monday_weeks():
    from datetime import date
    with closing(sqlite3.connect(":memory:")) as connection:
        for day in ("2026-01-01", "2026-01-05", "2026-03-04", "2024-01-01", "2023-12-31"):
            label = connection.execute("SELECT strftime('%Y-%W', ?)", (day,)).fetchone()[0]
            monday = prio.week_monday(label)
            assert monday.weekday() == 0 and 0 <= (date.fromisoformat(day) - monday).days < 7, (day, label)
    assert prio.week_monday("bad") is None


def test_sensitivity_is_deterministic_and_flags_unstable_ranks():
    weights = Weights().model_dump()

    def item(name, values):
        return {"requirement_id": name, "score_id": f"s-{name}", "factors": dict(zip(FACTORS, values)), "weights": weights}

    items = [item("x", (0, 0, 5, 0, 0)), item("c1", (2.9, 0, 0, 0, 0)), item("c2", (0, 4.1, 0, 0, 0)),
             item("c3", (2.8, 0, 0, 0, 0)), item("c4", (0, 3.95, 0, 0, 0)), item("top", (5, 5, 5, 5, 5))]
    first, second = prio.sensitivity_analysis(items, weights), prio.sensitivity_analysis(list(reversed(items)), weights)
    assert first == second
    scenarios, top, results = first
    assert top == ["customer_impact", "market_relevance"]
    assert len(scenarios) == 1 + 2 * 5 + 4  # base, one-at-a-time ±20 %, the 4 new cells of the 3×3 grid
    assert results["top"] == {"score_id": "s-top", "rank": 1, "min_rank": 1, "max_rank": 1, "rank_range": 0, "stable": True,
                              "best_scenario": "base", "worst_scenario": "base"}
    assert results["x"]["rank"] == 4 and (results["x"]["min_rank"], results["x"]["max_rank"]) == (2, 6)
    assert not results["x"]["stable"] and results["x"]["best_scenario"] == "strategic_fit+20%"
    assert prio.competition_ranks({"a": 1.0, "b": 1.00001, "c": 2}) == {"a": 2, "b": 2, "c": 1}


# Derivations on fixtures --------------------------------------------------------------------------

def test_v1_stays_default_and_untouched(client, us):
    ranking = client.get("/priorities/ranking").json()
    assert ranking["rubric"]["default"] and ranking["rubric"]["rubric_version"] == RUBRIC_V1
    assert [(item["topic"], item["rank"], item["total"], item["rubric_version"]) for item in ranking["items"]] == [
        ("comfort", 1, 80.0, RUBRIC_V1), ("quietness", 2, 50.0, RUBRIC_V1), ("driving-experience", 3, 40.0, RUBRIC_V1)]
    assert all(item["v2_preview"]["not_derived"] == list(prio.DERIVED_FACTORS) for item in ranking["items"])
    # Deriving inputs in a v1 scope records them but never rescores.
    result = derive(client)
    assert result["rubric_version"] == RUBRIC_V1 and result["written"] == 9 and result["rescored"] == []
    assert derive(client)["written"] == 0  # identical derivations are reused, not duplicated
    with closing(connect()) as connection:
        assert {row[0] for row in connection.execute("SELECT rubric_version FROM scores")} == {RUBRIC_V1}
    # v1 rescoring payloads keep working unchanged.
    comfort = client.get(f"/requirements/{us['comfort']['id']}").json()
    scored = post(client, f"/requirements/{comfort['id']}/scores", {
        "expected_version_id": comfort["current_version_id"], "actor": "PM", "rationale": "Reweight",
        "weights": {"customer_impact": .2, "market_relevance": .2, "strategic_fit": .2, "differentiation": .2,
                    "feasibility": .2}})
    assert scored["rubric_version"] == RUBRIC_V1 and scored["total"] == 80.0


def test_market_demand_formula_with_sales_weights(client, us):
    for market, topics in (("CN", CN), ("EU", EU)):
        requirements = load_market(client, market, topics)
        for topic, value in topics.items():
            set_factors(client, requirements[topic], equal(value))
    without = by_topic(derive(client))
    demand = without["comfort"]["inputs"]["market_demand"]
    assert (demand["value"], demand["measured"]) == (2.5, False)
    assert "market_weights_missing_equal_shares" in demand["flags"] and "not_measured" in demand["flags"]
    assert demand["summary"]["equal_share_index"] == pytest.approx(.6667) and demand["summary"]["demand_index"] is None

    insert_weights({"US": .5, "CN": .3, "EU": .2})
    items = by_topic(derive(client))
    values = {topic: items[topic]["inputs"]["market_demand"]["value"] for topic in items}
    assert values == {"comfort": 4.0, "quietness": pytest.approx(3.1625), "driving-experience": 2.25}
    with closing(connect()) as connection:
        row = connection.execute("SELECT * FROM priority_inputs WHERE id=?",
                                 (items["quietness"]["inputs"]["market_demand"]["priority_input_id"],)).fetchone()
    derivation = json.loads(row["derivation"])
    assert row["method_version"] == "market-demand-v1" and derivation["measured"]
    assert {item["market"]: item["normalised_priority"] for item in derivation["inputs"]["markets"]} == {
        "CN": .4, "EU": 1.0, "US": .625}
    assert derivation["source_ids"]["market_weight_ids"] == ["weight-CN", "weight-EU", "weight-US"]
    assert derivation["source_ids"]["sales_evidence_ids"] == ["sales-1"]
    assert len(derivation["source_ids"]["requirement_ids"]) == 8 and derivation["formula"] == prio.DEMAND_FORMULA


def test_sentiment_momentum_formula_public_cap_and_low_n(client, us):
    scored_import(client, "feedback", BMW_SENTIMENT[:3], "bmw-low")
    low = by_topic(derive(client))["driving-experience"]["inputs"]["sentiment_momentum"]
    assert (low["value"], low["measured"]) == (2.5, False) and "bmw_evidence_low_n" in low["flags"]

    scored_import(client, "feedback", BMW_SENTIMENT[3:], "bmw-rest")
    scored_import(client, "web", PUBLIC_SENTIMENT, "public")
    item = by_topic(derive(client))["driving-experience"]["inputs"]["sentiment_momentum"]
    assert item["measured"] and item["value"] == pytest.approx(2.875)
    with closing(connect()) as connection:
        derivation = json.loads(connection.execute("SELECT derivation FROM priority_inputs WHERE id=?",
                                                   (item["priority_input_id"],)).fetchone()[0])
    bmw, public = derivation["inputs"]["groups"]["bmw_evidence"], derivation["inputs"]["groups"]["public_web"]
    assert (bmw["n"], bmw["negative_share"], bmw["slope_per_week"], bmw["trend_score"]) == (6, .3333, -.04, 3.5)
    assert bmw["method_version"] == "lexicon-v1" and bmw["other_methods"] == {"openai:other:v1": 1}
    assert (public["n"], public["value"], public["flags"]) == (5, 3.75, ["trend_not_measured"])
    assert derivation["inputs"]["public_share"] == .25 and derivation["inputs"]["public_label"] == prio.PUBLIC_LABEL
    assert len(derivation["source_ids"]["bmw_evidence_ids"]) == 6  # the out-of-window point is excluded
    assert len(derivation["source_ids"]["public_imported_evidence_ids"]) == 5
    assert derivation["inputs"]["window"]["start"] == "2026-01-12" and derivation["inputs"]["window"]["end"] == "2026-03-08"
    # Other topics have no sentiment: neutral, flagged, never zero.
    comfort = by_topic(derive(client))["comfort"]["inputs"]["sentiment_momentum"]
    assert (comfort["value"], comfort["measured"]) == (2.5, False)


def test_request_pressure_formula_and_exclusions(client, us):
    nothing = by_topic(derive(client))["driving-experience"]["inputs"]["request_pressure"]
    assert (nothing["value"], nothing["measured"]) == (2.5, False)
    assert "no_triaged_requests_for_vehicle" in nothing["flags"]
    insert_requests(REQUESTS)
    items = by_topic(derive(client))
    pressure = items["driving-experience"]["inputs"]["request_pressure"]
    assert pressure["measured"] and pressure["value"] == pytest.approx(2.5167)
    with closing(connect()) as connection:
        derivation = json.loads(connection.execute("SELECT derivation FROM priority_inputs WHERE id=?",
                                                   (pressure["priority_input_id"],)).fetchone()[0])
    assert derivation["source_ids"]["request_ids"] == ["r-cn", "r-us"]
    assert {item["request_id"]: (item["weight"], item["triage_intensity"], item["intensity_basis"])
            for item in derivation["inputs"]["requests"]} == {"r-us": (1.0, 4.0, "total_0_100"),
                                                              "r-cn": (.5, 3.0, "factors_x_weights")}
    assert derivation["inputs"]["excluded"] == {"declined": ["r-declined"], "out_of_scope": ["r-pricing"],
                                                "untriaged": ["r-new"]}
    assert "includes_simulated_requests" in derivation["flags"]
    quiet = items["quietness"]["inputs"]["request_pressure"]
    assert (quiet["value"], quiet["measured"], quiet["flags"]) == (0.0, True, ["no_triaged_requests_for_topic"])


# Rubric switch (human gate) -----------------------------------------------------------------------

@pytest.mark.parametrize("actor", ["ai:agent:prioritizer", "system:scheduler", "AI:robot"])
def test_ai_actors_cannot_switch_rubric(client, us, actor):
    response = client.post("/priorities/rubric", json={"vehicle": "G60", "market": "US", "rubric_version": RUBRIC_V2,
                                                       "actor": actor, "rationale": "Agent wants v2"})
    assert response.status_code == 403, response.text
    with closing(connect()) as connection:
        assert connection.execute("SELECT count(*) FROM scope_rubrics").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM priority_inputs").fetchone()[0] == 0


def test_database_gates_scope_rubrics(db):
    with pytest.raises(sqlite3.IntegrityError, match="human actor"), transaction() as connection:
        connection.execute("INSERT INTO scope_rubrics VALUES ('x','G60','US',?,?,'ai:agent:x','r','t')",
                           (RUBRIC_V2, encode(V2_DEFAULT_WEIGHTS)))
    with pytest.raises(sqlite3.IntegrityError, match="customer-priority-v1 or customer-priority-v2"), \
            transaction() as connection:
        connection.execute("INSERT INTO scope_rubrics VALUES ('x','G60','US','custom-v9','{}','PM','r','t')")


def test_switch_rescores_and_reviews_only_changed_approved_scores(client, us):
    comfort, quiet = approve(client, us["comfort"]), approve(client, us["quietness"])
    result = switch(client)
    assert result["changed"] and result["rubric_version"] == RUBRIC_V2 and result["weights"] == V2_DEFAULT_WEIGHTS
    assert result["previous"]["default"] and result["run_id"] and result["audit_event_id"]
    entries = {entry["key"]: entry for entry in result["rescored"]}
    rows = requirement_rows()
    # v2 defaults give the PM-judged factors 0.70 and the derived ones 0.30 (all neutral 2.5 here):
    # comfort 80 → 4×0.7×20 + 2.5×0.3×20 = 71 (approved, changed → review); quietness 50 → 50 (approved, unchanged);
    # driving-experience 40 → 43 (changed, not approved → no review).
    assert {topic: entries[row["key"]]["total"] for topic, row in rows.items()} == {
        "comfort": 71.0, "quietness": 50.0, "driving-experience": 43.0}
    assert entries[rows["quietness"]["key"]]["changed"] is False and entries[rows["quietness"]["key"]]["review_id"] is None
    assert entries[rows["driving-experience"]["key"]]["review_id"] is None
    assert result["reviews_opened"] == [entries[rows["comfort"]["key"]]["review_id"]]
    assert rows["comfort"]["status"] == "needs_review" and rows["quietness"]["status"] == "approved"
    assert rows["comfort"]["approved_score_id"] == comfort["approved_score_id"]  # approval itself is untouched
    assert rows["quietness"]["approved_score_id"] == quiet["approved_score_id"]

    ranking = client.get("/priorities/ranking").json()
    assert ranking["rubric"]["rubric_version"] == RUBRIC_V2 and not ranking["rubric"]["default"]
    top = ranking["items"][0]
    assert top["topic"] == "comfort" and top["rubric_version"] == RUBRIC_V2 and top["needs_review"]
    derived = {factor["factor"]: factor for factor in top["factors"] if factor["source"] == "derived"}
    assert set(derived) == set(prio.DERIVED_FACTORS)
    assert all(factor["value"] == 2.5 and not factor["measured"] and "not_measured" in factor["flags"]
               and factor["derivation"]["formula"] for factor in derived.values())
    assert top["not_measured"] == list(prio.DERIVED_FACTORS) and ranking["warnings"]

    with closing(connect()) as connection:
        audit = connection.execute("SELECT * FROM audit_events WHERE action='priorities.rubric_switched'").fetchone()
        assert audit["actor"] == "PM" and connection.execute("SELECT count(*) FROM scope_rubrics").fetchone()[0] == 1
    assert switch(client)["changed"] is False  # same rubric and weights: no new row, no rescoring
    listing = client.get("/priorities/rubrics", params={"vehicle": "G60", "market": "US"}).json()
    assert [item["rubric_version"] for item in listing["items"]] == [RUBRIC_V1, RUBRIC_V2]
    assert listing["active"]["id"] == result["id"] and len(listing["history"]) == 1


def test_v2_scope_scores_new_versions_and_guards_rubric_mixing(client, us):
    switch(client)
    driving = client.get(f"/requirements/{us['driving-experience']['id']}").json()
    edited = set_factors(client, driving, equal(3))
    score = edited["current_version"]["score"]
    assert score["rubric_version"] == RUBRIC_V2 and score["total"] == pytest.approx(3 * .7 * 20 + 2.5 * .3 * 20)
    assert set(score["explanation"]["derived_inputs"]) == set(prio.DERIVED_FACTORS)
    with closing(connect()) as connection:
        assert connection.execute("SELECT count(*) FROM priority_inputs WHERE version_id=?",
                                  (edited["current_version_id"],)).fetchone()[0] == 3
    payload = {"expected_version_id": edited["current_version_id"], "actor": "PM", "rationale": "Reweight"}
    response = client.post(f"/requirements/{edited['id']}/scores", json={**payload, "weights": Weights().model_dump()})
    assert response.status_code == 409 and "POST /priorities/rubric" in response.json()["detail"]
    assert post(client, f"/requirements/{edited['id']}/scores", payload)["id"] == score["id"]  # scope weights, unchanged
    reweighted = post(client, f"/requirements/{edited['id']}/scores", {**payload, "weights": {
        **V2_DEFAULT_WEIGHTS, "customer_impact": .2, "request_pressure": .15}})
    assert reweighted["rubric_version"] == RUBRIC_V2 and reweighted["weights"]["request_pressure"] == .15

    # Switching back to v1 is also a human decision and restores v1 scores.
    back = switch(client, RUBRIC_V1)
    assert back["run_id"] is None and {entry["total"] for entry in back["rescored"]} == {80.0, 50.0, 60.0}


def test_derive_in_v2_scope_rescores_changed_values_and_reviews_approved(client, us):
    approve(client, us["comfort"])
    approve(client, us["quietness"])
    switch(client)
    first = derive(client)
    assert first["written"] == 0 and first["rescored"] == [] and first["reviews_opened"] == []
    insert_requests(REQUESTS)
    result = derive(client)
    items = by_topic(result)
    # comfort: one own-market request triaged 3/5 → 0.5×0.5... measured; quietness: measured 0 → both approved change.
    assert items["comfort"]["inputs"]["request_pressure"]["measured"]
    assert set(result["rescored"]) == {item["requirement_id"] for item in items.values()}
    assert len(result["reviews_opened"]) == 2 and items["driving-experience"]["review_id"] is None
    assert items["quietness"]["rescored"]["total"] == 50.0 - 2.5 * .1 * 20
    with closing(connect()) as connection:
        run = connection.execute("SELECT * FROM runs WHERE id=?", (result["run_id"],)).fetchone()
        assert run["capability"] == "priorities.derive_inputs" and run["actor"] == "ai:agent:prioritizer"
        assert run["status"] == "succeeded"
        assert connection.execute("SELECT count(*) FROM audit_events WHERE action='priorities.inputs_derived'").fetchone()[0] == 2


# Ranking extras -----------------------------------------------------------------------------------

def test_preserve_guard_warns_without_changing_scores(client, us):
    before = {item["topic"]: item["total"] for item in client.get("/priorities/ranking").json()["items"]}
    with record_run(None, "simulated.preserve", "system:test", "preserve-v1", {"simulated": True}) as run:
        with transaction() as connection:
            connection.execute("INSERT INTO preserve_attributes (id,vehicle,market,topic,label,evidence_ids,strength,method_version,run_id,created_at) "
                               "VALUES ('love-seats','G60','US','comfort','Seat comfort',"
                               "'[\"e1\"]',0.8,'preserve-v1',?,'t')", (run.id,))
            connection.execute("INSERT INTO preserve_attributes (id,vehicle,market,topic,label,evidence_ids,strength,method_version,run_id,created_at) "
                               "VALUES ('love-other','G60','CN','quietness','Quiet cabin',"
                               "'[]',0.9,'preserve-v1',?,'t')", (run.id,))
    items = by_topic(client.get("/priorities/ranking").json())
    assert {topic: item["total"] for topic, item in items.items()} == before
    warning = items["comfort"]["preserve_warnings"][0]
    assert warning["preserve_attribute_id"] == "love-seats" and warning["match"] == "topic"
    assert warning["message"] == "Customers love Seat comfort; confirm this requirement does not degrade it."
    # Keyword matches flag text that touches the attribute ("communicate comfortably"); other markets never apply.
    assert [(w["preserve_attribute_id"], w["match"]) for w in items["quietness"]["preserve_warnings"]] == [
        ("love-seats", "keyword:comfort")]
    assert not any(w["preserve_attribute_id"] == "love-other" for item in items.values() for w in item["preserve_warnings"])


def test_sensitivity_endpoint_records_and_marks_ranking(client, us):
    first = post(client, "/priorities/sensitivity", {"vehicle": "G60", "market": "US", "actor": "ai:agent:prioritizer"})
    second = post(client, "/priorities/sensitivity", {"vehicle": "G60", "market": "US", "actor": "ai:agent:prioritizer"})
    assert first["results"] == second["results"] and first["id"] != second["id"]
    assert first["rubric_version"] == RUBRIC_V1 and first["perturbation"]["each_weight"] == .2
    assert all(result["stable"] for result in first["results"].values())
    ranking = client.get("/priorities/ranking").json()
    assert ranking["sensitivity_id"] == second["id"]
    assert all(item["stability"]["current"] and item["stability"]["stable"] for item in ranking["items"])
    listed = client.get("/priorities/sensitivity", params={"vehicle": "G60", "market": "US", "limit": 1}).json()
    assert listed["total"] == 2 and listed["items"][0]["id"] == second["id"]
    # A changed score makes the old analysis stale, visibly.
    switch(client)
    assert not any(item["stability"]["current"] for item in client.get("/priorities/ranking").json()["items"])
    assert client.post("/priorities/sensitivity", json={"vehicle": "G60", "market": "CN", "actor": "PM"}).status_code == 422


def test_portfolio_matrix_patterns_and_conflicts(client, us):
    for market, topics in (("CN", CN), ("EU", EU)):
        requirements = load_market(client, market, topics)
        for topic, value in topics.items():
            set_factors(client, requirements[topic], equal(value))
    unweighted = client.get("/priorities/portfolio", params={"vehicle": "g60"}).json()
    assert unweighted["share_basis"] == "equal" and unweighted["warnings"]
    assert all(topic["pattern"] == "insufficient_data" for topic in unweighted["topics"])
    insert_weights({"US": .5, "CN": .3, "EU": .2})
    with record_run(None, "simulated.conflicts", "system:test", "simulated-v1", {}) as run:
        with transaction() as connection:
            connection.execute(
                "INSERT INTO market_conflicts (id,vehicle,topic,related_topic,markets,conflict_type,severity,metrics,"
                "evidence_ids,requirement_ids,recommendation,rationale,fingerprint,method_version,run_id,created_at) "
                "VALUES ('conflict','G60','comfort','quietness','[\"CN\",\"US\"]','direction_conflict','high','{}','{}',"
                "'[]','market_variant','simulated','fp','simulated-v1',?,'t')", (run.id,))
    result = client.get("/priorities/portfolio", params={"vehicle": "G60"}).json()
    assert result["markets"] == ["CN", "EU", "US"] and result["market_shares"] == {"CN": .3, "EU": .2, "US": .5}
    topics = {topic["topic"]: topic for topic in result["topics"]}
    assert {topic: (item["global_demand_index"], item["pattern"]) for topic, item in topics.items()} == {
        "comfort": (.8, "global_candidate"), "quietness": (.6325, "global_candidate"),
        "driving-experience": (.45, "global_candidate"), "range": (.3, "market_specific_candidate")}
    assert set(topics["comfort"]["cells"]) == {"CN", "US"} and topics["comfort"]["cells"]["US"]["v2_basis"] == "preview"
    assert [conflict["id"] for conflict in topics["quietness"]["conflicts"]] == ["conflict"]
    assert topics["range"]["conflicts"] == []


# Explanations (OpenAI interprets; never sets values) ----------------------------------------------

def test_explanation_template_baseline(client, us):
    switch(client)
    result = post(client, "/priorities/explain", {"vehicle": "G60", "market": "US", "provider": "deterministic",
                                                  "actor": "ai:agent:prioritizer"})
    assert result["ai_generated"] is False and result["method_version"] == prio.EXPLAIN_TEMPLATE and result["run_id"]
    first = result["items"][0]
    assert first["rank"] == 1 and first["cited_ids"][0] == first["score_id"]
    assert "not measured, neutral 2.5" in first["explanation"]


def test_explanation_openai_validated_and_recorded(client, us, fake_llm):
    ranking = client.get("/priorities/ranking").json()["items"]

    def responder(request):
        facts = json.loads(request["input"])["ranking"]
        return {"summary": "Comfort leads.", "items": [
            {"requirement_id": item["requirement_id"], "explanation": f"Ranks {item['rank']}.", "cited_ids": [item["score_id"]]}
            for item in facts]}

    fake_llm.responder = responder
    result = post(client, "/priorities/explain", {"vehicle": "G60", "market": "US", "limit": 2, "actor": "PM"})
    assert result["ai_generated"] and result["model"] == "fake-model"
    assert result["method_version"] == "openai:fake-model:priority-explanation-v1"
    assert [item["requirement_id"] for item in result["items"]] == [item["requirement_id"] for item in ranking[:2]]
    assert fake_llm.calls("/responses")[0]["text"]["format"]["name"] == "priority_explanation"
    with closing(connect()) as connection:
        metrics = json.loads(connection.execute("SELECT metrics FROM runs WHERE id=?", (result["run_id"],)).fetchone()[0])
        assert metrics["llm"]
    # Scores are untouched by the explanation.
    assert [item["total"] for item in client.get("/priorities/ranking").json()["items"]] == [item["total"] for item in ranking]

    fake_llm.responder = lambda request: {"summary": "x", "items": [
        {"requirement_id": item["requirement_id"], "explanation": "x", "cited_ids": ["invented-id"]}
        for item in json.loads(request["input"])["ranking"]]}
    response = client.post("/priorities/explain", json={"vehicle": "G60", "market": "US", "limit": 1, "actor": "PM"})
    assert response.status_code == 502
    with closing(connect()) as connection:
        assert connection.execute("SELECT status FROM runs WHERE capability='priorities.explain' "
                                  "ORDER BY started_at DESC,rowid DESC LIMIT 1").fetchone()[0] == "failed"


def test_explanation_openai_unconfigured_never_falls_back(client, us, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post("/priorities/explain", json={"vehicle": "G60", "market": "US", "actor": "PM"})
    assert response.status_code == 503


# Capabilities and listings ------------------------------------------------------------------------

def test_capabilities_registered_and_runnable_by_agents(client, us):
    assert {name: CAPABILITIES[name].autonomy_level for name in CAPABILITIES if name.startswith("priorities.")} == {
        "priorities.derive_inputs": "A0", "priorities.rank": "A0", "priorities.sensitivity": "A0",
        "priorities.explain": "A0"}
    ranked = run_capability("priorities.rank", {"vehicle": "G60", "market": "US"}, "ai:agent:prioritizer")
    assert ranked["outputs"]["rubric_version"] == RUBRIC_V1 and len(ranked["run_ids"]) == 1
    assert [item["topic"] for item in ranked["outputs"]["items"]] == ["comfort", "quietness", "driving-experience"]
    derived = run_capability("priorities.derive_inputs", {"vehicle": "G60", "market": "US", "as_of": AS_OF},
                             "ai:agent:prioritizer")
    assert derived["outputs"]["written"] == 9
    listing = client.get("/priorities/inputs", params={"vehicle": "G60", "market": "US", "factor": "market_demand",
                                                       "latest_only": True, "limit": 2}).json()
    assert listing["total"] == 3 and len(listing["items"]) == 2 and listing["items"][0]["derivation"]["formula"]
    assert "rubric switch" not in " ".join(CAPABILITIES)


async def test_mcp_tools_call_the_api_and_never_switch_rubrics():
    from mcp_server.priority_tools import register_priority_tools

    tools, calls = {}, []

    class Recorder:
        def tool(self):
            return lambda function: tools.setdefault(function.__name__, function)

    async def api_request(method, path, *, params=None, payload=None):
        calls.append((method, path, params, payload))
        return {}

    register_priority_tools(Recorder(), api_request, lambda value: value)
    assert set(tools) == {"get_priority_rubrics", "derive_priority_inputs", "list_priority_inputs", "get_priority_ranking",
                          "run_priority_sensitivity", "list_priority_sensitivity", "get_priority_portfolio",
                          "explain_priority_ranking"}
    for tool in tools.values():
        await tool()
    assert {(method, path) for method, path, _, _ in calls} == {
        ("GET", "/priorities/rubrics"), ("POST", "/priorities/inputs/derive"), ("GET", "/priorities/inputs"),
        ("GET", "/priorities/ranking"), ("POST", "/priorities/sensitivity"), ("GET", "/priorities/sensitivity"),
        ("GET", "/priorities/portfolio"), ("POST", "/priorities/explain")}
    assert all(payload["actor"] == "ai:mcp" for method, _, _, payload in calls if method == "POST")
