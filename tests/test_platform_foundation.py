"""Phase 0 platform foundation: migration 0009, server/platform.py, server/llm.py and pod registration."""

import json
import shutil
import sqlite3

import pytest
from fastapi import HTTPException
from pydantic import BaseModel, Field

from database import migrate, store
from database.integrity import verify
from database.store import audit, connect, init_database, transaction
from mcp_server import main as mcp_main
from server import agent_runtime, intake, main, market_data, markets, platform, prioritization, signals
from server.llm import (
    LLMBudgetExceeded,
    LLMOutputInvalid,
    ProviderUnavailable,
    ground_citations,
    llm_client,
    locate_quote,
    resolve_provider,
    strict_schema,
)
from tests.fakes import FakeOpenAI, fake_client

PLATFORM_TABLES = ("agents", "tasks", "runs", "threads", "messages", "llm_cache", "watchlists", "signal_items",
                   "sentiment_scores", "market_weights", "market_conflicts", "market_resolutions", "request_clusters",
                   "intake_requests", "request_links", "request_triage", "request_decisions", "priority_inputs",
                   "priority_sensitivity", "scope_rubrics", "preserve_attributes", "coverage_reports")
AUTOMATED = ("ai:agent:market-balancer", "AI:openai", "system:scheduler")


def _run(connection, run_id="run", actor="human:troy"):
    connection.execute("INSERT INTO runs (id,capability,actor,method_version,input_hash,inputs,status,started_at) "
                       "VALUES (?,'test.op',?,'v1','h','{}','running','t')", (run_id, actor))


def _requirement(connection):
    connection.execute("INSERT INTO requirements (id,vehicle,market,topic,status,created_at,updated_at) "
                       "VALUES ('req','G60','US','comfort','proposed','t','t')")


def _conflict(connection, conflict_id="conflict", fingerprint="fp"):
    connection.execute(
        "INSERT INTO market_conflicts (id,vehicle,topic,markets,conflict_type,severity,metrics,evidence_ids,"
        "requirement_ids,recommendation,rationale,fingerprint,method_version,run_id,created_at) "
        "VALUES (?,'G60','comfort','[\"CN\",\"US\"]','direction_conflict','high','{}','{}','[]','pm_tradeoff',"
        "'r',?,'market-balance-v1','run','t')", (conflict_id, fingerprint))


def _request(connection, request_id="request"):
    connection.execute(
        "INSERT INTO intake_requests (id,key,vehicle,market,origin_type,origin_name,title,body,requested_at,status,"
        "created_by,created_at,updated_at) VALUES (?,?,'G60','CN','market_org','BMW China','More rear legroom',"
        "'Body','t','new','human:troy','t','t')", (request_id, "MR-G60-CN-" + request_id))


def _agent(connection, slug="market-balancer"):
    connection.execute("INSERT INTO agents (id,slug,display_name,department,description,autonomy_level,capabilities,"
                       "created_at,updated_at) VALUES (?,?,'Market balancer','market_intelligence','d','A1','[]','t','t')",
                       ("ai:agent:" + slug, slug))


@pytest.fixture
def platform_rows(db):
    with transaction() as connection:
        _run(connection)
        _requirement(connection)
        _conflict(connection)
        _request(connection)
        _agent(connection)


# Migration -----------------------------------------------------------------------------------------

def test_migration_creates_every_platform_table_on_an_empty_database(db):
    with connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == migrate.latest_version() >= 9
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
    assert set(PLATFORM_TABLES) <= names and "v_sentiment_weekly" in names
    assert verify(db)["ok"]


def test_migration_upgrades_an_existing_v8_database_without_changing_it(tmp_path, monkeypatch):
    legacy = tmp_path / "migrations-v8"
    legacy.mkdir()
    for number, path in migrate.migrations():
        if number <= 8:
            shutil.copy(path, legacy / path.name)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", legacy)
    init_database()
    with transaction() as connection:
        connection.execute("INSERT INTO sources (id,title,kind,reference,vehicle,market) "
                           "VALUES ('s','Study','study','f','G60','US')")
        audit(connection, "source", "s", "source.created", "human:troy", "legacy row")
    with connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 8
        before = [tuple(row) for row in connection.execute("SELECT * FROM audit_events ORDER BY sequence")]

    monkeypatch.undo()
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path / "snapshots"))
    init_database()
    with connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == migrate.latest_version()
        assert [tuple(row) for row in connection.execute("SELECT * FROM audit_events ORDER BY sequence")] == before
        assert connection.execute("SELECT count(*) FROM watchlists").fetchone()[0] == 0
    assert verify(tmp_path / "app.db")["ok"]


# Human gates ---------------------------------------------------------------------------------------

def _gate_statements():
    return {
        "watchlists": "INSERT INTO watchlists (id,vehicle,market,topic,label,query_terms,domain_group,created_by,"
                      "rationale,created_at,updated_at) VALUES ('w','G60','US','comfort','L','[]','press',?,'r','t','t')",
        "market_resolutions": "INSERT INTO market_resolutions (id,conflict_id,decision,actor,rationale,created_at) "
                              "VALUES ('mr','conflict','adopt_global',?,'r','t')",
        "request_decisions": "INSERT INTO request_decisions (id,request_id,decision,actor,rationale,created_at) "
                             "VALUES ('rd','request','decline',?,'r','t')",
        "scope_rubrics": "INSERT INTO scope_rubrics (id,vehicle,market,rubric_version,weights,actor,rationale,created_at) "
                         "VALUES ('sr','G60','US','customer-priority-v2','{}',?,'r','t')",
        "agents": "UPDATE agents SET status='paused', status_changed_by=?, updated_at='t2'",
    }


@pytest.mark.parametrize("table", list(_gate_statements()))
@pytest.mark.parametrize("actor", AUTOMATED)
def test_human_gates_reject_ai_and_system_actors(platform_rows, table, actor):
    with pytest.raises(sqlite3.IntegrityError, match="this action requires a human actor"), transaction() as connection:
        connection.execute(_gate_statements()[table], (actor,))


@pytest.mark.parametrize("table", list(_gate_statements()))
def test_human_gates_accept_a_human_pm(platform_rows, table):
    with transaction() as connection:
        connection.execute(_gate_statements()[table], ("human:jakob",))


def test_signal_review_watchlist_status_and_agent_pause_need_humans(platform_rows):
    with transaction() as connection:
        connection.execute(_gate_statements()["watchlists"], ("human:troy",))
        connection.execute("INSERT INTO signal_items (id,watchlist_id,run_id,vehicle,market,topic,url,url_hash,domain,"
                           "excerpt,content_hash,retrieved_at,date_basis) VALUES ('i','w','run','G60','US','comfort',"
                           "'https://example.com','u','example.com','text','c','t','retrieved')")
    for statement in ("UPDATE signal_items SET review_status='dismissed', reviewed_by='ai:agent:trend-scout'",
                      "UPDATE watchlists SET status='paused', status_changed_by='system:scheduler'",
                      "UPDATE agents SET status='paused'"):
        with pytest.raises(sqlite3.IntegrityError, match="human actor"), transaction() as connection:
            connection.execute(statement)
    with transaction() as connection:
        connection.execute("UPDATE signal_items SET review_status='dismissed', reviewed_by='human:troy', reviewed_at='t'")
    with pytest.raises(sqlite3.IntegrityError, match="reviewed once"), transaction() as connection:
        connection.execute("UPDATE signal_items SET excerpt='changed'")


def test_agents_register_as_ai_actors(platform_rows):
    with connect() as connection:
        row = connection.execute("SELECT kind, role FROM actors WHERE id='ai:agent:market-balancer'").fetchone()
    assert tuple(row) == ("ai", "ai")
    with pytest.raises(sqlite3.IntegrityError), transaction() as connection:
        connection.execute("INSERT INTO agents (id,slug,display_name,department,description,autonomy_level,"
                           "capabilities,created_at,updated_at) VALUES ('human:x','x','X','governance','d','A0','[]',"
                           "'t','t')")


def test_conflict_and_request_status_follow_human_decisions(platform_rows):
    with pytest.raises(sqlite3.IntegrityError, match="resolution workflow"), transaction() as connection:
        connection.execute("UPDATE market_conflicts SET status='resolved'")
    with pytest.raises(sqlite3.IntegrityError, match="matching human decision"), transaction() as connection:
        connection.execute("UPDATE intake_requests SET status='declined', updated_at='t2'")
    with pytest.raises(sqlite3.IntegrityError, match="fixed"), transaction() as connection:
        connection.execute("UPDATE market_conflicts SET severity='low'")
    with transaction() as connection:
        connection.execute(_gate_statements()["market_resolutions"], ("human:troy",))
        connection.execute("UPDATE market_conflicts SET status='resolved'")
        connection.execute(_gate_statements()["request_decisions"], ("human:troy",))
        connection.execute("UPDATE intake_requests SET status='declined', updated_at='t2'")
    with pytest.raises(sqlite3.IntegrityError, match="one_open|UNIQUE"), transaction() as connection:
        _conflict(connection, "second", "fp2")
        _conflict(connection, "third", "fp2")


def test_append_only_and_no_delete(platform_rows):
    with transaction() as connection:
        connection.execute("INSERT INTO threads (id,kind,subject,created_by,created_at) VALUES ('t','agent','s',"
                           "'ai:agent:market-balancer','t')")
        connection.execute("INSERT INTO messages (id,thread_id,author,role,body,created_at) VALUES "
                           "('m','t','ai:agent:market-balancer','agent','hello','t')")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"), transaction() as connection:
        connection.execute("UPDATE messages SET body='edited'")
    with connect() as connection:
        triggers = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert {f"{table}_no_delete" for table in PLATFORM_TABLES} <= triggers
    for table in ("runs", "market_conflicts", "intake_requests", "agents", "threads", "messages"):
        with pytest.raises(sqlite3.IntegrityError, match="never deleted|append-only"), transaction() as connection:
            connection.execute(f"DELETE FROM {table}")
    with transaction() as connection:
        connection.execute("UPDATE threads SET status='closed'")
    with pytest.raises(sqlite3.IntegrityError, match="closed thread"), transaction() as connection:
        connection.execute("INSERT INTO messages (id,thread_id,author,role,body,created_at) VALUES "
                           "('m2','t','human:troy','human','late','t')")


def test_task_updates_increment_revision(platform_rows):
    with transaction() as connection:
        connection.execute("INSERT INTO tasks (id,vehicle,market,capability,title,input,requested_by,status,"
                           "created_at,updated_at) VALUES ('task','G60','US','markets.compare','T','{}',"
                           "'system:scheduler','backlog','t','t')")
        connection.execute("UPDATE tasks SET status='queued', revision=revision+1")
    with pytest.raises(sqlite3.IntegrityError, match="revision"), transaction() as connection:
        connection.execute("UPDATE tasks SET status='running'")


# record_run and the capability registry -------------------------------------------------------------

def _audit(entity_id):
    with connect() as connection:
        return [dict(row) for row in connection.execute(
            "SELECT action, actor, after_state FROM audit_events WHERE entity_id=? ORDER BY sequence", (entity_id,))]


def _run_row(run_id):
    with connect() as connection:
        return store.decode(connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone(),
                            ("inputs", "outputs", "metrics"))


def test_record_run_writes_a_run_and_an_audit_event_for_success(db):
    with platform.record_run(None, "test.op", "human:troy", "test-v1", {"b": 1, "a": [2]},
                             vehicle="G60", market="US") as run:
        assert _run_row(run.id)["status"] == "running"
        run.outputs["count"] = 3
        run.metrics["records"] = 3
    row = _run_row(run.id)
    assert row["status"] == "succeeded" and row["finished_at"] and row["outputs"] == {"count": 3}
    assert row["input_hash"] == platform.input_hash({"a": [2], "b": 1}) and row["metrics"]["records"] == 3
    assert [event["action"] for event in _audit(run.id)] == ["run.succeeded"]
    with pytest.raises(sqlite3.IntegrityError, match="immutable"), transaction() as connection:
        connection.execute("UPDATE runs SET error='x' WHERE id=?", (run.id,))


def test_record_run_keeps_failures_visible(db):
    with pytest.raises(HTTPException), platform.record_run(None, "test.op", "system:scheduler", "test-v1", {}) as run:
        raise HTTPException(409, "stale input")
    row = _run_row(run.id)
    assert row["status"] == "failed" and row["outputs"] is None and row["error"] == "HTTPException: stale input"
    assert [event["action"] for event in _audit(run.id)] == ["run.failed"]


def test_record_run_rejects_non_json_outputs_visibly(db):
    with pytest.raises(ValueError, match="finite JSON"), platform.record_run(None, "test.op", "human:troy", "v", {}) as run:
        run.outputs["bad"] = float("nan")
    assert _run_row(run.id)["status"] == "failed"


def test_record_run_can_share_the_callers_transaction(db):
    with transaction() as connection, platform.record_run(connection, "test.op", "human:troy", "v", {}) as run:
        run.outputs["ok"] = True
    assert _run_row(run.id)["status"] == "succeeded"


class EchoInput(BaseModel):
    value: int = Field(ge=0)


def _echo(command: EchoInput, actor: str) -> dict:
    with platform.record_run(None, "test.echo", actor, "echo-v1", command.model_dump()) as run:
        run.outputs["value"] = command.value
    return {"value": command.value, "awaiting_human": command.value > 5}


@pytest.fixture
def echo_capability():
    capability = platform.Capability("test.echo", "Echo a value", EchoInput, _echo, "A0", ())
    platform.register_capability(capability)
    yield capability
    platform.CAPABILITIES.pop("test.echo")


def test_capability_registry_rejects_duplicates_and_bad_definitions(echo_capability):
    with pytest.raises(ValueError, match="already registered"):
        platform.register_capability(echo_capability)
    with pytest.raises(ValueError):
        platform.Capability("NoModule", "d", EchoInput, _echo, "A0", ())
    with pytest.raises(ValueError):
        platform.Capability("test.bad", "d", EchoInput, _echo, "A9", ())
    assert platform.describe_capability(echo_capability)["input_schema"]["properties"]["value"]["minimum"] == 0


def test_run_capability_validates_records_and_links_the_task(db, echo_capability):
    with transaction() as connection:
        connection.execute("INSERT INTO tasks (id,vehicle,market,capability,title,input,requested_by,status,"
                           "created_at,updated_at) VALUES ('task','G60','US','test.echo','T','{}','human:troy',"
                           "'queued','t','t')")
    result = platform.run_capability("test.echo", {"value": 7}, "ai:agent:orchestrator", task_id="task")
    assert result["outputs"]["value"] == 7 and result["awaiting_human"] is True and len(result["run_ids"]) == 1
    assert _run_row(result["run_ids"][0])["task_id"] == "task"
    with pytest.raises(HTTPException) as invalid:
        platform.run_capability("test.echo", {"value": -1}, "human:troy")
    assert invalid.value.status_code == 422
    with pytest.raises(HTTPException) as unknown:
        platform.run_capability("test.missing", {}, "human:troy")
    assert unknown.value.status_code == 404


def test_require_human_mirrors_the_database_gate(db):
    for actor in (*AUTOMATED, " ", "System:reference"):
        with pytest.raises(platform.HumanActorRequired) as denied:
            platform.require_human(actor)
        assert denied.value.status_code == 403 and isinstance(denied.value, ValueError)
    platform.require_human("human:troy")
    with transaction() as connection:
        connection.execute("UPDATE actors SET active=0 WHERE id='human:jakob'")
    with connect() as connection, pytest.raises(HTTPException, match="inactive"):
        platform.require_human("human:jakob", connection)


def test_human_gate_trigger_maps_to_http_403(client):
    @signals.router.get("/_gate-probe")
    def probe():
        with transaction() as connection:
            connection.execute(_gate_statements()["scope_rubrics"], ("ai:agent:scorer",))

    try:
        main.app.include_router(signals.router)
        response = client.get("/signals/_gate-probe")
    finally:
        signals.router.routes.pop()
        main.app.router.routes[:] = [route for route in main.app.router.routes
                                     if getattr(route, "path", "") != "/signals/_gate-probe"]
    assert response.status_code == 403 and response.json()["detail"] == platform.HUMAN_REQUIRED


# Registration --------------------------------------------------------------------------------------

def test_every_pod_router_and_mcp_module_is_registered():
    mounted = {getattr(route, "path", None) for route in main.app.routes}
    pod_routers = [signals.router, markets.router, intake.router, prioritization.router, market_data.router,
                   *agent_runtime.routers]
    assert [router.prefix for router in pod_routers] == [
        "/signals", "/markets", "/requests", "/priorities", "/market-data",
        "/agents", "/capabilities", "/tasks", "/runs", "/threads"]
    for router in pod_routers:
        assert {route.path for route in router.routes} <= mounted, router.prefix
    assert (main.signals_router, main.markets_router, main.intake_router, main.prioritization_router,
            main.market_data_router) == tuple(pod_routers[:5])
    assert [register.__name__ for register in mcp_main.PLATFORM_TOOL_REGISTRARS] == [
        "register_signals_tools", "register_markets_tools", "register_intake_tools", "register_priority_tools",
        "register_market_data_tools", "register_agent_tools"]


# Sentiment view ------------------------------------------------------------------------------------

def test_weekly_sentiment_view_separates_sources_and_flags_undated(db):
    with transaction() as connection:
        _run(connection)
        for source_id, kind in (("bmw", "feedback"), ("web", "web")):
            connection.execute("INSERT INTO sources (id,title,kind,reference,vehicle,market) VALUES (?,?,?,'r','G60','US')",
                               (source_id, source_id, kind))
        for evidence_id, source_id, observed, polarity, label in (
                ("e1", "bmw", "2026-09-07", -0.6, "negative"), ("e2", "bmw", "2026-09-08T10:00:00.123456Z", 0.4, "positive"),
                ("e3", "bmw", None, 0.2, "positive"), ("e4", "web", "2026-09-07", 0.5, "positive")):
            connection.execute("INSERT INTO evidence VALUES (?,?,'G60','US','text','{}','{}',?,?, '2026-10-01T00:00:00Z')",
                               (evidence_id, source_id, observed, evidence_id))
            connection.execute("INSERT INTO sentiment_scores (id,subject_type,subject_id,topic,method_version,polarity,"
                               "label,input_hash,run_id,created_at) VALUES (?,'evidence',?,'comfort','lexicon-v1',?,?,"
                               "'h','run','t')", ("s-" + evidence_id, evidence_id, polarity, label))
    with connect() as connection:
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM v_sentiment_weekly ORDER BY source_class, week")]
    by_key = {(row["source_class"], row["week"]): row for row in rows}
    week = by_key[("bmw_evidence", "2026-36")]
    assert week["n"] == 2 and week["mean_polarity"] == pytest.approx(-0.1) and week["negative_share"] == 0.5
    assert sorted(json.loads(week["subject_ids"])) == ["e1", "e2"] and week["undated_n"] == 0
    assert by_key[("bmw_evidence", "2026-39")]["undated_n"] == 1
    assert by_key[("public_imported", "2026-36")]["positive_share"] == 1


# server/llm.py ---------------------------------------------------------------------------------------

class Verdict(BaseModel):
    label: str
    score: float = Field(ge=0, le=1)
    note: str | None = None


def _structured(client, run, value="text"):
    return client.structured(task="classify", prompt_version="test-v1", instructions="Classify.",
                             input={"text": value}, schema=Verdict, run=run)


def test_strict_schema_requires_every_property():
    schema = strict_schema(Verdict)
    assert schema["required"] == ["label", "score", "note"] and schema["additionalProperties"] is False
    assert "default" not in json.dumps(schema)


def test_structured_output_records_usage_and_serves_cache_hits(db):
    fake = FakeOpenAI(responder=lambda request: {"label": "positive", "score": 0.9, "note": None})
    client = fake_client(fake)
    with platform.record_run(None, "test.llm", "human:troy", client.method_version("test-v1"), {}) as run:
        first, second = _structured(client, run), _structured(client, run)
    assert first == second == Verdict(label="positive", score=0.9)
    assert len(fake.calls("/responses")) == 1
    request = fake.calls("/responses")[0]
    assert request["text"]["format"]["strict"] is True and request["store"] is False and request["model"] == "fake-model"
    llm = _run_row(run.id)["metrics"]["llm"]
    assert (llm["calls"], llm["cache_hits"], llm["total_tokens"], llm["models"]) == (1, 1, 18, ["fake-model"])
    assert [item["cached"] for item in llm["requests"]] == [False, True]
    assert _run_row(run.id)["method_version"] == "openai:fake-model:test-v1"
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM llm_cache").fetchone()[0] == 1


@pytest.mark.parametrize("raw", [FakeOpenAI.raw("not json"), FakeOpenAI.raw('{"label": "x", "score": 4}'),
                                 FakeOpenAI.raw('{"label": "x", "score": 0.1, "note": null, "extra": 1, "extra": 2}')])
def test_structured_output_rejects_invalid_json_or_schema(db, raw):
    client = fake_client(FakeOpenAI(responder=lambda request: raw))
    with pytest.raises(LLMOutputInvalid), platform.record_run(None, "test.llm", "human:troy", "v", {}) as run:
        _structured(client, run)
    assert _run_row(run.id)["status"] == "failed"
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM llm_cache").fetchone()[0] == 0


def test_incomplete_or_refused_responses_are_provider_errors(db):
    client = fake_client(FakeOpenAI(responder=lambda request: FakeOpenAI.raw("{}", status="incomplete")))
    with pytest.raises(ProviderUnavailable, match="did not complete"), \
            platform.record_run(None, "test.llm", "human:troy", "v", {}) as run:
        _structured(client, run)


def test_call_cap_per_run_is_enforced(db):
    fake = FakeOpenAI(responder=lambda request: {"label": "a", "score": 0.5, "note": None})
    client = fake_client(fake, max_calls_per_run=2)
    with pytest.raises(LLMBudgetExceeded), platform.record_run(None, "test.llm", "human:troy", "v", {}) as run:
        for value in ("one", "two", "three"):
            _structured(client, run, value)
    assert len(fake.calls("/responses")) == 2 and "budget" in _run_row(run.id)["error"]


def test_embeddings_are_ordered_cached_and_counted(db):
    fake = FakeOpenAI()
    client = fake_client(fake)
    with platform.record_run(None, "test.embed", "human:troy", "v", {}) as run:
        vectors = client.embed(["rear legroom", "exhaust note", "rear legroom"], run=run)
        again = client.embed(["exhaust note"], run=run)
    assert vectors[0] == vectors[2] == fake.vector("rear legroom") and again[0] == vectors[1]
    assert len(fake.calls("/embeddings")) == 1 and fake.calls("/embeddings")[0]["input"] == ["rear legroom", "exhaust note"]
    llm = _run_row(run.id)["metrics"]["llm"]
    assert llm["calls"] == 1 and llm["cache_hits"] == 1 and llm["models"] == ["text-embedding-3-small"]


def test_missing_credentials_raise_provider_unavailable(db, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    with pytest.raises(ProviderUnavailable, match="OPENAI_API_KEY"):
        llm_client()
    with pytest.raises(ProviderUnavailable):
        resolve_provider("openai", prompt_version="p1", deterministic_method="lexicon-v1")
    assert resolve_provider("deterministic", prompt_version="p1", deterministic_method="lexicon-v1") == (None, "lexicon-v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert llm_client().method_version("p1") == "openai:gpt-test:p1"


def test_fake_llm_fixture_overrides_the_configured_client(fake_llm):
    assert llm_client().model == "fake-model"
    assert resolve_provider("openai", prompt_version="p1", deterministic_method="x")[1] == "openai:fake-model:p1"


def test_citations_are_grounded_locally():
    text = "The rear seats feel  cramped on long trips, but the ride is quiet."
    assert locate_quote(text, "rear seats feel cramped") == (4, 28)
    assert text[slice(*locate_quote(text, "the RIDE is quiet"))] == "the ride is quiet"
    grounded = ground_citations([{"evidence_id": "e1", "quote": "ride is quiet"}], {"e1": text})
    assert grounded[0]["span"] == [52, 65] and text[52:65] == "ride is quiet"
    with pytest.raises(LLMOutputInvalid, match="outside"):
        ground_citations([{"evidence_id": "e2", "quote": "ride"}], {"e1": text})
    with pytest.raises(LLMOutputInvalid, match="not present"):
        ground_citations([{"evidence_id": "e1", "quote": "loud exhaust"}], {"e1": text})
