import os
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4


DEFAULT_DB_PATH = Path(__file__).resolve().parent / "local" / "app.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def database_path() -> Path:
    return Path(os.getenv("DB_PATH", str(DEFAULT_DB_PATH)))


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def init_database() -> None:
    with closing(connect()) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(SCHEMA_PATH.read_text())
        connection.commit()


def ping_database() -> None:
    with closing(connect()) as connection:
        connection.execute("SELECT 1").fetchone()


def list_sources(vehicle: str | None = None, market: str | None = None) -> list[dict]:
    clauses = []
    params = []
    if vehicle is not None:
        clauses.append("vehicle = ?")
        params.append(vehicle)
    if market is not None:
        clauses.append("market = ?")
        params.append(market)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with closing(connect()) as connection:
        rows = connection.execute(
            "SELECT * FROM sources" + where + " ORDER BY created_at DESC, id DESC",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def create_source(data: dict) -> dict:
    source_id = str(uuid4())
    with closing(connect()) as connection:
        connection.execute(
            "INSERT INTO sources (id, title, kind, reference, vehicle, market) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (source_id, data["title"], data["kind"], data["reference"], data["vehicle"], data["market"]),
        )
        connection.commit()
    result = get_source(source_id)
    assert result is not None
    return result


def get_source(source_id: str) -> dict | None:
    with closing(connect()) as connection:
        row = connection.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    return dict(row) if row else None
