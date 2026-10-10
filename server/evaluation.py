"""Operational evidence and decision metrics without claiming unmeasured AI accuracy."""

from contextlib import closing
from datetime import datetime
from statistics import median

from fastapi import APIRouter

from database.store import connect
from server.models import Scope

router = APIRouter()


@router.get("/metrics")
def metrics(vehicle: str = "G60", market: str = "US"):
    scope = Scope(vehicle=vehicle, market=market)
    params = (scope.vehicle, scope.market)
    with closing(connect()) as connection:
        counts = {table: connection.execute(f"SELECT count(*) FROM {table} WHERE vehicle=? AND market=?", params).fetchone()[0]
                  for table in ("sources", "evidence", "findings", "requirements")}
        traced = connection.execute(
            "SELECT count(*) FROM requirements r WHERE r.vehicle=? AND r.market=? AND EXISTS ("
            "SELECT 1 FROM requirement_findings rf JOIN finding_evidence fe ON fe.finding_id=rf.finding_id "
            "JOIN evidence e ON e.id=fe.evidence_id JOIN sources s ON s.id=e.source_id "
            "WHERE rf.version_id=r.current_version_id AND fe.relation='supports')", params).fetchone()[0]
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
    return {"scope": scope.model_dump(), "counts": {**counts, "decisions": decision_count, "open_reviews": open_reviews},
            "requirement_statuses": statuses,
            "traceability": {"requirements_with_source_links": traced, "requirements": counts["requirements"],
                             "coverage": traced / counts["requirements"] if counts["requirements"] else None},
            "time_to_first_decision_seconds": {"sample_count": len(durations), "median": median(durations) if durations else None},
            "limitations": ["Traceability measures the existence of links, not semantic correctness of evidence or requirement quality.",
                            "Decision time is elapsed wall time from version creation, not active PM effort or a productivity claim.",
                            "Change-detection precision/recall require labeled evaluation; run scripts/evaluate_pipeline.py."]}
