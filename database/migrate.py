"""Numbered schema migrations from user_version 3 onward.

Each `migrations/NNNN_name.sql` runs once, in order, inside the caller's transaction (init_database()
holds BEGIN IMMEDIATE). A Python hook may follow a file in the same transaction. Migrations only add
tables, columns, triggers and views; append-only rows are never rewritten.
"""

import os
import re
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
BASE_VERSION = 2  # Created by init_database() itself.


def _seed(connection: sqlite3.Connection) -> None:
    from database.seed import seed

    seed(connection)


def _seal_audit_history(connection: sqlite3.Connection) -> None:
    from database.store import seal_audit_history

    seal_audit_history(connection)


HOOKS = {3: _seed, 5: _seal_audit_history}


def migrations() -> list[tuple[int, Path]]:
    found = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        match = re.fullmatch(r"(\d{4})_[a-z0-9_]+\.sql", path.name)
        if not match:
            raise RuntimeError(f"Invalid migration file name: {path.name}")
        found.append((int(match.group(1)), path))
    numbers = [number for number, _ in found]
    if numbers != list(range(BASE_VERSION + 1, BASE_VERSION + 1 + len(numbers))):
        raise RuntimeError(f"Migrations must be numbered consecutively from {BASE_VERSION + 1}: {numbers}")
    return found


def latest_version() -> int:
    found = migrations()
    return found[-1][0] if found else BASE_VERSION


def _has_data(connection: sqlite3.Connection) -> bool:
    return any(connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
               for table in ("sources", "audit_events", "requirements"))


def _pre_migrate_snapshot(connection: sqlite3.Connection) -> None:
    """Copy the last committed state before changing a database that already holds data."""
    if os.getenv("MIGRATION_SNAPSHOTS", "1") == "0":
        return
    path = connection.execute("PRAGMA database_list").fetchone()[2]
    if not path:
        return
    from database.snapshot import create_snapshot

    create_snapshot(label="pre-migrate", source=Path(path))


def apply_migrations(connection: sqlite3.Connection) -> int:
    """Apply every pending migration in the open transaction; return the resulting user_version."""
    from database.store import _execute_schema

    current = connection.execute("PRAGMA user_version").fetchone()[0]
    pending = [(number, path) for number, path in migrations() if number > current]
    if not pending:
        return current
    if current >= BASE_VERSION and _has_data(connection):
        _pre_migrate_snapshot(connection)
    for number, path in pending:
        _execute_schema(connection, path)
        if number in HOOKS:
            HOOKS[number](connection)
        connection.execute(f"PRAGMA user_version = {number}")
    return pending[-1][0]
