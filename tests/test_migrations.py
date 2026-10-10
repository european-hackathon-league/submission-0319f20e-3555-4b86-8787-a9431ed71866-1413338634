import sqlite3

import pytest

from database import migrate, store
from database.store import connect, init_database, transaction

HISTORY = ("imports", "evidence", "analysis_runs", "findings", "finding_evidence", "requirement_versions",
           "requirement_findings", "scores", "decisions", "audit_events")


def _v2_database(path):
    """A database as main produced it before migrations existed, holding one row per history table."""
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(store.SCHEMA_PATH.read_text())
        for column in ("content_hash TEXT", "metadata TEXT NOT NULL DEFAULT '{}'", "observed_at TEXT",
                       "original_path TEXT"):
            connection.execute(f"ALTER TABLE sources ADD COLUMN {column}")
        connection.executescript(store.SCHEMA_PATH.with_name("workflow.sql").read_text())
        for statement in [
            "INSERT INTO sources (id,title,kind,reference,vehicle,market) VALUES ('source','S','study','f','G60','US')",
            "INSERT INTO sources (id,title,kind,reference,vehicle,market) VALUES ('other','S','study','f','G99','XX')",
            "INSERT INTO imports VALUES ('import','source','f',1,'t')",
            "INSERT INTO evidence VALUES ('evidence','source','G60','US','Need','{}','{}',NULL,'h','t')",
            "INSERT INTO analysis_runs VALUES ('run','G60','US','p','m','v1','h','[]','[]','{}','t')",
            "INSERT INTO findings VALUES ('finding','run','G60','US','topic','need','Need',1,'t')",
            "INSERT INTO finding_evidence VALUES ('finding','evidence','supports')",
            "INSERT INTO requirements VALUES ('req1','G60','US','topic',NULL,NULL,NULL,'proposed','t1','t1')",
            "INSERT INTO requirements VALUES ('req2','G60','US','other',NULL,NULL,NULL,'proposed','t2','t2')",
            "INSERT INTO requirement_versions VALUES ('version','req1',1,'T','S','N','[]','[]','{}','PM','r','t')",
            "INSERT INTO requirement_findings VALUES ('version','finding')",
            "INSERT INTO scores VALUES ('score','version','v1','{}','{}',10,'high','{}','t')",
            "INSERT INTO decisions VALUES ('decision','req1','version','score','postpone','PM','later','t')",
            "INSERT INTO audit_events (id,entity_type,entity_id,action,actor,rationale,metadata,created_at) "
            "VALUES ('event','source','source','source.created','PM','legacy','{}','t')",
        ]:
            connection.execute(statement)
        connection.execute("PRAGMA user_version = 2")


def _rows(path, table):
    with sqlite3.connect(path) as connection:
        columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
        return [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")], columns


def test_v2_database_upgrades_without_changing_history(tmp_path, monkeypatch):
    path = tmp_path / "app.db"
    _v2_database(path)
    before = {table: _rows(path, table) for table in HISTORY}
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path / "snapshots"))

    init_database()
    init_database()

    for table, (rows, columns) in before.items():
        after, after_columns = _rows(path, table)
        assert [row[:len(columns)] for row in after[:len(rows)]] == rows, table
        assert after_columns[:len(columns)] == columns
    with connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == migrate.latest_version()
        statuses = dict(connection.execute("SELECT code, status FROM vehicles"))
        assert statuses["G60"] == "seeded" and statuses["G99"] == "discovered"
        assert dict(connection.execute("SELECT code, status FROM markets"))["XX"] == "discovered"
    for table in HISTORY:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"), transaction() as connection:
            connection.execute(f"DELETE FROM {table}")
    snapshots = list((tmp_path / "snapshots").glob("*-pre-migrate.db"))
    assert len(snapshots) == 1
    assert _rows(snapshots[0], "sources")[0] == _rows(path, "sources")[0]


def test_reinitialising_is_a_no_op(db, tmp_path, monkeypatch):
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path / "snapshots"))
    with connect() as connection:
        schema = list(connection.execute("SELECT name, sql FROM sqlite_master ORDER BY name"))
        actors = list(connection.execute("SELECT * FROM actors ORDER BY id"))
    init_database()
    with connect() as connection:
        assert list(connection.execute("SELECT name, sql FROM sqlite_master ORDER BY name")) == schema
        assert list(connection.execute("SELECT * FROM actors ORDER BY id")) == actors
    assert not (tmp_path / "snapshots").exists()


def test_failing_migration_rolls_back_completely(tmp_path, monkeypatch):
    path = tmp_path / "app.db"
    _v2_database(path)
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    for number, source in migrate.migrations():
        (migrations / source.name).write_text(source.read_text())
    broken = migrate.latest_version() + 1
    (migrations / f"{broken:04d}_broken.sql").write_text("CREATE TABLE half_done (id TEXT);\nnot sql;")
    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", migrations)
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.setenv("MIGRATION_SNAPSHOTS", "0")

    with pytest.raises(sqlite3.OperationalError):
        init_database()

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
        assert "actors" not in names and "half_done" not in names


def test_unknown_actors_are_discovered_and_inactive_actors_rejected(db):
    with transaction() as connection:
        store.audit(connection, "test", "id", "test", "Alice", "free-text human")
        store.audit(connection, "test", "id", "test", "AI:openai", "legacy AI id")
        store.audit(connection, "test", "id", "test", "System:reference", "legacy system id")
    with connect() as connection:
        rows = {row["id"]: (row["kind"], row["role"], row["origin"]) for row in connection.execute(
            "SELECT * FROM actors WHERE origin = 'discovered'")}
    assert rows == {"Alice": ("human", "pm", "discovered"), "AI:openai": ("ai", "ai", "discovered"),
                    "System:reference": ("system", "system", "discovered")}
    with transaction() as connection:
        connection.execute("UPDATE actors SET active = 0 WHERE id = 'human:jakob'")
    with pytest.raises(sqlite3.IntegrityError, match="inactive actor"), transaction() as connection:
        store.audit(connection, "test", "id", "test", "human:jakob", "inactive")
    with pytest.raises(sqlite3.IntegrityError, match="never deleted"), transaction() as connection:
        connection.execute("DELETE FROM actors WHERE id = 'human:jakob'")
    with pytest.raises(sqlite3.IntegrityError, match="fixed"), transaction() as connection:
        connection.execute("UPDATE actors SET kind = 'human' WHERE id = 'AI:openai'")


def test_unknown_scope_is_registered_as_discovered(client):
    payload = dict(title="Study", kind="study", reference="f.xlsx", vehicle="G99", market="BR")
    assert client.post("/sources", json=payload).status_code == 201
    with connect() as connection:
        assert connection.execute("SELECT status FROM vehicles WHERE code = 'G99'").fetchone()[0] == "discovered"
        assert connection.execute("SELECT status FROM markets WHERE code = 'BR'").fetchone()[0] == "discovered"
        assert connection.execute("SELECT status FROM vehicles WHERE code = 'G60'").fetchone()[0] == "seeded"
        assert connection.execute("SELECT parent_code FROM markets WHERE code = 'DE'").fetchone()[0] == "EU"


def test_openai_model_actor_is_seeded(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("OPENAI_MODEL", "GPT-5.1 mini")
    init_database()
    with connect() as connection:
        assert connection.execute("SELECT kind FROM actors WHERE id = 'ai:openai:gpt-5.1-mini'").fetchone()[0] == "ai"
