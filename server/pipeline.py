"""BMW PM workflow: analyze evidence, define requirements, and assess new information."""

import hashlib
import os
from contextlib import closing

from fastapi import APIRouter, HTTPException, Query

from database.store import audit, connect, decode, encode, new_id, now, transaction
from server.evidence import evidence_rows
from server.models import AnalysisRequest, GenerateRequest, RequirementCreate, Scope, normalize_market
from server.requirements import (
    CONTENT_FIELDS,
    create_requirement,
    evidence_for_findings,
    finding_detail,
    list_requirements,
    list_reviews,
    new_version,
    open_review,
    requirement_detail,
    version_detail,
)

router = APIRouter()


def run_detail(connection, run_id):
    result = decode(connection.execute("SELECT * FROM analysis_runs WHERE id=?", (run_id,)).fetchone(),
                    ("evidence_ids", "warnings", "result"))
    if result is None:
        raise HTTPException(404, "Analysis run not found")
    result["findings"] = [finding_detail(connection, row[0]) for row in connection.execute(
        "SELECT id FROM findings WHERE run_id=? ORDER BY rowid", (run_id,)).fetchall()]
    return result


def run_analysis(command: AnalysisRequest):
    from server.analysis_engine import PROMPT_VERSION, AnalysisError, ProviderUnavailable, analyze_evidence

    with closing(connect()) as connection:
        if command.source_ids:
            for source_id in command.source_ids:
                source = connection.execute("SELECT vehicle,market FROM sources WHERE id=?", (source_id,)).fetchone()
                if source is None or tuple(source) != (command.vehicle, command.market):
                    raise HTTPException(422, "All source IDs must exist and match the selected vehicle and market")
        records = evidence_rows(connection, command.vehicle, command.market, command.source_ids)
        source_kinds = {row[0]: row[1] for row in connection.execute("SELECT id,kind FROM sources WHERE vehicle=? AND market=?",
                                                                   (command.vehicle, command.market))}
        for record in records:
            record["metadata"] = {"source_kind": source_kinds[record["source_id"]], **record["metadata"]}
        if not records:
            raise HTTPException(422, "Import evidence for this vehicle and market before analysis")
        fingerprint = {"evidence": [(row["id"], row["content_hash"]) for row in records],
                       "provider": command.provider, "model": os.getenv("OPENAI_MODEL", "") if command.provider == "openai" else "reference",
                       "prompt_version": PROMPT_VERSION}
        digest = hashlib.sha256(encode(fingerprint).encode()).hexdigest()
        cached = connection.execute("SELECT id FROM analysis_runs WHERE input_hash=? ORDER BY created_at DESC LIMIT 1", (digest,)).fetchone()
        if cached:
            return {**run_detail(connection, cached[0]), "cached": True}
    try:
        result = analyze_evidence(records, command.vehicle, command.market, command.provider)
    except ProviderUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except AnalysisError as exc:
        raise HTTPException(422, str(exc)) from exc
    # No write lock is held across an external model request.
    with transaction() as connection:
        cached = connection.execute("SELECT id FROM analysis_runs WHERE input_hash=? LIMIT 1", (digest,)).fetchone()
        if cached:
            return {**run_detail(connection, cached[0]), "cached": True}
        run_id, timestamp = new_id(), now()
        connection.execute("INSERT INTO analysis_runs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                           (run_id, command.vehicle, command.market, result["provider"], result["model"], result["prompt_version"],
                            digest, encode([row["id"] for row in records]), encode(result["warnings"]), encode(result), timestamp))
        evidence_ids = {row["id"] for row in records}
        for finding in result["findings"]:
            finding_id = new_id()
            connection.execute("INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?)",
                               (finding_id, run_id, command.vehicle, command.market, finding["topic"], finding["kind"],
                                finding["summary"], finding["confidence"], timestamp))
            for key, relation in (("evidence_ids", "supports"), ("conflicting_evidence_ids", "conflicts")):
                if not set(finding[key]).issubset(evidence_ids):
                    raise HTTPException(422, "Analysis referenced evidence outside its input")
                connection.executemany("INSERT INTO finding_evidence VALUES (?,?,?)",
                                       [(finding_id, eid, relation) for eid in sorted(set(finding[key]))])
        audit(connection, "analysis", run_id, "analysis.completed", command.actor,
              "Classified and contextualized source evidence", after={"finding_count": len(result["findings"]),
                                                                    "proposal_count": len(result["proposals"]), "input_hash": digest},
              metadata={"provider": result["provider"], "model": result["model"], "prompt_version": result["prompt_version"],
                        "source_ids": sorted({record["source_id"] for record in records}), "evidence_count": len(records), "warnings": result["warnings"]})
        return {**run_detail(connection, run_id), "cached": False}


def evidence_signature(connection, finding_ids):
    """Compare immutable evidence and its interpretation, independent of generated finding IDs."""
    groups = []
    for finding_id in finding_ids:
        finding = finding_detail(connection, finding_id)
        groups.append({"topic": finding["topic"], "kind": finding["kind"], "summary": finding["summary"],
                       "supports": sorted(finding["evidence_ids"]), "conflicts": sorted(finding["conflicting_evidence_ids"])})
    return sorted(groups, key=encode)


def preceding_proposal(connection, previous, topic):
    """Recover the generator baseline so new evidence cannot overwrite later PM edits."""
    for finding_id in previous["finding_ids"]:
        row = connection.execute("SELECT a.result FROM analysis_runs a JOIN findings f ON f.run_id=a.id WHERE f.id=?", (finding_id,)).fetchone()
        if row:
            result = decode(row, ("result",))["result"]
            proposal = next((p for p in result["proposals"] if p["topic"] == topic), None)
            if proposal:
                return proposal
    return None


def generate_requirements(command: GenerateRequest):
    with transaction() as connection:
        run = run_detail(connection, command.run_id)
        findings = run["findings"]
        created, updated, unchanged, requirements = [], [], [], []
        for proposal in run["result"]["proposals"]:
            finding_ids = [findings[index]["id"] for index in proposal["finding_indexes"]]
            content = {key: proposal[key] for key in CONTENT_FIELDS}
            existing = connection.execute("SELECT * FROM requirements WHERE vehicle=? AND market=? AND topic=?",
                                          (run["vehicle"], run["market"], proposal["topic"])).fetchone()
            actor = f"AI:{run['provider']}" if run["provider"] != "deterministic" else "System:reference"
            if existing is None:
                result = create_requirement(connection, RequirementCreate(**content, vehicle=run["vehicle"], market=run["market"],
                                            topic=proposal["topic"], finding_ids=finding_ids, actor=actor,
                                            rationale=f"Requirement proposed from analysis {run['id']}"))
                created.append(result["id"])
            else:
                requirement = dict(existing)
                previous = version_detail(connection, requirement["current_version_id"])
                previous_signature = evidence_signature(connection, previous["finding_ids"])
                proposed_signature = evidence_signature(connection, finding_ids)
                prior_proposal = preceding_proposal(connection, previous, proposal["topic"])
                preserved = []
                if prior_proposal:
                    for key in CONTENT_FIELDS:
                        if previous[key] != prior_proposal[key]:
                            content[key] = previous[key]
                            preserved.append(key)
                elif previous["actor"] not in ("AI:openai", "System:reference"):
                    content = {key: previous[key] for key in CONTENT_FIELDS}
                    preserved = list(CONTENT_FIELDS)
                same_content = content == {key: previous[key] for key in CONTENT_FIELDS}
                if previous_signature == proposed_signature and same_content:
                    unchanged.append(requirement["id"])
                    result = requirement_detail(connection, requirement["id"])
                else:
                    # A scoped historical analysis must not remove newer evidence from an existing decision.
                    previous_evidence = {e["id"] for e in evidence_for_findings(connection, previous["finding_ids"])}
                    proposed_evidence = {e["id"] for e in evidence_for_findings(connection, finding_ids)}
                    if not previous_evidence.issubset(set(run["evidence_ids"])):
                        raise HTTPException(409, "Analysis omits evidence in an existing requirement; run cumulative analysis for this scope")
                    version = new_version(connection, requirement, content, finding_ids, actor,
                                          f"New evidence assessed by analysis {run['id']}")
                    changes = {"added_evidence_ids": sorted(proposed_evidence - previous_evidence),
                               "removed_evidence_ids": sorted(previous_evidence - proposed_evidence),
                               "changed_fields": [key for key in CONTENT_FIELDS if previous[key] != content[key]],
                               "previous_score": previous["score"]["total"], "proposed_score": version["score"]["total"],
                               "preserved_pm_fields": preserved, "run_id": run["id"],
                               "evidence_interpretation_changed": previous_signature != proposed_signature}
                    # New support/conflict/acceptance changes affect the basis of a commitment even at the same score.
                    if requirement["approved_version_id"] or requirement["status"] in ("needs_review", "postponed", "rejected"):
                        open_review(connection, requirement["id"], "New evidence or analysis changes the requirement's decision basis", changes, command.actor)
                    updated.append(requirement["id"])
                    result = requirement_detail(connection, requirement["id"])
            requirements.append(result)
        audit(connection, "analysis", run["id"], "requirements.generated", command.actor,
              "Defined requirements and assessed affected decisions", after={"created": created, "updated": updated, "unchanged": unchanged})
        return {"run_id": run["id"], "created": created, "updated": updated, "unchanged": unchanged, "requirements": requirements}


@router.post("/analyses", status_code=201)
def analyze(command: AnalysisRequest):
    return run_analysis(command)


@router.get("/analyses/{run_id}")
def get_analysis(run_id: str):
    with closing(connect()) as connection:
        return run_detail(connection, run_id)


@router.post("/requirements/generate", status_code=201)
def generate(command: GenerateRequest):
    return generate_requirements(command)


@router.post("/pipeline/run", status_code=201)
def pipeline(command: AnalysisRequest):
    analysis = run_analysis(command)
    generation = generate_requirements(GenerateRequest(run_id=analysis["id"], actor=command.actor))
    return {"analysis": analysis, "generation": generation}


@router.post("/updates", status_code=201)
def assess_update(command: AnalysisRequest):
    if command.source_ids is not None:
        raise HTTPException(422, "Updates analyze all cumulative evidence for the selected scope; omit source_ids")
    result = pipeline(command)
    result["reviews"] = list_reviews(command.vehicle, command.market)
    return result


@router.get("/findings")
def list_findings(vehicle: str | None = None, market: str | None = None, run_id: str | None = None,
                  limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    vehicle = vehicle.strip().upper() if vehicle is not None else None
    market = normalize_market(market) if market is not None else None
    clauses, params = [], []
    for name, value in (("vehicle", vehicle), ("market", market), ("run_id", run_id)):
        if value is not None:
            clauses.append(f"{name}=?")
            params.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with closing(connect()) as connection:
        total = connection.execute("SELECT count(*) FROM findings" + where, params).fetchone()[0]
        rows = connection.execute("SELECT id FROM findings" + where + " ORDER BY created_at,id LIMIT ? OFFSET ?", [*params, limit, offset]).fetchall()
        return {"items": [finding_detail(connection, row[0]) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/findings/{finding_id}")
def get_finding(finding_id: str):
    with closing(connect()) as connection:
        return finding_detail(connection, finding_id)


@router.get("/workspace")
def workspace(vehicle: str = "G60", market: str = "US"):
    scope = Scope(vehicle=vehicle, market=market)
    with closing(connect()) as connection:
        selections = [dict(row) for row in connection.execute("SELECT vehicle,market,count(*) AS source_count FROM sources GROUP BY vehicle,market ORDER BY vehicle,market")]
        evidence_count = connection.execute("SELECT count(*) FROM evidence WHERE vehicle=? AND market=?", (scope.vehicle, scope.market)).fetchone()[0]
    return {"scope": scope.model_dump(), "available_scopes": selections, "evidence_count": evidence_count,
            "requirements": list_requirements(scope.vehicle, scope.market, limit=100, offset=0),
            "reviews": list_reviews(scope.vehicle, scope.market),
            "process": ["Situation analysis", "Structure and context", "Requirement definition", "Prioritization", "Documentation and tracking"]}
