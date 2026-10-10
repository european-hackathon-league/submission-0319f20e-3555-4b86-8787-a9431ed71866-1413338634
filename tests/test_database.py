import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from database import store
from database.migrate import latest_version
from database.store import audit, connect, init_database, list_sources, transaction


def test_upgrades_existing_sources_without_losing_data(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sources (id TEXT PRIMARY KEY,title TEXT,kind TEXT,reference TEXT,"
                           "vehicle TEXT,market TEXT,created_at TEXT)")
        connection.execute("INSERT INTO sources VALUES ('original','legacy','study','file','G60','US','2026')")
    monkeypatch.setenv("DB_PATH", str(path))
    init_database()
    init_database()
    assert list_sources()[0]["id"] == "original"
    assert list_sources()[0]["metadata"] == {}


def test_transaction_rolls_back_and_history_is_immutable(db):
    with pytest.raises(RuntimeError), transaction() as connection:
        audit(connection, "test", "id", "test", "PM", "rollback")
        raise RuntimeError("abort")
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 0
    with transaction() as connection:
        audit(connection, "test", "id", "test", "PM", "persist")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"), transaction() as connection:
        connection.execute("DELETE FROM audit_events")


def test_source_api_compatibility(client):
    payload = dict(title="A study", kind="study", reference="study.xlsx", vehicle="G60", market="US")
    response = client.post("/sources", json=payload)
    assert response.status_code == 201
    source = response.json()
    assert client.get(f"/sources/{source['id']}").json() == source
    assert len(client.get("/sources?vehicle=G60&market=US").json()) == 1
    assert client.get("/sources?market=CN").json() == []
    assert client.get("/sources/unknown").status_code == 404


def test_failed_migration_rolls_back_schema_and_preserves_sources(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sources (id TEXT PRIMARY KEY,title TEXT,kind TEXT,reference TEXT,"
                           "vehicle TEXT,market TEXT,created_at TEXT)")
        connection.execute("INSERT INTO sources VALUES ('original','legacy','study','file','G60','US','2026')")
    schema = tmp_path / "schema.sql"
    schema.write_text(store.SCHEMA_PATH.read_text())
    schema.with_name("workflow.sql").write_text("CREATE TABLE partial_migration (id TEXT);\ninvalid SQL;")
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.setattr(store, "SCHEMA_PATH", schema)

    with pytest.raises(sqlite3.OperationalError):
        init_database()

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT * FROM sources").fetchone()[0] == "original"
        assert "metadata" not in {row[1] for row in connection.execute("PRAGMA table_info(sources)")}
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'partial_migration'").fetchone() is None
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0

    monkeypatch.setattr(store, "SCHEMA_PATH", Path(store.__file__).with_name("schema.sql"))
    init_database()
    assert list_sources()[0]["metadata"] == {}


def test_concurrent_initialization_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "concurrent.db"))
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: init_database(), range(8)))
    with connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == latest_version()
        assert len(list(connection.execute("PRAGMA table_info(sources)"))) == 11


def test_concurrent_transactions_preserve_all_history(db):
    def write_event(index):
        with transaction() as connection:
            audit(connection, "test", str(index), "created", "PM", "concurrent write")

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(write_event, range(12)))
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 12


def test_foreign_key_failure_rolls_back_entire_workflow(db):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"), transaction() as connection:
        audit(connection, "source", "missing", "imported", "PM", "must roll back")
        connection.execute("INSERT INTO imports VALUES ('import', 'missing', 'file.xlsx', 1, 'now')")
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM imports").fetchone()[0] == 0


@pytest.fixture
def history_records(db):
    with transaction() as connection:
        statements = [
            "INSERT INTO sources (id,title,kind,reference,vehicle,market) "
            "VALUES ('source','Study','study','file.xlsx','G60','US')",
            "INSERT INTO imports VALUES ('import','source','file.xlsx',1,'now')",
            "INSERT INTO evidence VALUES ('evidence','source','G60','US','A customer need','{}','{}',NULL,'hash','now')",
            "INSERT INTO analysis_runs VALUES ('run','G60','US','provider','model','v1','hash','[]','[]','{}','now')",
            "INSERT INTO findings VALUES ('finding','run','G60','US','topic','need','Customer need',1,'now')",
            "INSERT INTO finding_evidence VALUES ('finding','evidence','supports')",
            "INSERT INTO requirements (id,vehicle,market,topic,status,created_at,updated_at) "
            "VALUES ('requirement','G60','US','topic','proposed','now','now')",
            "INSERT INTO requirement_versions VALUES "
            "('version','requirement',1,'Title','Statement','Need','[]','[]','{}','PM','Draft','now')",
            "INSERT INTO requirement_findings VALUES ('version','finding')",
            "INSERT INTO scores VALUES ('score','version','v1','{}','{}',10,'high','{}','now')",
            "INSERT INTO decisions VALUES ('decision','requirement','version','score','approve','PM','Approved','now')",
        ]
        for statement in statements:
            connection.execute(statement)
        audit(connection, "requirement", "requirement", "created", "PM", "history")


@pytest.mark.parametrize("table", [
    "imports", "evidence", "analysis_runs", "findings", "finding_evidence", "requirement_versions",
    "requirement_findings", "scores", "decisions", "audit_events",
])
@pytest.mark.parametrize("mutation", ["update", "delete", "replace"])
def test_all_history_rejects_mutation_including_replace(history_records, table, mutation):
    with connect() as connection:
        before = [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")]
        column = connection.execute(f"PRAGMA table_info({table})").fetchone()["name"]
    statements = {
        "update": f"UPDATE {table} SET {column} = {column}",
        "delete": f"DELETE FROM {table}",
        "replace": f"INSERT OR REPLACE INTO {table} SELECT * FROM {table}",
    }
    with pytest.raises(sqlite3.IntegrityError, match="append-only"), transaction() as connection:
        connection.execute(statements[mutation])
    with connect() as connection:
        assert [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")] == before
