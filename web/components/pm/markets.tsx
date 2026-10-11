"use client";
import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Info, Scale } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { allPages, date, readable } from "@/lib/api";
import { platform } from "@/lib/platform-api";
import {
  CONFLICT_DECISIONS,
  MARKETS,
  type ComparisonCell,
  type ConflictDetail,
  type MarketComparison,
  type MarketWeights,
  type MarketConflict,
  type Provider,
} from "@/lib/platform-types";
import type { Requirement } from "@/lib/types";
import { useWorkspace } from "./context";
import { PmSelect } from "./pm-select";
import {
  CapabilityButton,
  GateDialog,
  MethodLabel,
  PROVIDER_OPTIONS,
  PlatformView,
  ProvenanceLabel,
  type PlatformState,
  SourceLinks,
  Unavailable,
  fixed,
  percent,
  shortId,
  signed,
  useCapability,
  usePlatformQuery,
} from "./platform-shared";
import { Empty, ErrorMessage, Field, Heading, Loading, Panel, ScoreLabel, Status, useUrlState } from "./shared";

const RECOMMENDED_DECISION: Record<string, string> = {
  global: "adopt_global",
  market_variant: "market_variants",
  selectable_mode: "selectable_mode",
  optional_package: "optional_package",
  needs_research: "defer",
};

export function Markets() {
  const { scope } = useWorkspace();
  const { params, set } = useUrlState();
  const conflictId = params.get("conflict") || "";
  return (
    <>
      <Heading
        title="Market balancer"
        description={`Compare ${scope.vehicle} customer priorities across markets, see where markets pull in different directions, and record how the PM resolves it.`}
      />
      <div className="pm-alert">
        <Info size={16} />
        <span>
          The matrix, conflict rules and recommendations are deterministic and versioned; AI-drafted briefs are labelled separately. An empty market
          is missing data, not evidence of no customer need.
        </span>
      </div>
      <ComparisonPanel />
      <ConflictsPanel selected={conflictId} onSelect={(id) => set({ conflict: id || undefined })} />
      {conflictId && <ConflictDetailPanel key={conflictId} id={conflictId} onClose={() => set({ conflict: undefined })} />}
    </>
  );
}

function ComparisonPanel() {
  const { scope, actor } = useWorkspace();
  const weights = usePlatformQuery("weights", {
    queryKey: ["market-weights", scope.vehicle],
    queryFn: ({ signal }) => platform.weights(scope.vehicle, signal),
  });
  const compare = usePlatformQuery("compare", {
    queryKey: ["market-compare", scope.vehicle],
    queryFn: () => platform.compare(scope.vehicle, actor?.id),
    staleTime: Infinity,
  });
  return (
    <Panel
      title="Topic × market comparison"
      description="Per topic and market: requirement score and rank, evidence count and grade, BMW-evidence sentiment, request pressure and targets. Columns carry the market weight."
      action={
        !compare.unavailable && (
          <Button variant="outline" size="sm" disabled={compare.query.isFetching} onClick={() => void compare.query.refetch()}>
            {compare.query.isFetching ? "Comparing…" : "Recompute"}
          </Button>
        )
      }
    >
      <WeightsStrip state={weights} />
      {compare.unavailable ? (
        <>
          <Unavailable endpoint="compare" compact />
          <RequirementScoresByMarket />
        </>
      ) : (
        <PlatformView
          state={compare}
          isEmpty={(data) => !data.rows.length}
          empty={<Empty title="Nothing to compare yet" description="Import market evidence and run the pipeline for at least one market." />}
        >
          {(data) => <ComparisonMatrix data={data} />}
        </PlatformView>
      )}
    </Panel>
  );
}
function WeightsStrip({ state }: { state: PlatformState<MarketWeights> }) {
  return (
    <div className="weights-strip">
      <span className="mono muted">Sales-based market weights</span>
      <PlatformView
        state={state}
        compact
        isEmpty={(page) => !page.items.length && !page.warnings.length}
        empty={<span className="muted text-xs">No sales-based weights recorded; the comparison says when it falls back to equal weights.</span>}
      >
        {(page) => (
          <>
            <span className="chip-list">
              {[...page.items]
                .filter((w) => !page.selected || (w.period === page.selected.period && w.method_version === page.selected.methodVersion))
                .sort((a, b) => b.period.localeCompare(a.period) || a.market.localeCompare(b.market))
                .map((w) => (
                  <span
                    key={`${w.market}-${w.period}-${w.method_version}`}
                    className="chip"
                    title={`${w.method_version ?? "method not recorded"} · run ${w.run_id ?? "–"} · ${w.evidence_ids.length} sales records`}
                  >
                    {w.market} {w.period}: {percent(w.share)}
                    {w.units !== null && <small> · {Math.round(w.units).toLocaleString("en-US")} units</small>}
                  </span>
                ))}
            </span>
            {page.selected && (
              <span className="muted text-xs">
                Used by the comparison: {page.selected.methodVersion ?? "method not recorded"} · {page.selected.period}
              </span>
            )}
            {page.warnings.map((warning) => (
              <span key={warning} className="attention-text text-xs">
                {warning}
              </span>
            ))}
          </>
        )}
      </PlatformView>
    </div>
  );
}
function ComparisonMatrix({ data }: { data: MarketComparison }) {
  const { scope } = useWorkspace();
  return (
    <>
      {data.warnings.map((warning) => (
        <div key={warning} className="pm-alert attention">
          <Info size={16} />
          <span>{warning}</span>
        </div>
      ))}
      <p className="chart-meta">
        <MethodLabel methodVersion={data.methodVersion} runId={data.runId} />
        <span className="muted">
          Weights:{" "}
          {data.weightBasis === "sales"
            ? `sales shares (${data.weightsMethodVersion ?? "method not recorded"})`
            : data.weightBasis === "equal_fallback"
              ? "equal fallback — sales shares missing"
              : (data.weightBasis ?? "basis not recorded")}
          {" · "}Sentiment: {data.sentimentMethodVersion ?? "not scored"}
        </span>
      </p>
      <div className="pm-table-wrap">
        <table className="pm-table market-table market-matrix">
          <thead>
            <tr>
              <th className="pin-column">Customer topic</th>
              {data.markets.map((m) => (
                <th key={m.market}>
                  {m.market}
                  {m.name && <span className="muted"> · {m.name}</span>}
                  <small>
                    weight {percent(m.weight)}
                    {m.equalWeight ? " · equal (no sales share)" : m.share !== null ? ` · sales share ${percent(m.share)}` : ""}
                    {m.period && ` · ${m.period}`}
                  </small>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr key={row.topic}>
                <td className="pin-column matrix-topic">
                  <strong>{row.label ?? readable(row.topic)}</strong>
                  <small>
                    Demand index {row.demandIndex === null ? "not measured" : fixed(row.demandIndex, 2)}
                    {row.demandCoverage !== null && ` · covers ${percent(row.demandCoverage)} of weight`}
                  </small>
                  {row.alignment && <small>Alignment: {readable(row.alignment)}</small>}
                  {row.recommendation && <small>Rule recommends {readable(row.recommendation)}</small>}
                </td>
                {data.markets.map((m) => (
                  <td key={m.market}>
                    {row.cells[m.market] ? (
                      <MatrixCell cell={row.cells[m.market]} vehicle={scope.vehicle} topic={row.topic} />
                    ) : (
                      <span className="market-missing">Not returned for this market</span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
function MatrixCell({ cell, vehicle, topic }: { cell: ComparisonCell; vehicle: string; topic: string }) {
  const missing = Object.entries(cell.missing);
  const scoped = `/${vehicle.toLowerCase()}/${cell.market.toLowerCase()}`;
  return (
    <div className="matrix-cell">
      {cell.requirement ? (
        <Link className="market-cell" href={`${scoped}/requirements?requirement=${cell.requirement.id}`}>
          {cell.requirement.score !== null && <ScoreLabel score={cell.requirement.score} grade={cell.evidenceGrade ?? "–"} />}
          <span>
            {cell.requirement.title || cell.requirement.key || shortId(cell.requirement.id)}
            {cell.requirement.rank !== null && (
              <small>
                {" "}
                · rank {cell.requirement.rank}
                {cell.requirement.rankOf ? ` of ${cell.requirement.rankOf}` : ""}
              </small>
            )}
          </span>
          {cell.requirement.status && <Status value={cell.requirement.status} />}
        </Link>
      ) : (
        <span className="market-missing">No requirement</span>
      )}
      <dl className="matrix-facts">
        <div>
          <dt>Evidence</dt>
          <dd>
            {cell.evidenceCount === null ? (
              "–"
            ) : cell.evidenceCount > 0 ? (
              <Link className="text-link" href={`${scoped}/evidence?topic=${encodeURIComponent(topic)}`}>
                {cell.evidenceCount}
                {cell.evidenceGrade ? ` · grade ${cell.evidenceGrade}` : ""}
              </Link>
            ) : (
              `0${cell.evidenceGrade ? ` · grade ${cell.evidenceGrade}` : ""}`
            )}
          </dd>
        </div>
        <div>
          <dt>BMW sentiment</dt>
          <dd className={`tabular-nums ${cell.sentimentLowN ? "low-n-flag" : ""}`}>
            {signed(cell.sentiment)}
            {cell.sentimentN !== null && ` · n ${cell.sentimentN}${cell.sentimentLowN ? " (low n)" : ""}`}
          </dd>
        </div>
        <div>
          <dt>Requests</dt>
          <dd className="tabular-nums">
            {cell.requestPressure === null ? "–" : cell.requestPressure}
            {cell.requestMeanTriage !== null && ` · mean triage ${fixed(cell.requestMeanTriage)}`}
          </dd>
        </div>
      </dl>
      {!!cell.targets.length && <small className="matrix-targets">Targets: {cell.targets.join("; ")}</small>}
      {missing.map(([field, reason]) => (
        <small key={field} className="market-missing">
          {readable(field)}: {reason}
        </small>
      ))}
    </div>
  );
}
/** Read-only fallback from the existing requirement register when the market balancer API is absent. */
function RequirementScoresByMarket() {
  const { scope, workspace } = useWorkspace();
  const result = useQuery({
    queryKey: ["market-requirements", scope.vehicle],
    queryFn: ({ signal }) => allPages<Requirement>(`/requirements?vehicle=${encodeURIComponent(scope.vehicle)}`, signal),
  });
  const topics = [...new Set(result.data?.map((r) => r.topic) || [])].sort();
  const markets = [...new Set([...MARKETS, ...(workspace?.available_scopes.filter((s) => s.vehicle === scope.vehicle).map((s) => s.market) || [])])];
  if (result.error) return <ErrorMessage error={result.error} />;
  if (result.isPending) return <Loading />;
  if (!topics.length)
    return <Empty title="No market requirements yet" description="Import market-specific evidence and run the pipeline to compare priorities." />;
  return (
    <>
      <p className="muted text-xs">Requirement scores by market from the requirement register (each market’s own rubric and evidence).</p>
      <div className="pm-table-wrap">
        <table className="pm-table market-table">
          <thead>
            <tr>
              <th className="pin-column">Customer topic</th>
              {markets.map((m) => (
                <th key={m}>
                  {m}
                  <small>{result.data.filter((r) => r.market === m).length} requirements</small>
                </th>
              ))}
              <th>Priority spread</th>
            </tr>
          </thead>
          <tbody>
            {topics.map((topic) => {
              const values = result.data.filter((r) => r.topic === topic);
              const scores = values.map((r) => r.priority);
              const spread = scores.length > 1 ? Math.max(...scores) - Math.min(...scores) : null;
              return (
                <tr key={topic}>
                  <td className="pin-column">
                    <strong>{readable(topic)}</strong>
                  </td>
                  {markets.map((m) => (
                    <td key={m}>
                      {values.filter((r) => r.market === m).length ? (
                        values
                          .filter((r) => r.market === m)
                          .map((r) => (
                            <Link
                              key={r.id}
                              className="market-cell"
                              href={`/${scope.vehicle.toLowerCase()}/${m.toLowerCase()}/requirements?requirement=${r.id}`}
                            >
                              <ScoreLabel score={r.priority} grade={r.evidence_grade} />
                              <span>{r.title}</span>
                              <Status value={r.status} />
                            </Link>
                          ))
                      ) : (
                        <span className="market-missing">No requirement data</span>
                      )}
                    </td>
                  ))}
                  <td>
                    {spread == null ? (
                      <span className="muted">One market only</span>
                    ) : (
                      <span className={spread >= 15 ? "spread-high" : ""}>{spread.toFixed(1)} points</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

function ConflictsPanel({ selected, onSelect }: { selected: string; onSelect: (id: string) => void }) {
  const { scope } = useWorkspace();
  const [status, setStatus] = useState("open");
  const [provider, setProvider] = useState<Provider>("openai");
  const state = usePlatformQuery("conflicts", {
    queryKey: ["market-conflicts", scope.vehicle, status],
    queryFn: ({ signal }) => platform.conflicts(scope.vehicle, status === "all" ? "" : status, signal),
  });
  const detect = useCapability("detectConflicts", (actor) => platform.detectConflicts(scope.vehicle, { actor, provider }), [
    ["market-conflicts"],
    ["market-compare"],
  ]);
  return (
    <Panel
      title="Market conflicts"
      description="Detected with named thresholds; re-detection with unchanged inputs is idempotent and changed inputs supersede, keeping history."
    >
      <div className="platform-toolbar">
        <PmSelect
          aria-label="Conflict status"
          value={status}
          onValueChange={setStatus}
          options={["open", "resolved", "dismissed", "superseded", "all"].map((value) => ({
            value,
            label: value === "all" ? "All statuses" : readable(value),
          }))}
        />
        <span className="toolbar-spacer" />
        <PmSelect
          aria-label="Direction extraction provider"
          value={provider}
          onValueChange={(value) => setProvider(value as Provider)}
          options={PROVIDER_OPTIONS}
        />
        <CapabilityButton capability={detect}>
          <Scale size={14} />
          Detect conflicts
        </CapabilityButton>
      </div>
      <PlatformView
        state={state}
        isEmpty={(page) => !page.items.length}
        empty={
          <Empty
            title={`No ${status === "all" ? "" : status} conflicts`}
            description="Run detection after market evidence and requirements exist for more than one market."
          />
        }
      >
        {(page) => (
          <div className="pm-table-wrap">
            <table className="pm-table conflict-table">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Topic</th>
                  <th>Markets</th>
                  <th>Type</th>
                  <th>Recommendation</th>
                  <th>Status</th>
                  <th>Detected</th>
                </tr>
              </thead>
              <tbody>
                {[...page.items]
                  .sort((a, b) => severityRank(b) - severityRank(a) || b.created_at.localeCompare(a.created_at))
                  .map((c) => (
                    <tr key={c.id} className={c.id === selected ? "is-selected" : undefined}>
                      <td>
                        <span className={`severity severity-${c.severity}`}>{c.severity}</span>
                      </td>
                      <td>
                        <button type="button" className="text-link" onClick={() => onSelect(c.id)}>
                          {readable(c.topic)}
                          {c.related_topic && ` ↔ ${readable(c.related_topic)}`}
                        </button>
                      </td>
                      <td className="mono">{c.markets.join(" · ")}</td>
                      <td>{readable(c.conflict_type)}</td>
                      <td>{readable(c.recommendation)}</td>
                      <td>
                        <Status value={c.status} />
                      </td>
                      <td className="date-cell">{date(c.created_at)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
            {page.total > page.items.length && (
              <p className="muted text-xs">
                Showing {page.items.length} of {page.total} conflicts.
              </p>
            )}
          </div>
        )}
      </PlatformView>
    </Panel>
  );
}
const severityRank = (c: MarketConflict) => ({ high: 3, medium: 2, low: 1 })[c.severity as "high"] ?? 0;

function ConflictDetailPanel({ id, onClose }: { id: string; onClose: () => void }) {
  const state = usePlatformQuery("conflict", {
    queryKey: ["market-conflict", id],
    queryFn: ({ signal }) => platform.conflict(id, signal),
  });
  return (
    <Panel
      title="Conflict detail"
      description="Per-market evidence side by side, the recorded metrics behind the rule, and the human resolution."
      action={
        <Button variant="ghost" size="sm" onClick={onClose}>
          Close
        </Button>
      }
    >
      <PlatformView state={state}>{(detail) => <ConflictBody detail={detail} />}</PlatformView>
    </Panel>
  );
}
function ConflictBody({ detail }: { detail: ConflictDetail }) {
  const { conflict } = detail;
  const [resolving, setResolving] = useState(false);
  const brief = useCapability("draftBrief", (actor) => platform.draftBrief(conflict.id, { actor }), [
    ["market-conflict", conflict.id],
    ["market-conflicts"],
  ]);
  const markets = [...new Set([...conflict.markets, ...Object.keys(detail.evidenceByMarket)])];
  const scalars = Object.entries(conflict.metrics).filter(([key, value]) => key !== "ai_brief" && (typeof value !== "object" || value === null));
  const nested = Object.fromEntries(
    Object.entries(conflict.metrics).filter(([key, value]) => key !== "ai_brief" && typeof value === "object" && value !== null),
  );
  return (
    <div className="conflict-detail">
      <div className="conflict-summary">
        <div>
          <span className={`severity severity-${conflict.severity}`}>{conflict.severity}</span> <strong>{readable(conflict.topic)}</strong>
          {conflict.related_topic && <strong> ↔ {readable(conflict.related_topic)}</strong>}
          <span className="muted">
            {" "}
            · {readable(conflict.conflict_type)} · {conflict.markets.join(" vs ")}
          </span>
        </div>
        <span className="conflict-actions">
          <Status value={conflict.status} />
          {conflict.status === "open" && <Button onClick={() => setResolving(true)}>Resolve conflict</Button>}
        </span>
      </div>
      <div className="conflict-rationale">
        <h3>Recommendation: {readable(conflict.recommendation)}</h3>
        <p>{conflict.rationale}</p>
        <MethodLabel methodVersion={conflict.method_version} runId={conflict.run_id} />
      </div>
      {conflict.aiBrief ? (
        <AiBriefView brief={conflict.aiBrief} />
      ) : (
        conflict.status === "open" && (
          <div className="ai-brief-actions">
            <span className="muted text-xs">
              No AI trade-off brief yet. OpenAI drafts one from the recorded metrics and cited evidence; it never decides.
            </span>
            <CapabilityButton capability={brief}>Draft AI brief</CapabilityButton>
          </div>
        )
      )}
      {conflict.aiBrief && conflict.status === "open" && (
        <div className="ai-brief-actions">
          <CapabilityButton capability={brief} variant="ghost">
            Redraft AI brief
          </CapabilityButton>
        </div>
      )}
      {(scalars.length > 0 || Object.keys(nested).length > 0) && (
        <details className="conflict-metrics" open>
          <summary>Recorded metrics</summary>
          {scalars.length > 0 && (
            <dl className="record-details">
              {scalars.map(([key, value]) => (
                <div key={key}>
                  <dt>{readable(key)}</dt>
                  <dd>{String(value)}</dd>
                </div>
              ))}
            </dl>
          )}
          {Object.keys(nested).length > 0 && <pre className="json-record">{JSON.stringify(nested, null, 2)}</pre>}
        </details>
      )}
      <div className="conflict-evidence-grid" style={{ "--market-count": Math.max(1, markets.length) } as React.CSSProperties}>
        {markets.map((market) => (
          <section key={market}>
            <h3>{market}</h3>
            {(detail.evidenceByMarket[market] || []).length ? (
              detail.evidenceByMarket[market].map((e) => (
                <article key={e.id} className="evidence-card">
                  {!!e.mentions.length && (
                    <span className="mention-list">
                      {e.mentions.map((m, i) => (
                        <span key={i} className="chip" title={`“${m.quote}”`}>
                          {readable(m.attribute)} · {m.direction}
                        </span>
                      ))}
                    </span>
                  )}
                  {e.quote || e.content ? (
                    <blockquote>
                      <Highlighted text={e.quote || e.content || ""} quotes={e.mentions.map((m) => m.quote)} />
                    </blockquote>
                  ) : (
                    <p className="muted text-xs">Evidence text not included in this response.</p>
                  )}
                  <span className="muted text-xs">
                    {e.sourceTitle && `${e.sourceTitle} · `}
                    {e.observedAt ? `Observed ${date(e.observedAt)}` : "Observation date not recorded"}
                  </span>
                  <SourceLinks refs={[{ type: "evidence", id: e.id }]} market={market === "unscoped" || market === "all" ? null : market} />
                </article>
              ))
            ) : (
              <p className="market-missing">No evidence recorded for {market} on this conflict.</p>
            )}
          </section>
        ))}
      </div>
      {detail.requirements.length ? (
        <section>
          <h3 className="muted text-xs">Requirements in this conflict</h3>
          <div className="chip-list">
            {detail.requirements.map((r) => (
              <Link
                key={r.id}
                className="source-chip"
                href={`/${conflict.vehicle.toLowerCase()}/${(r.market ?? "").toLowerCase()}/requirements?requirement=${encodeURIComponent(r.id)}`}
                title={r.title ?? r.id}
              >
                {r.market} · {r.key ?? shortId(r.id)}
                {r.score !== null && ` · ${fixed(r.score)}`}
                {r.status && ` · ${readable(r.status)}`}
              </Link>
            ))}
          </div>
        </section>
      ) : (
        !!conflict.requirement_ids.length && (
          <p className="muted text-xs">
            Linked requirements: <SourceLinks refs={conflict.requirement_ids.map((rid) => ({ type: "requirement", id: rid }))} />
          </p>
        )
      )}
      {detail.history.length > 1 && (
        <p className="muted text-xs">
          Detection history for this fingerprint: {detail.history.map((h) => `${readable(h.status)} ${date(h.createdAt)}`).join(" → ")}
          {detail.supersededBy && " · superseded by a newer detection"}
        </p>
      )}
      <ResolutionHistory detail={detail} />
      <ResolveDialog conflict={conflict} requirements={detail.requirements} open={resolving} onOpenChange={setResolving} />
    </div>
  );
}
function AiBriefView({ brief }: { brief: NonNullable<MarketConflict["aiBrief"]> }) {
  return (
    <section className="ai-brief">
      <ProvenanceLabel value={brief.provenance} />
      <p>{brief.summary}</p>
      {brief.tradeOff && (
        <p>
          <strong>Trade-off: </strong>
          {brief.tradeOff}
        </p>
      )}
      {!!brief.options.length && (
        <ul>
          {brief.options.map((option, i) => (
            <li key={`${option.option}-${i}`}>
              <strong>{readable(option.option)}</strong>
              {option.summary && `: ${option.summary}`}
              {!!option.benefits.length && <small className="muted"> Benefits: {option.benefits.join("; ")}.</small>}
              {!!option.risks.length && <small className="muted"> Risks: {option.risks.join("; ")}.</small>}
            </li>
          ))}
        </ul>
      )}
      {!!brief.openQuestions.length && (
        <>
          <h4>Open questions</h4>
          <ul>
            {brief.openQuestions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </>
      )}
      {!!brief.citations.length && (
        <>
          <h4>Cited evidence</h4>
          <ul>
            {brief.citations.map((c, i) => (
              <li key={`${c.evidenceId}-${i}`}>
                “{c.quote}” <SourceLinks refs={[{ type: "evidence", id: c.evidenceId }]} market={c.market} />
              </li>
            ))}
          </ul>
        </>
      )}
      <small className="muted">
        {brief.label ?? "Drafted from the recorded metrics. The templated rationale above is authoritative; the PM decides."}
      </small>
    </section>
  );
}
/** Marks the exact quotes the direction extraction located in an evidence text (first occurrence each). */
function Highlighted({ text, quotes }: { text: string; quotes: string[] }) {
  const ranges = quotes
    .map((q) => ({ start: text.indexOf(q), length: q.length }))
    .filter((r) => r.start >= 0 && r.length > 0)
    .sort((a, b) => a.start - b.start)
    .filter((r, i, all) => i === 0 || r.start >= all[i - 1].start + all[i - 1].length);
  if (!ranges.length) return <>{text}</>;
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  ranges.forEach((r, i) => {
    if (r.start > cursor) parts.push(text.slice(cursor, r.start));
    parts.push(
      <mark key={i} className="mention">
        {text.slice(r.start, r.start + r.length)}
      </mark>,
    );
    cursor = r.start + r.length;
  });
  if (cursor < text.length) parts.push(text.slice(cursor));
  return <>{parts}</>;
}
function ResolutionHistory({ detail }: { detail: ConflictDetail }) {
  if (!detail.resolutions.length) return <p className="muted text-xs">No resolution recorded yet.</p>;
  return (
    <div className="audit-timeline">
      {[...detail.resolutions]
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
        .map((r) => (
          <article key={r.id || r.created_at}>
            <span className="timeline-dot" />
            <div>
              <div className="audit-event-title">
                <strong>{readable(r.decision)}</strong>
                <span className="mono muted">{shortId(r.id)}</span>
              </div>
              <p>{r.rationale}</p>
              <small>
                {r.actor} · {date(r.created_at)}
                {!!r.requirement_ids.length && ` · ${r.requirement_ids.length} requirements`}
              </small>
            </div>
          </article>
        ))}
    </div>
  );
}
function ResolveDialog({
  conflict,
  requirements,
  open,
  onOpenChange,
}: {
  conflict: MarketConflict;
  requirements: ConflictDetail["requirements"];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const client = useQueryClient();
  const [decision, setDecision] = useState(RECOMMENDED_DECISION[conflict.recommendation] ?? "");
  const [linked, setLinked] = useState<string[]>(conflict.requirement_ids);
  const resolve = useMutation({
    mutationFn: ({ actor, rationale }: { actor: string; rationale: string }) =>
      platform.resolveConflict(conflict.id, { decision, actor, rationale, requirement_ids: linked }),
    onSuccess: () => {
      toast.success("Resolution recorded with your rationale.");
      onOpenChange(false);
      void client.invalidateQueries({ queryKey: ["market-conflicts"] });
      void client.invalidateQueries({ queryKey: ["market-conflict", conflict.id] });
    },
  });
  return (
    <GateDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Resolve market conflict"
      description={`${readable(conflict.topic)}${conflict.related_topic ? ` ↔ ${readable(conflict.related_topic)}` : ""} across ${conflict.markets.join(", ")}. The rule recommends ${readable(conflict.recommendation)}; the decision is yours.`}
      submitLabel="Record resolution"
      role="approve"
      pending={resolve.isPending}
      error={resolve.error}
      ready={!!decision}
      onSubmit={(actor, rationale) => resolve.mutate({ actor, rationale })}
    >
      <Field label="Resolution">
        <PmSelect
          aria-label="Resolution"
          value={decision}
          onValueChange={setDecision}
          options={[
            { value: "", label: "Choose a resolution" },
            ...CONFLICT_DECISIONS.map((value) => ({
              value,
              label: `${readable(value)}${RECOMMENDED_DECISION[conflict.recommendation] === value ? " · matches the recommendation" : ""}`,
            })),
          ]}
        />
      </Field>
      {!!conflict.requirement_ids.length && (
        <fieldset className="checkbox-list">
          <legend className="muted text-xs">Requirements this resolution applies to</legend>
          {conflict.requirement_ids.map((rid) => (
            <label key={rid} className="muted text-xs">
              <input
                type="checkbox"
                checked={linked.includes(rid)}
                onChange={(e) => setLinked(e.target.checked ? [...linked, rid] : linked.filter((x) => x !== rid))}
              />{" "}
              <span className="mono">
                {(() => {
                  const r = requirements.find((item) => item.id === rid);
                  return r ? `${r.market ?? ""} · ${r.key ?? rid}${r.title ? ` · ${r.title}` : ""}` : rid;
                })()}
              </span>
            </label>
          ))}
        </fieldset>
      )}
    </GateDialog>
  );
}
