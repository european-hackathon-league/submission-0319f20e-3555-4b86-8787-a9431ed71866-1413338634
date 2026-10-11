"""Pod H: the platform evaluation's metric functions on toy data, its fixtures, and its HTTP error mapping.

No network: metric functions are pure, HTTP helpers use httpx.MockTransport, and the smoke test runs the
whole evaluation in-process against the API on a temporary database.
"""

import json

import httpx
import pytest

from scripts import evaluate_platform as ev

# Classification -------------------------------------------------------------------------------------------


def test_accuracy_counts_matches_and_rejects_length_mismatch():
    assert ev.accuracy(["a", "b", "c", "d"], ["a", "b", "x", None]) == 0.5
    assert ev.accuracy([], []) is None
    with pytest.raises(ValueError):
        ev.accuracy(["a"], [])


def test_classification_report_macro_f1_on_toy_labels():
    gold = ["pos", "pos", "neg", "neg", "neu"]
    predicted = ["pos", "neg", "neg", "neg", None]       # None: the system did not score that item
    report = ev.classification_report(gold, predicted, ["pos", "neg", "neu", "mixed"])
    classes = report["classes"]
    assert set(classes) == {"pos", "neg", "neu"}          # 'mixed' occurs on neither side: undefined, left out
    assert classes["pos"] == {"support": 2, "predicted": 1, "precision": 1.0, "recall": 0.5, "f1": pytest.approx(2 / 3)}
    assert classes["neg"]["precision"] == pytest.approx(2 / 3) and classes["neg"]["recall"] == 1.0
    assert classes["neu"] == {"support": 1, "predicted": 0, "precision": None, "recall": 0.0, "f1": 0.0}
    assert report["macro_f1"] == pytest.approx((2 / 3 + 0.8 + 0.0) / 3)


def test_classification_report_without_labels_uses_observed_values():
    report = ev.classification_report(["a", "b"], ["a", "a"])
    assert list(report["classes"]) == ["a", "b"] and report["classes"]["b"]["f1"] == 0.0


def test_confusion_matrix_rows_are_gold_labels():
    assert ev.confusion(["pos", "pos", "neg"], ["pos", "neg", None]) == {"neg": {"None": 1}, "pos": {"neg": 1, "pos": 1}}


# Sets, pairs and clusters ---------------------------------------------------------------------------------


def test_precision_recall_marks_undefined_values_as_none():
    assert ev.precision_recall({1, 2, 3}, {2, 3, 4}) == {
        "true_positive": 2, "false_positive": 1, "false_negative": 1,
        "precision": pytest.approx(2 / 3), "recall": pytest.approx(2 / 3), "f1": pytest.approx(2 / 3)}
    empty = ev.precision_recall(set(), set())
    assert empty["precision"] is None and empty["recall"] is None and empty["f1"] is None
    assert ev.precision_recall({1}, set())["precision"] is None


def test_cluster_pairs_treat_none_as_singleton():
    pairs = ev.cluster_pairs({"r1": "A", "r2": "A", "r3": "A", "r4": None, "r5": None, "r6": "B"})
    assert pairs == {frozenset(p) for p in (("r1", "r2"), ("r1", "r3"), ("r2", "r3"))}


def test_pairwise_clustering_on_toy_assignment():
    gold = {"r1": "legroom", "r2": "legroom", "r3": "legroom", "r4": "exhaust", "r5": "exhaust", "r6": "solo"}
    predicted = {"r1": "c1", "r2": "c1", "r3": "c2", "r4": "c2", "r5": "c2", "extra": "c1"}   # r6 missing, extra ignored
    result = ev.pairwise_clustering(gold, predicted)
    # gold pairs: r1r2 r1r3 r2r3 r4r5 (4); predicted pairs over gold items: r1r2 r3r4 r3r5 r4r5 (4)
    assert (result["true_positive"], result["false_positive"], result["false_negative"]) == (2, 2, 2)
    assert result["precision"] == 0.5 and result["recall"] == 0.5
    assert result["gold_pairs"] == 4 and result["predicted_pairs"] == 4 and result["missing_items"] == ["r6"]


def test_pairwise_clustering_all_singletons_has_undefined_precision():
    result = ev.pairwise_clustering({"a": 1, "b": 1}, {"a": "x", "b": "y"})
    assert result["precision"] is None and result["recall"] == 0.0


# Conflicts ----------------------------------------------------------------------------------------------


def test_conflict_key_ignores_attributes_and_topic_order():
    first = ev.conflict_key({"conflict_type": "direction_conflict", "topic": "quietness",
                             "related_topic": "driving-experience/exhaust-sound"})
    second = ev.conflict_key({"conflict_type": "direction_conflict", "topics": ["driving-experience", "quietness"]})
    assert first == second == ("direction_conflict", ("driving-experience", "quietness"))
    assert ev.key_label(first) == "direction_conflict:driving-experience+quietness"


def test_score_conflicts_precision_recall_markets_and_control():
    gold = [{"conflict_type": "direction_conflict", "topics": ["driving-experience", "quietness"], "markets": ["CN", "US"],
             "acceptable_recommendations": ["selectable_mode"]},
            {"conflict_type": "priority_divergence", "topics": ["comfort"], "markets": ["CN", "US"],
             "acceptable_recommendations": ["market_variant"]}]
    predicted = [
        {"conflict_type": "direction_conflict", "topic": "driving-experience", "related_topic": "quietness",
         "markets": ["CN", "US"], "recommendation": "selectable_mode", "evidence_ids": {"CN": ["e1"], "US": ["e2"]}},
        {"conflict_type": "priority_divergence", "topic": "connectivity", "markets": ["EU", "US"],
         "recommendation": "pm_tradeoff", "evidence_ids": {"EU": ["e3"], "US": []}}]
    result = ev.score_conflicts(gold, predicted, control_topic="connectivity")
    assert result["precision"] == 0.5 and result["recall"] == 0.5
    assert result["market_coverage"] == 1.0 and result["recommendation_agreement"] == 1.0
    assert result["evidence_per_market"] == 0.5               # the second has no US evidence
    assert result["control_topic_clean"] is False
    assert result["false_positive_keys"] == ["priority_divergence:connectivity"]
    assert result["false_negative_keys"] == ["priority_divergence:comfort"]


def test_score_conflicts_unites_markets_of_rows_with_one_key():
    gold = [{"conflict_type": "priority_divergence", "topics": ["comfort"], "markets": ["CN", "EU", "US"],
             "acceptable_recommendations": ["market_variant"]}]
    rows = [{"conflict_type": "priority_divergence", "topic": "comfort", "markets": ["CN", "US"]},
            {"conflict_type": "priority_divergence", "topic": "comfort", "markets": ["EU", "US"],
             "recommendation": "market_variant"}]
    result = ev.score_conflicts(gold, rows, control_topic="design")
    assert result["true_positive"] == 1 and result["false_positive"] == 0
    assert result["market_coverage"] == 1.0 and result["recommendation_agreement"] == 1.0 and result["control_topic_clean"]


# Scope flags and topics -----------------------------------------------------------------------------------


def test_normalise_flags_maps_synonyms_and_objects():
    assert ev.normalise_flags(["Price", {"flag": "Type approval"}, "engineering-specification"]) == {
        "pricing", "homologation", "engineering_spec"}
    assert ev.normalise_flags(None) is None and ev.normalise_flags([]) == frozenset()


def test_score_scope_flags_exact_binary_and_per_flag():
    gold = {"r1": [], "r2": ["pricing"], "r3": ["supplier"], "r4": []}
    predicted = {"r1": [], "r2": ["pricing", "business_case"], "r3": [], "r4": ["price"]}   # r4: hard negative missed
    result = ev.score_scope_flags(gold, predicted)
    assert result["exact_match_accuracy"] == 0.25                 # only r1
    assert result["out_of_scope_accuracy"] == 0.5                 # r1 and r2 right; r3 missed; r4 false alarm
    assert result["flag_precision"] == pytest.approx(1 / 3) and result["flag_recall"] == 0.5
    assert result["per_flag"]["supplier"]["recall"] == 0.0 and result["per_flag"]["pricing"]["precision"] == 0.5
    assert result["errors"] == ["r2", "r3", "r4"] and result["unknown_flags"] == []


def test_score_scope_flags_counts_missing_requests_as_wrong():
    result = ev.score_scope_flags({"r1": [], "r2": ["pricing"]}, {"r1": []})
    assert result["exact_match_accuracy"] == 0.5 and result["out_of_scope_accuracy"] == 0.5 and result["errors"] == ["r2"]


def test_score_topics_skips_requests_without_gold_topic():
    result = ev.score_topics({"r1": "comfort", "r2": "controls", "r3": None}, {"r1": "comfort", "r2": "comfort"})
    assert result["n"] == 2 and result["accuracy"] == 0.5
    assert result["errors"] == {"r2": {"gold": "controls", "predicted": "comfort"}}


# Ranking ------------------------------------------------------------------------------------------------


def test_order_and_weighted_totals_follow_the_v1_rubric():
    factors = {"a": {"x": 5, "y": 1}, "b": {"x": 1, "y": 5}, "c": {"x": 3, "y": 3}}
    totals = ev.weighted_totals(factors, {"x": 0.75, "y": 0.25})
    assert totals == {"a": 80.0, "b": 40.0, "c": 60.0}
    assert ev.order_by_score(totals) == ["a", "c", "b"]
    assert ev.order_by_score({"b": 1.0, "a": 1.0}) == ["a", "b"]   # ties by id: total and reproducible


def test_perturbed_weights_are_one_at_a_time_and_renormalised():
    variants = ev.perturbed_weights({"x": 0.5, "y": 0.5}, delta=0.2)
    assert len(variants) == 4
    assert all(sum(variant.values()) == pytest.approx(1) for variant in variants)
    assert variants[0] == {"x": pytest.approx(0.4 / 0.9), "y": pytest.approx(0.5 / 0.9)}


def test_rank_ranges_kendall_tau_and_top_k():
    ranges = ev.rank_ranges([["a", "b", "c"], ["b", "a", "c"], ["a", "c", "b"]])
    assert ranges["a"] == {"min_rank": 1, "max_rank": 2, "range": 1} and ranges["c"]["range"] == 1
    assert ev.kendall_tau(["a", "b", "c"], ["a", "b", "c"]) == 1.0
    assert ev.kendall_tau(["a", "b", "c"], ["c", "b", "a"]) == -1.0
    assert ev.kendall_tau(["a", "x"], ["a", "y"]) is None
    assert ev.top_k_overlap(["a", "b", "c"], ["c", "a", "d"], 3) == pytest.approx(2 / 3)


def test_ranking_order_prefers_rank_then_score():
    names = {"r1": "comfort", "r2": "charging"}
    assert ev.ranking_order([{"requirement_id": "r1", "rank": 2}, {"requirement_id": "r2", "rank": 1}], names) == [
        "charging", "comfort"]
    assert ev.ranking_order([{"id": "r1", "total": 40}, {"id": "r2", "score": 70.5}], names) == ["charging", "comfort"]


def test_ranking_fixture_top3_dominates_the_tail_under_perturbation():
    fixture = ev.load_fixtures()["ranking"]
    factors = {row["topic"]: row["factors"] for row in fixture["requirements"]}
    equal = {name: 0.2 for name in next(iter(factors.values()))}
    orders = [ev.order_by_score(ev.weighted_totals(factors, w)) for w in (equal, *ev.perturbed_weights(equal))]
    assert all(order[:3] == fixture["gold"]["top3"] for order in orders)
    assert all(ev.rank_ranges(orders)[topic]["range"] == 0 for topic in fixture["gold"]["stable"])


# Trace, runs and audit ------------------------------------------------------------------------------------


def test_link_coverage_with_alternative_and_nested_paths():
    required = (("run_id",), ("version_id", "requirement_id"), ("evidence_ids",))
    records = [{"run_id": "u1", "requirement_id": "q1", "evidence_ids": {"US": ["e1"], "CN": []}},
               {"run_id": "u2", "version_id": "v1", "evidence_ids": {"US": []}},
               {"run_id": "", "requirement_id": "q2", "evidence_ids": ["e2"]}]
    result = ev.link_coverage(records, required)
    assert result == {"records": 3, "traced": 1, "coverage": pytest.approx(1 / 3),
                      "missing": {"evidence_ids": 1, "run_id": 1}}
    assert ev.link_coverage([], required)["coverage"] is None


def test_run_audit_completeness_needs_an_outcome_event():
    events = {"u1": [{"action": "run.started"}, {"action": "run.succeeded"}], "u2": [{"action": "run.failed"}],
              "u3": [{"action": "market_conflict.detected"}]}
    result = ev.run_audit_completeness(["u1", "u2", "u3", "u4"], events)
    assert result["completeness"] == 0.5 and result["missing"] == ["u3", "u4"]


def test_run_ids_in_finds_nested_ids():
    body = {"run_id": "a", "items": [{"run_id": "b", "triage": {"run_id": "c"}}], "run_ids": ["d", 5], "x": {"run_id": 3}}
    assert ev.run_ids_in(body) == {"a", "b", "c", "d"}


def test_method_provider_and_require_provider():
    assert ev.method_provider("openai:gpt-x:prompt-v1") == "openai"
    assert ev.method_provider("lexicon-v1") == "deterministic" and ev.method_provider(None) is None
    assert ev.require_provider("request-cluster-v1", "deterministic", "here") == "request-cluster-v1"
    with pytest.raises(ev.Failed, match="not a openai method"):
        ev.require_provider("request-classify-v1", "openai", "POST /requests/classify")


# Fixtures -------------------------------------------------------------------------------------------------


def test_fixtures_match_the_brief_and_are_labelled_simulated():
    fixtures = ev.load_fixtures()
    sentiment, conflicts, requests, ranking = (fixtures[name] for name in ("sentiment", "market_conflicts", "requests",
                                                                            "ranking"))
    for fixture in fixtures.values():
        assert fixture["simulated"] is True
        assert "Not BMW data" in fixture["description"] or "fictional" in fixture["description"]
    assert len(sentiment["items"]) == 40 and {item["label"] for item in sentiment["items"]} == set(ev.SENTIMENT_LABELS)
    categories = [category for item in sentiment["items"] for category in item["categories"]]
    assert categories.count("negation") >= 5 and categories.count("contrast") >= 5
    assert len(conflicts["markets"]) == 3 and len(conflicts["gold_conflicts"]) == 3
    assert len(requests["requests"]) == 30 and len(ranking["gold"]["top3"]) == 3
    records = sentiment["items"] + conflicts["records"] + requests["requests"] + ranking["requirements"]
    assert all(record["simulated"] is True for record in records)
    assert {flag for request in requests["requests"] for flag in request["gold"]["scope_flags"]} <= set(ev.SCOPE_FLAGS)
    assert len({request["title"] for request in requests["requests"]}) == 30   # titles map API rows back to fixture ids


def test_conflict_fixture_design_ranks_follow_record_counts():
    fixture = ev.load_fixtures()["market_conflicts"]
    for market, order in fixture["design"]["intended_ranks"].items():
        counts = [sum(1 for row in fixture["records"] if row["market"] == market and row["topic"] == topic) for topic in order]
        assert counts == sorted(counts, reverse=True) and len(set(counts)) == len(counts), market


# HTTP mapping and report ------------------------------------------------------------------------------------


def mock_api(handler) -> ev.Api:
    return ev.Api(httpx.Client(base_url="http://eval.test", transport=httpx.MockTransport(handler)))


def test_api_maps_missing_endpoints_and_providers_to_not_available():
    statuses = {"/a": 404, "/b": 405, "/c": 503, "/d": 422}

    def handler(request):
        return httpx.Response(statuses[request.url.path], json={"detail": "nope"})

    api = mock_api(handler)
    for path in ("/a", "/b", "/c"):
        with pytest.raises(ev.Unavailable):
            api("POST", path)
    with pytest.raises(ev.Failed) as failed:
        api("POST", "/d")
    assert failed.value.status == 422 and "nope" in str(failed.value)
    assert ev.outcome(ev.Unavailable("x"))["status"] == "not_available" and ev.outcome(ev.Failed("y"))["status"] == "failed"


def test_api_collects_platform_run_ids_and_pages_lists():
    def handler(request):
        offset = int(request.url.params["offset"])
        items = [{"id": f"r{i}", "run_id": f"u{i}"} for i in range(offset, min(offset + 2, 3))]
        return httpx.Response(200, json={"items": items, "total": 3, "limit": 2, "offset": offset})

    api = mock_api(handler)
    assert [row["id"] for row in ev.all_items(api, "/requests")] == ["r0", "r1", "r2"]
    assert api.run_ids == {"u0", "u1", "u2"}


def test_sensitivity_accepts_a_list_and_rejects_an_empty_answer():
    answers = iter([{"results": [{"requirement_id": "q1", "rank": 1, "stable": True}]}, {"results": {}}])
    api = mock_api(lambda request: httpx.Response(200, json=next(answers)))
    assert ev.priority_sensitivity(api, "V", "US") == {"q1": {"requirement_id": "q1", "rank": 1, "stable": True}}
    with pytest.raises(ev.Failed):
        ev.priority_sensitivity(api, "V", "US")


def test_render_markdown_separates_not_measured_from_not_applicable():
    report = {"providers": ["deterministic", "openai"], "token": "T", "comparison": {"ranking_v2_identical_across_providers": True},
              "audit_chain": {"status": "measured", "ok": True, "events": 3},
              "metrics": {"sentiment": {"deterministic": ev.measured(accuracy=0.75, scored=4, n=4),
                                        "openai": {"status": "not_available", "reason": "503 provider"}},
                          "ranking_v1": {"deterministic": ev.measured(top3_exact=True),
                                         "openai": ev.not_applicable("deterministic code")}}}
    text = ev.render_markdown(report)
    assert "| Sentiment accuracy (40 sentences) | 0.750 (4/4 scored) | n/a |" in text
    assert "| Ranking v1 top-3 exact (deterministic code) | yes | not applicable |" in text
    assert "Not measured:\n- sentiment (openai): 503 provider" in text
    assert "Not applicable:\n- ranking_v1 (openai): deterministic code" in text
    assert "Ranking v2 identical across providers: yes." in text and "Audit hash chain: verified (3 events)." in text


def test_parse_providers_rejects_unknown_names():
    assert ev.parse_providers("openai, deterministic,openai") == ("openai", "deterministic")
    with pytest.raises(Exception):
        ev.parse_providers("anthropic")


# In-process smoke run (temporary database, no network) -------------------------------------------------------


def test_evaluation_runs_in_process_and_never_crashes(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    report = ev.evaluate(client, ("deterministic", "openai"), token="TEST")
    allowed = {"measured", "not_available", "failed", "not_applicable"}
    assert all(result["status"] in allowed for group in report["metrics"].values() for result in group.values())
    assert set(report["metrics"]) >= {"sentiment", "conflicts", "clustering", "scope_flags", "request_topics", "ranking_v1",
                                      "ranking_v2", "ranking_v2_stability", "coverage", "trace_coverage", "run_audit"}
    v1 = report["metrics"]["ranking_v1"]
    assert v1["deterministic"]["status"] == "measured" and v1["deterministic"]["top3_exact"] is True
    assert v1["deterministic"]["top3_stable"] is True and v1["deterministic"]["recomputed_matches_api"] is True
    assert v1["openai"]["status"] == "not_applicable"
    assert report["metrics"]["trace_coverage"]["deterministic"]["coverage"] == 1.0
    assert report["audit_chain"]["ok"] is True and report["simulated"] is True
    assert all(entry["contract"] in ("verified", "assumed") for calls in report["endpoints"].values() for entry in calls)
    json.dumps(report)                                   # the JSON report is serialisable
    assert "| Metric | deterministic | openai |" in ev.render_markdown(report)
