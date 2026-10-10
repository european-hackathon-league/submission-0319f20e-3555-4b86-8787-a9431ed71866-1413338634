import sqlite3

import pytest

from database.store import audit, connect, init_database, transaction


def _requirement(connection, requirement_id="req", topic="topic", vehicle="G60", market="US"):
    connection.execute("INSERT INTO requirements (id,vehicle,market,topic,status,created_at,updated_at) "
                       "VALUES (?,?,?,?,'proposed','t','t')", (requirement_id, vehicle, market, topic))
    connection.execute("INSERT INTO requirement_versions VALUES (?,?,1,'Title','Statement','Need','[]','[]','{}',"
                       "'ai:reference:v1','Proposed from findings','t')", (requirement_id + "-v1", requirement_id))
    connection.execute("INSERT INTO scores VALUES (?,?,'v1','{}','{}',3.5,'B','{}','t')",
                       (requirement_id + "-s1", requirement_id + "-v1"))
    connection.execute("UPDATE requirements SET current_version_id = ? WHERE id = ?",
                       (requirement_id + "-v1", requirement_id))


def _decide(connection, action, actor, requirement_id="req", decision_id=None):
    connection.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,'t')",
                       (decision_id or f"{requirement_id}-{action}-{actor}", requirement_id, requirement_id + "-v1",
                        requirement_id + "-s1", action, actor, "rationale"))


def _approve(connection, requirement_id="req"):
    connection.execute("UPDATE requirements SET approved_version_id = ?, approved_score_id = ?, status = 'approved' "
                       "WHERE id = ?", (requirement_id + "-v1", requirement_id + "-s1", requirement_id))


@pytest.fixture
def requirement(db):
    with transaction() as connection:
        _requirement(connection)


def _status(requirement_id="req"):
    with connect() as connection:
        return connection.execute("SELECT status, approved_version_id FROM requirements WHERE id = ?",
                                  (requirement_id,)).fetchone()


@pytest.mark.parametrize("actor,message", [
    ("ai:reference:v1", "human actor"),
    ("system:scoring", "human actor"),
    ("Somebody", "unknown or inactive actor|human actor"),
])
def test_ai_and_system_actors_cannot_decide(requirement, actor, message):
    with pytest.raises(sqlite3.IntegrityError, match=message), transaction() as connection:
        _decide(connection, "approve", actor)
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM decisions").fetchone()[0] == 0


def test_approve_and_reject_require_pm_role(requirement):
    with transaction() as connection:
        connection.execute("INSERT INTO actors (id,kind,display_name,role) "
                           "VALUES ('human:eng','human','Engineer','engineering')")
    for action in ("approve", "reject"):
        with pytest.raises(sqlite3.IntegrityError, match="PM role"), transaction() as connection:
            _decide(connection, action, "human:eng")
    with transaction() as connection:
        _decide(connection, "challenge", "human:eng")


def test_approval_without_decision_fails(requirement):
    with pytest.raises(sqlite3.IntegrityError, match="approval requires a PM decision"), transaction() as connection:
        _approve(connection)
    with transaction() as connection:
        _decide(connection, "postpone", "human:jakob")
    with pytest.raises(sqlite3.IntegrityError, match="approval requires a PM decision"), transaction() as connection:
        _approve(connection)
    with pytest.raises(sqlite3.IntegrityError, match="decision workflow|needs an approved version"), \
            transaction() as connection:
        connection.execute("UPDATE requirements SET status = 'approved' WHERE id = 'req'")
    assert tuple(_status()) == ("proposed", None)


def test_pm_approval_succeeds_and_is_audited(requirement):
    with transaction() as connection:
        _decide(connection, "approve", "human:troy", decision_id="decision")
        _approve(connection)
        audit(connection, "decision", "decision", "requirement.approved", "human:troy", "Clear customer need")
    assert tuple(_status()) == ("approved", "req-v1")
    with connect() as connection:
        event = connection.execute("SELECT actor, action FROM audit_events WHERE entity_id = 'decision'").fetchone()
    assert tuple(event) == ("human:troy", "requirement.approved")
    with pytest.raises(sqlite3.IntegrityError, match="decision workflow"), transaction() as connection:
        connection.execute("UPDATE requirements SET status = 'proposed' WHERE id = 'req'")
    with transaction() as connection:
        connection.execute("UPDATE requirements SET status = 'needs_review' WHERE id = 'req'")


def test_decision_must_match_requirement_version_and_score(requirement):
    with transaction() as connection:
        _requirement(connection, "other", topic="other")
    with pytest.raises(sqlite3.IntegrityError, match="must belong"), transaction() as connection:
        connection.execute("INSERT INTO decisions VALUES ('d','req','other-v1','other-s1','approve','PM','x','t')")


def test_requirements_cannot_be_created_approved_or_deleted(requirement):
    with pytest.raises(sqlite3.IntegrityError, match="start proposed"), transaction() as connection:
        connection.execute("INSERT INTO requirements (id,vehicle,market,topic,status,created_at,updated_at) "
                           "VALUES ('x','G60','US','x','approved','t','t')")
    with pytest.raises(sqlite3.IntegrityError, match="never deleted"), transaction() as connection:
        connection.execute("DELETE FROM requirements")


def test_requirement_keys_are_sequential_per_scope_and_fixed(db):
    with transaction() as connection:
        _requirement(connection, "a", topic="a")
        _requirement(connection, "b", topic="b")
        _requirement(connection, "c", topic="c", market="CN")
    with connect() as connection:
        keys = dict(connection.execute("SELECT id, key FROM requirements"))
    assert keys == {"a": "REQ-G60-US-001", "b": "REQ-G60-US-002", "c": "REQ-G60-CN-001"}
    with pytest.raises(sqlite3.IntegrityError, match="fixed"), transaction() as connection:
        connection.execute("UPDATE requirements SET key = 'REQ-G60-US-009' WHERE id = 'a'")
    with pytest.raises(sqlite3.IntegrityError, match="assigned by the database"), transaction() as connection:
        connection.execute("INSERT INTO requirements (id,vehicle,market,topic,key,status,created_at,updated_at) "
                           "VALUES ('d','G60','US','d','REQ-G60-US-003','proposed','t','t')")
    with pytest.raises(sqlite3.IntegrityError, match="only increase"), transaction() as connection:
        connection.execute("UPDATE requirement_key_sequences SET last_number = 0")


def test_failed_creation_does_not_consume_a_key(db):
    with pytest.raises(RuntimeError), transaction() as connection:
        _requirement(connection, "a", topic="a")
        raise RuntimeError("abort")
    with transaction() as connection:
        _requirement(connection, "b", topic="b")
    with connect() as connection:
        assert connection.execute("SELECT key FROM requirements").fetchone()[0] == "REQ-G60-US-001"


def test_existing_requirements_receive_keys_on_upgrade(tmp_path, monkeypatch):
    from tests.test_migrations import _v2_database

    path = tmp_path / "app.db"
    _v2_database(path)
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.setenv("MIGRATION_SNAPSHOTS", "0")
    init_database()
    with transaction() as connection:
        connection.execute("INSERT INTO requirements (id,vehicle,market,topic,status,created_at,updated_at) "
                           "VALUES ('req3','G60','US','third','proposed','t3','t3')")
    with connect() as connection:
        keys = dict(connection.execute("SELECT id, key FROM requirements"))
    assert keys == {"req1": "REQ-G60-US-001", "req2": "REQ-G60-US-002", "req3": "REQ-G60-US-003"}
