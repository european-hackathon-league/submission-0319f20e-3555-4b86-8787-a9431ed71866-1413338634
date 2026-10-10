"""Labelled SQLite snapshots with a manifest: python -m database.snapshot [--label NAME]."""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from database.store import database_path

TABLES = ("sources", "imports", "evidence", "analysis_runs", "findings", "finding_evidence", "requirements",
          "requirement_versions", "requirement_findings", "scores", "decisions", "review_items", "audit_events",
          "actors", "vehicles", "markets")


def snapshot_dir() -> Path:
    return Path(os.getenv("SNAPSHOT_DIR", str(Path(__file__).resolve().parent / "snapshots")))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit() -> str | None:
    if os.getenv("GIT_COMMIT"):
        return os.getenv("GIT_COMMIT")
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent,
                                capture_output=True, text=True, timeout=5, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def describe(path: Path) -> dict:
    """Database facts for a manifest. Contains counts and hashes only, no BMW content."""
    with closing(sqlite3.connect(path)) as connection:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        counts = {table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                  for table in TABLES if table in names}
        columns = {row[1] for row in connection.execute("PRAGMA table_info(audit_events)")}
        head = None
        if "event_hash" in columns:
            row = connection.execute("SELECT sequence, event_hash FROM audit_events "
                                     "ORDER BY sequence DESC LIMIT 1").fetchone()
            head = {"sequence": row[0], "event_hash": row[1]} if row else None
        inputs = []
        if "sources" in names and "content_hash" in {row[1] for row in connection.execute("PRAGMA table_info(sources)")}:
            inputs = [{"reference": row[0], "vehicle": row[1], "market": row[2], "sha256": row[3]}
                      for row in connection.execute("SELECT reference, vehicle, market, content_hash FROM sources "
                                                    "WHERE content_hash IS NOT NULL "
                                                    "ORDER BY reference, vehicle, market")]
        return {"user_version": connection.execute("PRAGMA user_version").fetchone()[0],
                "row_counts": counts, "audit_head": head, "inputs": inputs}


def manifest_path(snapshot: Path) -> Path:
    return snapshot.with_name(snapshot.name.removesuffix(".db") + ".manifest.json")


def create_snapshot(label: str | None = None, source: Path | None = None, directory: Path | None = None) -> Path:
    """Copy the committed database state with the backup API and write `<name>.manifest.json` beside it."""
    source = source or database_path()
    if not source.is_file():
        raise FileNotFoundError(f"Database does not exist: {source}")
    if label is not None and not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}", label):
        raise ValueError("Label must be lowercase letters, digits and dashes")
    directory = directory or snapshot_dir()
    directory.mkdir(parents=True, exist_ok=True)
    created = datetime.now(timezone.utc)
    name = "app-" + created.strftime("%Y%m%dT%H%M%S%fZ") + (f"-{label}" if label else "")
    target = directory / f"{name}.db"
    with closing(sqlite3.connect(source, timeout=10)) as live, closing(sqlite3.connect(target)) as backup:
        live.backup(backup)
        # A self-contained single file: no -wal/-shm to ship alongside, opens immutably.
        backup.execute("PRAGMA journal_mode = DELETE")
    manifest = {"file": target.name, "created_at": created.isoformat().replace("+00:00", "Z"), "label": label,
                "git_commit": _git_commit(), **describe(target), "sha256": file_sha256(target)}
    manifest_path(target).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return target


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label")
    args = parser.parse_args(argv)
    try:
        print(create_snapshot(args.label))
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
