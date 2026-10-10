// Mounts a widget with a synthetic in-memory host. Fixture content is invented for design review only.
import type { App } from "@modelcontextprotocol/ext-apps";
import { applyDocumentTheme } from "@modelcontextprotocol/ext-apps";
import { mountScoringPanel } from "../src/scoring-panel";
import { TraceExplorer } from "../src/trace-explorer";

const params = new URLSearchParams(location.search);
const theme = params.get("theme") === "dark" ? "dark" : "light";
applyDocumentTheme(theme);
const root = document.getElementById("preview-root")!;
const weights = { customer_impact: .35, market_relevance: .25, strategic_fit: .2, differentiation: .1, feasibility: .1 };
const factors = { customer_impact: 4.6, market_relevance: 4, strategic_fit: 3, differentiation: 2, feasibility: 3 };
const statement = "Drivers of the successor to the sample sedan shall be able to change cabin temperature and fan speed without leaving the primary driving view. Preserve the positively reported qualities while addressing slow, multi-step touch interactions.";
const assumptions = [
  "The 3–5 year introduction horizon is a PM planning assumption; current sample evidence is the predecessor anchor.",
  "The 5-second task target is a proposed PM assumption, not a measured result; PM must approve the evaluation protocol.",
  "Strategic fit, differentiation and feasibility are unvalidated PM judgments.",
  "Record counts describe the imported sample, not customer prevalence.",
];
function version(number: number, scoreId = `score-${number}`) {
  return {
    id: `ver-${number}`, requirement_id: "req-demo", version: number, title: "Simplify climate control access", statement,
    customer_need: "Drivers need to adjust the cabin climate quickly and safely while driving.",
    acceptance_criteria: [{ metric: "Median time to change temperature in a representative evaluation", target: "At most 5", unit: "seconds", basis: "PM assumption", source_ids: [] }],
    assumptions, factors, actor: "Sample PM", rationale: "Proposed from synthetic analysis", created_at: "2026-10-01T09:12:00Z", finding_ids: ["finding-1", "finding-2", "finding-3"],
    score: { id: scoreId, version_id: `ver-${number}`, total: 75.1, evidence_grade: "C", factors, weights, rubric_version: "customer-priority-v1", created_at: "2026-10-01T09:12:00Z",
      explanation: { formula: "sum(factor × weight × 20)", contributions: { customer_impact: 32.2, market_relevance: 20, strategic_fit: 12, differentiation: 4, feasibility: 6 }, limitations: ["Synthetic sample counts are not market prevalence; the evidence grade is separate from priority."] } },
  };
}
let requirementVersion = 2;
function requirement() {
  return {
    id: "req-demo", key: "REQ-DEMO-US-014", vehicle: "G60", market: "US", status: "needs_review", current_version_id: `ver-${requirementVersion}`,
    approved_version_id: "ver-1", approved_score_id: "score-1", approved_version: version(1), needs_review: true,
    reviews: [{ status: "open", reason: "New conflicting evidence was linked after approval" }], current_version: version(requirementVersion),
  };
}
const quotes = [
  "Changing the temperature takes three taps and I have to look away from the road every time. I wish there was a simple knob.",
  "The climate screen is beautiful but it is too slow when the windshield fogs up in the morning.",
  "Love the car overall. Voice control for the fan works most of the time, which helps.",
  "I keep accidentally opening the seat heating menu when I only want to turn the fan down.",
];
const evidence = Array.from({ length: 13 }, (_, index) => ({
  id: `ev-${index + 1}`, source_id: index % 4 === 2 ? "src-web" : "src-sample", content: quotes[index % quotes.length], vehicle: "G60", market: "US", observed_at: null, created_at: "2026-10-01T09:00:00Z",
  location: { sheet: "Sample_Feedback", row: 120 + index * 7, column: "Customer Feedback" },
  metadata: { record_type: "customer_feedback", provenance: "Synthetic sample", review_status: index % 4 === 2 ? "unreviewed" : undefined },
}));
const sources = [
  { id: "src-sample", title: "Synthetic feedback sample.xlsx", kind: "feedback", reference: "synthetic-feedback-sample.xlsx", vehicle: "G60", market: "US", created_at: "2026-10-01T08:00:00Z", observed_at: null, content_hash: "4f1c0d…e92a", metadata: { dates: "Only dates present in the source are used" } },
  { id: "src-web", title: "Example owner forum thread", kind: "web", reference: "https://example.com/forum/climate-controls", vehicle: "G60", market: "US", created_at: "2026-10-02T08:00:00Z", observed_at: null, content_hash: "9ab3…11fe",
    metadata: { review_status: "unreviewed", web_evidence: { publication_date: "2026-09-14", retrieved_at: "2026-10-02T07:58:00Z", uncertainties: ["Applicability to the requested market is unverified."] } } },
];
const findings = [
  { id: "finding-1", kind: "problem", topic: "climate-controls", summary: "Temperature and fan changes need several touch steps and pull attention from the road.", confidence: .82, created_at: "2026-10-01T09:05:00Z", evidence_ids: ["ev-1", "ev-2", "ev-5", "ev-6", "ev-9", "ev-10", "ev-13"], conflicting_evidence_ids: ["ev-3"] },
  { id: "finding-2", kind: "need", topic: "climate-controls", summary: "Drivers want a physical or glanceable control for the most frequent climate adjustments.", confidence: .74, created_at: "2026-10-01T09:05:00Z", evidence_ids: ["ev-4", "ev-8", "ev-12"], conflicting_evidence_ids: [] },
  { id: "finding-3", kind: "strength", topic: "climate-controls", summary: "Voice control for fan speed is reported as helpful when it recognizes the request.", confidence: .61, created_at: "2026-10-01T09:05:00Z", evidence_ids: ["ev-3", "ev-7", "ev-11"], conflicting_evidence_ids: [] },
];
const decisions = [
  { id: "dec-1", version_id: "ver-1", score_id: "score-1", action: "approve", actor: "Sample PM", rationale: "Strong recurring signal across the sample; approve for concept evaluation.", created_at: "2026-10-01T11:40:00Z" },
  { id: "dec-2", version_id: "ver-2", score_id: "score-2", action: "challenge", actor: "Second Reviewer", rationale: "New conflicting voice-control feedback; confirm whether the target still holds.", created_at: "2026-10-03T15:02:00Z" },
];
function trace(args: Record<string, unknown>) {
  const offset = Number(args.offset ?? 0), limit = Number(args.limit ?? 12);
  const selected = typeof args.version_id === "string" ? Number(String(args.version_id).split("-")[1]) : requirementVersion;
  return { requirement: { ...requirement(), topic: "climate-controls" }, version: version(selected), findings, sources, evidence: { items: evidence.slice(offset, offset + limit), total: evidence.length, limit, offset }, decisions: decisions.filter((item) => item.version_id === `ver-${selected}`) };
}
const audit = Array.from({ length: 14 }, (_, index) => ({ sequence: index + 1, entity_id: "req-demo", action: ["requirement_created", "score_recorded", "decision_recorded", "trace_viewed"][index % 4], actor: index % 3 ? "Sample PM" : "System:reference", created_at: `2026-10-0${1 + (index % 5)}T1${index % 10}:00:00Z`, rationale: "Synthetic audit event", before_state: index ? { version: 1 } : null, after_state: { version: 1 + (index % 2), status: "needs_review" }, metadata: { source: "preview" } }));
function result(value: unknown) { return { content: [{ type: "text", text: JSON.stringify(value) }] }; }
async function tool(name: string, args: Record<string, unknown>): Promise<unknown> {
  await new Promise((resolve) => setTimeout(resolve, 250));
  switch (name) {
    case "get_requirement": return requirement();
    case "edit_requirement": requirementVersion += 1; return requirement();
    case "score_requirement": return requirement().current_version.score;
    case "decide_requirement": return { decision_id: "dec-new" };
    case "trace_requirement": return trace(args);
    case "get_requirement_versions": return Array.from({ length: requirementVersion }, (_, index) => version(index + 1));
    case "get_finding": return findings.find((item) => item.id === args.finding_id);
    case "get_evidence": return evidence.find((item) => item.id === args.evidence_id);
    case "get_source": return sources.find((item) => item.id === args.source_id);
    case "list_audit": { const after = Number(args.after ?? 0); const items = audit.filter((item) => item.sequence > after).slice(0, Number(args.limit ?? 10)); return { items, next_after: items.at(-1)?.sequence ?? after }; }
    default: throw new Error(`Unknown tool ${name}`);
  }
}
const host = {
  ontoolresult: undefined as undefined | ((value: unknown) => void),
  onhostcontextchanged: undefined as unknown,
  async connect() {},
  getHostContext: () => ({ theme }),
  async callServerTool({ name, arguments: args }: { name: string; arguments: Record<string, unknown> }) { return result(await tool(name, args)); },
  async updateModelContext() { return {}; },
  async sendSizeChanged(params: { height?: number }) { parent.postMessage(params, "*"); },
};
if (params.get("app") === "trace") {
  const explorer = new TraceExplorer(root, (name, args) => tool(name, args), async (url) => { window.open(url, "_blank", "noopener"); return {}; });
  explorer.shell.attach(host);
  explorer.setConnected();
  explorer.receive(trace({ limit: 12, offset: 0 }));
} else {
  const panel = mountScoringPanel(host as unknown as App, root);
  void panel.connect();
  host.ontoolresult?.(result(requirement()));
}
