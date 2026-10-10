import type { Requirement, Detail } from "./types";
export function csvCell(value: unknown) {
  let text = value == null ? "" : String(value);
  // Spreadsheet applications must not execute source-provided formulas.
  if (/^[\s]*[=+@\-\t\r]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}
export function csv(rows: Record<string, unknown>[]) {
  if (!rows.length) return "";
  const keys = Object.keys(rows[0]);
  return [
    keys.map(csvCell).join(","),
    ...rows.map((r) => keys.map((k) => csvCell(r[k])).join(",")),
  ].join("\r\n");
}
export function download(
  name: string,
  content: string,
  type = "application/json",
) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function registerRows(items: Requirement[]) {
  return items.map((r) => ({
    key: r.key,
    title: r.title,
    vehicle: r.vehicle,
    market: r.market,
    topic: r.topic,
    status: r.status,
    version: r.version,
    version_id: r.current_version_id,
    score: r.priority,
    evidence_grade: r.evidence_grade,
    score_id: r.score_id,
    needs_review: r.needs_review,
    approved_version_id: r.approved_version_id,
    updated_at: r.updated_at,
  }));
}
const xml = (s: unknown) =>
  String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
// Minimal ReqIF 1.2 exchange: approved immutable versions, plain-text attributes.
export function reqif(items: Detail[], timestamp = new Date().toISOString()) {
  const fields = [
    "Key",
    "Statement",
    "Acceptance criteria",
    "Evidence grade",
    "Priority",
    "Version ID",
    "Score ID",
    "Source trace",
  ];
  const approved = items.filter((r) => r.approved_version);
  return `<?xml version="1.0" encoding="UTF-8"?><REQ-IF xmlns="http://www.omg.org/spec/ReqIF/20110401/reqif.xsd"><THE-HEADER><REQ-IF-HEADER IDENTIFIER="bmw-pm-export"><CREATION-TIME>${xml(timestamp)}</CREATION-TIME><REQ-IF-TOOL-ID>BMW PM workspace</REQ-IF-TOOL-ID><REQ-IF-VERSION>1.2</REQ-IF-VERSION><SOURCE-TOOL-ID>BMW PM workspace</SOURCE-TOOL-ID><TITLE>Approved customer requirements</TITLE></REQ-IF-HEADER></THE-HEADER><CORE-CONTENT><REQ-IF-CONTENT><DATATYPES><DATATYPE-DEFINITION-STRING IDENTIFIER="text" LAST-CHANGE="${xml(timestamp)}" LONG-NAME="Text" MAX-LENGTH="65535"/></DATATYPES><SPEC-TYPES><SPEC-OBJECT-TYPE IDENTIFIER="requirement-type" LAST-CHANGE="${xml(timestamp)}" LONG-NAME="Customer requirement"><SPEC-ATTRIBUTES>${fields.map((f, i) => `<ATTRIBUTE-DEFINITION-STRING IDENTIFIER="attr-${i}" LAST-CHANGE="${xml(timestamp)}" LONG-NAME="${xml(f)}"><TYPE><DATATYPE-DEFINITION-STRING-REF>text</DATATYPE-DEFINITION-STRING-REF></TYPE></ATTRIBUTE-DEFINITION-STRING>`).join("")}</SPEC-ATTRIBUTES></SPEC-OBJECT-TYPE><SPECIFICATION-TYPE IDENTIFIER="spec-type" LAST-CHANGE="${xml(timestamp)}" LONG-NAME="Approved register"/></SPEC-TYPES><SPEC-OBJECTS>${approved
    .map((r) => {
      const v = r.approved_version!;
      const vals = [
        r.key,
        v.statement,
        v.acceptance_criteria
          .map(
            (c) =>
              `${c.metric}: ${c.target} ${c.unit || ""} (${c.basis}); citations: ${c.source_ids.join(", ")}`,
          )
          .join("\n"),
        v.score.evidence_grade,
        v.score.total,
        v.id,
        v.score.id,
        `/requirements/${r.id}/trace?version_id=${v.id}&score_id=${v.score.id}`,
      ];
      return `<SPEC-OBJECT IDENTIFIER="req-${xml(r.id)}" LAST-CHANGE="${xml(v.created_at)}" LONG-NAME="${xml(v.title)}"><VALUES>${vals.map((value, i) => `<ATTRIBUTE-VALUE-STRING THE-VALUE="${xml(value)}"><DEFINITION><ATTRIBUTE-DEFINITION-STRING-REF>attr-${i}</ATTRIBUTE-DEFINITION-STRING-REF></DEFINITION></ATTRIBUTE-VALUE-STRING>`).join("")}</VALUES><TYPE><SPEC-OBJECT-TYPE-REF>requirement-type</SPEC-OBJECT-TYPE-REF></TYPE></SPEC-OBJECT>`;
    })
    .join(
      "",
    )}</SPEC-OBJECTS><SPECIFICATIONS><SPECIFICATION IDENTIFIER="register" LAST-CHANGE="${xml(timestamp)}" LONG-NAME="Approved register"><TYPE><SPECIFICATION-TYPE-REF>spec-type</SPECIFICATION-TYPE-REF></TYPE><CHILDREN>${approved.map((r) => `<SPEC-HIERARCHY IDENTIFIER="hierarchy-${xml(r.id)}" LAST-CHANGE="${xml(timestamp)}"><OBJECT><SPEC-OBJECT-REF>req-${xml(r.id)}</SPEC-OBJECT-REF></OBJECT></SPEC-HIERARCHY>`).join("")}</CHILDREN></SPECIFICATION></SPECIFICATIONS></REQ-IF-CONTENT></CORE-CONTENT></REQ-IF>`;
}
