/**
 * Platform API contract assumed by the web workspace (Pod G) until the backend pods (A–F) merge.
 *
 * Sources: PLATFORM_BUILD_PLAN.md §5.1 (record fields), §5.3 (endpoints) and §8 (what each endpoint
 * returns), plus notes/platform-foundation.md "Response conventions":
 * - a record is its §5.1 row with JSON columns decoded, plus computed fields;
 * - lists are {items, total, limit, offset} (a bare array is accepted too), filterable by vehicle/market;
 * - writes return the record's fields at the top level plus run_id and audit_event_id;
 * - AI output carries provider, model / method_version ("openai:<model>:<prompt>") and run_id.
 *
 * Every response-shape assumption lives in exactly one transform per endpoint in lib/platform-api.ts
 * (`to<Thing>`), unit-tested with simulated fixtures in lib/platform-api.test.ts. When the real
 * backends differ, adapt the transform (and the request body builder next to it), not the screens.
 *
 * Availability: the UI reads GET /openapi.json once and calls only endpoints listed there (path
 * parameters normalised to `{}`); a missing endpoint renders "Not available on this server" without a
 * request. If the catalogue itself cannot be read, endpoints are tried and FastAPI's default 404
 * ("Not Found") or a 405 is treated the same way. Nothing is ever substituted for missing data.
 *
 * Request bodies follow the existing API: the acting identity is `actor` (a declared human for every
 * gate) and human decisions carry a non-empty `rationale`. Server models forbid extra fields, so each
 * body is built in one function in lib/platform-api.ts.
 *
 * | Endpoint (§5.3)                          | Request (query / body)                                         | Response fields read (see types below)                         |
 * | ---------------------------------------- | -------------------------------------------------------------- | -------------------------------------------------------------- |
 * | GET    /signals/watchlists               | vehicle, market, limit, offset                                 | Page<Watchlist>                                                |
 * | POST   /signals/watchlists               | WatchlistInput (actor = human, rationale)                      | Watchlist + run_id? + audit_event_id                           |
 * | PATCH  /signals/watchlists/{id}          | {status: active|paused, actor, rationale}                      | Watchlist + audit_event_id                                     |
 * | POST   /signals/watchlists/{id}/refresh  | {actor}                                                        | run_id, created/items counts (shown as returned)               |
 * | POST   /signals/watchlists/{id}/backfill | {actor, weeks}                                                 | run_id, created/items counts                                   |
 * | GET    /signals/items                    | vehicle, market, topic?, review_status?, limit, offset         | Page<SignalItem>                                               |
 * | POST   /signals/items/{id}/import        | {actor, rationale}                                             | SignalItem (review_status imported, evidence_id)               |
 * | POST   /signals/items/{id}/dismiss       | {actor, rationale}                                             | SignalItem (review_status dismissed)                           |
 * | POST   /signals/sentiment/score          | {vehicle, market, provider, actor}                             | run_id, counts                                                 |
 * | GET    /signals/sentiment/timeseries     | vehicle, market, topic, source_class?                          | points[] | items[] | series[].points[] (v_sentiment_weekly)    |
 * | GET    /signals/summary                  | vehicle, market                                                | items[] | topics[]: topic, n, mean_polarity, momentum, sample_ids |
 * | POST   /markets/compare                  | {vehicle, actor?}                                              | markets[], topics[] (cells per market) | cells[], warnings[]   |
 * | POST   /markets/conflicts/detect         | {vehicle, provider, actor}                                     | run_id, created/superseded counts                              |
 * | GET    /markets/conflicts                | vehicle, status?, limit, offset                                | Page<MarketConflict>                                           |
 * | GET    /markets/conflicts/{id}           | –                                                              | MarketConflict + evidence {market: Evidence[]} + resolutions[] |
 * | POST   /markets/conflicts/{id}/resolve   | {decision, actor, rationale, requirement_ids}                  | resolution + conflict status + audit_event_id                  |
 * | GET    /markets/weights                  | vehicle                                                        | Page<MarketWeight>                                             |
 * | GET    /requests                         | vehicle, market?, status?, sort=triage, limit, offset          | Page<IntakeRequest + triage (latest request_triage)>           |
 * | GET    /requests/{id}                    | –                                                              | IntakeRequest + links[] + decisions[] + triage_history[] + position |
 * | POST   /requests/triage | /cluster       | {vehicle, market?, actor, provider?}                           | run_id, counts                                                 |
 * | POST   /requests/{id}/decide             | {decision, actor, rationale, requirement_id?}                  | request_decision + request status + audit_event_id             |
 * | GET    /requests/aggregates              | vehicle, market?                                               | by_market/by_topic/by_status/by_origin (maps or count rows), demand_index, median_age_days, sla_breaches |
 * | POST   /requests/fixtures/simulated      | {actor}                                                        | created count                                                  |
 * | GET    /priorities/rubrics               | vehicle, market                                                | items[] (rubric definitions) + current scope rubric + history  |
 * | POST   /priorities/rubric                | {vehicle, market, rubric_version, weights, actor, rationale}   | scope_rubric + review ids + run_id + audit_event_id            |
 * | POST   /priorities/inputs/derive         | {vehicle, market, actor}                                       | run_id, counts                                                 |
 * | GET    /priorities/ranking               | vehicle, market                                                | items[]: factors (map or list) with derivations, stability, preserve_warnings |
 * | POST   /priorities/sensitivity           | {vehicle, market, actor}                                       | results {requirement_id: {rank, min_rank, max_rank, stable}}   |
 * | GET    /runs                             | vehicle, capability?, status?, limit, offset                   | Page<Run> (§5.1 runs with metrics.llm from server/llm.py)      |
 *
 * Clusters are derived from the request records (`cluster_id`, optional `cluster` / `cluster_title`);
 * no clusters endpoint is assumed.
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

// Signals (Pod A) -------------------------------------------------------------------------------
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
  week: string;
  sourceClass: SourceClass;
  methodVersion: string;
  n: number;
  meanPolarity: number | null;
  negativeShare: number | null;
  positiveShare: number | null;
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
  momentum: number | null;
  lowN: boolean;
  sampleIds: string[];
};

// Markets (Pod B) -------------------------------------------------------------------------------
export type MarketWeight = Scope & {
  period: string;
  units: number | null;
  share: number | null;
  evidence_ids: string[];
  method_version: string | null;
  run_id: string | null;
};
export type ComparisonCell = {
  market: string;
  evidenceCount: number | null;
  evidenceGrade: string | null;
  sentiment: number | null;
  requirement: { id: string; key: string | null; title: string | null; status: string | null; score: number | null; rank: number | null } | null;
  targets: string[];
  requestPressure: number | null;
  missing: Record<string, string>;
};
export type MarketComparison = {
  vehicle: string;
  methodVersion: string | null;
  runId: string | null;
  markets: { market: string; share: number | null; equalWeight: boolean; period: string | null }[];
  rows: { topic: string; cells: Record<string, ComparisonCell> }[];
  warnings: string[];
};
export const CONFLICT_DECISIONS = ["adopt_global", "market_variants", "selectable_mode", "optional_package", "defer", "dismiss"] as const;
export type ConflictDecision = (typeof CONFLICT_DECISIONS)[number];
export type AiBrief = { text: string; options: string[]; provenance: Provenance };
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
};
export type EvidenceSnippet = {
  id: string;
  market: string | null;
  content: string | null;
  quote: string | null;
  sourceId: string | null;
  observedAt: string | null;
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
export type ConflictDetail = {
  conflict: MarketConflict;
  evidenceByMarket: Record<string, EvidenceSnippet[]>;
  resolutions: MarketResolution[];
};

// Requests (Pod C) ------------------------------------------------------------------------------
export const REQUEST_DECISIONS = ["convert", "link", "decline", "defer"] as const;
export type RequestDecisionKind = (typeof REQUEST_DECISIONS)[number];
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
  rubricVersion: string | null;
  total: number | null;
  factors: FactorView[];
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
  requested_at: string;
  simulated: boolean;
  scope_flags: string[];
  status: string;
  cluster_id: string | null;
  clusterTitle: string | null;
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
};
export type RequestDecision = {
  id: string;
  decision: string;
  actor: string;
  rationale: string;
  requirement_id: string | null;
  created_at: string;
};
export type PositionDraft = {
  caseFor: string[];
  caseAgainst: string[];
  openQuestions: string[];
  citedIds: string[];
  provenance: Provenance;
};
export type RequestDetail = {
  request: IntakeRequest;
  links: RequestLink[];
  decisions: RequestDecision[];
  triageHistory: Triage[];
  position: PositionDraft | null;
};
export type RequestAggregates = {
  total: number | null;
  byMarket: Record<string, number>;
  byTopic: Record<string, number>;
  byStatus: Record<string, number>;
  byOrigin: Record<string, number>;
  demandIndex: Record<string, number>;
  medianAgeDays: number | null;
  slaBreaches: number | null;
};
export type RequestCluster = {
  id: string;
  title: string;
  topic: string | null;
  requests: IntakeRequest[];
  markets: string[];
};

// Priorities (Pod D) ----------------------------------------------------------------------------
export type SourceRef = { type: string; id: string };
export type RubricDefinition = { version: string; weights: Record<string, number>; description: string | null };
export type ScopeRubric = Scope & {
  id: string;
  rubric_version: string;
  weights: Record<string, number>;
  actor: string;
  rationale: string;
  created_at: string;
};
export type RubricState = { available: RubricDefinition[]; current: ScopeRubric | null; history: ScopeRubric[] };
export type Stability = { rank: number | null; minRank: number | null; maxRank: number | null; stable: boolean | null };
export type PreserveWarning = { label: string; message: string; evidenceIds: string[] };
export type RankingRow = {
  requirementId: string;
  key: string | null;
  title: string;
  topic: string | null;
  status: string | null;
  versionId: string | null;
  total: number | null;
  rank: number | null;
  evidenceGrade: string | null;
  factors: FactorView[];
  preserveWarnings: PreserveWarning[];
  stability: Stability | null;
  explanation: { text: string; provenance: Provenance } | null;
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
