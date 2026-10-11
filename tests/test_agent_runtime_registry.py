"""Pod F migration 0015: the seeded agent registry and the database gates under the runtime API."""

import json
import sqlite3

import pytest

from database.store import connect, transaction

ROSTER = {  # slug: (department, autonomy level)
    "orchestrator": ("orchestration", "A0"), "feedback-analyst": ("customer_insights", "A1"),
    "trend-scout": ("market_intelligence", "A1"), "competitor-analyst": ("market_intelligence", "A1"),
    "market-balancer": ("market_intelligence", "A1"), "request-triage": ("communications", "A1"),
    "requirement-writer": ("requirements", "A1"), "scorer": ("requirements", "A0"),
    "challenger": ("governance", "A2"), "change-watcher": ("governance", "A2"),
    "comms-drafter": ("communications", "A3"), "research-planner": ("customer_insights", "A1"),
}
POD_CAPABILITIES = {
    "signals.refresh_watchlist", "signals.backfill_watchlist", "signals.score_sentiment", "signals.summarise",
    "markets.compare", "markets.detect_conflicts", "requests.cluster", "requests.link_evidence", "requests.triage",
    "priorities.derive_inputs", "priorities.rank", "priorities.sensitivity", "market_data.import_bmw",
    "market_data.derive_weights", "market_data.derive_preserve", "market_data.coverage",
    "pipeline.analyze", "pipeline.generate_requirements", "pipeline.assess_updates",
}


def _agents():
    with connect() as connection:
        return {row["slug"]: dict(row) for row in connection.execute("SELECT * FROM agents ORDER BY rowid")}


def _task(connection, task_id="task", status="queued"):
    connection.execute("INSERT INTO tasks (id,vehicle,market,capability,title,input,requested_by,status,created_at,"
                       "updated_at) VALUES (?,'G60','US','pipeline.analyze','T','{}','human:troy',?,'t','t')",
                       (task_id, status))


def test_registry_seeds_the_roster_as_a_hierarchy(db):
    agents = _agents()
    assert {slug: (row["department"], row["autonomy_level"]) for slug, row in agents.items()} == ROSTER
    assert agents["orchestrator"]["parent_agent_id"] is None
    assert {row["parent_agent_id"] for slug, row in agents.items() if slug != "orchestrator"} == {"ai:agent:orchestrator"}
    assert agents["scorer"]["id"] == "system:agent:scorer"
    assert all(row["id"] == f"ai:agent:{slug}" for slug, row in agents.items() if slug != "scorer")
    assert all(row["status"] == "active" and row["model"] is None for row in agents.values())
    granted = {name for row in agents.values() for name in json.loads(row["capabilities"])}
    assert granted == POD_CAPABILITIES
    assert json.loads(agents["orchestrator"]["capabilities"]) == []  # plans and delegates, runs nothing itself


def test_seeded_agents_are_registered_actors(db):
    with connect() as connection:
        actors = {row["id"]: (row["kind"], row["role"]) for row in connection.execute(
            "SELECT id, kind, role FROM actors WHERE id GLOB '*:agent:*'")}
    assert actors["ai:agent:market-balancer"] == ("ai", "ai")
    assert actors["system:agent:scorer"] == ("system", "system")
    assert len(actors) == len(ROSTER)


def test_re_registering_an_agent_keeps_the_reviewed_row(db):
    with transaction() as connection:
        connection.execute("UPDATE agents SET status='paused', status_changed_by='human:troy' "
                           "WHERE id='ai:agent:trend-scout'")
        connection.execute("INSERT INTO agents (id,slug,display_name,department,description,autonomy_level,"
                           "capabilities,created_at,updated_at) VALUES ('ai:agent:trend-scout','trend-scout','X',"
                           "'governance','d','A3','[]','t','t')")
    row = _agents()["trend-scout"]
    assert (row["status"], row["department"], row["display_name"]) == ("paused", "market_intelligence", "Trend scout")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"), transaction() as connection:
        connection.execute("INSERT INTO agents (id,slug,display_name,department,description,autonomy_level,"
                           "capabilities,created_at,updated_at) VALUES ('system:agent:trend-scout','trend-scout','X',"
                           "'governance','d','A0','[]','t','t')")


@pytest.mark.parametrize("actor", ["ai:agent:orchestrator", "system:scheduler", None])
def test_model_changes_need_a_human(db, actor):
    with pytest.raises(sqlite3.IntegrityError, match="human actor"), transaction() as connection:
        connection.execute("UPDATE agents SET model='gpt-test', model_changed_by=? WHERE slug='challenger'", (actor,))


def test_model_is_human_configured_and_never_set_on_deterministic_agents(db):
    with transaction() as connection:
        connection.execute("UPDATE agents SET model='gpt-test', model_changed_by='human:troy' WHERE slug='challenger'")
    assert _agents()["challenger"]["model"] == "gpt-test"
    with pytest.raises(sqlite3.IntegrityError, match="no model"), transaction() as connection:
        connection.execute("UPDATE agents SET model='gpt-test', model_changed_by='human:troy' WHERE slug='scorer'")
    with pytest.raises(sqlite3.IntegrityError, match="no model"), transaction() as connection:
        connection.execute("INSERT INTO agents (id,slug,display_name,department,description,autonomy_level,"
                           "capabilities,model,created_at,updated_at) VALUES ('system:agent:ranker','ranker','R',"
                           "'requirements','d','A0','[]','gpt-test','t','t')")


@pytest.mark.parametrize(("start", "status"), [("queued", "cancelled"), ("awaiting_human", "succeeded")])
@pytest.mark.parametrize("actor", ["ai:agent:orchestrator", "system:scheduler", None])
def test_cancel_and_accept_need_a_human(db, start, status, actor):
    with transaction() as connection:
        _task(connection, status=start)
    with pytest.raises(sqlite3.IntegrityError, match="human actor"), transaction() as connection:
        connection.execute("UPDATE tasks SET status=?, updated_by=?, revision=revision+1", (status, actor))
    with transaction() as connection:
        connection.execute("UPDATE tasks SET status=?, updated_by='human:jakob', revision=revision+1", (status,))


def test_finished_tasks_are_final(db):
    with transaction() as connection:
        _task(connection, "done", "running")
        connection.execute("UPDATE tasks SET status='succeeded', updated_by='system:agent-runtime', revision=revision+1")
    with pytest.raises(sqlite3.IntegrityError, match="final"), transaction() as connection:
        connection.execute("UPDATE tasks SET status='queued', revision=revision+1")
