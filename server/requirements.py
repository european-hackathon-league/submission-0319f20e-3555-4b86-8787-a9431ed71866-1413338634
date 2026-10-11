"""Versioned requirements, explainable priorities, PM decisions, and review history."""

from contextlib import closing
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from database.store import audit, connect, decode, encode, new_id, now, transaction
from server.grounding import target_supported
from server.models import (
    DERIVED_FACTORS,
    RUBRIC_V1,
    RUBRIC_V2,
    DecisionRequest,
    RequirementContent,
    RequirementCreate,
    RequirementEdit,
    ScoreRequest,
    Weights,
    normalize_market,
)

router = APIRouter()
CONTENT_FIELDS = ("title", "statement", "customer_need", "acceptance_criteria", "assumptions", "factors")
VERSION_JSON = ("acceptance_criteria", "assumptions", "factors")
SCORE_JSON = ("factors", "weights", "explanation")


def require_row(connection, requirement_id):
    row = connection.execute("SELECT * FROM requirements WHERE id=?", (requirement_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Requirement not found")
    return dict(row)


def latest_score(connection, version_id):
    return decode(connection.execute("SELECT * FROM scores WHERE version_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1",
                                     (version_id,)).fetchone(), SCORE_JSON)


def finding_detail(connection, finding_id):
    finding = decode(connection.execute("SELECT * FROM findings WHERE id=?", (finding_id,)).fetchone())
    if finding is None:
        raise HTTPException(404, "Finding not found")
    links = connection.execute("SELECT evidence_id,relation FROM finding_evidence WHERE finding_id=? ORDER BY evidence_id",
                               (finding_id,)).fetchall()
    finding["evidence_ids"] = [row[0] for row in links if row[1] == "supports"]
    finding["conflicting_evidence_ids"] = [row[0] for row in links if row[1] == "conflicts"]
    return finding


def version_detail(connection, version_id, score_id=None):
    if version_id is None:
        return None
    version = decode(connection.execute("SELECT * FROM requirement_versions WHERE id=?", (version_id,)).fetchone(), VERSION_JSON)
    if version is None:
        raise HTTPException(404, "Requirement version not found")
    version["finding_ids"] = [row[0] for row in connection.execute(
        "SELECT finding_id FROM requirement_findings WHERE version_id=? ORDER BY finding_id", (version_id,))]
    version["score"] = (decode(connection.execute("SELECT * FROM scores WHERE id=? AND version_id=?", (score_id, version_id)).fetchone(), SCORE_JSON)
                        if score_id else latest_score(connection, version_id))
    return version


def requirement_detail(connection, requirement_id):
    requirement = require_row(connection, requirement_id)
    requirement["current_version"] = version_detail(connection, requirement["current_version_id"])
    requirement["approved_version"] = version_detail(connection, requirement["approved_version_id"], requirement["approved_score_id"])
    requirement["reviews"] = [decode(row, ("changes",)) for row in connection.execute(
        "SELECT * FROM review_items WHERE requirement_id=? ORDER BY created_at,id", (requirement_id,))]
    requirement["needs_review"] = any(item["status"] == "open" for item in requirement["reviews"])
    return requirement


def validate_findings(connection, finding_ids, vehicle, market):
    if not finding_ids:
        raise HTTPException(422, "At least one finding is required")
    customer_findings = False
    for finding_id in set(finding_ids):
        finding = connection.execute("SELECT vehicle,market,kind FROM findings WHERE id=?", (finding_id,)).fetchone()
        if finding is None:
            raise HTTPException(422, f"Unknown finding: {finding_id}")
        if (finding["vehicle"], finding["market"]) != (vehicle, market):
            raise HTTPException(422, "Findings must match the requirement vehicle and market")
        customer_findings |= finding["kind"] != "context"
    if not customer_findings:
        raise HTTPException(422, "A requirement needs customer findings; context alone is insufficient")


def finding_interpretations(connection, finding_ids):
    """Compare immutable interpretations without generated finding identities."""
    groups = []
    for finding_id in finding_ids:
        finding = finding_detail(connection, finding_id)
        groups.append({"topic": finding["topic"], "kind": finding["kind"], "summary": finding["summary"],
                       "confidence": finding["confidence"], "supports": sorted(finding["evidence_ids"]),
                       "conflicts": sorted(finding["conflicting_evidence_ids"])})
    return sorted(groups, key=encode)


def evidence_for_findings(connection, finding_ids, relation=None):
    if not finding_ids:
        return []
    marks = ",".join("?" for _ in finding_ids)
    relation_clause = " AND f.relation=?" if relation else ""
    params = [*finding_ids, relation] if relation else finding_ids
    return [decode(row, ("metadata", "location")) for row in connection.execute(
        "SELECT DISTINCT e.* FROM evidence e JOIN finding_evidence f ON f.evidence_id=e.id "
        f"WHERE f.finding_id IN ({marks}){relation_clause} ORDER BY e.id", params)]


def validate_targets(connection, content, finding_ids):
    supporting = evidence_for_findings(connection, finding_ids, "supports")
    sources = {e["source_id"] for e in supporting}
    for criterion in content["acceptance_criteria"]:
        if criterion["basis"] == "source" and not set(criterion["source_ids"]).issubset(sources):
            raise HTTPException(422, "Acceptance target source references must belong to the linked evidence")
        if criterion["basis"] == "source":
            source_texts = [record["content"] for record in supporting if record["source_id"] in criterion["source_ids"]]
            if not target_supported(str(criterion["target"]), source_texts):
                raise HTTPException(422, "Source-based target must be quoted in a linked explicit desired outcome; use PM assumption otherwise")


def weights_rubric(weights) -> str:
    """customer-priority-v2 when the weights carry every derived factor; anything else scores as v1, as before."""
    return RUBRIC_V2 if set(DERIVED_FACTORS) <= set(weights) else RUBRIC_V1


def active_rubric(connection, vehicle, market):
    """The scope's rubric: the latest human switch (scope_rubrics), else the v1 default for every scope."""
    row = decode(connection.execute("SELECT * FROM scope_rubrics WHERE vehicle=? AND market=? "
                                    "ORDER BY created_at DESC,rowid DESC LIMIT 1", (vehicle, market)).fetchone(), ("weights",))
    if row is not None:
        return {**row, "default": False}
    return {"id": None, "vehicle": vehicle, "market": market, "rubric_version": RUBRIC_V1, "weights": Weights().model_dump(),
            "actor": None, "rationale": "Default rubric until a human PM switches this scope", "created_at": None, "default": True}


def score_version(connection, version_id, weights, actor, rationale):
    version = version_detail(connection, version_id)
    factors, rubric_version, derived = version["factors"], weights_rubric(weights), {}
    if rubric_version == RUBRIC_V2:
        # v2 adds data-derived factors; their recorded derivations (priority_inputs) are cited by id.
        from server.prioritization import ensure_inputs

        derived = ensure_inputs(connection, version, actor)
        factors = {**factors, **{key: derived[key]["value"] for key in DERIVED_FACTORS}}
    total = round(sum(factors[key] * weights[key] * 20 for key in weights), 4)
    evidence = evidence_for_findings(connection, version["finding_ids"])
    provenances = {str(row["metadata"].get("provenance") or row["source_id"]) for row in evidence}
    sources = sorted({row["source_id"] for row in evidence})
    dated = sum(bool(row["observed_at"]) for row in evidence)
    conflicts = len({eid for fid in version["finding_ids"]
                     for eid in finding_detail(connection, fid)["conflicting_evidence_ids"]})
    grade = "A" if len(provenances) >= 3 and dated == len(evidence) and not conflicts else (
        "B" if len(provenances) >= 2 and not conflicts else "C" if evidence else "D")
    explanation = {
        "formula": "sum(factor × weight × 20); factors 0–5, priority 0–100",
        "contributions": {key: round(factors[key] * weights[key] * 20, 4) for key in weights},
        "evidence_count": len(evidence), "source_ids": sources, "source_count": len(sources),
        "provenance_count": len(provenances), "dated_evidence_count": dated, "conflict_count": conflicts,
        "conflict_flag": bool(conflicts),
        "evidence_grade_rubric": "A: >=3 provenances, all dated, no conflicts; B: >=2 provenances, no conflicts; C: linked evidence; D: none",
        "limitations": ["Sample counts are not market prevalence.", "Priority reflects recorded judgments; evidence grade is separate."]
                      + (["Some evidence has no observation date."] if dated < len(evidence) else [])
                      + (["Conflicting evidence requires PM review."] if conflicts else []),
    }
    if derived:
        not_measured = [key for key in DERIVED_FACTORS if not derived[key]["derivation"]["measured"]]
        explanation["derived_inputs"] = {key: {
            "priority_input_id": row["id"], "value": row["value"], "measured": row["derivation"]["measured"],
            "flags": row["derivation"]["flags"], "method_version": row["method_version"], "run_id": row["run_id"],
        } for key, row in derived.items()}
        explanation["not_measured"] = not_measured
        explanation["limitations"] += (["Derived factors are recorded data summaries, not PM judgments."]
                                       + ([f"Not measured, neutral 2.5 used: {', '.join(not_measured)}."] if not_measured else []))
    score = {"id": new_id(), "version_id": version_id, "rubric_version": rubric_version,
             "factors": factors, "weights": weights, "total": total, "evidence_grade": grade,
             "explanation": explanation, "created_at": now()}
    connection.execute("INSERT INTO scores VALUES (?,?,?,?,?,?,?,?,?)",
                       (score["id"], version_id, score["rubric_version"], encode(factors), encode(weights), total,
                        grade, encode(explanation), score["created_at"]))
    audit(connection, "requirement", version["requirement_id"], "requirement.scored", actor, rationale,
          before=version["score"], after=score)
    return score


def new_version(connection, requirement, content, finding_ids, actor, rationale, weights=None):
    content = RequirementContent.model_validate(content).model_dump()
    validate_findings(connection, finding_ids, requirement["vehicle"], requirement["market"])
    validate_targets(connection, content, finding_ids)
    previous = version_detail(connection, requirement["current_version_id"])
    version_id, timestamp = new_id(), now()
    number = connection.execute("SELECT coalesce(max(version),0)+1 FROM requirement_versions WHERE requirement_id=?",
                                (requirement["id"],)).fetchone()[0]
    connection.execute(
        "INSERT INTO requirement_versions "
        "(id,requirement_id,version,title,statement,customer_need,acceptance_criteria,assumptions,factors,actor,rationale,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (version_id, requirement["id"], number, content["title"], content["statement"], content["customer_need"],
         encode(content["acceptance_criteria"]), encode(content["assumptions"]), encode(content["factors"]), actor, rationale, timestamp),
    )
    connection.executemany("INSERT INTO requirement_findings VALUES (?,?)", [(version_id, fid) for fid in sorted(set(finding_ids))])
    status = "needs_review" if requirement["approved_version_id"] else "proposed"
    connection.execute("UPDATE requirements SET current_version_id=?,status=?,updated_at=? WHERE id=?",
                       (version_id, status, timestamp, requirement["id"]))
    # Keep the previous weights (e.g. a PM's reweighting) while they belong to the scope's rubric; a scope a PM
    # switched to another rubric scores new versions with that rubric's weights.
    rubric = active_rubric(connection, requirement["vehicle"], requirement["market"])
    previous_weights = previous["score"]["weights"] if previous and previous["score"] else None
    selected_weights = weights or (previous_weights if previous_weights is not None
                                   and weights_rubric(previous_weights) == rubric["rubric_version"] else rubric["weights"])
    score_version(connection, version_id, selected_weights, actor, "Recalculate priority for the new requirement version")
    result = version_detail(connection, version_id)
    audit(connection, "requirement", requirement["id"], "requirement.version_created", actor, rationale,
          before=previous, after=result, metadata={"source_ids": result["score"]["explanation"]["source_ids"]})
    return result


def create_requirement(connection, command: RequirementCreate):
    existing = connection.execute("SELECT id FROM requirements WHERE vehicle=? AND market=? AND topic=?",
                                  (command.vehicle, command.market, command.topic)).fetchone()
    if existing:
        raise HTTPException(409, {"message": "A requirement for this topic already exists", "requirement_id": existing[0]})
    requirement_id, timestamp = new_id(), now()
    connection.execute("INSERT INTO requirements (id,vehicle,market,topic,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                       (requirement_id, command.vehicle, command.market, command.topic, "proposed", timestamp, timestamp))
    content = {key: command.model_dump()[key] for key in CONTENT_FIELDS}
    new_version(connection, require_row(connection, requirement_id), content, command.finding_ids, command.actor, command.rationale)
    return requirement_detail(connection, requirement_id)


def open_review(connection, requirement_id, reason, changes, actor):
    req = require_row(connection, requirement_id)
    proposed = version_detail(connection, req["current_version_id"])
    baseline = version_detail(connection, req["approved_version_id"], req["approved_score_id"])
    if baseline:
        baseline_evidence = {e["id"] for e in evidence_for_findings(connection, baseline["finding_ids"])}
        proposed_evidence = {e["id"] for e in evidence_for_findings(connection, proposed["finding_ids"])}
        changes = {**changes, "against_approved": {
            "baseline_version_id": baseline["id"], "proposed_version_id": proposed["id"],
            "fields": {key: {"before": baseline[key], "after": proposed[key]}
                       for key in CONTENT_FIELDS if baseline[key] != proposed[key]},
            "added_evidence_ids": sorted(proposed_evidence - baseline_evidence),
            "removed_evidence_ids": sorted(baseline_evidence - proposed_evidence),
            "finding_interpretation": {"before": finding_interpretations(connection, baseline["finding_ids"]),
                                       "after": finding_interpretations(connection, proposed["finding_ids"])},
            "approved_score": baseline["score"], "proposed_score": proposed["score"],
        }}
    timestamp = now()
    connection.execute("UPDATE review_items SET status='superseded',resolved_at=? WHERE requirement_id=? AND status='open'",
                       (timestamp, requirement_id))
    review_id = new_id()
    connection.execute("INSERT INTO review_items VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (review_id, requirement_id, req["approved_version_id"], req["current_version_id"], reason,
                        encode(changes), "Compare the proposal with the approved version and evidence; approve, edit, reject, or postpone.",
                        "open", timestamp, None))
    connection.execute("UPDATE requirements SET status='needs_review',updated_at=? WHERE id=?", (timestamp, requirement_id))
    audit(connection, "requirement", requirement_id, "review.opened", actor, reason,
          after={"review_id": review_id, "changes": changes, "proposed_version_id": req["current_version_id"],
                 "approved_version_id": req["approved_version_id"]})
    return review_id


@router.post("/requirements", status_code=201)
def add_requirement(command: RequirementCreate):
    with transaction() as connection:
        return create_requirement(connection, command)


@router.get("/requirements")
def list_requirements(vehicle: str | None = None, market: str | None = None,
                      status: Literal["proposed", "approved", "rejected", "postponed", "needs_review"] | None = None,
                      needs_review: bool = False, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    vehicle = vehicle.strip().upper() if vehicle is not None else None
    market = normalize_market(market) if market is not None else None
    clauses, params = [], []
    for name, value in (("vehicle", vehicle), ("market", market), ("status", status)):
        if value is not None:
            clauses.append(f"r.{name}=?")
            params.append(value)
    if needs_review:
        clauses.append("EXISTS (SELECT 1 FROM review_items q WHERE q.requirement_id=r.id AND q.status='open')")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with closing(connect()) as connection:
        rows = connection.execute("SELECT r.* FROM requirements r" + where, params).fetchall()
        items = []
        for row in rows:
            req = dict(row)
            version = version_detail(connection, req["current_version_id"])
            score = version["score"]
            req.update(title=version["title"], priority=score["total"], evidence_grade=score["evidence_grade"],
                       score_id=score["id"], version=version["version"],
                       needs_review=bool(connection.execute("SELECT 1 FROM review_items WHERE requirement_id=? AND status='open'", (req["id"],)).fetchone()))
            items.append(req)
    items.sort(key=lambda item: (-item["priority"], item["id"]))
    return {"items": items[offset:offset + limit], "total": len(items), "limit": limit, "offset": offset}


@router.get("/requirements/{requirement_id}")
def get_requirement(requirement_id: str):
    with transaction() as connection:
        result = requirement_detail(connection, requirement_id)
        audit(connection, "requirement", requirement_id, "requirement.viewed", "PM", "Requirement detail accessed")
        return result


@router.get("/requirements/{requirement_id}/versions")
def get_versions(requirement_id: str):
    with closing(connect()) as connection:
        require_row(connection, requirement_id)
        ids = connection.execute("SELECT id FROM requirement_versions WHERE requirement_id=? ORDER BY version", (requirement_id,))
        return [version_detail(connection, row[0]) for row in ids.fetchall()]


@router.get("/requirements/{requirement_id}/trace")
def trace_requirement(requirement_id: str, version_id: str | None = None,
                      limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
                      score_id: str | None = None):
    with transaction() as connection:
        req = require_row(connection, requirement_id)
        version = version_detail(connection, version_id or req["current_version_id"], score_id)
        if version["requirement_id"] != requirement_id:
            raise HTTPException(404, "Version does not belong to this requirement")
        if score_id is not None and (version["score"] is None or version["score"]["id"] != score_id):
            raise HTTPException(404, "Score does not belong to this requirement version")
        findings = [finding_detail(connection, fid) for fid in version["finding_ids"]]
        evidence = evidence_for_findings(connection, version["finding_ids"])
        sources = [decode(connection.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone(), ("metadata",))
                   for sid in sorted({e["source_id"] for e in evidence})]
        audit(connection, "requirement", requirement_id, "requirement.trace_viewed", "PM", "Source-to-decision trace accessed",
              metadata={"version_id": version["id"], "score_id": score_id})
        decisions = [dict(row) for row in connection.execute(
            "SELECT * FROM decisions WHERE version_id=?" + (" AND score_id=?" if score_id is not None else "")
            + " ORDER BY created_at,rowid", [version["id"], score_id] if score_id is not None else [version["id"]])]
        return {"requirement": req, "version": version, "findings": findings, "sources": sources,
                "evidence": {"items": evidence[offset:offset + limit], "total": len(evidence), "limit": limit, "offset": offset},
                "decisions": decisions}


@router.patch("/requirements/{requirement_id}")
def edit_requirement(requirement_id: str, command: RequirementEdit):
    with transaction() as connection:
        requirement = require_row(connection, requirement_id)
        if requirement["current_version_id"] != command.expected_version_id:
            raise HTTPException(409, "Requirement changed; reload before editing")
        previous = version_detail(connection, requirement["current_version_id"])
        content = {key: previous[key] for key in CONTENT_FIELDS}
        changes = command.model_dump(exclude_unset=True)
        for key in CONTENT_FIELDS:
            if key in changes:
                if changes[key] is None:
                    raise HTTPException(422, f"{key} cannot be null")
                content[key] = changes[key]
        if "finding_ids" in changes and changes["finding_ids"] is None:
            raise HTTPException(422, "finding_ids cannot be null")
        finding_ids = command.finding_ids or previous["finding_ids"]
        if content == {key: previous[key] for key in CONTENT_FIELDS} and set(finding_ids) == set(previous["finding_ids"]):
            raise HTTPException(422, "Edit must change the requirement or evidence")
        edited_fields = [key for key in CONTENT_FIELDS if content[key] != previous[key]]
        if set(finding_ids) != set(previous["finding_ids"]):
            edited_fields.append("finding_ids")
        new_version(connection, requirement, content, finding_ids, command.actor, command.rationale)
        audit(connection, "requirement", requirement_id, "requirement.edited", command.actor, command.rationale,
              metadata={"edited_fields": edited_fields,
                        "before_finding_ids": previous["finding_ids"], "after_finding_ids": finding_ids})
        if requirement["approved_version_id"] or requirement["status"] == "needs_review":
            open_review(connection, requirement_id, "PM edited the requirement", {"edited_fields": sorted(edited_fields)}, command.actor)
        return requirement_detail(connection, requirement_id)


@router.post("/requirements/{requirement_id}/scores", status_code=201)
def rescore_requirement(requirement_id: str, command: ScoreRequest):
    with transaction() as connection:
        requirement = require_row(connection, requirement_id)
        if requirement["current_version_id"] != command.expected_version_id:
            raise HTTPException(409, "Requirement changed; reload before scoring")
        before = latest_score(connection, requirement["current_version_id"])
        if command.expected_score_id is not None and before["id"] != command.expected_score_id:
            raise HTTPException(409, "Score changed; reload before scoring")
        rubric = active_rubric(connection, requirement["vehicle"], requirement["market"])
        # Omitted weights mean the scope rubric's weights (the v1 defaults unless a PM switched the scope).
        weights = command.weights.model_dump() if "weights" in command.model_fields_set else rubric["weights"]
        if before["weights"] == weights:
            return before
        if weights_rubric(weights) != rubric["rubric_version"]:
            # Changing a scope's rubric is a human gate (POST /priorities/rubric); one ranking never mixes rubrics.
            raise HTTPException(409, f"This scope uses {rubric['rubric_version']}; submit {rubric['rubric_version']} weights "
                                     "or switch the scope rubric through POST /priorities/rubric")
        result = score_version(connection, requirement["current_version_id"], weights, command.actor, command.rationale)
        if requirement["approved_version_id"] and before["weights"] != result["weights"]:
            open_review(connection, requirement_id, "Prioritization weights changed", {"previous_score": before, "proposed_score": result}, command.actor)
        return result


@router.post("/requirements/{requirement_id}/decisions", status_code=201)
def decide_requirement(requirement_id: str, command: DecisionRequest):
    with transaction() as connection:
        requirement = require_row(connection, requirement_id)
        score = latest_score(connection, requirement["current_version_id"])
        if requirement["current_version_id"] != command.version_id or score["id"] != command.score_id:
            raise HTTPException(409, "Requirement or score changed; reload before deciding")
        decision_id, timestamp = new_id(), now()
        connection.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?)",
                           (decision_id, requirement_id, command.version_id, command.score_id, command.action, command.actor, command.rationale, timestamp))
        status = {"approve": "approved", "reject": "rejected", "postpone": "postponed", "challenge": "needs_review"}[command.action]
        connection.execute("UPDATE requirements SET status=?,updated_at=? WHERE id=?", (status, timestamp, requirement_id))
        if command.action == "approve":
            connection.execute("UPDATE requirements SET approved_version_id=?,approved_score_id=? WHERE id=?",
                               (command.version_id, command.score_id, requirement_id))
        if command.action in ("approve", "reject"):
            connection.execute("UPDATE review_items SET status='resolved',resolved_at=? WHERE requirement_id=? AND status='open'",
                               (timestamp, requirement_id))
        elif command.action == "challenge":
            open_review(connection, requirement_id, command.rationale, {"decision_id": decision_id, "challenged": True}, command.actor)
        result = requirement_detail(connection, requirement_id)
        audit(connection, "requirement", requirement_id, f"requirement.{command.action}", command.actor, command.rationale,
              before=requirement, after={key: result[key] for key in requirement}, metadata={"decision_id": decision_id, "score_id": command.score_id})
        return {"decision_id": decision_id, "requirement": result}


@router.get("/reviews")
def list_reviews(vehicle: str | None = None, market: str | None = None, status: Literal["open", "resolved", "superseded"] = "open"):
    vehicle = vehicle.strip().upper() if vehicle is not None else None
    market = normalize_market(market) if market is not None else None
    clauses, params = ["q.status=?"], [status]
    for name, value in (("vehicle", vehicle), ("market", market)):
        if value is not None:
            clauses.append(f"r.{name}=?")
            params.append(value)
    with closing(connect()) as connection:
        rows = connection.execute("SELECT q.*,r.vehicle,r.market FROM review_items q JOIN requirements r ON r.id=q.requirement_id WHERE "
                                  + " AND ".join(clauses) + " ORDER BY q.created_at,q.id", params)
        return [decode(row, ("changes",)) for row in rows]


@router.get("/audit")
def list_audit(entity_id: str | None = None, after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000)):
    clauses, params = ["sequence>?"], [after]
    if entity_id:
        clauses.append("entity_id=?")
        params.append(entity_id)
    with closing(connect()) as connection:
        rows = connection.execute("SELECT * FROM audit_events WHERE " + " AND ".join(clauses) + " ORDER BY sequence LIMIT ?", [*params, limit]).fetchall()
    items = [decode(row, ("before_state", "after_state", "metadata")) for row in rows]
    return {"items": items, "next_after": items[-1]["sequence"] if items else after}
