import type { components } from "./generated-api";
export type Schema = components["schemas"];
export type Scope = { vehicle: string; market: string };
export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};
export type Actor = {
  id: string;
  display_name: string;
  kind: string;
  role: string;
  active: number;
};
export type Source = Schema["Source"];
export type Criterion = Schema["AcceptanceCriterion"] & {
  source_ids: string[];
};
export type Factors = Record<
  | "customer_impact"
  | "market_relevance"
  | "strategic_fit"
  | "differentiation"
  | "feasibility",
  number
>;
export type Score = {
  id: string;
  total: number;
  evidence_grade: string;
  factors: Factors;
  weights: Factors;
  rubric_version: string;
  created_at: string;
  explanation: {
    formula: string;
    contributions: Factors;
    limitations: string[];
    evidence_grade_rubric: string;
    provenance_count: number;
    [key: string]: unknown;
  };
};
export type Version = {
  id: string;
  requirement_id: string;
  version: number;
  title: string;
  statement: string;
  customer_need: string;
  acceptance_criteria: Criterion[];
  assumptions: string[];
  factors: Factors;
  finding_ids: string[];
  score: Score;
  actor: string;
  created_by?: string;
  rationale: string;
  created_at: string;
};
export type Requirement = Scope & {
  id: string;
  key: string;
  title: string;
  topic: string;
  status: string;
  priority: number;
  evidence_grade: string;
  score_id: string;
  version: number;
  current_version_id: string;
  approved_version_id: string | null;
  approved_score_id: string | null;
  needs_review: boolean;
  created_at: string;
  updated_at: string;
};
export type Review = {
  id: string;
  requirement_id: string;
  reason: string;
  status: string;
  changes: Record<string, unknown>;
  created_at: string;
};
export type Detail = Requirement & {
  current_version: Version;
  approved_version: Version | null;
  reviews: Review[];
};
export type Evidence = Scope & {
  id: string;
  source_id: string;
  content: string;
  location: Record<string, unknown>;
  metadata: Record<string, unknown>;
  observed_at: string | null;
  content_hash: string;
  created_at: string;
};
export type Finding = Scope & {
  id: string;
  run_id: string;
  topic: string;
  kind: string;
  summary: string;
  confidence: number;
  evidence_ids: string[];
  conflicting_evidence_ids: string[];
  created_at: string;
};
export type Decision = {
  id: string;
  action: string;
  actor: string;
  rationale: string;
  created_at: string;
  version_id: string;
  score_id: string;
};
export type Trace = {
  requirement: Requirement;
  version: Version;
  findings: Finding[];
  sources: Source[];
  evidence: Page<Evidence>;
  decisions: Decision[];
};
export type Audit = {
  id: string;
  sequence: number;
  entity_type: string;
  entity_id: string;
  action: string;
  actor: string;
  rationale: string;
  created_at: string;
  event_hash?: string;
  previous_hash?: string;
  metadata: Record<string, unknown>;
  before_state: unknown;
  after_state: unknown;
};
export type Metrics = {
  counts: Record<string, number>;
  requirement_statuses: Record<string, number>;
  traceability: {
    coverage: number | null;
    requirements_with_source_links: number;
    requirements: number;
  };
  time_to_first_decision_seconds: {
    sample_count: number;
    median: number | null;
  };
  limitations: string[];
};
export type Workspace = {
  scope: Scope;
  available_scopes: (Scope & { source_count: number })[];
  evidence_count: number;
  requirements: Page<Requirement>;
  reviews: Review[];
};
export type Workflow = Scope & {
  id: string;
  kind: string;
  provider: string;
  status: string;
  revision: number;
  created_at: string;
  updated_at: string;
  analysis_id: string | null;
  stages: {
    key: string;
    label: string;
    status: string;
    output: Record<string, unknown> | null;
  }[];
  error: { message: string; retryable: boolean } | null;
  requirement_snapshots: {
    requirement_id: string;
    version_id: string;
    score_id: string;
    decision_id?: string;
  }[];
};
export type BriefRequirement = {
  requirement_id: string;
  key: string;
  topic: string;
  version: Version;
  score: Score;
  decision: Decision | null;
  findings: Finding[];
  sources: Source[];
  evidence: Evidence[];
  checks: {
    code: string;
    message: string;
    next_action: string;
    severity: string;
  }[];
  approved_baseline: Version | null;
};
export type Brief = {
  workflow_id: string;
  snapshot: string;
  requirements: BriefRequirement[];
  summary: {
    requirement_count: number;
    approved_count: number;
    rejected_count: number;
    needs_decision_count: number;
    attention_count: number;
  };
  warnings: string[];
  limitations: string[];
};
