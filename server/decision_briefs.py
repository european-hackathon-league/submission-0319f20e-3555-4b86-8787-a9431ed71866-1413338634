"""Evidence-backed planning briefs; these checks are prompts for PM judgment, not approvals."""

from contextlib import closing
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from database.store import audit, connect, decode, transaction
from server.requirements import evidence_for_findings, finding_detail, require_row, version_detail

router = APIRouter()
PROCESS_CONTEXT = {
    "focus": "Market research and needs analysis → product planning",
    "sequence": ["Situation analysis", "Structure and context", "Requirements definition", "Prioritization",
                 "Human review", "Documentation and tracking"],
    "basis": ["materials/images/product-management-process.png", "notes/bmw-guidance.md"],
    "meaning": "A customer-requirements planning record; not a BMW engineering, homologation or production approval.",
}
LIMITATIONS = [
    "Sample counts are not market prevalence; provenance labels do not establish statistical independence.",
    "Readiness checks identify recorded evidence gaps, not semantic truth or engineering feasibility.",
    "PM-assumed targets remain assumptions after approval and require customer validation.",
    "Actor selection follows the prototype's declared-identity model; it is not authenticated enterprise sign-in.",
]


@router.get("/actors")
def actors():
    """Discover declared actors so clients can explain existing database decision gates."""
    with closing(connect()) as connection:
        return [dict(row) for row in connection.execute(
            "SELECT id,kind,display_name,role,active,origin FROM actors ORDER BY display_name,id")]


def requirement_brief(connection, snapshot, *, frozen=False):
    requirement = require_row(connection, snapshot["requirement_id"])
    version_id = snapshot["version_id"] if frozen else requirement["current_version_id"]
    version = version_detail(connection, version_id, snapshot["score_id"] if frozen else None)
    if version["requirement_id"] != requirement["id"] or not version["score"]:
        raise HTTPException(409, "Workflow snapshot no longer resolves to its requirement and score")
    score = version["score"]
    if frozen:
        decision = connection.execute("SELECT * FROM decisions WHERE id=?", (snapshot["decision_id"],)).fetchone()
    else:
        decision = connection.execute(
            "SELECT * FROM decisions WHERE requirement_id=? ORDER BY rowid DESC LIMIT 1", (requirement["id"],),
        ).fetchone()
    decision = dict(decision) if decision else None
    if decision and (decision["requirement_id"], decision["version_id"], decision["score_id"]) != (
        requirement["id"], version["id"], score["id"],
    ):
        if frozen:
            raise HTTPException(409, "Workflow decision does not match its frozen version and score")
        decision = None
    findings = [finding_detail(connection, fid) for fid in version["finding_ids"]]
    evidence = evidence_for_findings(connection, version["finding_ids"])
    support = {eid for finding in findings for eid in finding["evidence_ids"]}
    conflict = {eid for finding in findings for eid in finding["conflicting_evidence_ids"]}
    for item in evidence:
        item["relations"] = (["supports"] if item["id"] in support else []) + (
            ["conflicts"] if item["id"] in conflict else [])
    sources = [decode(connection.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone(), ("metadata",))
               for sid in sorted({item["source_id"] for item in evidence})]
    checks = []

    def attention(code, message, next_action, evidence_ids=()):
        checks.append({"code": code, "severity": "attention", "message": message, "next_action": next_action,
                       "evidence_ids": sorted(evidence_ids)})

    if conflict:
        attention("conflicting_evidence", f"{len(conflict)} evidence records conflict with linked findings.",
                  "Compare customer groups and contexts; record why the chosen requirement is appropriate.", conflict)
    undated = [item["id"] for item in evidence if not item["observed_at"]]
    if undated:
        attention("undated_evidence", f"{len(undated)} records have no observation date.",
                  "Confirm recency before applying this evidence to a future vehicle; do not infer a trend.", undated)
    assumed = [item for item in version["acceptance_criteria"] if item["basis"] == "PM assumption"]
    if assumed:
        attention("assumed_targets", f"{len(assumed)} acceptance targets are explicitly PM assumptions.",
                  "Confirm a realistic metric, target, validation method and deadline with customer research.")
    if score["explanation"].get("provenance_count", 0) < 2:
        attention("limited_provenance", "Linked evidence has fewer than two recorded provenance labels.",
                  "Seek independent customer or market corroboration; avoid treating repeated records as prevalence.",
                  [item["id"] for item in evidence])
    if version["assumptions"]:
        attention("open_assumptions", f"{len(version['assumptions'])} future-facing assumptions are recorded.",
                  "Review each assumption and identify who will validate it before the planning commitment.")
    if not decision or decision["action"] not in {"approve", "reject"}:
        attention("human_decision", "This exact version and score still need a terminal PM decision.",
                  "Review supporting and conflicting evidence, edit if needed, then approve or reject with rationale.")
    return {
        "requirement_id": requirement["id"], "key": requirement["key"], "topic": requirement["topic"],
        "version": version, "score": score, "decision": decision, "checks": checks,
        "evidence": evidence, "sources": sources, "findings": findings,
        "approved_baseline": None if frozen else version_detail(
            connection, requirement["approved_version_id"], requirement["approved_score_id"]),
        "trace_url": (f"/requirements/{quote(requirement['id'], safe='')}/trace"
                      f"?version_id={quote(version['id'], safe='')}&score_id={quote(score['id'], safe='')}"),
    }


def coverage_warnings(connection, vehicle, market):
    """Representativeness warnings from the current coverage report (market data, coverage-v1)."""
    row = connection.execute("SELECT warnings, method_version FROM v_coverage_current WHERE vehicle=? AND market=? "
                             "ORDER BY created_at DESC, id DESC LIMIT 1", (vehicle, market)).fetchone()
    if row is None:
        return []
    return [f"Data coverage ({row['method_version']}): {warning['message']}" for warning in decode(row, ("warnings",))["warnings"]
            if isinstance(warning, dict) and warning.get("severity") in ("medium", "high")]


def build_brief(connection, workflow):
    frozen = workflow["status"] == "completed"
    snapshots = workflow["requirement_snapshots"]
    if not frozen and snapshots:
        # Completion reviews every current requirement in scope, including PM
        # additions since generation. Keep the preparation brief on that same set.
        snapshots = [dict(row) for row in connection.execute(
            "SELECT id AS requirement_id FROM requirements WHERE vehicle=? AND market=? ORDER BY key,id",
            (workflow["vehicle"], workflow["market"]))]
    requirements = [requirement_brief(connection, snapshot, frozen=frozen) for snapshot in snapshots]
    requirements.sort(key=lambda item: (-item["score"]["total"], item["key"]))
    approved = sum(item["decision"] is not None and item["decision"]["action"] == "approve" for item in requirements)
    rejected = sum(item["decision"] is not None and item["decision"]["action"] == "reject" for item in requirements)
    current_evidence = {row[0] for row in connection.execute(
        "SELECT id FROM evidence WHERE vehicle=? AND market=?", (workflow["vehicle"], workflow["market"]))}
    warnings = []
    if not frozen and current_evidence != set(workflow.get("evidence_ids", [])):
        warnings.append("Evidence differs from this run's assessed input. Run a cumulative update before completing.")
    if not requirements:
        warnings.append("No requirements are available yet; finish the autonomous stages before review.")
    if not frozen:
        warnings += coverage_warnings(connection, workflow["vehicle"], workflow["market"])
    return {
        "workflow_id": workflow["id"], "vehicle": workflow["vehicle"], "market": workflow["market"],
        "status": workflow["status"], "snapshot": "completed" if frozen else "live",
        "provider": workflow["provider"], "analysis_id": workflow["analysis_id"],
        "created_at": workflow["created_at"], "documented_at": workflow["updated_at"] if frozen else None,
        "summary": {"requirement_count": len(requirements), "approved_count": approved, "rejected_count": rejected,
                    "needs_decision_count": len(requirements) - approved - rejected,
                    "attention_count": sum(len(item["checks"]) for item in requirements)},
        "requirements": requirements, "warnings": warnings, "process_context": PROCESS_CONTEXT, "limitations": LIMITATIONS,
    }


def md(value):
    """Keep imported evidence as text even in a downloaded Markdown document."""
    text = str(value).replace("\r", " ").replace("\n", " ")
    for character in "\\`*_{}[]<>()#!|":
        text = text.replace(character, "\\" + character)
    return text


def brief_markdown(brief):
    lines = [f"# Customer requirements planning brief — {md(brief['vehicle'])} / {md(brief['market'])}", "",
             f"Workflow: {md(brief['workflow_id'])} · {md(brief['snapshot'])} · {md(brief['provider'])}", "",
             brief["process_context"]["meaning"], "", "## Review summary", ""]
    summary = brief["summary"]
    lines += [f"{summary['requirement_count']} requirements; {summary['approved_count']} approved; "
              f"{summary['rejected_count']} rejected; {summary['needs_decision_count']} awaiting a terminal decision.", ""]
    for warning in brief["warnings"]:
        lines += [f"- {md(warning)}"]
    for item in brief["requirements"]:
        version, score = item["version"], item["score"]
        lines += ["", f"## {md(item['key'])} — {md(version['title'])}", "", md(version["statement"]), "",
                  f"Version {version['version']} ({md(version['id'])}); score {score['total']}/100; "
                  f"evidence grade {score['evidence_grade']}; score ID {md(score['id'])}.", "",
                  f"Customer need: {md(version['customer_need'])}", "", "### Acceptance criteria", ""]
        for criterion in version["acceptance_criteria"]:
            lines.append(f"- {md(criterion['metric'])}: {md(criterion['target'])} {md(criterion.get('unit') or '')} "
                         f"({md(criterion['basis'])}); sources: {md(', '.join(criterion['source_ids']) or 'none claimed')}.")
        lines += ["", "### Priority rationale", "", md(score["explanation"]["formula"])]
        for factor, weight in score["weights"].items():
            lines.append(f"- {md(factor)}: {score['factors'][factor]} × {weight} × 20 "
                         f"= {score['explanation']['contributions'][factor]}")
        lines += ["", "### PM decision", ""]
        decision = item["decision"]
        lines.append(f"{md(decision['action'])} by {md(decision['actor'])}: {md(decision['rationale'])} "
                     f"({md(decision['id'])}, {md(decision['created_at'])})." if decision else "Awaiting human decision.")
        lines += ["", "### Assumptions and review actions", ""]
        lines += [f"- Assumption: {md(assumption)}" for assumption in version["assumptions"]]
        lines += [f"- {md(check['message'])} {md(check['next_action'])}" for check in item["checks"]]
        lines += ["", "### Evidence and exact source locations", ""]
        source_map = {source["id"]: source for source in item["sources"]}
        for evidence in item["evidence"]:
            source = source_map[evidence["source_id"]]
            lines += [f"- {md(', '.join(evidence['relations']))}: {md(evidence['content'])}",
                      f"  Source {md(source['title'])} ({md(source['id'])}), {md(source['reference'])}; "
                      f"location {md(evidence['location'])}; observed {md(evidence['observed_at'] or 'unknown')}; "
                      f"evidence {md(evidence['id'])}."]
    lines += ["", "## Limits", ""] + [f"- {md(item)}" for item in brief["limitations"]]
    return "\n".join(lines) + "\n"


@router.get("/workflows/{workflow_id}/brief")
def workflow_brief(workflow_id: str, format: Literal["json", "markdown"] = "json"):
    from server.workflows import workflow_detail

    with transaction() as connection:
        brief = build_brief(connection, workflow_detail(connection, workflow_id))
        audit(connection, "workflow", workflow_id, "workflow.brief_viewed", "system:workflow",
              "Source-linked PM planning brief accessed", metadata={"format": format, "snapshot": brief["snapshot"]})
    if format == "markdown":
        return Response(brief_markdown(brief), media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="pm-brief-{brief["workflow_id"]}.md"'})
    return brief
