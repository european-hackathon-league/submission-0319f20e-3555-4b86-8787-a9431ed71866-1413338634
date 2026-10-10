import sqlite3

import pytest

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
