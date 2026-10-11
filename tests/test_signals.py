"""Simulated public signals and private customer text; all external clients are offline doubles."""

import json
import sqlite3
from datetime import date, timedelta

import httpx
import pytest

from database.integrity import verify
from database.store import connect, transaction
from mcp_server.cache import FileCache
from mcp_server.exa_client import ExaClient
from server import exa_research, signals
from server.platform import run_capability

HUMAN = {"actor": "human:signals-test", "rationale": "Simulated PM authorisation"}
WATCHLIST = {"vehicle": "G60", "market": "US", "topic": "comfort", "label": "Simulated cabin watch", **HUMAN}
SCORE = {"vehicle": "G60", "market": "US", "provider": "deterministic", "actor": "ai:signals-test"}


def watchlist(client, **changes):
    response = client.post("/signals/watchlists", json={**WATCHLIST, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def import_texts(client, texts, dates=None, market="US", kind="feedback"):
    response = client.post("/imports/records", json={"title": "Simulated signals fixture", "reference": "simulated.json",
        "vehicle": "G60", "market": market, "kind": kind, "actor": HUMAN["actor"],
        "records": [{"content": text, "location": {"row": i}, "metadata": {"simulated": True},
                     "observed_at": dates[i] if dates else None} for i, text in enumerate(texts)]})
    assert response.status_code == 201, response.text
    with connect() as connection:
        return [row[0] for row in connection.execute("SELECT id FROM evidence WHERE source_id=? ORDER BY id",
                                                   (response.json()["source_id"],))]


@pytest.fixture
def exa(tmp_path, monkeypatch):
    requests = []
    state = {"text": "The BMW seats are comfortable.", "published": "2026-01-05T12:00:00Z", "status": 200}

    def respond(request):
        requests.append(request)
        payload = json.loads(request.content)
        fetched = request.url.path.endswith("contents")
        return httpx.Response(state["status"], json={"results": [{"id": "simulated-exa-1",
            "url": "https://caranddriver.com/simulated-bmw-review", "title": "Simulated review",
            "text": state["text"] if fetched else None, "highlights": [state["text"]],
            "publishedDate": state["published"]}], "requestId": "simulated", "statuses": [],
            "query": payload.get("query")})

    transport = httpx.Client(transport=httpx.MockTransport(respond))
    client = ExaClient(api_key="simulated", client=transport, cache=FileCache(tmp_path / "exa-cache"))
    monkeypatch.setattr(exa_research, "exa_client", lambda: client)
    return client, requests, state


def discover(client, exa):
    item = watchlist(client)
    response = client.post(f"/signals/watchlists/{item['id']}/refresh", json={"actor": "system:signals-test"})
    assert response.status_code == 200, response.text
    return item, client.get("/signals/items").json()["items"][0]


def assert_failed_run():
    with connect() as connection:
        row = connection.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
        assert row["status"] == "failed" and row["error"]
        assert connection.execute("SELECT 1 FROM audit_events WHERE entity_id=? AND action='run.failed'", (row["id"],)).fetchone()


@pytest.mark.parametrize("actor", ["ai:signals-test", "AI:signals-test", "system:signals-test"])
def test_watchlist_api_and_database_gate(client, actor):
    assert client.post("/signals/watchlists", json={**WATCHLIST, "actor": actor}).status_code == 403
    with pytest.raises(sqlite3.IntegrityError, match="human actor"), transaction() as connection:
        connection.execute("INSERT INTO watchlists (id,vehicle,market,topic,label,query_terms,domain_group,created_by,rationale,created_at,updated_at) VALUES ('gate','G60','US','comfort','x','[]','all',?,'r','t','t')", (actor,))


def test_edit_pause_resume_and_audit(client, db):
    w = watchlist(client)
    for actor in ("ai:test", "system:test"):
        assert client.patch(f"/signals/watchlists/{w['id']}", json={**HUMAN, "actor": actor, "status": "paused"}).status_code == 403
    response = client.patch(f"/signals/watchlists/{w['id']}", json={**HUMAN, "status": "paused", "cadence_days": 14})
    assert response.status_code == 200, response.text
    assert response.json()["status_changed_by"] == HUMAN["actor"]
    assert response.json()["cadence_days"] == 14
    assert client.post(f"/signals/watchlists/{w['id']}/refresh", json={"actor": "ai:test"}).status_code == 409
    assert_failed_run()
    assert client.patch(f"/signals/watchlists/{w['id']}", json={**HUMAN, "status": "active"}).status_code == 200
    assert verify(db)["ok"]
    with pytest.raises(sqlite3.IntegrityError, match="human actor"), transaction() as connection:
        connection.execute("UPDATE watchlists SET label='agent edit',updated_by='ai:test' WHERE id=?", (w["id"],))
    with pytest.raises(sqlite3.IntegrityError), transaction() as connection:
        connection.execute("DELETE FROM watchlists WHERE id=?", (w["id"],))


@pytest.mark.parametrize("changes", [{"query_terms": ["x" * 61]}, {"query_terms": ["a@example.com"]},
    {"query_terms": ["customer id 1234"]}, {"query_terms": ["line\nbreak"]},
    {"domains": ["localhost"]}, {"domains": ["https://reddit.com"]}, {"vehicle": "Private customer"},
    {"market": "Private"}, {"topic": "pricing"}])
def test_invalid_public_templates_rejected(client, changes):
    assert client.post("/signals/watchlists", json={**WATCHLIST, **changes}).status_code == 422


def test_privacy_guard_on_create_edit_and_every_refresh(client, exa):
    w = watchlist(client, query_terms=["special cabin discussion"])
    import_texts(client, ["The special cabin discussion includes a simulated private verbatim."])
    assert client.post("/signals/watchlists", json={**WATCHLIST, "query_terms": ["special cabin discussion"]}).status_code == 422
    assert client.patch(f"/signals/watchlists/{w['id']}", json={**HUMAN, "competitors": ["simulated private verbatim"]}).status_code == 422
    response = client.post(f"/signals/watchlists/{w['id']}/refresh", json={"actor": "ai:test"})
    assert response.status_code == 422
    assert not exa[1]
    assert_failed_run()


def test_refresh_is_idempotent_audited_and_not_evidence(client, exa, db):
    w, item = discover(client, exa)
    response = client.post(f"/signals/watchlists/{w['id']}/refresh", json={"actor": "ai:test"})
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 0 and response.json()["existing"] == 1
    assert len(exa[1]) == 1  # existing Exa cache contract
    query = json.loads(exa[1][0].content)
    assert "BMW 5 Series i5" in query["query"] and "United States" in query["query"]
    assert set(query["includeDomains"]) == set(signals.default_domains("US", "all"))  # curated union, not the open web
    assert {"caranddriver.com", "bimmerpost.com", "youtube.com", "x.com"} <= set(query["includeDomains"])
    assert item["published_at"] and item["date_basis"] == "published" and item["evidence_id"] is None
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM evidence").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM signal_items").fetchone()[0] == 1
    assert verify(db)["ok"]


def test_backfill_bounded_disjoint_weekly_windows(client, exa):
    w = watchlist(client, domain_group="press")
    response = client.post(f"/signals/watchlists/{w['id']}/backfill", json={"actor": "ai:test", "weeks": 12})
    assert response.status_code == 200, response.text
    assert len(exa[1]) == 12
    payloads = [json.loads(request.content) for request in exa[1]]
    windows = [(date.fromisoformat(p["startPublishedDate"][:10]), date.fromisoformat(p["endPublishedDate"][:10])) for p in payloads]
    assert all(end - start == timedelta(days=6) for start, end in windows)
    assert all(windows[i][0] - windows[i + 1][1] == timedelta(days=1) for i in range(11))
    assert payloads[0]["includeDomains"] == ["caranddriver.com", "motortrend.com"]
    assert client.post(f"/signals/watchlists/{w['id']}/backfill", json={"actor": "ai:test", "weeks": 13}).status_code == 422
    assert len(exa[1]) == 12


def test_provider_error_is_visible_and_writes_no_partial_items(client, exa, monkeypatch):
    w = watchlist(client)
    monkeypatch.setattr(exa[0], "api_key", "")
    response = client.post(f"/signals/watchlists/{w['id']}/refresh", json={"actor": "ai:test"})
    assert response.status_code == 503 and "EXA_CONFIGURATION_ERROR" in response.text
    assert client.get("/signals/items").json()["total"] == 0
    assert_failed_run()


def test_human_import_reuses_candidate_pipeline_and_is_atomic(client, exa, db):
    _, item = discover(client, exa)
    assert client.post(f"/signals/items/{item['id']}/import", json={**HUMAN, "actor": "ai:test"}).status_code == 403
    assert len(exa[1]) == 1
    response = client.post(f"/signals/items/{item['id']}/import", json=HUMAN)
    assert response.status_code == 200, response.text
    assert response.json()["review_status"] == "imported" and response.json()["evidence_id"]
    with connect() as connection:
        evidence = connection.execute("SELECT * FROM evidence WHERE id=?", (response.json()["evidence_id"],)).fetchone()
        source = connection.execute("SELECT * FROM sources WHERE id=?", (evidence["source_id"],)).fetchone()
        assert source["kind"] == "web"
        assert json.loads(evidence["metadata"])["web_evidence"]["content_status"] == "fetched"
        assert source["reference"] == item["url"]
    assert client.post(f"/signals/items/{item['id']}/dismiss", json=HUMAN).status_code == 409
    assert client.post(f"/signals/items/{item['id']}/import", json=HUMAN).status_code == 409
    assert verify(db)["ok"]


def test_failed_review_step_leaves_item_unreviewed_and_retry_links_same_snapshot(client, exa, db):
    _, item = discover(client, exa)
    with transaction() as connection:
        connection.execute("CREATE TRIGGER simulated_review_failure BEFORE UPDATE OF review_status ON signal_items BEGIN SELECT RAISE(ABORT, 'simulated review failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="simulated review failure"):
        client.post(f"/signals/items/{item['id']}/import", json=HUMAN)
    assert_failed_run()
    with connect() as connection:
        assert connection.execute("SELECT review_status FROM signal_items").fetchone()[0] == "unreviewed"
        assert not connection.execute("SELECT 1 FROM audit_events WHERE action='signal.imported'").fetchone()
        sources = connection.execute("SELECT count(*) FROM sources").fetchone()[0]
    with transaction() as connection:
        connection.execute("DROP TRIGGER simulated_review_failure")
    response = client.post(f"/signals/items/{item['id']}/import", json=HUMAN)
    assert response.status_code == 200, response.text
    with connect() as connection:
        # The existing import deduplicates by content hash: no second source for the same snapshot.
        assert connection.execute("SELECT count(*) FROM sources").fetchone()[0] == sources == 1
        run = connection.execute("SELECT outputs FROM runs WHERE id=?", (response.json()["run_id"],)).fetchone()
        assert json.loads(run[0])["deduplicated"] is True
    assert verify(db)["ok"]


def test_dismiss_removes_from_series_and_cannot_be_automated(client, exa):
    _, item = discover(client, exa)
    scored = client.post("/signals/sentiment/score", json=SCORE)
    assert scored.status_code == 200, scored.text
    assert client.get("/signals/sentiment/timeseries").json()["total"] == 1
    assert client.post(f"/signals/items/{item['id']}/dismiss", json={**HUMAN, "actor": "system:test"}).status_code == 403
    with pytest.raises(sqlite3.IntegrityError, match="human actor"), transaction() as connection:
        connection.execute("UPDATE signal_items SET review_status='dismissed',reviewed_by='ai:test',reviewed_at='t' WHERE id=?", (item["id"],))
    assert client.post(f"/signals/items/{item['id']}/dismiss", json=HUMAN).status_code == 200
    assert client.get("/signals/sentiment/timeseries").json()["total"] == 0


def test_scoring_scope_idempotency_and_dates(client, exa):
    import_texts(client, ["The seats are comfortable.", "The seats are terrible."], ["2025-12-29", "2026-01-02"])
    import_texts(client, ["The seats are roomy."], market="CN")
    response = client.post("/signals/sentiment/score", json=SCORE)
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 2
    assert {r["provider"] for r in response.json()["items"]} == {"deterministic"}
    again = client.post("/signals/sentiment/score", json=SCORE).json()
    assert again["created"] == 0 and again["reused"] == 2
    points = client.get("/signals/sentiment/timeseries", params={"vehicle": "G60", "market": "US"}).json()["items"]
    assert len(points) == 1  # New Year is still a single Monday-aligned week.
    assert points[0]["week_start"] == "2025-12-29" and points[0]["iso_week"] == "2026-W01"
    assert points[0]["source_class"] == "bmw_evidence" and points[0]["n"] == 2
    assert points[0]["negative_share"] == 0.5 and points[0]["undated_n"] == 0 and points[0]["low_n"]
    assert len(points[0]["subject_ids"]) == 2
    assert client.get("/signals/sentiment/scores", params={"market": "CN"}).json()["total"] == 0


def test_score_filter_limit_and_invalid_ids(client):
    ids = import_texts(client, ["The seats are comfortable.", "The seats are terrible."])
    assert client.post("/signals/sentiment/score", json={**SCORE, "subject_ids": ["other-scope"]}).status_code == 422
    first = client.post("/signals/sentiment/score", json={**SCORE, "limit": 1}).json()
    assert first["created"] == 1 and first["remaining"] == 1
    second = client.post("/signals/sentiment/score", json={**SCORE, "limit": 1}).json()
    assert second["created"] == 1 and second["remaining"] == 0
    selected = client.post("/signals/sentiment/score", json={**SCORE, "subject_ids": [ids[0]]}).json()
    assert len(selected["items"]) == 1 and selected["items"][0]["subject_id"] == ids[0]


def test_openai_is_grounded_batched_and_never_mixed_with_lexicon(client, fake_llm):
    texts = [f"The seats are comfortable. Simulated record {i}." for i in range(26)]
    import_texts(client, texts, ["2026-01-05"] * 26)
    fake_llm.responder = lambda request: {"items": [{"item_id": item["item_id"], "relevant": True,
        "overall_polarity": 0.8, "aspects": [{"topic": "comfort", "attribute": "seat comfort", "polarity": 0.8,
        "quote": "seats are comfortable"}]} for item in json.loads(request["input"])["items"]]}
    first = client.post("/signals/sentiment/score", json={**SCORE, "provider": "openai"})
    assert first.status_code == 200, first.text
    assert first.json()["created"] == 26
    assert len(fake_llm.calls("/responses")) == 2
    assert first.json()["method_version"] == "openai:fake-model:aspect-sentiment-v1"
    score = first.json()["items"][0]
    assert score["aspects"][0]["span"] == [4, 25]
    again = client.post("/signals/sentiment/score", json={**SCORE, "provider": "openai"}).json()
    assert again["created"] == 0 and again["reused"] == 26 and len(fake_llm.calls("/responses")) == 2
    assert client.post("/signals/sentiment/score", json=SCORE).status_code == 200
    points = client.get("/signals/sentiment/timeseries").json()["items"]
    assert len(points) == 2 and {p["n"] for p in points} == {26}
    assert {p["method_version"] for p in points} == {"lexicon-v1", first.json()["method_version"]}
    with connect() as connection:
        run = connection.execute("SELECT * FROM runs WHERE id=?", (first.json()["run_id"],)).fetchone()
        assert run["method_version"] == first.json()["method_version"]
        assert json.loads(run["metrics"])["llm"]["total_tokens"] == 36


@pytest.mark.parametrize("failure", ["quote", "foreign_id", "missing", "duplicate", "no_aspects"])
def test_ungrounded_openai_output_rejected_atomically(client, fake_llm, failure):
    import_texts(client, ["The seats are comfortable."])

    def response(request):
        item = json.loads(request["input"])["items"][0]
        output = {"item_id": "foreign" if failure == "foreign_id" else item["item_id"], "relevant": True,
                  "overall_polarity": 0.8, "aspects": [] if failure == "no_aspects" else [{"topic": "comfort",
                  "attribute": None, "polarity": 0.8, "quote": "invented" if failure == "quote" else "comfortable"}]}
        return {"items": [] if failure == "missing" else [output, output] if failure == "duplicate" else [output]}

    fake_llm.responder = response
    result = client.post("/signals/sentiment/score", json={**SCORE, "provider": "openai"})
    assert result.status_code == 502, result.text
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM sentiment_scores").fetchone()[0] == 0
    assert_failed_run()


def test_missing_openai_configuration_fails_without_lexicon_fallback(client, monkeypatch):
    import_texts(client, ["The seats are comfortable."])
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    response = client.post("/signals/sentiment/score", json={**SCORE, "provider": "openai"})
    assert response.status_code == 503, response.text
    assert client.get("/signals/sentiment/scores").json()["total"] == 0
    assert_failed_run()


def test_summary_grounding_provider_trace_and_capability(client, fake_llm):
    import_texts(client, ["The seats are comfortable."])
    client.post("/signals/sentiment/score", json=SCORE)
    fake_llm.responder = lambda request: {"claims": [{"text": "A simulated owner praises seat comfort.",
        "subject_id": next(iter(json.loads(request["input"])["texts"])), "quote": "seats are comfortable"}]}
    result = client.post("/signals/summary", json={**SCORE, "provider": "openai"})
    assert result.status_code == 200, result.text
    assert result.json()["provider"] == "openai" and result.json()["claims"][0]["span"] == [4, 25]
    assert result.json()["audit_event_id"] and result.json()["run_id"]
    replay = run_capability("signals.summarise", {"vehicle": "G60", "market": "US", "provider": "deterministic"}, "ai:test")
    assert replay["outputs"]["items"][0]["n"] == 1
    assert replay["outputs"]["claims"] == [] and replay["run_ids"]


def test_pagination_and_source_classes(client, exa):
    _, item = discover(client, exa)
    import_texts(client, ["The seats are comfortable."])
    client.post(f"/signals/items/{item['id']}/import", json=HUMAN)
    result = client.post("/signals/sentiment/score", json=SCORE)
    assert result.status_code == 200, result.text
    points = client.get("/signals/sentiment/timeseries").json()["items"]
    assert {p["source_class"] for p in points} == {"bmw_evidence", "public_monitoring", "public_imported"}
    assert all(p["undated_n"] == 1 for p in points if p["source_class"] != "public_monitoring")
    page = client.get("/signals/summary", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 3 and len(page["items"]) == 1 and page["offset"] == 1
    assert client.get("/signals/watchlists", params={"limit": 0}).status_code == 422


def test_pause_during_network_request_cancels_stale_persistence(client, exa, monkeypatch):
    w = watchlist(client)
    search = exa[0].search

    def pause(request):
        result = search(request)
        signals.patch_watchlist(w["id"], signals.WatchlistPatch(**HUMAN, status="paused"))
        return result

    monkeypatch.setattr(exa[0], "search", pause)
    response = client.post(f"/signals/watchlists/{w['id']}/refresh", json={"actor": "ai:test"})
    assert response.status_code == 409
    assert client.get("/signals/items").json()["total"] == 0
    assert_failed_run()


def test_capabilities_registered_and_refresh_runs_as_the_executing_agent(client, exa):
    from server.platform import CAPABILITIES

    names = ("signals.refresh_watchlist", "signals.backfill_watchlist", "signals.score_sentiment", "signals.summarise")
    assert all(CAPABILITIES[name].autonomy_level == "A0" for name in names)
    w = watchlist(client)
    result = run_capability("signals.refresh_watchlist", {"watchlist_id": w["id"], "actor": "human:spoofed"},
                            "ai:agent:signals")
    assert result["outputs"]["created"] == 1 and len(result["run_ids"]) == 1
    with connect() as connection:
        run = connection.execute("SELECT * FROM runs WHERE id=?", (result["run_ids"][0],)).fetchone()
        assert run["actor"] == "ai:agent:signals" and run["capability"] == "signals.refresh_watchlist"
        assert run["method_version"] == signals.MONITOR_VERSION and run["status"] == "succeeded"
        item = connection.execute("SELECT * FROM signal_items").fetchone()
        assert item["run_id"] == run["id"] and item["window_end"] and item["search_query"]
