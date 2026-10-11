import type { Review } from "@/lib/types";

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function count(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

function score(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function reviewChangeFacts(changes: Review["changes"]): string[] {
  const baseline = record(changes.against_approved);
  const added = count(baseline?.added_evidence_ids ?? changes.added_evidence_ids);
  const removed = count(baseline?.removed_evidence_ids ?? changes.removed_evidence_ids);
  const approved = score(record(baseline?.approved_score)?.total ?? changes.previous_score);
  const proposed = score(record(baseline?.proposed_score)?.total ?? changes.proposed_score);
  const fields = record(baseline?.fields);
  const facts: string[] = [];

  if (added || removed) {
    const parts = [];
    if (added) parts.push(`${added} linked evidence ${added === 1 ? "record" : "records"} added`);
    if (removed) parts.push(`${removed} linked evidence ${removed === 1 ? "record" : "records"} removed`);
    facts.push(parts.join("; "));
  }
  if (approved !== null && proposed !== null) {
    const delta = proposed - approved;
    facts.push(
      delta === 0
        ? `Priority unchanged at ${approved.toFixed(2)}`
        : `Priority ${approved.toFixed(2)} → ${proposed.toFixed(2)} (${delta > 0 ? "+" : ""}${delta.toFixed(2)})`,
    );
  }
  if (fields && Object.keys(fields).length === 1 && "factors" in fields) {
    facts.push("Score factors changed; wording and acceptance target stayed the same");
  }
  return facts;
}

export function ReviewChangeSummary({ review }: { review: Review }) {
  const facts = reviewChangeFacts(review.changes);
  if (!facts.length) return null;
  return (
    <div className="review-change-summary">
      <strong>Change since approved version</strong>
      <ul>
        {facts.map((fact) => <li key={fact}>{fact}</li>)}
      </ul>
    </div>
  );
}
