"""Migration 0011: database guards for market resolutions (Pod B)."""

import sqlite3

import pytest

from database.store import connect, transaction

CONFLICT = ("INSERT INTO market_conflicts (id,vehicle,topic,markets,conflict_type,severity,metrics,evidence_ids,"
            "requirement_ids,recommendation,rationale,fingerprint,method_version,run_id,created_at) VALUES "
            "(?,'G60','comfort','[\"CN\",\"US\"]','priority_divergence','high','{}','{}','[]','market_variant','r',"
            "?,'market-balance-v1','run','t')")
RESOLUTION = ("INSERT INTO market_resolutions (id,conflict_id,decision,actor,rationale,requirement_ids,created_at) "
              "VALUES (?,?,?,'human:troy','Reviewed per-market evidence',?,'t')")


@pytest.fixture
def conflict(db):
    with transaction() as connection:
        connection.execute("INSERT INTO runs (id,capability,actor,method_version,input_hash,inputs,status,started_at) "
                           "VALUES ('run','markets.detect_conflicts','human:troy','market-balance-v1','h','{}',"
                           "'running','t')")
        connection.execute(CONFLICT, ("open", "fp"))
    return "open"


def test_resolutions_need_an_open_conflict(conflict):
    with transaction() as connection:
        connection.execute(RESOLUTION, ("r1", conflict, "market_variants", "[]"))
        connection.execute("UPDATE market_conflicts SET status='resolved' WHERE id=?", (conflict,))
    with pytest.raises(sqlite3.IntegrityError, match="open conflict"), transaction() as connection:
        connection.execute(RESOLUTION, ("r2", conflict, "dismiss", "[]"))
    with pytest.raises(sqlite3.IntegrityError, match="open conflict"), transaction() as connection:
        connection.execute(RESOLUTION, ("r3", "missing", "defer", "[]"))


def test_resolution_requirement_ids_are_an_array(conflict):
    with pytest.raises(sqlite3.IntegrityError, match="JSON array"), transaction() as connection:
        connection.execute(RESOLUTION, ("r1", conflict, "defer", '{"CN": []}'))


def test_conflict_history_index_exists(db):
    with connect() as connection:
        indexes = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "market_conflicts_fingerprint" in indexes


@pytest.mark.parametrize("requirements", ['["missing"]', '[1]', '[null]'])
def test_resolution_requirements_must_exist_in_conflict_scope(conflict, requirements):
    with pytest.raises(sqlite3.IntegrityError, match="conflict scope"), transaction() as connection:
        connection.execute(RESOLUTION, ("r1", conflict, "defer", requirements))
