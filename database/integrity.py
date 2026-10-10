"""Database verification: SQLite integrity, append-only guards, schema version and the audit hash chain."""

import sqlite3
from contextlib import closing
from pathlib import Path

from database.migrate import latest_version
from database.store import audit_event_hash, pre_chain_digest

HISTORY_TABLES = ("evidence", "analysis_runs", "findings", "finding_evidence", "requirement_versions",
                  "requirement_findings", "scores", "decisions", "audit_events", "imports")
GOVERNANCE_TRIGGERS = ("audit_events_known_actor", "requirement_versions_known_actor", "decisions_known_actor",
                       "decisions_human_actor", "decisions_pm_role", "requirements_approval_requires_decision",
                       "requirements_status_workflow", "requirements_assign_key", "audit_events_chain")


def verify_audit_chain(connection: sqlite3.Connection) -> dict:
    """Walk the chain in sequence order and report the first event whose linkage or content does not match."""
    connection.row_factory = sqlite3.Row
    rows = connection.execute("SELECT * FROM audit_events ORDER BY sequence").fetchall()
    pre_chain, previous = [], None
    for row in rows:
        if previous is None and row["event_hash"] is None:
            pre_chain.append(row)
            continue
        if row["event_hash"] is None:
            return {"ok": False, "events": len(rows), "broken_at": row["sequence"], "reason": "unhashed event"}
        if previous is None:
            expected = pre_chain_digest(pre_chain)
            if pre_chain and row["action"] != "audit.chain.started":
                return {"ok": False, "events": len(rows), "broken_at": row["sequence"],
                        "reason": "pre-chain events are not sealed by a genesis event"}
        else:
            expected = previous["event_hash"]
        if row["prev_hash"] != expected:
            reason = "sealed pre-chain history changed" if previous is None else "previous event changed or removed"
            return {"ok": False, "events": len(rows), "broken_at": row["sequence"], "reason": reason}
        if audit_event_hash(row) != row["event_hash"]:
            return {"ok": False, "events": len(rows), "broken_at": row["sequence"], "reason": "event content changed"}
        previous = row
    if pre_chain and previous is None:
        return {"ok": False, "events": len(rows), "broken_at": pre_chain[-1]["sequence"],
                "reason": "pre-chain events are not sealed by a genesis event"}
    head = {"sequence": previous["sequence"], "event_hash": previous["event_hash"]} if previous else None
    return {"ok": True, "events": len(rows), "head": head}


def verify(path: Path, require_latest: bool = True) -> dict:
    """All checks for one database file. `ok` is false if any check fails; `warnings` never fail.

    With require_latest=False an older schema passes (it migrates on the next start); a newer one never does.
    """
    if not path.is_file():
        return {"ok": False, "path": str(path), "errors": [f"Database does not exist: {path}"], "warnings": []}
    errors, warnings = [], []
    with closing(sqlite3.connect(path)) as connection:
        integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
        if integrity != ["ok"]:
            errors.append("integrity_check: " + "; ".join(integrity[:5]))
        foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign:
            errors.append(f"foreign_key_check: {len(foreign)} broken references, first in table {foreign[0][0]}")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > latest_version() or (require_latest and version != latest_version()):
            errors.append(f"user_version is {version}, code expects {latest_version()}")
        triggers = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
        expected = GOVERNANCE_TRIGGERS if version >= latest_version() else ()
        missing = [f"immutable_{table}_{action}" for table in HISTORY_TABLES for action in ("update", "delete")
                   if f"immutable_{table}_{action}" not in triggers]
        missing += [name for name in expected if name not in triggers]
        if missing:
            errors.append("missing triggers: " + ", ".join(missing))
        chain = {"ok": version < latest_version(), "reason": "audit chain not installed"}
        if "audit_events_chain" in triggers:
            chain = verify_audit_chain(connection)
            if not chain["ok"]:
                errors.append(f"audit chain broken at sequence {chain['broken_at']}: {chain['reason']}")
        discovered = {}
        if "vehicles" in {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}:
            discovered = {
                "vehicles": [row[0] for row in connection.execute(
                    "SELECT code FROM vehicles WHERE status = 'discovered' ORDER BY code")],
                "markets": [row[0] for row in connection.execute(
                    "SELECT code FROM markets WHERE status = 'discovered' ORDER BY code")],
            }
            for kind, codes in discovered.items():
                if codes:
                    warnings.append(f"discovered {kind} awaiting PM confirmation: {', '.join(codes)}")
            unknown = [row[0] for row in connection.execute(
                "SELECT DISTINCT actor FROM audit_events WHERE actor NOT IN (SELECT id FROM actors) ORDER BY actor")]
            if unknown:
                warnings.append(f"history written by unregistered legacy actors: {', '.join(unknown)}")
    return {"ok": not errors, "path": str(path), "user_version": version, "errors": errors, "warnings": warnings,
            "audit_chain": chain, "discovered": discovered}
