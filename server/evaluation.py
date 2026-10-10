"""Operational evidence and decision metrics without claiming unmeasured AI accuracy."""

from contextlib import closing
from datetime import datetime
from statistics import median

from fastapi import APIRouter

from database.store import connect
from server.evidence import scope_filters

router = APIRouter()


@router.get("/metrics")
def metrics(vehicle: str = "G60", market: str = "US"):
    vehicle, market = scope_filters(vehicle, market)
    params = (vehicle, market)
    with closing(connect()) as connection:
        # All measurements describe the same committed database snapshot.
        connection.execute("BEGIN")
        counts = {table: connection.execute(f"SELECT count(*) FROM {table} WHERE vehicle=? AND market=?", params).fetchone()[0]
                  for table in ("sources", "evidence", "findings", "requirements")}
        traced = connection.execute(
            "SELECT count(*) FROM requirements r WHERE r.vehicle=? AND r.market=? AND EXISTS ("
            "SELECT 1 FROM requirement_findings rf JOIN finding_evidence fe ON fe.finding_id=rf.finding_id "
            "JOIN findings f ON f.id=rf.finding_id JOIN evidence e ON e.id=fe.evidence_id "
            "JOIN sources s ON s.id=e.source_id WHERE rf.version_id=r.current_version_id "
            "AND fe.relation='supports' AND f.vehicle=r.vehicle AND f.market=r.market "
            "AND e.vehicle=r.vehicle AND e.market=r.market AND s.vehicle=r.vehicle AND s.market=r.market)", params).fetchone()[0]
        open_reviews = connection.execute("SELECT count(*) FROM review_items q JOIN requirements r ON r.id=q.requirement_id "
                                          "WHERE r.vehicle=? AND r.market=? AND q.status='open'", params).fetchone()[0]
        statuses = {row[0]: row[1] for row in connection.execute(
            "SELECT status,count(*) FROM requirements WHERE vehicle=? AND market=? GROUP BY status", params)}
        rows = connection.execute(
            "SELECT v.created_at,min(d.created_at) AS decided_at FROM requirement_versions v "
            "JOIN requirements r ON r.id=v.requirement_id JOIN decisions d ON d.version_id=v.id "
            "WHERE r.vehicle=? AND r.market=? GROUP BY v.id", params).fetchall()
        durations = [max(0.0, (datetime.fromisoformat(row[1]) - datetime.fromisoformat(row[0])).total_seconds()) for row in rows]
        decision_count = connection.execute("SELECT count(*) FROM decisions d JOIN requirements r ON r.id=d.requirement_id "
                                             "WHERE r.vehicle=? AND r.market=?", params).fetchone()[0]
    return {"scope": {"vehicle": vehicle, "market": market}, "counts": {**counts, "decisions": decision_count, "open_reviews": open_reviews},
            "requirement_statuses": statuses,
            "traceability": {"requirements_with_source_links": traced, "requirements": counts["requirements"],
                             "coverage": traced / counts["requirements"] if counts["requirements"] else None},
            "time_to_first_decision_seconds": {"sample_count": len(durations), "median": median(durations) if durations else None},
            "limitations": ["Traceability covers current requirement versions with at least one in-scope supporting source link; it does not measure semantic correctness or requirement quality.",
                            "Decision time counts each decided requirement version once, from creation to its first approve/reject/postpone/challenge action. Undecided versions are excluded.",
                            "Decision time is elapsed wall time, not active PM effort or a productivity claim.",
                            "Change-detection precision/recall require labeled evaluation; run scripts/evaluate_pipeline.py."]}
