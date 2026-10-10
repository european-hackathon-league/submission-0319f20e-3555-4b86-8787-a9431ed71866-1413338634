import json
import os
import sqlite3
import time
from contextlib import closing, contextmanager
from datetime import datetime, timezone
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
    connection.execute("PRAGMA foreign_keys = ON")
    # REPLACE deletes the existing row; recursive triggers make the append-only
    # DELETE guards apply to that implicit deletion too.
    connection.execute("PRAGMA recursive_triggers = ON")
    return connection


def _execute_schema(connection: sqlite3.Connection, path: Path) -> None:
    """Execute schema statements without executescript's implicit commit."""
    statement = ""
    for line in path.read_text().splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            connection.execute(statement)
            statement = ""
    if statement.strip():
        connection.execute(statement)


def init_database() -> None:
    with closing(connect()) as connection:
        _enable_wal(connection)
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_schema(connection, SCHEMA_PATH)
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(sources)")}
            for name, definition in {
                "content_hash": "TEXT",
                "metadata": "TEXT NOT NULL DEFAULT '{}'",
                "observed_at": "TEXT",
                "original_path": "TEXT",
            }.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE sources ADD COLUMN {name} {definition}")
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_source_hash_scope "
                               "ON sources(content_hash, vehicle, market) WHERE content_hash IS NOT NULL")
            _execute_schema(connection, SCHEMA_PATH.with_name("workflow.sql"))
            for table in ("evidence", "analysis_runs", "findings", "finding_evidence", "requirement_versions",
                          "requirement_findings", "scores", "decisions", "audit_events", "imports"):
                for action in ("UPDATE", "DELETE"):
                    connection.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action.lower()} "
                                       f"BEFORE {action} ON {table} BEGIN "
                                       f"SELECT RAISE(ABORT, '{table} is append-only'); END")
            connection.execute("PRAGMA user_version = 2")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def _enable_wal(connection) -> None:
    # SQLite's journal-mode transition can report BUSY immediately despite the
    # connection busy timeout when multiple processes create a database at once.
    deadline = time.monotonic() + 10
    while True:
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            return
        except sqlite3.OperationalError as exc:
            code = getattr(exc, "sqlite_errorcode", 0) & 255
            if (code not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
                    and str(exc) not in ("database is locked", "database table is locked")) or time.monotonic() >= deadline:
                raise
            time.sleep(0.025)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def new_id() -> str:
    return str(uuid4())


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


@contextmanager
def transaction():
    """Serialize writes and roll the complete workflow back if any step fails."""
    with closing(connect()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def audit(connection, entity_type: str, entity_id: str, action: str, actor: str,
          rationale: str, before=None, after=None, metadata=None) -> str:
    event_id = new_id()
    connection.execute(
        "INSERT INTO audit_events (id,entity_type,entity_id,action,actor,rationale,before_state,after_state,metadata,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (event_id, entity_type, entity_id, action, actor, rationale,
         encode(before) if before is not None else None, encode(after) if after is not None else None,
         encode(metadata or {}), now()),
    )
    return event_id


def decode(row, fields=()) -> dict | None:
    if row is None:
        return None
    result = dict(row)
    for field in fields:
        if result.get(field) is not None:
            result[field] = json.loads(result[field])
    return result


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
    return [decode(row, ("metadata",)) for row in rows]


def create_source(data: dict) -> dict:
    source_id = str(uuid4())
    with transaction() as connection:
        connection.execute(
            "INSERT INTO sources (id, title, kind, reference, vehicle, market) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (source_id, data["title"], data["kind"], data["reference"], data["vehicle"], data["market"]),
        )
        audit(connection, "source", source_id, "source.created", "PM", "Source registered", after=data)
    result = get_source(source_id)
    assert result is not None
    return result


def get_source(source_id: str) -> dict | None:
    with closing(connect()) as connection:
        row = connection.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    return decode(row, ("metadata",))
