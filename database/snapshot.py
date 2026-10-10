"""Create a consistent local SQLite backup: python -m database.snapshot."""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from database.store import database_path


def main() -> None:
    source = database_path()
    if not source.is_file():
        raise SystemExit(f"Database does not exist: {source}")

    directory = Path(os.getenv("SNAPSHOT_DIR", str(Path(__file__).resolve().parent / "snapshots")))
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = directory / f"app-{timestamp}.db"

    with sqlite3.connect(source) as live, sqlite3.connect(target) as backup:
        live.backup(backup)
    print(target)


if __name__ == "__main__":
    main()
