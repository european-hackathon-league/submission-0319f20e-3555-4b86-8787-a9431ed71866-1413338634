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


@pytest.fixture
def fake_llm(db):
    """Install an offline OpenAI double as llm_client() for this test (see tests/fakes.py)."""
    from server.llm import override_llm_client
    from tests.fakes import FakeOpenAI, fake_client

    fake = FakeOpenAI()
    with override_llm_client(fake_client(fake)):
        yield fake
