"""Offline behavior and adversarial provider contract tests; no network or secrets."""
import copy
import json
import traceback
from urllib.error import HTTPError

import pytest

from server import analysis_engine as engine


def record(eid="e1", text="The seats are uncomfortable", *, kind="Defect", topic="Seats", **extra):
    return {"id": eid, "source_id": "s1", "content": text, "vehicle": "G60", "market": "US", "location": {"sheet": "Feedback", "row": 2}, "observed_at": None,
            "metadata": {"Feedback Type": kind, "Vfc level2 Name": topic}, **extra}


def analyze(records, **kwargs):
    return engine.analyze_evidence(records, "G60", "US", **kwargs)


def ai_result(records):
    result = analyze(records)
    return {key: copy.deepcopy(result[key]) for key in ("findings", "proposals", "warnings")}


@pytest.fixture
def ai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-structured-model")
    monkeypatch.setenv("ANALYSIS_BATCH_SIZE", "40")
    monkeypatch.setenv("ANALYSIS_MAX_BATCHES", "20")


def test_customer_pipeline_retains_strengths_needs_and_conflicts():
    result = analyze([record(), record("e2", "The seats are very comfortable", kind="Likes"), record("e3", "I want more support", kind="Wants")])
    assert {f["kind"] for f in result["findings"]} == {"problem", "strength", "need"}
    strength = next(f for f in result["findings"] if f["kind"] == "strength")
    assert strength["evidence_ids"] == ["e2"]
    assert strength["conflicting_evidence_ids"] == ["e1", "e3"]
    assert len(result["proposals"]) == 1
    proposal = result["proposals"][0]
    assert "Preserve the positively" in proposal["statement"]
    assert "successor to G60" in proposal["statement"]
    assert "3–5 years" in proposal["statement"]
    assert proposal["acceptance_criteria"][0]["basis"] == "PM assumption"
    assert any("not a measured result" in assumption for assumption in proposal["assumptions"])
    assert any("PM planning assumption" in assumption for assumption in proposal["assumptions"])
    assert all(0 <= score <= 5 for score in proposal["factors"].values())
    assert result["provider"] == "deterministic"
    assert result["analyzed_evidence_ids"] == ["e1", "e2", "e3"]


def test_positive_evidence_generates_preservation_requirement():
    result = analyze([record(text="A peaceful quiet ride", kind="Likes", topic="Interior acoustics")])
    assert result["findings"][0]["kind"] == "strength"
    assert result["proposals"][0]["title"] == "Preserve cabin quietness"


def test_exact_scope_and_invalid_evidence_are_not_leaked():
    result = analyze([record(), record("foreign", vehicle="G70"), record("eu", market="EU"), record("missing", market=None)])
    assert result["findings"][0]["evidence_ids"] == ["e1"]
    assert "Excluded 3" in result["warnings"][0]


def test_input_order_and_unrelated_topic_do_not_change_existing_proposal():
    baseline = [record(), record("e2", "Seat support needed", kind="Wants")]
    assert analyze(baseline) == analyze(list(reversed(baseline)))
    original = analyze(baseline)
    extended = analyze(baseline + [record("e3", "Charging is hard to start", topic="Public charging")])
    # Finding indexes are referential positions and can shift as new themes appear.
    a = {k: v for k, v in original["proposals"][0].items() if k != "finding_indexes"}
    b = next({k: v for k, v in p.items() if k != "finding_indexes"} for p in extended["proposals"] if p["topic"] == "comfort")
    assert a == b
    assert original["findings"][0] == next(f for f in extended["findings"] if f["topic"] == original["findings"][0]["topic"] and f["kind"] == original["findings"][0]["kind"])


def test_duplicate_ids_are_idempotent_but_conflicting_ids_fail():
    assert analyze([record(), record()]) == analyze([record()])
    with pytest.raises(engine.AnalysisError, match="Conflicting duplicate"):
        analyze([record(), record(text="different")])


def test_context_records_never_generate_requirements():
    result = analyze([record(text="Seats: mean 8.4", kind=None, metadata={"kind": "study", "topic": "Seats"}), record("sales", "2025 volume 78000", metadata={"kind": "sales"})])
    assert result["findings"]
    assert {f["kind"] for f in result["findings"]} == {"context"}
    assert result["proposals"] == []


@pytest.mark.parametrize("kind", ["study_aggregate", "sales_aggregate", "document_context", "context"])
def test_imported_context_type_overrides_sentiment_and_complaint_words(kind):
    result = analyze([record(metadata={"record_type": kind, "Feedback Type": "Defect", "topic": "Seats"})])
    assert {finding["kind"] for finding in result["findings"]} == {"context"}
    assert result["proposals"] == []


def test_empty_evidence_is_valid_and_explained():
    result = analyze([record(text="   ")])
    assert result["findings"] == result["proposals"] == []
    assert any("No non-empty evidence" in w for w in result["warnings"])


@pytest.mark.parametrize("change", [{"id": ""}, {"source_id": None}, {"content": 42}, {"metadata": []}])
def test_malformed_scoped_evidence_is_rejected(change):
    with pytest.raises(engine.AnalysisError):
        analyze([record(**change)])


def test_negative_phrase_is_not_misclassified_as_positive():
    assert analyze([record(text="The seats are not comfortable", kind=None)])["findings"][0]["kind"] == "problem"


def test_bmw_survey_question_is_not_mistaken_for_a_customer_request():
    text = 'What would you want to say to the vehicle manufacturer?\n: "Really love this car!"'
    result = analyze([record(text=text, kind=None, topic=None)])
    assert result["findings"][0]["kind"] == "strength"
    assert "What would you want" not in result["findings"][0]["summary"]


def test_real_provider_cannot_silently_fallback(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    with pytest.raises(engine.ProviderUnavailable, match="OPENAI_API_KEY and OPENAI_MODEL"):
        analyze([record()], provider="openai")
    with pytest.raises(engine.ProviderUnavailable, match="Unsupported"):
        analyze([record()], provider="made-up")


def test_openai_uses_responses_strict_schema_and_validates_result(ai, monkeypatch):
    calls = []
    def request(payload, key):
        calls.append(payload)
        assert key == "test-only-key"
        return ai_result([record()])
    monkeypatch.setattr(engine, "_request_openai", request)
    result = analyze([record()], provider="openai")
    assert result["provider"] == "openai"
    assert result["model"] == "test-structured-model"
    assert calls[0]["store"] is False
    assert calls[0]["text"]["format"]["strict"] is True
    schema = calls[0]["text"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    for definition in schema["$defs"].values():
        assert definition["additionalProperties"] is False
        assert set(definition["required"]) == set(definition["properties"])
    assert "minLength" not in json.dumps(schema)
    assert "maxLength" not in json.dumps(schema)
    assert json.loads(calls[0]["input"])["evidence"][0]["id"] == "e1"


@pytest.mark.parametrize("alter", [
    lambda p: p["findings"][0]["evidence_ids"].append("invented"),
    lambda p: p["findings"][0]["conflicting_evidence_ids"].append("foreign"),
    lambda p: p["findings"][0]["conflicting_evidence_ids"].append("e1"),
    lambda p: p["findings"][0].update(confidence=float("nan")),
    lambda p: p["findings"][0].update(topic="manufacturing-process"),
    lambda p: p["proposals"][0].update(finding_indexes=[99]),
    lambda p: p["proposals"][0].update(finding_indexes=[-1]),
    lambda p: p["proposals"][0].update(finding_indexes=[True]),
    lambda p: p["proposals"][0].update(topic="charging"),
    lambda p: p["proposals"][0]["factors"].update(feasibility=6.0),
    lambda p: p["proposals"][0]["acceptance_criteria"][0].update(basis="source", source_ids=[]),
    lambda p: p["proposals"][0]["acceptance_criteria"][0].update(basis="source", source_ids=["unrelated"]),
    lambda p: p["proposals"][0]["acceptance_criteria"][0].update(basis="source", source_ids=["s1"], target="95%"),
    lambda p: p["proposals"][0]["acceptance_criteria"][0].update(basis="PM assumption", source_ids=["s1"]),
    lambda p: p["proposals"][0].update(title="x" * 301),
    lambda p: p["proposals"][0].update(assumptions=[" "]),
    lambda p: p.update(warnings=[""]),
    lambda p: p.update(unexpected="not allowed"),
])
def test_openai_hallucinations_and_malformed_results_are_rejected(ai, monkeypatch, alter):
    output = ai_result([record()])
    alter(output)
    monkeypatch.setattr(engine, "_request_openai", lambda *_: output)
    with pytest.raises(engine.AnalysisError):
        analyze([record()], provider="openai")


def test_openai_batches_remap_provenance_and_detect_cross_batch_conflicts(ai, monkeypatch):
    monkeypatch.setenv("ANALYSIS_BATCH_SIZE", "1")
    calls = []
    def request(payload, key):
        records = json.loads(payload["input"])["evidence"]
        calls.append(records)
        return ai_result(records)
    monkeypatch.setattr(engine, "_request_openai", request)
    result = analyze([record(), record("e2", "Comfortable seats", kind="Likes")], provider="openai")
    assert len(calls) == 2
    assert len(result["findings"]) == 2
    assert len(result["proposals"]) == 1
    assert result["proposals"][0]["finding_indexes"] == [0, 1]
    assert result["findings"][0]["conflicting_evidence_ids"] == ["e2"]
    assert any("2/2" in warning for warning in result["warnings"])


def test_openai_partial_coverage_and_truncation_are_explicit(ai, monkeypatch):
    monkeypatch.setenv("ANALYSIS_BATCH_SIZE", "1")
    monkeypatch.setenv("ANALYSIS_MAX_BATCHES", "1")
    def request(payload, key):
        batch = json.loads(payload["input"])["evidence"]
        assert len(batch[0]["content"]) == 6000
        return ai_result(batch)
    monkeypatch.setattr(engine, "_request_openai", request)
    result = analyze([record(text="seat " * 2000), record("e2")], provider="openai")
    assert any("Partial AI source coverage" in warning and "1 records omitted" in warning for warning in result["warnings"])
    assert any("truncated to 6000" in warning for warning in result["warnings"])
    assert result["findings"][0]["evidence_ids"] == ["e1"]
    assert result["analyzed_evidence_ids"] == ["e1"]


def test_cross_batch_citations_rejected_even_if_id_exists_in_full_input(ai, monkeypatch):
    monkeypatch.setenv("ANALYSIS_BATCH_SIZE", "1")
    output = ai_result([record("e2")])
    monkeypatch.setattr(engine, "_request_openai", lambda *_: output)
    with pytest.raises(engine.AnalysisError, match="outside its scoped input batch"):
        analyze([record(), record("e2")], provider="openai")


def test_provider_cannot_relabel_aggregate_context_to_justify_requirement(ai, monkeypatch):
    output = ai_result([record()])
    monkeypatch.setattr(engine, "_request_openai", lambda *_: output)
    with pytest.raises(engine.AnalysisError, match="cannot be relabeled"):
        analyze([record(metadata={"record_type": "study_aggregate"})], provider="openai")


def test_provider_cannot_drop_explicitly_liked_customer_attributes(ai, monkeypatch):
    monkeypatch.setattr(engine, "_request_openai", lambda *_: {"findings": [], "proposals": [], "warnings": []})
    with pytest.raises(engine.AnalysisError, match="retained as strengths"):
        analyze([record(kind="Likes")], provider="openai")


@pytest.mark.parametrize("text,target", [
    ("Seat satisfaction measured at 80%", "At least 80%"),
    ("Seat satisfaction measured at 80%", "80%"),
    ("The target is 180%", "80%"),
    ("The target is 80%. Another measure is 95%", "95%"),
])
def test_coincidental_numbers_cannot_be_source_targets(ai, monkeypatch, text, target):
    evidence = [record(text=text)]
    output = ai_result(evidence)
    output["proposals"][0]["acceptance_criteria"][0].update(basis="source", source_ids=["s1"], target=target)
    monkeypatch.setattr(engine, "_request_openai", lambda *_: output)
    with pytest.raises(engine.AnalysisError, match="explicit desired outcome"):
        analyze(evidence, provider="openai")


def test_explicit_quoted_source_target_is_allowed(ai, monkeypatch):
    evidence = [record(text="Customer comfort evaluation target: At least 80%")]
    output = ai_result(evidence)
    output["proposals"][0]["acceptance_criteria"][0].update(basis="source", source_ids=["s1"])
    monkeypatch.setattr(engine, "_request_openai", lambda *_: output)
    assert analyze(evidence, provider="openai")["proposals"][0]["acceptance_criteria"][0]["basis"] == "source"


def test_openai_rejects_oversized_provenance_before_request(ai, monkeypatch):
    def unexpected(*_):
        pytest.fail("Oversized provenance must not reach the provider")
    monkeypatch.setattr(engine, "_request_openai", unexpected)
    with pytest.raises(engine.AnalysisError, match="provenance is too large"):
        analyze([record(source_id="s" * 10001)], provider="openai")


def test_metadata_reduction_preserves_context_classification(ai, monkeypatch):
    evidence = record(metadata={"record_type": "study_aggregate", "extra": "x" * 15000})
    def request(payload, _):
        batch = json.loads(payload["input"])["evidence"]
        assert batch[0]["metadata"] == {"record type": "study_aggregate"}
        return ai_result(batch)
    monkeypatch.setattr(engine, "_request_openai", request)
    result = analyze([evidence], provider="openai")
    assert result["proposals"] == []
    assert any("reduced to classifications" in warning for warning in result["warnings"])


def test_openai_accepts_optional_metadata(ai, monkeypatch):
    evidence = record()
    evidence.pop("metadata")
    def request(payload, _):
        batch = json.loads(payload["input"])["evidence"]
        assert batch[0]["metadata"] == {}
        return ai_result(batch)
    monkeypatch.setattr(engine, "_request_openai", request)
    assert analyze([evidence], provider="openai")["findings"]


def test_metadata_reduction_preserves_measurement_context(ai, monkeypatch):
    evidence = record(metadata={"metric": "seat satisfaction", "extra": "x" * 15000})
    def request(payload, _):
        batch = json.loads(payload["input"])["evidence"]
        assert batch[0]["metadata"]["record type"] == "context"
        return ai_result(batch)
    monkeypatch.setattr(engine, "_request_openai", request)
    assert analyze([evidence], provider="openai")["proposals"] == []


class Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, limit):
        return self.payload[:limit]


def test_transport_extracts_output_text_and_keeps_auth_out_of_body(monkeypatch):
    def open_request(request, timeout):
        assert request.full_url == "https://api.openai.com/v1/responses"
        assert request.get_header("Authorization") == "Bearer secret"
        assert b"secret" not in request.data
        assert timeout == 90
        return Response({"status": "completed", "output": [{"type": "reasoning", "summary": []}, {"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": '{"ok": true}'}]}]})
    monkeypatch.setattr(engine, "urlopen", open_request)
    assert engine._request_openai({"model": "test"}, "secret") == {"ok": True}


@pytest.mark.parametrize("payload", [
    {"status": "incomplete", "output": []},
    {"status": "completed", "output": [{"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "refusal", "refusal": "no"}]}]},
    {"status": "completed", "output": [{"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": "invalid"}]}]},
    {"status": "completed", "output": [42]},
    {"status": "completed", "output": None},
    {"status": "completed", "output": [{"content": None}]},
    {"status": "completed", "output": [{"type": "message", "role": "user", "status": "completed", "content": [{"type": "output_text", "text": '{"ok": true}'}]}]},
    {"status": "completed", "output": [{"type": "message", "role": "assistant", "status": "incomplete", "content": [{"type": "output_text", "text": '{"ok": true}'}]}]},
    {"status": "completed", "output": [{"type": "tool_call", "content": [{"type": "output_text", "text": '{"ok": true}'}]}]},
    {"status": "completed", "output": [{"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": '[]'}]}]},
    {"status": "completed", "output": [{"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": '{"ok": true, "ok": false}'}]}]},
    {"status": "completed", "output": [{"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": '{"ok": NaN}'}]}]},
    {"status": "completed", "output": [{"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": '{"ok": 1e999}'}]}]},
])
def test_transport_incomplete_refusal_invalid_json_raise(monkeypatch, payload):
    monkeypatch.setattr(engine, "urlopen", lambda *_args, **_kwargs: Response(payload))
    with pytest.raises(engine.AnalysisError):
        engine._request_openai({}, "secret")


def test_transport_response_size_is_bounded(monkeypatch):
    monkeypatch.setattr(engine, "urlopen", lambda *_args, **_kwargs: Response({"text": "x" * 4_000_001}))
    with pytest.raises(engine.ProviderUnavailable, match="exceeded the allowed size"):
        engine._request_openai({}, "secret")


def test_http_error_does_not_expose_provider_body_or_api_key(monkeypatch):
    def fail(*args, **kwargs):
        raise HTTPError("https://api.openai.com/v1/responses", 401, "Bearer secret", {}, None)
    monkeypatch.setattr(engine, "urlopen", fail)
    api_key = "secret"
    with pytest.raises(engine.ProviderUnavailable) as error:
        engine._request_openai({}, api_key)
    assert "401" in str(error.value)
    assert "secret" not in str(error.value)
    assert "secret" not in "".join(traceback.format_exception(error.value))
