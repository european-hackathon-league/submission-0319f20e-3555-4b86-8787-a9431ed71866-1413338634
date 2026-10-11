/**
 * Typed client and response transforms for the platform endpoints (§5.3). The contract table is at the
 * top of lib/platform-types.ts. One transform per endpoint (`to<Thing>`); every screen reads only the
 * transformed view models, so adapting to the merged backends happens here. Transforms never invent
 * values: a missing field stays null / empty and the screens label it.
 */
import { ApiError, api, write } from "./api";
import type {
  AiBrief,
  CapabilityUsage,
  ComparisonCell,
  ComparisonRow,
  ConflictDetail,
  EvidenceSnippet,
  FactorView,
  IntakeRequest,
  Json,
  ListPage,
  LlmUsage,
  MarketComparison,
  MarketConflict,
  MarketResolution,
  MarketWeight,
  MarketWeights,
  PositionDraft,
  PositionPoint,
  PreserveWarning,
  Provenance,
  Provider,
  Ranking,
  RankingExplanation,
  RankingRow,
  RequestAggregates,
  RequestCluster,
  RequestDecision,
  RequestDetail,
  RequestLink,
  RubricState,
  Run,
  Scope,
  ScopeRubric,
  SentimentChart,
  SentimentPoint,
  SignalItem,
  SourceClass,
  SourceRef,
  Stability,
  TopicSummary,
  Triage,
  Watchlist,
  WatchlistInput,
  WriteResult,
} from "./platform-types";
import { SOURCE_CLASSES } from "./platform-types";

// Small, total readers for untrusted JSON -------------------------------------------------------
const isObj = (v: unknown): v is Json => typeof v === "object" && v !== null && !Array.isArray(v);
/** JSON columns are decoded by convention; an encoded string is tolerated. */
const json = (v: unknown): unknown => {
  if (typeof v !== "string" || !/^\s*[[{]/.test(v)) return v;
  try {
    return JSON.parse(v);
  } catch {
    return v;
  }
};
const obj = (v: unknown): Json => {
  const value = json(v);
  return isObj(value) ? value : {};
};
const arr = (v: unknown): unknown[] => {
  const value = json(v);
  return Array.isArray(value) ? value : [];
};
const str = (v: unknown): string | null =>
  typeof v === "string" && v.trim() ? v : typeof v === "number" && Number.isFinite(v) ? String(v) : null;
const num = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v)
    ? v
    : typeof v === "string" && v.trim() && Number.isFinite(Number(v))
      ? Number(v)
      : null;
const strs = (v: unknown): string[] => arr(v).map(str).filter((s): s is string => !!s);
const bool = (v: unknown): boolean | null =>
  typeof v === "boolean" ? v : v === 1 || v === 0 ? v === 1 : null;
const first = (...values: unknown[]) => values.find((v) => v !== undefined && v !== null);
const numMap = (v: unknown): Record<string, number> => {
  const out: Record<string, number> = {};
  for (const [key, value] of Object.entries(obj(v))) {
    const n = num(isObj(value) ? value.value : value);
    if (n !== null) out[key] = n;
  }
  return out;
};
const unique = <T,>(values: T[]) => [...new Set(values)];
function need(o: Json, key: string, what: string): string {
  const value = str(o[key]);
  if (!value) throw new Error(`The server returned a ${what} without ${key}.`);
  return value;
}

// Conventions -----------------------------------------------------------------------------------
export function toPage<T>(value: unknown, item: (v: unknown) => T): ListPage<T> {
  if (Array.isArray(value)) {
    const items = value.map(item);
    return { items, total: items.length, limit: items.length, offset: 0 };
  }
  if (isObj(value) && Array.isArray(value.items)) {
    const items = value.items.map(item);
    return {
      items,
      total: num(value.total) ?? items.length,
      limit: num(value.limit) ?? items.length,
      offset: num(value.offset) ?? 0,
    };
  }
  throw new Error("The server returned an unexpected list shape.");
}
export function toWrite<T>(value: unknown, item: (v: unknown) => T): WriteResult<T> {
  const raw = obj(value);
  return { record: item(value), runId: str(raw.run_id), auditEventId: str(raw.audit_event_id), raw };
}
/** "openai:<model>:<prompt>" → recorded model call; any other label is deterministic, versioned code. */
export function parseMethodVersion(methodVersion: string | null | undefined) {
  if (!methodVersion) return { provider: null, model: null, promptVersion: null };
  const parts = methodVersion.split(":");
  if (parts[0] === "openai" && parts.length >= 3)
    return { provider: "openai", model: parts.slice(1, -1).join(":"), promptVersion: parts.at(-1) || null };
  return { provider: "deterministic", model: null, promptVersion: null };
}
export function provenance(source: unknown, fallbackMethod?: string | null, forceGenerated = false): Provenance {
  const o = obj(source);
  const methodVersion = str(o.method_version) ?? fallbackMethod ?? null;
  const parsed = parseMethodVersion(methodVersion);
  const provider = str(o.provider) ?? parsed.provider ?? (forceGenerated ? "openai" : null);
  return {
    generated: forceGenerated || (!!provider && provider !== "deterministic"),
    provider,
    model: str(o.model) ?? parsed.model,
    promptVersion: str(o.prompt_version) ?? parsed.promptVersion,
    methodVersion,
    runId: str(o.run_id),
  };
}
/** Summarises a capability response for a toast: its run id and any counts, exactly as returned. */
export function describeWrite(value: unknown): string {
  const o = obj(value);
  const counts = Object.entries(o)
    .filter(([key, v]) => typeof v === "number" && !["limit", "offset"].includes(key))
    .map(([key, v]) => `${key.replaceAll("_", " ")} ${v}`);
  const run = str(o.run_id) ?? strs(o.run_ids)[0];
  return [run ? `Run ${run.slice(0, 8)} recorded` : "Recorded", ...counts].join(" · ");
}
export const endpointKey = (method: string, path: string) =>
  `${method.toUpperCase()} ${path.replace(/\{[^}]*\}/g, "{}")}`;
export function toApiPaths(openapi: unknown): Set<string> {
  const paths = new Set<string>();
  for (const [path, operations] of Object.entries(obj(obj(openapi).paths)))
    for (const method of Object.keys(obj(operations)))
      if (["get", "post", "patch", "put", "delete"].includes(method)) paths.add(endpointKey(method, path));
  return paths;
}
/** A route the server does not have (FastAPI's default 404, the proxy allowlist, or 405/501). */
export function isUnavailable(error: unknown) {
  return (
    error instanceof ApiError &&
    (error.status === 405 ||
      error.status === 501 ||
      (error.status === 404 && /^(Not Found|Unknown API route)$/.test(error.message.trim())))
  );
}
/** Human-gate failures are explained, never retried. */
export function gateError(error: unknown): Error {
  if (error instanceof ApiError && error.status === 403)
    return new Error(
      `The server refused this decision (403): ${error.message}. Only an active human PM can take it; AI and system actors are rejected by the API and the database.`,
    );
  if (error instanceof ApiError && error.status === 422)
    return new Error(`The server rejected the submitted fields (422): ${error.message}`);
  return error instanceof Error ? error : new Error(String(error));
}

export const ENDPOINTS = {
  watchlists: "GET /signals/watchlists",
  createWatchlist: "POST /signals/watchlists",
  updateWatchlist: "PATCH /signals/watchlists/{}",
  refreshWatchlist: "POST /signals/watchlists/{}/refresh",
  backfillWatchlist: "POST /signals/watchlists/{}/backfill",
  signalItems: "GET /signals/items",
  importItem: "POST /signals/items/{}/import",
  dismissItem: "POST /signals/items/{}/dismiss",
  scoreSentiment: "POST /signals/sentiment/score",
  timeseries: "GET /signals/sentiment/timeseries",
  summary: "GET /signals/summary",
  compare: "POST /markets/compare",
  detectConflicts: "POST /markets/conflicts/detect",
  conflicts: "GET /markets/conflicts",
  conflict: "GET /markets/conflicts/{}",
  resolveConflict: "POST /markets/conflicts/{}/resolve",
  draftBrief: "POST /markets/conflicts/{}/brief",
  weights: "GET /markets/weights",
  requests: "GET /requests",
  request: "GET /requests/{}",
  editRequest: "PATCH /requests/{}",
  clusters: "GET /requests/clusters",
  classify: "POST /requests/classify",
  proposeLinks: "POST /requests/links/propose",
  positions: "POST /requests/positions",
  triage: "POST /requests/triage",
  cluster: "POST /requests/cluster",
  decideRequest: "POST /requests/{}/decide",
  aggregates: "GET /requests/aggregates",
  simulatedRequests: "POST /requests/fixtures/simulated",
  rubrics: "GET /priorities/rubrics",
  switchRubric: "POST /priorities/rubric",
  deriveInputs: "POST /priorities/inputs/derive",
  ranking: "GET /priorities/ranking",
  sensitivity: "POST /priorities/sensitivity",
  explain: "POST /priorities/explain",
  runs: "GET /runs",
} as const;
export type EndpointName = keyof typeof ENDPOINTS;

// Shared factor / derivation reader (request triage and priority v2) --------------------------------
const SOURCE_KEYS: [string, string][] = [
  ["evidence_ids", "evidence"],
  ["finding_ids", "finding"],
  ["signal_item_ids", "signal_item"],
  ["request_ids", "request"],
  ["cluster_ids", "request_cluster"],
  ["conflict_ids", "market_conflict"],
  ["requirement_ids", "requirement"],
  ["weight_ids", "market_weight"],
  ["preserve_ids", "preserve_attribute"],
  ["run_ids", "run"],
  ["sample_ids", "record"],
  ["ids", "record"],
];
/** bmw_evidence, public_imported_evidence and sales_evidence ids all open in the evidence explorer. */
const refType = (type: string) => (/(^|_)evidence$/.test(type) ? "evidence" : type);
export function toSourceRefs(value: unknown): SourceRef[] {
  const d = obj(value);
  const refs: SourceRef[] = [];
  const add = (type: string, id: unknown) => {
    const text = str(id);
    if (text) refs.push({ type, id: text });
  };
  const sourceIds = json(d.source_ids ?? d.sources);
  if (Array.isArray(sourceIds))
    for (const entry of sourceIds)
      if (isObj(entry)) add(str(entry.type) ?? str(entry.entity_type) ?? "record", entry.id);
      else add("record", entry);
  else for (const [type, ids] of Object.entries(obj(sourceIds))) for (const id of arr(ids)) add(refType(type.replace(/_ids?$|s$/, "")), id);
  for (const [key, type] of SOURCE_KEYS) for (const id of arr(d[key])) add(type, id);
  const seen = new Set<string>();
  return refs.filter((ref) => !seen.has(`${ref.type}:${ref.id}`) && !!seen.add(`${ref.type}:${ref.id}`));
}
const uniqueRefs = (refs: SourceRef[]) => {
  const seen = new Set<string>();
  return refs.filter((ref) => !seen.has(`${ref.type}:${ref.id}`) && !!seen.add(`${ref.type}:${ref.id}`));
};
export function toFactors(
  factorsRaw: unknown,
  weightsRaw?: unknown,
  detailsRaw?: unknown,
  contributionsRaw?: unknown,
  notMeasuredRaw?: unknown,
): FactorView[] {
  const list = arr(factorsRaw).filter(isObj);
  const map = obj(factorsRaw);
  const details = obj(detailsRaw);
  const values = numMap(factorsRaw);
  const weights = numMap(weightsRaw);
  const contributions = numMap(contributionsRaw);
  const notMeasured = new Set(strs(notMeasuredRaw));
  const names = list.length
    ? list.map((f) => str(f.factor) ?? str(f.name) ?? "factor")
    : unique([...Object.keys(map), ...Object.keys(details)]);
  return names.map((name, index) => {
    const entry = list.length ? list[index] : obj(map[name]);
    const d = { ...obj(details[name]), ...obj(entry.derivation), ...entry };
    const flags = unique([...strs(obj(details[name]).flags), ...strs(obj(entry.derivation).flags), ...strs(entry.flags)]);
    const note = str(d.note) ?? str(d.reason);
    return {
      name,
      value: values[name] ?? num(d.value),
      weight: weights[name] ?? num(d.weight),
      contribution: contributions[name] ?? num(d.contribution),
      notMeasured:
        notMeasured.has(name) || d.not_measured === true || d.measured === false || flags.includes("not_measured"),
      formula: str(d.formula),
      inputs: obj(d.inputs),
      sources: uniqueRefs([...toSourceRefs(d), ...toSourceRefs(d.inputs)]),
      notes: unique([...flags.filter((f) => f !== "not_measured"), ...strs(d.notes), ...(note ? [note] : []), ...(str(d.summary) ? [str(d.summary)!] : [])]),
      methodVersion: str(d.method_version),
      runId: str(d.run_id),
    };
  });
}

// Signals (Pod A) -------------------------------------------------------------------------------
export function toWatchlist(value: unknown): Watchlist {
  const o = obj(value);
  return {
    id: need(o, "id", "watchlist"),
    vehicle: str(o.vehicle) ?? "",
    market: str(o.market) ?? "",
    topic: str(o.topic) ?? "",
    label: str(o.label) ?? "Untitled watchlist",
    query_terms: strs(o.query_terms),
    competitors: strs(o.competitors),
    domain_group: (str(o.domain_group) ?? "all") as Watchlist["domain_group"],
    domains: strs(o.domains),
    cadence_days: num(o.cadence_days) ?? 7,
    max_results: num(o.max_results) ?? 10,
    status: str(o.status) === "paused" ? "paused" : "active",
    created_by: str(o.created_by) ?? "",
    rationale: str(o.rationale) ?? "",
    status_changed_by: str(o.status_changed_by),
    created_at: str(o.created_at) ?? "",
    updated_at: str(o.updated_at) ?? "",
    last_run_id: str(o.last_run_id),
  };
}
export function toSignalItem(value: unknown): SignalItem {
  const o = obj(value);
  const status = str(o.review_status);
  return {
    id: need(o, "id", "signal item"),
    watchlist_id: str(o.watchlist_id) ?? "",
    run_id: str(o.run_id) ?? "",
    vehicle: str(o.vehicle) ?? "",
    market: str(o.market) ?? "",
    topic: str(o.topic) ?? "",
    url: str(o.url) ?? "",
    domain: str(o.domain) ?? "",
    title: str(o.title),
    excerpt: str(o.excerpt) ?? "",
    published_at: str(o.published_at),
    retrieved_at: str(o.retrieved_at) ?? "",
    date_basis: str(o.date_basis) === "published" ? "published" : "retrieved",
    review_status: status === "imported" || status === "dismissed" ? status : "unreviewed",
    evidence_id: str(o.evidence_id),
    reviewed_by: str(o.reviewed_by),
    reviewed_at: str(o.reviewed_at),
  };
}
function toSentimentPoint(value: unknown, inherited: Json = {}): SentimentPoint | null {
  const p = { ...inherited, ...obj(value) };
  const week = str(p.week) ?? str(p.period);
  const sourceClass = str(p.source_class);
  if (!week || !sourceClass) return null;
  const n = num(p.n) ?? 0;
  return {
    week,
    sourceClass: sourceClass as SourceClass,
    methodVersion: str(p.method_version) ?? "unrecorded",
    n,
    meanPolarity: num(p.mean_polarity ?? p.mean),
    negativeShare: num(p.negative_share),
    positiveShare: num(p.positive_share),
    lowN: bool(p.low_n) ?? bool(p.lowN) ?? n < 5,
    undatedN: num(p.undated_n) ?? 0,
    subjectIds: strs(p.subject_ids ?? p.ids ?? p.sample_ids),
  };
}
/** GET /signals/sentiment/timeseries: `points`, `items`, `series[].points` or a bare array. */
export function toSentimentPoints(value: unknown): SentimentPoint[] {
  const o = obj(value);
  const pairs: [unknown, Json][] = Array.isArray(value)
    ? value.map((p) => [p, {}])
    : arr(o.points).length || arr(o.items).length
      ? arr(o.points).concat(arr(o.items)).map((p) => [p, {}])
      : arr(o.series).flatMap((s) => {
          const series = obj(s);
          const inherited = { source_class: series.source_class, method_version: series.method_version };
          return arr(series.points).map((p) => [p, inherited] as [unknown, Json]);
        });
  return pairs.map(([p, inherited]) => toSentimentPoint(p, inherited)).filter((p): p is SentimentPoint => !!p);
}
export const weekLabel = (week: string) => {
  const match = /^(\d{4})-W?(\d{1,2})$/.exec(week);
  return match ? `${match[1]} W${match[2].padStart(2, "0")}` : week;
};
/** One method version per chart: series never mix lexicon and model scores. */
export function toSentimentChart(points: SentimentPoint[], methodVersion?: string | null): SentimentChart {
  const counts = new Map<string, number>();
  for (const p of points) counts.set(p.methodVersion, (counts.get(p.methodVersion) || 0) + 1);
  const methodVersions = [...counts.keys()].sort((a, b) => counts.get(b)! - counts.get(a)! || a.localeCompare(b));
  const selected = methodVersion && counts.has(methodVersion) ? methodVersion : methodVersions[0] ?? null;
  const chosen = points.filter((p) => p.methodVersion === selected);
  const present = new Set(chosen.map((p) => p.sourceClass));
  const sourceClasses = [
    ...SOURCE_CLASSES.filter((c) => present.has(c)),
    ...[...present].filter((c) => !SOURCE_CLASSES.includes(c)).sort(),
  ];
  const lookup: Record<string, SentimentPoint> = {};
  for (const p of chosen) lookup[`${p.week}|${p.sourceClass}`] = p;
  const rows = unique(chosen.map((p) => p.week))
    .sort()
    .map((week) => {
      const row: SentimentChart["rows"][number] = { week, label: weekLabel(week) };
      for (const c of sourceClasses) row[c] = lookup[`${week}|${c}`]?.meanPolarity ?? null;
      return row;
    });
  return { methodVersion: selected, methodVersions, sourceClasses, rows, points: lookup };
}
/** GET /signals/summary: `items`, `topics`, a bare array, or a {topic: summary} map. */
export function toTopicSummaries(value: unknown): TopicSummary[] {
  const o = obj(value);
  const list = Array.isArray(value)
    ? value
    : arr(o.items).length
      ? arr(o.items)
      : arr(o.topics).length
        ? arr(o.topics)
        : Object.entries(obj(o.topics ?? (o.items === undefined ? o : {})))
            .filter(([, v]) => isObj(v))
            .map(([topic, v]) => ({ topic, ...obj(v) }));
  return list
    .map((v) => {
      const s = obj(v);
      const topic = str(s.topic);
      if (!topic) return null;
      const n = num(s.n) ?? 0;
      return {
        topic,
        sourceClass: (str(s.source_class) as SourceClass | null) ?? null,
        methodVersion: str(s.method_version),
        n,
        meanPolarity: num(s.mean_polarity ?? s.mean),
        momentum: num(s.momentum ?? s.momentum_8w ?? s.slope),
        lowN: bool(s.low_n) ?? n < 5,
        sampleIds: strs(s.sample_ids ?? s.subject_ids),
      };
    })
    .filter((s): s is TopicSummary => !!s);
}

// Markets (Pod B) – verified against codex/platform-markets-complete:server/markets.py -----------------
export function toMarketWeight(value: unknown): MarketWeight {
  const o = obj(value);
  return {
    vehicle: str(o.vehicle) ?? "",
    market: need(o, "market", "market weight"),
    period: str(o.period) ?? "",
    units: num(o.units),
    share: num(o.share),
    evidence_ids: strs(o.evidence_ids),
    method_version: str(o.method_version),
    run_id: str(o.run_id),
  };
}
/** GET /markets/weights: the recorded rows plus the selection compare/detect use and its warnings. */
export function toWeights(value: unknown): MarketWeights {
  const o = obj(value);
  const selected = obj(o.selected);
  return {
    ...toPage(value, toMarketWeight),
    selected: str(selected.period) ? { period: str(selected.period)!, methodVersion: str(selected.method_version) } : null,
    warnings: strs(o.warnings),
  };
}
function targetText(t: unknown) {
  if (typeof t === "string") return t;
  const x = obj(t);
  const target = str(first(x.target, x.text, x.value));
  if (!target) return JSON.stringify(t);
  return [str(x.metric), target, str(x.unit)].filter(Boolean).join(" ") + (str(x.basis) ? ` (${str(x.basis)})` : "");
}
function toCell(market: string, value: unknown): ComparisonCell {
  const c = obj(value);
  const evidence = obj(c.evidence);
  const sentiment = c.sentiment ?? c.bmw_sentiment;
  const s = obj(sentiment);
  const req = obj(c.requirement);
  const requirementId = str(req.id) ?? str(c.requirement_id);
  const pressure = c.request_pressure;
  const p = obj(pressure);
  const missing: Record<string, string> = {};
  for (const [key, reason] of Object.entries(obj(c.missing ?? c.reasons))) {
    const text = str(reason);
    if (text) missing[key] = text;
  }
  for (const [key, reason] of Object.entries(c))
    if (key.endsWith("_reason") && str(reason)) missing[key.slice(0, -7)] = str(reason)!;
  return {
    market,
    evidenceCount: num(first(c.evidence_count, evidence.count, c.evidence_n)),
    evidenceGrade: str(first(c.evidence_grade, evidence.grade)),
    evidenceIds: strs(first(evidence.evidence_ids, c.evidence_ids)),
    findingIds: strs(first(evidence.finding_ids, c.finding_ids)),
    sentiment: num(isObj(sentiment) ? first(s.mean_polarity, s.mean) : sentiment),
    sentimentN: num(s.n),
    sentimentLowN: bool(s.low_n) ?? false,
    requirement: requirementId
      ? {
          id: requirementId,
          key: str(first(req.key, c.requirement_key)),
          title: str(first(req.title, c.requirement_title)),
          status: str(first(req.status, c.requirement_status)),
          score: num(first(c.score, req.score, req.priority, req.total, c.priority)),
          rank: num(first(c.rank, req.rank)),
          rankOf: num(c.rank_of),
        }
      : null,
    targets: arr(c.targets).map(targetText),
    requestPressure: num(isObj(pressure) ? first(p.count, p.value, p.index) : pressure),
    requestMeanTriage: num(p.mean_triage),
    requestIds: strs(p.request_ids),
    missing,
  };
}
/**
 * POST /markets/compare: `markets[]` (basis, share, weight) and `topics[]` with `cells` keyed by market
 * (verified); flat `cells|matrix` rows and a topic→market map are tolerated.
 */
export function toComparison(value: unknown, vehicle: string): MarketComparison {
  const o = obj(value);
  const rows = new Map<string, ComparisonRow>();
  const row = (topic: string, entry: Json = {}) => {
    if (!rows.has(topic))
      rows.set(topic, {
        topic,
        label: str(entry.label),
        demandIndex: num(entry.demand_index),
        demandCoverage: num(entry.demand_coverage),
        alignment: str(entry.alignment),
        recommendation: str(entry.recommendation),
        cells: {},
      });
    return rows.get(topic)!;
  };
  const put = (topic: unknown, market: unknown, cell: unknown, entry?: Json) => {
    const t = str(topic);
    const m = str(market);
    if (!t || !m) return;
    row(t, entry).cells[m] = toCell(m, cell);
  };
  const flat = arr(o.cells).length ? arr(o.cells) : arr(o.matrix);
  if (arr(o.topics).length)
    for (const item of arr(o.topics)) {
      const t = obj(item);
      if (str(t.topic)) row(str(t.topic)!, t);
      const cells = json(t.cells ?? t.markets);
      if (Array.isArray(cells)) for (const c of cells) put(t.topic, obj(c).market, c, t);
      else for (const [m, c] of Object.entries(obj(cells))) put(t.topic, m, c, t);
    }
  else if (flat.length) for (const c of flat) put(obj(c).topic, obj(c).market, c);
  else for (const [t, markets] of Object.entries(obj(o.matrix))) for (const [m, c] of Object.entries(obj(markets))) put(t, m, c);
  const weights = obj(o.weights);
  const weightMap = numMap(weights);
  const basis = str(weights.basis);
  const period = str(weights.period);
  const listed = arr(o.markets).map((m) => {
    const entry = isObj(m) ? m : { market: m };
    const market = str(entry.market) ?? "";
    const entryBasis = str(first(entry.basis, entry.weight_basis, entry.weight_source));
    return {
      market,
      name: str(entry.name),
      share: num(entry.share),
      weight: num(entry.weight) ?? weightMap[market] ?? null,
      units: num(entry.units),
      equalWeight: entry.equal_weight === true || entryBasis === "equal" || entryBasis === "equal_fallback",
      period: str(entry.period) ?? period,
    };
  });
  const cellMarkets = unique([...rows.values()].flatMap((r) => Object.keys(r.cells))).sort();
  const markets = listed.filter((m) => m.market).length
    ? listed.filter((m) => m.market)
    : unique([...Object.keys(weightMap), ...cellMarkets]).map((market) => ({
        market,
        name: null,
        share: null,
        weight: weightMap[market] ?? null,
        units: null,
        equalWeight: false,
        period: null,
      }));
  return {
    vehicle: str(o.vehicle) ?? vehicle,
    methodVersion: str(o.method_version),
    runId: str(o.run_id),
    weightBasis: basis,
    weightsMethodVersion: str(weights.method_version),
    sentimentMethodVersion: str(o.sentiment_method_version),
    markets,
    rows: [...rows.values()].filter((r) => Object.keys(r.cells).length).sort((a, b) => a.topic.localeCompare(b.topic)),
    warnings: strs(o.warnings),
  };
}
/** metrics.ai_brief (markets.draft_conflict_brief): summary, trade-off, options, open questions, grounded citations. */
function toAiBrief(value: unknown, conflict: Json): AiBrief | null {
  if (value === undefined || value === null) return null;
  const b = obj(value);
  const summary = typeof value === "string" ? value : str(first(b.summary, b.text, b.brief, b.explanation));
  if (!summary) return null;
  return {
    summary,
    tradeOff: str(b.trade_off),
    options: arr(b.options).map((o) => {
      const x = obj(o);
      return typeof o === "string"
        ? { option: o, summary: "", benefits: [], risks: [] }
        : { option: str(first(x.option, x.label)) ?? "option", summary: str(first(x.summary, x.text)) ?? "", benefits: strs(x.benefits), risks: strs(x.risks) };
    }),
    openQuestions: strs(b.open_questions),
    citations: arr(b.citations)
      .map((c) => obj(c))
      .filter((c) => str(c.evidence_id))
      .map((c) => ({ evidenceId: str(c.evidence_id)!, quote: str(c.quote) ?? "", market: str(c.market) })),
    label: str(b.label),
    provenance: provenance({ run_id: conflict.ai_brief_run_id, ...b }, null, true),
  };
}
export function toConflict(value: unknown): MarketConflict {
  const o = obj(value);
  const metrics = obj(o.metrics);
  const evidence = json(o.evidence_ids);
  return {
    id: need(o, "id", "market conflict"),
    vehicle: str(o.vehicle) ?? "",
    topic: str(o.topic) ?? "",
    related_topic: str(o.related_topic),
    markets: strs(o.markets),
    conflict_type: str(o.conflict_type) ?? "",
    severity: str(o.severity) ?? "",
    metrics,
    evidence_ids: Array.isArray(evidence)
      ? { all: strs(evidence) }
      : Object.fromEntries(Object.entries(obj(evidence)).map(([m, ids]) => [m, strs(ids)])),
    requirement_ids: strs(o.requirement_ids),
    recommendation: str(o.recommendation) ?? "",
    rationale: str(o.rationale) ?? "",
    method_version: str(o.method_version) ?? "",
    run_id: str(o.run_id) ?? "",
    status: str(o.status) ?? "open",
    created_at: str(o.created_at) ?? "",
    aiBrief: toAiBrief(first(metrics.ai_brief, o.ai_brief), metrics),
    latestResolution: isObj(o.latest_resolution) ? toResolution(o.latest_resolution, str(o.id) ?? "") : null,
  };
}
function toSnippet(value: unknown, market: string | null): EvidenceSnippet | null {
  if (typeof value === "string")
    return { id: value, market, content: null, quote: null, sourceId: null, sourceTitle: null, observedAt: null, mentions: [] };
  const e = obj(value);
  const id = str(first(e.id, e.evidence_id));
  if (!id) return null;
  return {
    id,
    market: str(e.market) ?? market,
    content: str(first(e.content, e.excerpt, e.text)),
    quote: str(first(e.quote, e.span_text)),
    sourceId: str(e.source_id),
    sourceTitle: str(e.source_title),
    observedAt: str(e.observed_at),
    mentions: arr(e.mentions)
      .map((m) => obj(m))
      .filter((m) => str(m.quote))
      .map((m) => ({ attribute: str(m.attribute) ?? "", direction: str(m.direction) ?? "", quote: str(m.quote)! })),
  };
}
function toResolution(r: unknown, conflictId: string): MarketResolution {
  const x = obj(r);
  return {
    id: str(x.id) ?? "",
    conflict_id: str(x.conflict_id) ?? conflictId,
    decision: str(x.decision) ?? "",
    actor: str(x.actor) ?? "",
    rationale: str(x.rationale) ?? "",
    requirement_ids: strs(x.requirement_ids),
    created_at: str(x.created_at) ?? "",
  };
}
/** GET /markets/conflicts/{id}: conflict fields plus `evidence` {market: [...]}, requirements, resolutions, history. */
export function toConflictDetail(value: unknown): ConflictDetail {
  const o = obj(value);
  const conflict = toConflict(isObj(o.conflict) ? o.conflict : o);
  const evidenceByMarket: Record<string, EvidenceSnippet[]> = {};
  const add = (market: string | null, item: unknown) => {
    const snippet = toSnippet(item, market);
    if (!snippet) return;
    const key = market ?? snippet.market ?? "unscoped";
    (evidenceByMarket[key] ||= []).push(snippet);
  };
  const evidence = json(first(o.evidence_by_market, o.evidence_per_market, o.evidence));
  if (Array.isArray(evidence)) for (const item of evidence) add(null, item);
  else for (const [market, items] of Object.entries(obj(evidence))) for (const item of arr(items)) add(market, item);
  if (!Object.keys(evidenceByMarket).length)
    for (const [market, ids] of Object.entries(conflict.evidence_ids)) for (const id of ids) add(market, id);
  return {
    conflict,
    evidenceByMarket,
    requirements: arr(o.requirements)
      .map((r) => obj(r))
      .filter((r) => str(r.id))
      .map((r) => ({
        id: str(r.id)!,
        key: str(r.key),
        market: str(r.market),
        topic: str(r.topic),
        status: str(r.status),
        title: str(r.title),
        score: num(first(r.score_total, r.score)),
        evidenceGrade: str(r.evidence_grade),
      })),
    resolutions: arr(o.resolutions).map((r) => toResolution(r, conflict.id)),
    history: arr(o.history)
      .map((h) => obj(h))
      .filter((h) => str(h.id))
      .map((h) => ({ id: str(h.id)!, status: str(h.status) ?? "", runId: str(h.run_id), createdAt: str(h.created_at) ?? "" })),
    supersededBy: str(o.superseded_by),
  };
}

// Requests (Pod C) – verified against codex/platform-intake-complete:server/intake.py ------------------
/** request-triage-v1 flags name unmeasured factors: `<factor>_not_measured`, and `effort_unknown`. */
const unmeasured = (flags: string[]) =>
  flags.flatMap((flag) => (flag === "effort_unknown" ? ["effort"] : flag.endsWith("_not_measured") ? [flag.slice(0, -13)] : []));
/**
 * A triage record: the list summary (`factors` values, `flags`, `suggested_action`) or a full
 * request_triage row whose `explanation.factors` carries value, measured, formula, inputs, weight and
 * contribution per factor, plus `explanation.scope` (flags, reasons, cap).
 */
export function toTriage(value: unknown): Triage | null {
  if (value === undefined || value === null) return null;
  const o = obj(value);
  const explanation = obj(o.explanation);
  const flags = unique([...strs(o.flags), ...strs(explanation.flags)]);
  const scope = obj(explanation.scope);
  const capRaw = first(explanation.cap, explanation.capped, explanation.scope_cap, o.cap_reason, o.cap);
  const scopeCap = num(scope.cap);
  const cap =
    scopeCap !== null
      ? `Capped at ${scopeCap} from ${fixedNumber(num(scope.capped_from))}: ${strs(scope.reasons).join(" ") || "out-of-scope flags"}`
      : isObj(capRaw)
        ? str(first(capRaw.reason, capRaw.text))
        : typeof capRaw === "boolean"
          ? null
          : str(capRaw);
  const suggested = obj(first(o.suggested_action, explanation.suggested_action));
  return {
    id: str(o.id),
    rubricVersion: str(o.rubric_version),
    total: num(first(o.total, o.score)),
    factors: toFactors(
      o.factors,
      o.weights,
      isObj(explanation.factors) ? explanation.factors : explanation,
      o.contributions,
      unmeasured(flags),
    ).map((f) => ({ ...f, notes: f.notes.filter((note) => !note.endsWith("_not_measured") && note !== "effort_unknown") })),
    flags,
    suggestedAction: str(suggested.decision) ? { decision: str(suggested.decision)!, reason: str(suggested.reason) ?? "" } : null,
    formula: str(explanation.formula),
    cap,
    runId: str(o.run_id),
    createdAt: str(o.created_at),
  };
}
const fixedNumber = (value: number | null) => (value === null ? "–" : String(Math.round(value * 100) / 100));
export function toRequest(value: unknown): IntakeRequest {
  const o = obj(value);
  const cluster = obj(o.cluster);
  const triage = first(o.triage, o.latest_triage);
  return {
    id: need(o, "id", "request"),
    key: str(o.key) ?? "",
    vehicle: str(o.vehicle) ?? "",
    market: str(o.market) ?? "",
    origin_type: str(o.origin_type) ?? "other",
    origin_name: str(o.origin_name) ?? "",
    title: str(o.title) ?? "Untitled request",
    body: str(o.body) ?? "",
    topic: str(o.topic),
    attribute: str(o.attribute),
    effort: str(o.effort),
    requested_at: str(o.requested_at) ?? "",
    simulated: o.simulated === true || o.simulated === 1,
    scope_flags: strs(o.scope_flags),
    status: str(o.status) ?? "new",
    cluster_id: str(first(o.cluster_id, cluster.id)),
    clusterTitle: str(first(o.cluster_title, cluster.canonical_title)),
    clusterSize: num(cluster.size),
    ageDays: num(o.age_days),
    slaBreach: o.sla_breach === true,
    pmPinned: strs(o.pm_pinned),
    created_by: str(o.created_by) ?? "",
    created_at: str(o.created_at) ?? "",
    triage:
      triage === undefined
        ? num(o.triage_total) === null
          ? null
          : { id: null, rubricVersion: null, total: num(o.triage_total), factors: [], flags: [], suggestedAction: null, formula: null, cap: null, runId: null, createdAt: null }
        : toTriage(triage),
  };
}
/** Deterministic display order: triage score (untriaged last), then oldest request, then key. */
export function sortByTriage(requests: IntakeRequest[]): IntakeRequest[] {
  return [...requests].sort(
    (a, b) =>
      (b.triage?.total ?? -Infinity) - (a.triage?.total ?? -Infinity) ||
      a.requested_at.localeCompare(b.requested_at) ||
      a.key.localeCompare(b.key),
  );
}
/** GET /requests/clusters items: {id, canonical_title, topic, method_version, size, markets, members}. */
export function toCluster(value: unknown): RequestCluster {
  const o = obj(value);
  const members = arr(o.members).map((m) => {
    const x = obj(m);
    return { id: str(x.id) ?? "", key: str(x.key) ?? "", market: str(x.market) ?? "", title: str(x.title) ?? "", status: str(x.status) ?? "" };
  });
  return {
    id: need(o, "id", "request cluster"),
    title: str(first(o.canonical_title, o.title)) ?? `Cluster ${(str(o.id) ?? "").slice(0, 8)}`,
    topic: str(o.topic),
    methodVersion: str(o.method_version),
    markets: strs(o.markets).length ? strs(o.markets) : unique(members.map((m) => m.market)).sort(),
    members,
  };
}
/** Fallback when GET /requests/clusters is absent: groups the loaded requests by cluster_id. */
export function clusterRequests(requests: IntakeRequest[]): RequestCluster[] {
  const groups = new Map<string, IntakeRequest[]>();
  for (const r of requests) if (r.cluster_id) groups.set(r.cluster_id, [...(groups.get(r.cluster_id) || []), r]);
  return [...groups.entries()]
    .map(([id, members]) => {
      const topics = members.map((m) => m.topic).filter((t): t is string => !!t);
      const topic = topics.sort((a, b) => topics.filter((t) => t === b).length - topics.filter((t) => t === a).length)[0] ?? null;
      return {
        id,
        title: members.find((m) => m.clusterTitle)?.clusterTitle ?? `Cluster ${id.slice(0, 8)}`,
        topic,
        methodVersion: null,
        markets: unique(members.map((m) => m.market)).sort(),
        members: sortByTriage(members).map((m) => ({ id: m.id, key: m.key, market: m.market, title: m.title, status: m.status })),
      };
    })
    .sort((a, b) => b.members.length - a.members.length || a.title.localeCompare(b.title));
}
function toLink(value: unknown): RequestLink {
  const o = obj(value);
  const entity = obj(o.entity);
  const basis = obj(o.basis);
  const createdBy = str(o.created_by) ?? "";
  return {
    id: str(o.id) ?? `${str(o.entity_type)}:${str(o.entity_id)}`,
    entity_type: str(o.entity_type) ?? "record",
    entity_id: str(o.entity_id) ?? "",
    relation: str(o.relation) ?? "supports",
    status: str(o.status) ?? "active",
    created_by: createdBy,
    created_at: str(o.created_at) ?? "",
    summary: str(first(entity.summary, entity.title, entity.content, entity.key, o.summary)),
    market: str(first(entity.market, o.market)),
    quote: str(first(o.quote, o.span_text, basis.quote, entity.quote)),
    methodVersion: str(basis.method_version),
    rationale: str(basis.rationale),
    aiGenerated: o.ai_generated === true || createdBy.toLowerCase().startsWith("ai:"),
  };
}
function toPoints(value: unknown): PositionPoint[] {
  return arr(value).map((v) => {
    if (typeof v === "string") return { text: v, evidenceId: null, quote: null };
    const x = obj(v);
    return {
      text: str(first(x.point, x.text)) ?? JSON.stringify(v),
      evidenceId: str(first(x.evidence_id, strs(x.evidence_ids)[0])),
      quote: str(x.quote),
    };
  });
}
/** A position draft message: `positions[]` (thread messages; the latest wins) or a `position` object. */
function toPosition(value: unknown): PositionDraft | null {
  if (value === undefined || value === null) return null;
  const outer = obj(value);
  const o = { ...outer, ...obj(outer.payload) };
  const caseFor = toPoints(first(o.case_for, o.for, o.supporting));
  const caseAgainst = toPoints(first(o.case_against, o.against, o.conflicting));
  const openQuestions = arr(first(o.open_questions, o.questions)).map((q) => str(q) ?? str(obj(q).text) ?? JSON.stringify(q));
  if (!caseFor.length && !caseAgainst.length && !openQuestions.length) return null;
  const cited = [...caseFor, ...caseAgainst].map((p) => p.evidenceId).filter((id): id is string => !!id);
  const generated = o.ai_generated === false ? false : o.ai_generated === true || parseMethodVersion(str(o.method_version)).provider !== "deterministic";
  return {
    summary: str(o.summary),
    caseFor,
    caseAgainst,
    openQuestions,
    citedIds: unique([...cited, ...strs(o.cited_ids), ...strs(o.cited_evidence_ids)]),
    label: str(o.label),
    createdAt: str(first(outer.created_at, o.created_at)),
    provenance: { ...provenance({ ...o, run_id: first(o.run_id, outer.run_id) }), generated, ...(generated ? {} : { provider: "deterministic" }) },
  };
}
/** GET /requests/{id}: summary fields plus links, decisions, triage_history (newest first) and positions. */
export function toRequestDetail(value: unknown): RequestDetail {
  const o = obj(value);
  const request = toRequest(isObj(o.request) ? o.request : o);
  const triageHistory = arr(first(o.triage_history, o.triages)).map(toTriage).filter((t): t is Triage => !!t);
  const full = triageHistory.find((t) => t.id && t.id === request.triage?.id) ?? (request.triage ? null : triageHistory[0]);
  const positions = arr(o.positions).filter((m) => obj(obj(m).payload).kind === undefined || obj(obj(m).payload).kind === "request_position");
  return {
    request: full ? { ...request, triage: { ...full, suggestedAction: full.suggestedAction ?? request.triage?.suggestedAction ?? null } } : request,
    links: arr(o.links).map(toLink),
    decisions: arr(o.decisions).map((d): RequestDecision => {
      const x = obj(d);
      return {
        id: str(x.id) ?? "",
        decision: str(x.decision) ?? "",
        actor: str(x.actor) ?? "",
        rationale: str(x.rationale) ?? "",
        requirement_id: str(x.requirement_id),
        created_at: str(x.created_at) ?? "",
      };
    }),
    triageHistory,
    position: toPosition(first(o.position, o.position_draft, positions.at(-1))),
    positionCount: positions.length,
  };
}
function countMap(value: unknown, rows: unknown[], key: string): Record<string, number> {
  const direct = numMap(value);
  if (Object.keys(direct).length || !rows.length) return direct;
  const out: Record<string, number> = {};
  for (const row of rows) {
    const r = obj(row);
    const name = str(r[key]);
    if (name) out[name] = (out[name] || 0) + (num(first(r.count, r.n)) ?? 0);
  }
  return out;
}
/** GET /requests/aggregates: `by_*` maps (or count rows), demand index list, aging, SLA breaches, weights basis. */
export function toAggregates(value: unknown): RequestAggregates {
  const o = obj(value);
  const rows = arr(first(o.counts, o.rows));
  const demand = json(o.demand_index);
  const sla = json(o.sla_breaches);
  const aging = obj(o.aging);
  const weights = obj(o.market_weights);
  return {
    total: num(o.total),
    byMarket: countMap(o.by_market, rows, "market"),
    byTopic: countMap(o.by_topic, rows, "topic"),
    byStatus: countMap(o.by_status, rows, "status"),
    byOrigin: countMap(o.by_origin, rows, "origin_type"),
    demandIndex: Array.isArray(demand)
      ? Object.fromEntries(
          demand
            .map((d) => [str(obj(d).topic), num(first(obj(d).index, obj(d).value))] as const)
            .filter((d): d is [string, number] => !!d[0] && d[1] !== null),
        )
      : numMap(demand),
    demandMethod: str(o.demand_index_method),
    weightsMeasured: bool(weights.measured),
    medianAgeDays: num(first(o.median_age_days, aging.median_days, aging.median_age_days)),
    slaDays: num(o.sla_days),
    slaBreaches: num(o.sla_breach_count) ?? (Array.isArray(sla) ? sla.length : num(first(sla, obj(sla).count))),
    simulatedCount: num(o.simulated_count),
    methodVersion: str(o.method_version),
  };
}

// Priorities (Pod D) – ASSUMED: §5.3 plus the in-progress Pod D branch (not merged, not verified) ---------
function toScopeRubric(value: unknown): ScopeRubric | null {
  if (!isObj(json(value))) return null;
  const o = obj(value);
  const version = str(o.rubric_version);
  if (!version) return null;
  return {
    id: str(o.id) ?? "",
    vehicle: str(o.vehicle) ?? "",
    market: str(o.market) ?? "",
    rubric_version: version,
    weights: numMap(o.weights),
    actor: str(o.actor) ?? "",
    rationale: str(o.rationale) ?? "",
    created_at: str(o.created_at) ?? "",
    isDefault: o.default === true || (!str(o.id) && !str(o.actor)),
  };
}
/** GET /priorities/rubrics: definitions (`items|rubrics|available` or a bare array) + the scope's active rubric + history. */
export function toRubricState(value: unknown): RubricState {
  const o = obj(value);
  const definitions = Array.isArray(value) ? value : arr(first(o.items, o.rubrics, o.available));
  return {
    available: definitions
      .map((r) => {
        const x = obj(r);
        const version = str(first(x.version, x.rubric_version, x.id));
        return version
          ? {
              version,
              weights: numMap(first(x.default_weights, x.weights)),
              description: str(first(x.description, x.label)),
              formula: str(x.formula),
              derived: Object.entries(obj(x.derived_factors)).map(([factor, d]) => ({
                factor,
                methodVersion: str(obj(d).method_version),
                formula: str(obj(d).formula),
              })),
            }
          : null;
      })
      .filter((r): r is RubricState["available"][number] => !!r),
    current: toScopeRubric(first(o.current, o.active, o.scope)),
    history: arr(o.history).map(toScopeRubric).filter((r): r is ScopeRubric => !!r),
  };
}
function toStability(value: unknown): Stability | null {
  const s = obj(value);
  const result = {
    rank: num(s.rank),
    minRank: num(s.min_rank),
    maxRank: num(s.max_rank),
    stable: bool(s.stable),
  };
  if (Object.values(result).every((v) => v === null)) {
    const reason = str(s.reason);
    return reason ? { ...result, current: false, reason } : null;
  }
  return { ...result, current: s.current === false ? false : true, reason: str(s.reason) };
}
function toRankingRow(value: unknown): RankingRow {
  const r = obj(value);
  const explanation = obj(r.explanation);
  const ai = isObj(r.ai_explanation)
    ? r.ai_explanation
    : typeof r.ai_explanation === "string"
      ? { text: r.ai_explanation }
      : str(explanation.text) && (str(explanation.provider) || str(explanation.model))
        ? explanation
        : null;
  const preview = obj(r.v2_preview);
  return {
    requirementId: need(r, str(r.requirement_id) ? "requirement_id" : "id", "ranking row"),
    key: str(r.key),
    title: str(r.title) ?? "Untitled requirement",
    topic: str(r.topic),
    status: str(r.status),
    versionId: str(r.version_id),
    scoreId: str(r.score_id),
    rubricVersion: str(r.rubric_version),
    total: num(first(r.total, isObj(r.score) ? r.score.total : r.score)),
    rank: num(r.rank),
    evidenceGrade: str(r.evidence_grade),
    needsReview: r.needs_review === true,
    v2PreviewTotal: num(preview.total),
    factors: toFactors(
      r.factors,
      r.weights,
      first(r.derivations, isObj(explanation.derivations) ? explanation.derivations : undefined, r.inputs),
      first(r.contributions, explanation.contributions),
      r.not_measured,
    ),
    preserveWarnings: arr(first(r.preserve_warnings, r.preserve)).map((w): PreserveWarning => {
      if (typeof w === "string") return { label: "", message: w, evidenceIds: [] };
      const x = obj(w);
      return {
        label: str(first(x.label, x.attribute, x.topic)) ?? "",
        message: str(first(x.message, x.warning, x.text)) ?? "",
        evidenceIds: strs(x.evidence_ids),
      };
    }),
    stability: toStability(first(r.stability, r.sensitivity)),
    explanation: ai ? { text: str(first(obj(ai).text, obj(ai).explanation)) ?? "", citedIds: strs(obj(ai).cited_ids), provenance: provenance(ai, null, true) } : null,
  };
}
/** GET /priorities/ranking: `items|ranking|requirements` (or a bare array) with per-row factors. */
export function toRanking(value: unknown, scope: Scope): Ranking {
  const o = obj(value);
  const rows = (Array.isArray(value) ? value : arr(first(o.items, o.ranking, o.requirements))).map(toRankingRow);
  return {
    vehicle: str(o.vehicle) ?? scope.vehicle,
    market: str(o.market) ?? scope.market,
    rubricVersion: str(first(o.rubric_version, obj(o.rubric).rubric_version)),
    methodVersion: str(o.method_version),
    runId: str(o.run_id),
    rows: [...rows].sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity) || (b.total ?? -Infinity) - (a.total ?? -Infinity)),
    warnings: strs(o.warnings),
  };
}
/** POST /priorities/sensitivity → {results: {requirement_id: {rank, min_rank, max_rank, stable}}}. */
export function mergeSensitivity(rows: RankingRow[], value: unknown): RankingRow[] {
  const o = obj(value);
  const results = obj(first(o.results, isObj(o.items) ? o.items : undefined, o));
  return rows.map((row) => {
    const stability = toStability(results[row.requirementId]);
    return stability ? { ...row, stability } : row;
  });
}
/**
 * POST /priorities/explain → {summary, items: [{requirement_id, explanation, cited_ids}], provider, model,
 * method_version, prompt_version, ai_generated, run_id}. OpenAI or the labelled deterministic template.
 */
export function toExplanation(value: unknown): RankingExplanation {
  const o = obj(value);
  const generated = o.ai_generated === false ? false : o.ai_generated === true || parseMethodVersion(str(o.method_version)).provider === "openai";
  const base = provenance(o);
  const prov: Provenance = { ...base, generated, provider: generated ? base.provider ?? "openai" : "deterministic" };
  const items: RankingExplanation["items"] = {};
  for (const entry of arr(o.items)) {
    const x = obj(entry);
    const id = str(x.requirement_id);
    const text = str(first(x.explanation, x.text));
    if (id && text) items[id] = { text, citedIds: strs(x.cited_ids), provenance: prov };
  }
  return { summary: str(o.summary), provenance: prov, items };
}
export function mergeExplanation(rows: RankingRow[], explanation: RankingExplanation | undefined): RankingRow[] {
  if (!explanation) return rows;
  return rows.map((row) => (explanation.items[row.requirementId] ? { ...row, explanation: explanation.items[row.requirementId] } : row));
}

// Runs (Pod F) ----------------------------------------------------------------------------------
export function toRun(value: unknown): Run {
  const o = obj(value);
  const metrics = obj(o.metrics);
  const llm = obj(metrics.llm);
  const usage: LlmUsage | null = Object.keys(llm).length
    ? {
        calls: num(llm.calls) ?? 0,
        cacheHits: num(llm.cache_hits) ?? 0,
        inputTokens: num(llm.input_tokens) ?? 0,
        outputTokens: num(llm.output_tokens) ?? 0,
        totalTokens: num(llm.total_tokens) ?? 0,
        models: strs(llm.models),
      }
    : null;
  const methodVersion = str(o.method_version) ?? "";
  const base = provenance({ method_version: methodVersion, run_id: o.id });
  const modelCalled = !!usage && usage.calls > 0;
  return {
    id: need(o, "id", "run"),
    capability: str(o.capability) ?? "",
    task_id: str(o.task_id),
    actor: str(o.actor) ?? "",
    vehicle: str(o.vehicle),
    market: str(o.market),
    method_version: methodVersion,
    input_hash: str(o.input_hash) ?? "",
    inputs: obj(o.inputs),
    outputs: o.outputs === null || o.outputs === undefined ? null : obj(o.outputs),
    metrics,
    status: str(o.status) ?? "running",
    error: str(o.error),
    started_at: str(o.started_at) ?? "",
    finished_at: str(o.finished_at),
    provenance: modelCalled
      ? { ...base, generated: true, provider: "openai", model: base.model ?? usage!.models[0] ?? null }
      : base,
    usage,
    durationMs: num(metrics.duration_ms),
  };
}
export function usageByCapability(runs: Run[]): CapabilityUsage[] {
  const groups = new Map<string, CapabilityUsage>();
  for (const run of runs) {
    const g = groups.get(run.capability) ?? { capability: run.capability, runs: 0, failed: 0, calls: 0, cacheHits: 0, totalTokens: 0, models: [] };
    g.runs += 1;
    if (run.status === "failed") g.failed += 1;
    if (run.usage) {
      g.calls += run.usage.calls;
      g.cacheHits += run.usage.cacheHits;
      g.totalTokens += run.usage.totalTokens;
      g.models = unique([...g.models, ...run.usage.models]);
    }
    groups.set(run.capability, g);
  }
  return [...groups.values()].sort((a, b) => b.totalTokens - a.totalTokens || a.capability.localeCompare(b.capability));
}

// Client ----------------------------------------------------------------------------------------
const enc = encodeURIComponent;
export function params(values: Record<string, string | number | null | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(values))
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  return search.toString();
}
/** Reads every page (100 per request, the smallest common cap) up to `cap` records; totals stay visible. */
export async function collect<T>(path: string, item: (v: unknown) => T, signal?: AbortSignal, cap = 1000): Promise<ListPage<T>> {
  const items: T[] = [];
  let total = 0;
  for (;;) {
    const page = toPage(
      await api<unknown>(`${path}${path.includes("?") ? "&" : "?"}limit=100&offset=${items.length}`, { signal }),
      item,
    );
    items.push(...page.items);
    total = page.total;
    if (!page.items.length || items.length >= total || items.length >= cap) break;
  }
  return { items, total, limit: items.length, offset: 0 };
}
type Actor = { actor: string };
type Gate = Actor & { rationale: string };
const raw = (value: unknown) => obj(value);
export const platform = {
  watchlists: (scope: Scope, signal?: AbortSignal) =>
    collect(`/signals/watchlists?${params(scope)}`, toWatchlist, signal),
  createWatchlist: (input: WatchlistInput) =>
    write<unknown>("/signals/watchlists", input).then((v) => toWrite(v, toWatchlist)),
  setWatchlistStatus: (id: string, body: Gate & { status: "active" | "paused" }) =>
    write<unknown>(`/signals/watchlists/${enc(id)}`, body, "PATCH").then((v) => toWrite(v, toWatchlist)),
  refreshWatchlist: (id: string, body: Actor) => write<unknown>(`/signals/watchlists/${enc(id)}/refresh`, body).then(raw),
  backfillWatchlist: (id: string, body: Actor & { weeks: number }) =>
    write<unknown>(`/signals/watchlists/${enc(id)}/backfill`, body).then(raw),
  signalItems: (scope: Scope, filters: { topic?: string; review_status?: string }, signal?: AbortSignal) =>
    collect(`/signals/items?${params({ ...scope, ...filters })}`, toSignalItem, signal, 300),
  importItem: (id: string, body: Gate) =>
    write<unknown>(`/signals/items/${enc(id)}/import`, body).then((v) => toWrite(v, toSignalItem)),
  dismissItem: (id: string, body: Gate) =>
    write<unknown>(`/signals/items/${enc(id)}/dismiss`, body).then((v) => toWrite(v, toSignalItem)),
  scoreSentiment: (scope: Scope, body: Actor & { provider: Provider }) =>
    write<unknown>("/signals/sentiment/score", { ...scope, ...body }).then(raw),
  timeseries: (scope: Scope, topic: string, signal?: AbortSignal) =>
    api<unknown>(`/signals/sentiment/timeseries?${params({ ...scope, topic })}`, { signal }).then(toSentimentPoints),
  summary: (scope: Scope, signal?: AbortSignal) =>
    api<unknown>(`/signals/summary?${params(scope)}`, { signal }).then(toTopicSummaries),
  compare: (vehicle: string, actor?: string) =>
    write<unknown>("/markets/compare", actor ? { vehicle, actor } : { vehicle }).then((v) => toComparison(v, vehicle)),
  detectConflicts: (vehicle: string, body: Actor & { provider: Provider }) =>
    write<unknown>("/markets/conflicts/detect", { vehicle, ...body }).then(raw),
  conflicts: (vehicle: string, status: string, signal?: AbortSignal) =>
    collect(`/markets/conflicts?${params({ vehicle, status })}`, toConflict, signal),
  conflict: (id: string, signal?: AbortSignal) =>
    api<unknown>(`/markets/conflicts/${enc(id)}`, { signal }).then(toConflictDetail),
  resolveConflict: (id: string, body: Gate & { decision: string; requirement_ids: string[] }) =>
    write<unknown>(`/markets/conflicts/${enc(id)}/resolve`, body).then(raw),
  draftBrief: (id: string, body: Actor) =>
    write<unknown>(`/markets/conflicts/${enc(id)}/brief`, { ...body, provider: "openai" }).then(raw),
  weights: (vehicle: string, signal?: AbortSignal) =>
    api<unknown>(`/markets/weights?${params({ vehicle, limit: 200 })}`, { signal }).then(toWeights),
  requests: (vehicle: string, filters: { market?: string; status?: string }, signal?: AbortSignal) =>
    collect(`/requests?${params({ vehicle, ...filters, sort: "triage" })}`, toRequest, signal),
  request: (id: string, actor: string | undefined, signal?: AbortSignal) =>
    api<unknown>(`/requests/${enc(id)}?${params({ actor })}`, { signal }).then(toRequestDetail),
  editRequest: (id: string, body: Gate & { topic?: string; effort?: string | null }) =>
    write<unknown>(`/requests/${enc(id)}`, body, "PATCH").then((v) => toWrite(v, toRequest)),
  clusters: (vehicle: string, market?: string, signal?: AbortSignal) =>
    collect(`/requests/clusters?${params({ vehicle, market })}`, toCluster, signal),
  aggregates: (vehicle: string, market?: string, signal?: AbortSignal) =>
    api<unknown>(`/requests/aggregates?${params({ vehicle, market })}`, { signal }).then(toAggregates),
  classify: (vehicle: string, body: Actor & { market?: string; provider: Provider }) =>
    write<unknown>("/requests/classify", { vehicle, ...body }).then(raw),
  triage: (vehicle: string, body: Actor & { market?: string; link_provider: Provider | "none" }) =>
    write<unknown>("/requests/triage", { vehicle, ...body }).then(raw),
  cluster: (vehicle: string, body: Actor & { provider: Provider }) =>
    write<unknown>("/requests/cluster", { vehicle, ...body }).then(raw),
  proposeLinks: (vehicle: string, body: Actor & { market?: string; request_ids?: string[]; provider: Provider }) =>
    write<unknown>("/requests/links/propose", { vehicle, ...body }).then(raw),
  draftPositions: (vehicle: string, body: Actor & { market?: string; request_ids?: string[]; provider: Provider }) =>
    write<unknown>("/requests/positions", { vehicle, ...body }).then(raw),
  loadSimulated: (body: Actor) => write<unknown>("/requests/fixtures/simulated", body).then(raw),
  decideRequest: (id: string, body: Gate & { decision: string; requirement_id?: string }) =>
    write<unknown>(`/requests/${enc(id)}/decide`, body).then(raw),
  rubrics: (scope: Scope, signal?: AbortSignal) =>
    api<unknown>(`/priorities/rubrics?${params(scope)}`, { signal }).then(toRubricState),
  switchRubric: (body: Scope & Gate & { rubric_version: string; weights: Record<string, number> }) =>
    write<unknown>("/priorities/rubric", body).then(raw),
  deriveInputs: (scope: Scope, body: Actor) => write<unknown>("/priorities/inputs/derive", { ...scope, ...body }).then(raw),
  ranking: (scope: Scope, signal?: AbortSignal) =>
    api<unknown>(`/priorities/ranking?${params(scope)}`, { signal }).then((v) => toRanking(v, scope)),
  sensitivity: (scope: Scope, body: Actor) => write<unknown>("/priorities/sensitivity", { ...scope, ...body }).then(raw),
  explain: (scope: Scope, body: Actor & { provider: Provider; limit?: number }) =>
    write<unknown>("/priorities/explain", { ...scope, ...body }).then(toExplanation),
  runs: (vehicle: string, filters: { market?: string; capability?: string; status?: string }, signal?: AbortSignal) =>
    api<unknown>(`/runs?${params({ vehicle, ...filters, limit: 50 })}`, { signal }).then((v) => toPage(v, toRun)),
};
