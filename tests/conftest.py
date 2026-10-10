import pytest
from fastapi.testclient import TestClient

from database.store import init_database
from server.main import app


@pytest.fixture(autouse=True)
def isolated_snapshots(tmp_path, monkeypatch):
    """Automatic pre-migrate snapshots must never land in the repository's database/snapshots."""
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path / "snapshots"))


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    init_database()
    return tmp_path / "app.db"


@pytest.fixture
def client(db):
    with TestClient(app) as client:
        yield client

