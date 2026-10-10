import csv
import hashlib
import json
import sqlite3

import pytest

from database import cli
from database.integrity import verify
from database.snapshot import create_snapshot, manifest_path
from database.store import audit, connect, transaction


@pytest.fixture
def snapshots(db, tmp_path, monkeypatch):
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path / "snapshots"))
    return tmp_path / "snapshots"


def _state(path):
    with sqlite3.connect(path) as connection:
        counts = {row[0]: connection.execute(f"SELECT count(*) FROM {row[0]}").fetchone()[0]
                  for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' "
                                                "AND name NOT LIKE 'sqlite_%'")}
        head = connection.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
    return counts, head


def _event(rationale):
    with transaction() as connection:
        audit(connection, "test", rationale, "test.created", "human:troy", rationale)


def test_snapshot_restore_round_trip_keeps_counts_and_chain_head(db, snapshots, capsys):
    _event("before snapshot")
    assert cli.main(["snapshot", "--label", "demo"]) == 0
    snapshot = next(snapshots.glob("*-demo.db"))
    manifest = json.loads(manifest_path(snapshot).read_text())
    expected = _state(db)
    assert manifest["sha256"] == hashlib.sha256(snapshot.read_bytes()).hexdigest()
    assert manifest["audit_head"]["event_hash"] == expected[1][0]
    assert manifest["row_counts"]["audit_events"] == 1 and manifest["label"] == "demo"

    _event("after snapshot")
    assert cli.main(["restore", str(snapshot)]) == 0
    assert _state(db) == expected
    assert cli.main(["verify"]) == 0
    safety = next(snapshots.glob("*-pre-restore.db"))
    assert json.loads(manifest_path(safety).read_text())["row_counts"]["audit_events"] == 2
    capsys.readouterr()


def test_restore_refuses_a_changed_or_unverified_snapshot(db, snapshots):
    _event("x")
    snapshot = create_snapshot("demo")
    with sqlite3.connect(snapshot) as connection:
        connection.execute("DROP TRIGGER immutable_audit_events_update")
        connection.execute("UPDATE audit_events SET rationale = 'forged'")
    with pytest.raises(SystemExit, match="does not match its manifest"):
        cli.main(["restore", str(snapshot)])
    manifest_path(snapshot).unlink()
    with pytest.raises(SystemExit, match="no manifest"):
        cli.main(["restore", str(snapshot)])
    with pytest.raises(SystemExit, match="failed verification"):
        cli.main(["restore", str(snapshot), "--allow-missing-manifest"])
    assert verify(db)["ok"]


def test_restore_refuses_while_a_writer_holds_the_database(db, snapshots):
    snapshot = create_snapshot("demo")
    with connect() as writer:
        writer.execute("BEGIN IMMEDIATE")
        with pytest.raises(SystemExit, match="stop the API"):
            cli.main(["restore", str(snapshot)])
        writer.rollback()


def test_verify_fails_on_tampered_snapshot(db, snapshots, capsys):
    _event("a")
    _event("b")
    snapshot = create_snapshot()
    assert cli.main(["verify", str(snapshot)]) == 0
    with sqlite3.connect(snapshot) as connection:
        connection.execute("DROP TRIGGER immutable_audit_events_update")
        connection.execute("UPDATE audit_events SET actor = 'PM' WHERE sequence = 1")
    capsys.readouterr()
    assert cli.main(["verify", str(snapshot)]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["audit_chain"]["broken_at"] == 1
    assert "file SHA-256 differs from its manifest" in result["errors"]


def test_export_writes_requirement_list_and_access_event(db, snapshots, capsys):
    with transaction() as connection:
        connection.execute("INSERT INTO requirements (id,vehicle,market,topic,status,created_at,updated_at) "
                           "VALUES ('req','G60','US','topic','proposed','t','t')")
    assert cli.main(["export", "--format", "csv", "--actor", "human:jakob", "--market", "US"]) == 0
    path = next((snapshots / "exports").glob("requirements-*.csv"))
    rows = list(csv.DictReader(path.open()))
    assert [row["key"] for row in rows] == ["REQ-G60-US-001"]
    with connect() as connection:
        event = connection.execute("SELECT * FROM audit_events WHERE action = 'access.export'").fetchone()
    assert event["actor"] == "human:jakob" and json.loads(event["metadata"])["keys"] == ["REQ-G60-US-001"]
    capsys.readouterr()


def test_seed_is_idempotent(db, capsys):
    assert cli.main(["seed"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert cli.main(["seed"]) == 0
    assert json.loads(capsys.readouterr().out) == first


def test_rebuild_imports_verified_inputs_into_a_fresh_database(tmp_path, monkeypatch, capsys):
    data = tmp_path / "data" / "BMW-Data"
    data.mkdir(parents=True)
    feedback = data / "G60_feedback_hackathon.csv"
    feedback.write_text("Comment,Market\nRear seats need USB-C,US\n")
    changed = data / "G70_feedback_hackathon.csv"
    changed.write_text("Comment\nchanged\n")
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps({"files": [
        {"path": "data/BMW-Data/G60_feedback_hackathon.csv", "kind": "google-drive-input",
         "sha256": hashlib.sha256(feedback.read_bytes()).hexdigest()},
        {"path": "data/BMW-Data/G70_feedback_hackathon.csv", "kind": "google-drive-input", "sha256": "0" * 64},
        {"path": "data/BMW-Data/missing.xlsx", "kind": "google-drive-input", "sha256": "0" * 64},
        {"path": "materials/briefing.pdf", "kind": "discord-attachment", "sha256": "0" * 64},
    ]}))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "live.db"))
    target = tmp_path / "rebuilt" / "app.db"

    assert cli.main(["rebuild", "--target", str(target), "--data-dir", str(tmp_path / "data"),
                     "--inventory", str(inventory)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["imports"] == [{"file": "G60_feedback_hackathon.csv", "scope": "G60:US", "records": 1}]
    assert report["mismatched"] == ["data/BMW-Data/G70_feedback_hackathon.csv"]
    assert report["missing"] == ["data/BMW-Data/missing.xlsx"]
    assert report["verify"]["ok"]
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT actor FROM audit_events").fetchone()[0] == "system:importer"
    with pytest.raises(SystemExit, match="fresh database"):
        cli.main(["rebuild", "--target", str(target), "--inventory", str(inventory)])
