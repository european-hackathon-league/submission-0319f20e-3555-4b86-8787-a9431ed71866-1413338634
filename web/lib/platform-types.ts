/**
 * Platform API contract used by the web workspace (Pod G).
 *
 * Status per pod (read-only review of the pod branches; nothing is merged into this branch):
 * - VERIFIED against the real backends: markets (codex/platform-markets-complete:server/markets.py),
 *   requests (codex/platform-intake-complete:server/intake.py), runs (codex/platform-runtime-complete:
 *   server/agent_runtime.py), and signals, priorities and market data (codex/platform-integration-main:
 *   server/signals.py, server/prioritization.py, server/market_data.py). Transforms are tested with fixtures
 *   that mirror the server's response construction. They still tolerate older alternatives, never invent data.
 *
 * Conventions (notes/platform-foundation.md "Response conventions"): a record is its §5.1 row with JSON
 * decoded plus computed fields; lists are {items, total, limit, offset}; writes return the record plus
 * run_id and audit_event_id; AI output carries provider, model / method_version ("openai:<model>:<prompt>")
 * and run_id. Every response-shape assumption lives in one transform per endpoint in lib/platform-api.ts
 * (`to<Thing>`); screens read only the transformed view models.
 *
 * Availability: the UI reads GET /openapi.json once and calls only endpoints listed there; a missing
 * endpoint renders "Not available on this server" without a request. Nothing is substituted for missing data.
 *
 * Request bodies: the acting identity is `actor` (a declared human for every gate) and human decisions carry
 * a non-empty `rationale`. Server models forbid extra fields, so each body is built in one client function.
 *
 * | Endpoint                                   | Body / query sent                                         | Status   |
 * | ------------------------------------------ | --------------------------------------------------------- | -------- |
 * | GET    /signals/watchlists                 | vehicle, market, limit, offset                            | verified |
 * | POST   /signals/watchlists                 | scope, topic, label, query_terms, competitors, domain_group, domains, cadence_days, max_results, actor, rationale | verified |
 * | PATCH  /signals/watchlists/{id}            | {status, actor, rationale}                                | verified |
 * | POST   /signals/watchlists/{id}/refresh    | {actor}                                                   | verified |
 * | POST   /signals/watchlists/{id}/backfill   | {actor, weeks}                                            | verified |
 * | GET    /signals/items                      | vehicle, market, topic?, review_status?                   | verified |
 * | POST   /signals/items/{id}/import|dismiss  | {actor, rationale}                                        | verified |
 * | POST   /signals/sentiment/score            | {vehicle, market, provider, actor}                        | verified |
 * | GET    /signals/sentiment/timeseries       | vehicle, market, topic → v_sentiment_weekly rows          | verified |
 * | GET    /signals/summary                    | vehicle, market → per topic × source_class × method rows  | verified |
 * | POST   /signals/summary                    | {vehicle, market, provider, topic?, actor} → rows + claims | verified |
 * | POST   /markets/compare                    | {vehicle, actor}                                          | verified |
 * | POST   /markets/conflicts/detect           | {vehicle, provider, actor}                                | verified |
 * | GET    /markets/conflicts                  | vehicle, status?                                          | verified |
 * | GET    /markets/conflicts/{id}             | –                                                         | verified |
 * | POST   /markets/conflicts/{id}/brief       | {actor, provider: openai}                                 | verified |
 * | POST   /markets/conflicts/{id}/resolve     | {decision, actor, rationale, requirement_ids}             | verified |
 * | GET    /markets/weights                    | vehicle, limit                                            | verified |
 * | GET    /requests                           | vehicle, market?, status?, sort=triage                    | verified |
 * | GET    /requests/{id}                      | actor (the view is audited)                               | verified |
 * | PATCH  /requests/{id}                      | {topic?, effort?, actor, rationale}                       | verified |
 * | GET    /requests/clusters                  | vehicle, market?                                          | verified |
 * | GET    /requests/aggregates                | vehicle, market?                                          | verified |
 * | POST   /requests/classify                  | {vehicle, market?, provider, actor}                       | verified |
 * | POST   /requests/cluster                   | {vehicle, provider, actor}                                | verified |
 * | POST   /requests/triage                    | {vehicle, market?, link_provider, actor}                  | verified |
 * | POST   /requests/links/propose             | {vehicle, market, request_ids, provider, actor}           | verified |
 * | POST   /requests/positions                 | {vehicle, market?, request_ids?, provider, actor}         | verified |
 * | POST   /requests/{id}/decide               | {decision, actor, rationale, requirement_id (link only)}  | verified |
 * | POST   /requests/fixtures/simulated        | {actor}                                                   | verified |
 * | GET    /priorities/rubrics                 | vehicle, market → items, active, history                  | verified |
 * | POST   /priorities/rubric                  | {vehicle, market, rubric_version, weights, actor, rationale} | verified |
 * | POST   /priorities/inputs/derive           | {vehicle, market, actor}                                  | verified |
 * | GET    /priorities/ranking                 | vehicle, market                                           | verified |
 * | POST   /priorities/sensitivity             | {vehicle, market, actor}                                  | verified |
 * | POST   /priorities/explain                 | {vehicle, market, provider, limit, actor}                 | verified |
 * | GET    /priorities/portfolio               | vehicle                                                   | verified |
 * | GET    /market-data/coverage               | vehicle, status=current                                   | verified |
 * | GET    /runs                               | vehicle, market?, capability?, status?, limit=50          | verified |
 */
import type { Scope } from "./types";

export type { Scope };
export type Json = Record<string, unknown>;
export type ListPage<T> = { items: T[]; total: number; limit: number; offset: number };
export type WriteResult<T> = { record: T; runId: string | null; auditEventId: string | null; raw: Json };

/** Mirrors the keys of server.analysis_engine.TOPICS (§5.5); tests/test_web_topics.py keeps them in sync. */
export const TOPICS = [
  ["charging", "Charging experience"],
  ["range", "Driving range"],
  ["comfort", "Cabin comfort"],
  ["quietness", "Cabin quietness"],
  ["controls", "Intuitive vehicle controls"],
  ["connectivity", "Digital connectivity"],
  ["access-storage", "Access and everyday storage"],
  ["driving-experience", "Driving experience"],
  ["driver-assistance", "Driver assistance experience"],
  ["design", "Vehicle design appeal"],
  ["overall-experience", "Overall customer experience"],
] as const;
export const MARKETS = ["US", "CN", "EU"] as const;
export type Provider = "openai" | "deterministic";

/** Where a value came from: a recorded model call ("Generated by AI") or deterministic, versioned code. */
export type Provenance = {
  generated: boolean;
  provider: string | null;
  model: string | null;
  promptVersion: string | null;
  methodVersion: string | null;
  runId: string | null;
};

// Signals (Pod A) – verified against codex/platform-integration-main:server/signals.py --------------------
export type DomainGroup = "press" | "forums" | "social" | "video" | "all";
export type Watchlist = Scope & {
  id: string;
  topic: string;
  label: string;
  query_terms: string[];
  competitors: string[];
  domain_group: DomainGroup;
  domains: string[];
  cadence_days: number;
  max_results: number;
  status: "active" | "paused";
  created_by: string;
  rationale: string;
  status_changed_by: string | null;
  created_at: string;
  updated_at: string;
  last_run_id: string | null;
};
export type WatchlistInput = Scope & {
  topic: string;
  label: string;
  query_terms: string[];
  competitors: string[];
  domain_group: DomainGroup;
  domains: string[];
  cadence_days: number;
  max_results: number;
  actor: string;
  rationale: string;
};
export type ReviewStatus = "unreviewed" | "imported" | "dismissed";
export type SignalItem = Scope & {
  id: string;
  watchlist_id: string;
  run_id: string;
  topic: string;
  url: string;
  domain: string;
  title: string | null;
  excerpt: string;
  published_at: string | null;
  retrieved_at: string;
  date_basis: "published" | "retrieved";
  review_status: ReviewStatus;
  evidence_id: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
};
export type SourceClass = "bmw_evidence" | "public_monitoring" | "public_imported";
export const SOURCE_CLASSES: SourceClass[] = ["bmw_evidence", "public_monitoring", "public_imported"];
export type SentimentPoint = {
  /** Sort key: the Monday `week_start` (0010), else the legacy `week` label. */
  week: string;
  /** Display label: the ISO 8601 week (e.g. 2026-W38) when the server sends it. */
  label: string;
  sourceClass: SourceClass;
  methodVersion: string;
  n: number;
  meanPolarity: number | null;
  negativeShare: number | null;
  positiveShare: number | null;
  mixedShare: number | null;
  lowN: boolean;
  undatedN: number;
  subjectIds: string[];
};
export type SentimentChart = {
  methodVersion: string | null;
  methodVersions: string[];
  sourceClasses: SourceClass[];
  rows: ({ week: string; label: string } & Partial<Record<SourceClass, number | null>>)[];
  points: Record<string, SentimentPoint>;
};
export type TopicSummary = {
  topic: string;
  sourceClass: SourceClass | null;
  methodVersion: string | null;
  n: number;
  meanPolarity: number | null;
  negativeShare: number | null;
  /** n-weighted least-squares slope of the weekly mean (polarity per week) over the last 8 ISO weeks with data. */
  momentum: number | null;
  momentumWeeks: number | null;
  windowStart: string | null;
  lastWeek: string | null;
  weeks: number | null;
  recentN: number | null;
  recentLowN: boolean | null;
  recentMeanPolarity: number | null;
  recentNegativeShare: number | null;
  undatedN: number;
  lowN: boolean;
  sampleIds: string[];
};
/** POST /signals/summary: the deterministic series rows plus, for OpenAI, grounded "what changed" claims. */
export type SignalsDigest = {
  claims: { text: string; subjectId: string; quote: string }[];
  rows: TopicSummary[];
  provenance: Provenance;
  runId: string | null;
};

// Markets (Pod B) – verified against codex/platform-markets-complete:server/markets.py -----------------
export type MarketWeight = Scope & {
  period: string;
  units: number | null;
  share: number | null;
  evidence_ids: string[];
  method_version: string | null;
  run_id: string | null;
};
export type MarketWeights = ListPage<MarketWeight> & {
  selected: { period: string; methodVersion: string | null } | null;
  warnings: string[];
};
export type ComparisonCell = {
  market: string;
  evidenceCount: number | null;
  evidenceGrade: string | null;
  evidenceIds: string[];
  findingIds: string[];
  sentiment: number | null;
  sentimentN: number | null;
  sentimentLowN: boolean;
  requirement: {
    id: string;
    key: string | null;
    title: string | null;
    status: string | null;
    score: number | null;
    rank: number | null;
    rankOf: number | null;
  } | null;
  targets: string[];
  requestPressure: number | null;
  requestMeanTriage: number | null;
  requestIds: string[];
  missing: Record<string, string>;
};
export type ComparisonRow = {
  topic: string;
  label: string | null;
  demandIndex: number | null;
  demandCoverage: number | null;
  alignment: string | null;
  recommendation: string | null;
  cells: Record<string, ComparisonCell>;
};
export type MarketColumn = {
  market: string;
  name: string | null;
  /** Recorded sales share (null when not measured). */
  share: number | null;
  /** Normalised weight used by the comparison (sales-based or the equal fallback). */
  weight: number | null;
  units: number | null;
  equalWeight: boolean;
  period: string | null;
};
export type MarketComparison = {
  vehicle: string;
  methodVersion: string | null;
  runId: string | null;
  weightBasis: string | null;
  weightsMethodVersion: string | null;
  sentimentMethodVersion: string | null;
  markets: MarketColumn[];
  rows: ComparisonRow[];
  warnings: string[];
};
export const CONFLICT_DECISIONS = ["adopt_global", "market_variants", "selectable_mode", "optional_package", "defer", "dismiss"] as const;
export type ConflictDecision = (typeof CONFLICT_DECISIONS)[number];
export type AiBrief = {
  summary: string;
  tradeOff: string | null;
  options: { option: string; summary: string; benefits: string[]; risks: string[] }[];
  openQuestions: string[];
  citations: { evidenceId: string; quote: string; market: string | null }[];
  label: string | null;
  provenance: Provenance;
};
export type MarketResolution = {
  id: string;
  conflict_id: string;
  decision: string;
  actor: string;
  rationale: string;
  requirement_ids: string[];
  created_at: string;
};
export type MarketConflict = {
  id: string;
  vehicle: string;
  topic: string;
  related_topic: string | null;
  markets: string[];
  conflict_type: "priority_divergence" | "direction_conflict" | "target_incompatible" | "evidence_gap" | string;
  severity: "low" | "medium" | "high" | string;
  metrics: Json;
  evidence_ids: Record<string, string[]>;
  requirement_ids: string[];
  recommendation: string;
  rationale: string;
  method_version: string;
  run_id: string;
  status: "open" | "resolved" | "superseded" | "dismissed" | string;
  created_at: string;
  aiBrief: AiBrief | null;
  latestResolution: MarketResolution | null;
};
export type EvidenceSnippet = {
  id: string;
  market: string | null;
  content: string | null;
  quote: string | null;
  sourceId: string | null;
  sourceTitle: string | null;
  observedAt: string | null;
  mentions: { attribute: string; direction: string; quote: string }[];
};
export type ConflictDetail = {
  conflict: MarketConflict;
  evidenceByMarket: Record<string, EvidenceSnippet[]>;
  requirements: {
    id: string;
    key: string | null;
    market: string | null;
    topic: string | null;
    status: string | null;
    title: string | null;
    score: number | null;
    evidenceGrade: string | null;
  }[];
  resolutions: MarketResolution[];
  history: { id: string; status: string; runId: string | null; createdAt: string }[];
  supersededBy: string | null;
};

// Requests (Pod C) – verified against codex/platform-intake-complete:server/intake.py ------------------
export const REQUEST_DECISIONS = ["convert", "link", "decline", "defer"] as const;
export type RequestDecisionKind = (typeof REQUEST_DECISIONS)[number];
export const REQUEST_STATUSES = ["new", "triaged", "linked", "converted", "declined", "deferred"] as const;
export const EFFORTS = ["low", "medium", "high"] as const;
export type FactorView = {
  name: string;
  value: number | null;
  weight: number | null;
  contribution: number | null;
  notMeasured: boolean;
  formula: string | null;
  inputs: Json;
  sources: SourceRef[];
  notes: string[];
  methodVersion: string | null;
  runId: string | null;
};
export type Triage = {
  id: string | null;
  rubricVersion: string | null;
  total: number | null;
  factors: FactorView[];
  flags: string[];
  suggestedAction: { decision: string; reason: string } | null;
  formula: string | null;
  cap: string | null;
  runId: string | null;
  createdAt: string | null;
};
export type IntakeRequest = Scope & {
  id: string;
  key: string;
  origin_type: string;
  origin_name: string;
  title: string;
  body: string;
  topic: string | null;
  attribute: string | null;
  effort: string | null;
  requested_at: string;
  simulated: boolean;
  scope_flags: string[];
  status: string;
  cluster_id: string | null;
  clusterTitle: string | null;
  clusterSize: number | null;
  ageDays: number | null;
  slaBreach: boolean;
  pmPinned: string[];
  created_by: string;
  created_at: string;
  triage: Triage | null;
};
export type RequestLink = {
  id: string;
  entity_type: string;
  entity_id: string;
  relation: "supports" | "conflicts" | "duplicates" | "addresses" | string;
  status: string;
  created_by: string;
  created_at: string;
  summary: string | null;
  market: string | null;
  quote: string | null;
  methodVersion: string | null;
  rationale: string | null;
  aiGenerated: boolean;
};
export type RequestDecision = {
  id: string;
  decision: string;
  actor: string;
  rationale: string;
  requirement_id: string | null;
  created_at: string;
};
export type PositionPoint = { text: string; evidenceId: string | null; quote: string | null };
export type PositionDraft = {
  summary: string | null;
  caseFor: PositionPoint[];
  caseAgainst: PositionPoint[];
  openQuestions: string[];
  citedIds: string[];
  label: string | null;
  createdAt: string | null;
  provenance: Provenance;
};
export type RequestDetail = {
  request: IntakeRequest;
  links: RequestLink[];
  decisions: RequestDecision[];
  triageHistory: Triage[];
  position: PositionDraft | null;
  positionCount: number;
};
export type RequestAggregates = {
  total: number | null;
  byMarket: Record<string, number>;
  byTopic: Record<string, number>;
  byStatus: Record<string, number>;
  byOrigin: Record<string, number>;
  demandIndex: Record<string, number>;
  demandMethod: string | null;
  weightsMeasured: boolean | null;
  medianAgeDays: number | null;
  slaDays: number | null;
  slaBreaches: number | null;
  simulatedCount: number | null;
  methodVersion: string | null;
};
export type RequestCluster = {
  id: string;
  title: string;
  topic: string | null;
  methodVersion: string | null;
  markets: string[];
  members: { id: string; key: string; market: string; title: string; status: string }[];
};

// Priorities (Pod D) – verified against codex/platform-integration-main:server/prioritization.py ----------
export type SourceRef = { type: string; id: string };
export type RubricDefinition = {
  version: string;
  weights: Record<string, number>;
  description: string | null;
  formula: string | null;
  derived: { factor: string; methodVersion: string | null; formula: string | null }[];
};
export type ScopeRubric = Scope & {
  id: string;
  rubric_version: string;
  weights: Record<string, number>;
  actor: string;
  rationale: string;
  created_at: string;
  /** The v1 default: no human switch is recorded for this scope. */
  isDefault: boolean;
};
export type RubricState = { available: RubricDefinition[]; current: ScopeRubric | null; history: ScopeRubric[] };
export type Stability = {
  rank: number | null;
  minRank: number | null;
  maxRank: number | null;
  stable: boolean | null;
  /** false when the scores changed since the recorded sensitivity analysis. */
  current: boolean;
  reason: string | null;
};
export type PreserveWarning = { label: string; message: string; evidenceIds: string[] };
export type ExplanationText = { text: string; citedIds: string[]; provenance: Provenance };
export type RankingRow = {
  requirementId: string;
  key: string | null;
  title: string;
  topic: string | null;
  status: string | null;
  versionId: string | null;
  scoreId: string | null;
  rubricVersion: string | null;
  total: number | null;
  rank: number | null;
  evidenceGrade: string | null;
  needsReview: boolean;
  /** customer-priority-v2 preview total for a v1-scored version (not stored, not a decision). */
  v2PreviewTotal: number | null;
  factors: FactorView[];
  preserveWarnings: PreserveWarning[];
  stability: Stability | null;
  explanation: ExplanationText | null;
};
export type Ranking = {
  vehicle: string;
  market: string;
  rubricVersion: string | null;
  methodVersion: string | null;
  runId: string | null;
  rows: RankingRow[];
  warnings: string[];
};
export type RankingExplanation = { summary: string | null; provenance: Provenance; items: Record<string, ExplanationText> };

/** GET /priorities/portfolio: topic × market v2 totals with the global demand index (priority-portfolio-v1). */
export type PortfolioCell = {
  requirementId: string;
  key: string | null;
  status: string | null;
  rubricVersion: string | null;
  total: number | null;
  v2Total: number | null;
  v2Basis: string | null;
  notMeasured: string[];
};
export type PortfolioTopic = {
  topic: string;
  label: string | null;
  cells: Record<string, PortfolioCell>;
  globalDemandIndex: number | null;
  demandMeasured: boolean;
  demandFlags: string[];
  demandMarkets: { market: string; share: number | null; normalisedPriority: number | null }[];
  pattern: string | null;
  conflicts: { id: string; conflictType: string; severity: string; recommendation: string | null; markets: string[] }[];
};
export type Portfolio = {
  vehicle: string;
  methodVersion: string | null;
  markets: string[];
  marketShares: Record<string, number>;
  shareBasis: string | null;
  sharesPeriod: string | null;
  rubrics: Record<string, string>;
  topics: PortfolioTopic[];
  patternRule: string | null;
  warnings: string[];
};

// BMW data (Pod E) – verified against codex/platform-integration-main:server/market_data.py -------------
export type CoverageWarning = { market: string; code: string; severity: string; message: string };
export type CoverageReport = {
  id: string;
  vehicle: string;
  market: string;
  methodVersion: string | null;
  runId: string | null;
  createdAt: string | null;
  warnings: CoverageWarning[];
};

// Runs (Pod F) ----------------------------------------------------------------------------------
export type LlmUsage = {
  calls: number;
  cacheHits: number;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  models: string[];
};
export type Run = {
  id: string;
  capability: string;
  task_id: string | null;
  actor: string;
  vehicle: string | null;
  market: string | null;
  method_version: string;
  input_hash: string;
  inputs: Json;
  outputs: Json | null;
  metrics: Json;
  status: "running" | "succeeded" | "failed" | string;
  error: string | null;
  started_at: string;
  finished_at: string | null;
  provenance: Provenance;
  usage: LlmUsage | null;
  durationMs: number | null;
};
export type CapabilityUsage = {
  capability: string;
  runs: number;
  failed: number;
  calls: number;
  cacheHits: number;
  totalTokens: number;
  models: string[];
};
