import pytest
from fastapi.testclient import TestClient

from database.store import init_database
from server.main import app


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    init_database()
    return tmp_path / "app.db"


@pytest.fixture
def client(db):
    with TestClient(app) as client:
        yield client

