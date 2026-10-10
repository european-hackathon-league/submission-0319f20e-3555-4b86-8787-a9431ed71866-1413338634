"""Database operations: python -m database.cli <command>.

snapshot  labelled backup + manifest          verify   integrity, guards, schema and audit chain
restore   replace the live DB from a snapshot  seed     idempotent reference data
export    requirement list as CSV or JSON      rebuild  fresh DB from the original BMW inputs
"""

import argparse
import csv
import io
import json
import os
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from database import store
from database.integrity import verify
from database.snapshot import create_snapshot, file_sha256, manifest_path, snapshot_dir

ROOT = Path(__file__).resolve().parents[1]


def _print(result: dict) -> None:
    print(json.dumps(result, indent=2, sort_keys=True))


def cmd_snapshot(args) -> int:
    path = create_snapshot(args.label)
    _print({"snapshot": str(path), "manifest": str(manifest_path(path))})
    return 0


def cmd_verify(args) -> int:
    path = Path(args.file) if args.file else store.database_path()
    result = verify(path, require_latest=not args.allow_older)
    snapshot_manifest = manifest_path(path)
    if args.file and snapshot_manifest.is_file():
        expected = json.loads(snapshot_manifest.read_text())["sha256"]
        result["manifest_sha256_matches"] = expected == file_sha256(path)
        if not result["manifest_sha256_matches"]:
            result["ok"] = False
            result["errors"].append("file SHA-256 differs from its manifest")
    _print(result)
    return 0 if result["ok"] else 1


def _writer_active(path: Path) -> bool:
    """Lock probe: True if another connection holds the write lock right now."""
    try:
        with closing(sqlite3.connect(path, timeout=0)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.rollback()
        return False
    except sqlite3.OperationalError:
        return True


def cmd_restore(args) -> int:
    source, target = Path(args.file), store.database_path()
    manifest = manifest_path(source)
    if manifest.is_file():
        if json.loads(manifest.read_text())["sha256"] != file_sha256(source):
            raise SystemExit(f"Refusing: {source.name} does not match its manifest")
    elif not args.allow_missing_manifest:
        raise SystemExit(f"Refusing: no manifest at {manifest} (pass --allow-missing-manifest to override)")
    result = verify(source, require_latest=False)
    if not result["ok"]:
        _print(result)
        raise SystemExit(f"Refusing: {source.name} failed verification")
    if target.exists() and _writer_active(target):
        raise SystemExit("Refusing: the live database is being written; stop the API first (docker compose stop api)")
    safety = create_snapshot("pre-restore", source=target) if target.exists() else None
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(target.name + ".restoring")
    with closing(sqlite3.connect(source)) as snapshot, closing(sqlite3.connect(staging)) as copy:
        snapshot.backup(copy)
    for suffix in ("-wal", "-shm"):
        Path(str(target) + suffix).unlink(missing_ok=True)
    os.replace(staging, target)
    _print({"restored": str(target), "from": str(source), "safety_snapshot": str(safety) if safety else None,
            "user_version": result["user_version"], "audit_head": result["audit_chain"].get("head")})
    return 0


def cmd_seed(args) -> int:
    from database.seed import seed

    store.init_database()
    with store.transaction() as connection:
        seed(connection)
        counts = {table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                  for table in ("actors", "vehicles", "markets")}
    _print({"seeded": counts})
    return 0


def cmd_export(args) -> int:
    store.init_database()
    clauses, params = [], []
    for column in ("vehicle", "market"):
        if getattr(args, column):
            clauses.append(f"{column} = ?")
            params.append(getattr(args, column))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with store.transaction() as connection:
        rows = [dict(row) for row in connection.execute(
            f"SELECT * FROM v_requirement_list{where} ORDER BY vehicle, market, rank IS NULL, rank, key", params)]
        if args.format == "json":
            content = json.dumps(rows, indent=2, ensure_ascii=False) + "\n"
        else:
            buffer = io.StringIO()
            columns = [row["name"] for row in connection.execute("PRAGMA table_info(v_requirement_list)")]
            writer = csv.DictWriter(buffer, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
            content = buffer.getvalue()
        directory = Path(args.output_dir) if args.output_dir else snapshot_dir() / "exports"
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = directory / f"requirements-{stamp}.{args.format}"
        path.write_text(content)
        store.audit(connection, "export", path.name, "access.export", args.actor, "Requirement list exported",
                    metadata={"format": args.format, "rows": len(rows), "vehicle": args.vehicle,
                              "market": args.market, "keys": [row["key"] for row in rows]})
    _print({"export": str(path), "rows": len(rows)})
    return 0


def _kind(name: str) -> str:
    lower = name.lower()
    for word, kind in (("feedback", "feedback"), ("stud", "study"), ("sales", "sales")):
        if word in lower:
            return kind
    return "document"


def cmd_rebuild(args) -> int:
    from fastapi import HTTPException

    target = Path(args.target).resolve()
    if target.exists():
        raise SystemExit(f"Refusing: {target} exists; rebuild always starts from a fresh database")
    data_dir = Path(args.data_dir or os.getenv("DATA_DIR", str(ROOT / "data")))
    inventory = json.loads(Path(args.inventory).read_text())
    scopes = [tuple(scope.split(":", 1)) for scope in args.scope]
    os.environ["DB_PATH"] = str(target)
    store.init_database()
    from server.evidence import import_file

    report = {"target": str(target), "imports": [], "skipped": [], "missing": [], "mismatched": []}
    for entry in inventory["files"]:
        if entry["kind"] != "google-drive-input":
            continue
        path = data_dir / entry["path"].removeprefix("data/")
        if not path.is_file():
            report["missing"].append(entry["path"])
            continue
        if file_sha256(path) != entry["sha256"]:
            report["mismatched"].append(entry["path"])
            continue
        data = path.read_bytes()
        for vehicle, market in scopes:
            try:
                result = import_file(path.name, data, vehicle, market, kind=_kind(path.name), actor="system:importer")
            except HTTPException as exc:
                report["skipped"].append({"file": path.name, "scope": f"{vehicle}:{market}", "reason": exc.detail})
                continue
            report["imports"].append({"file": path.name, "scope": f"{vehicle}:{market}",
                                      "records": result["record_count"]})
    report["analysis"] = "not replayed: no persisted analysis runs to reuse yet (backend milestone 4)"
    report["verify"] = verify(target)
    _print(report)
    return 0 if not report["mismatched"] and report["verify"]["ok"] else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m database.cli", description=__doc__,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = root.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot", help="labelled backup with manifest")
    snapshot.add_argument("--label")
    snapshot.set_defaults(run=cmd_snapshot)
    check = commands.add_parser("verify", help="verify the live database or a snapshot file")
    check.add_argument("file", nargs="?")
    check.add_argument("--allow-older", action="store_true", help="accept a schema that migrates on next start")
    check.set_defaults(run=cmd_verify)
    restore = commands.add_parser("restore", help="replace the live database with a verified snapshot")
    restore.add_argument("file")
    restore.add_argument("--allow-missing-manifest", action="store_true")
    restore.set_defaults(run=cmd_restore)
    commands.add_parser("seed", help="idempotent reference data").set_defaults(run=cmd_seed)
    export = commands.add_parser("export", help="export v_requirement_list")
    export.add_argument("--format", choices=("csv", "json"), default="csv")
    export.add_argument("--vehicle")
    export.add_argument("--market")
    export.add_argument("--actor", default="system:cli")
    export.add_argument("--output-dir")
    export.set_defaults(run=cmd_export)
    rebuild = commands.add_parser("rebuild", help="fresh database from the original inputs in DATA_DIR")
    rebuild.add_argument("--target", required=True)
    rebuild.add_argument("--scope", action="append", help="VEHICLE:MARKET, repeatable (default G60:US)")
    rebuild.add_argument("--data-dir")
    rebuild.add_argument("--inventory", default=str(ROOT / "notes" / "source-inventory.json"))
    rebuild.set_defaults(run=cmd_rebuild)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if getattr(args, "scope", None) is None and args.command == "rebuild":
        args.scope = ["G60:US"]
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
