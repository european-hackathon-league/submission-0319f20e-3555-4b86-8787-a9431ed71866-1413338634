"use client";
import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CartesianGrid, Line, LineChart, ReferenceLine, XAxis, YAxis } from "recharts";
import { ArrowDownRight, ArrowUpRight, ExternalLink, Info, Minus, Plus, Radar } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, type ChartConfig } from "@/components/ui/chart";
import { date, readable } from "@/lib/api";
import { gateError, platform, toSentimentChart } from "@/lib/platform-api";
import {
  TOPICS,
  type DomainGroup,
  type Provider,
  type SentimentChart,
  type SentimentPoint,
  type SignalItem,
  type SignalsDigest,
  type SourceClass,
  type TopicSummary,
  type Watchlist,
} from "@/lib/platform-types";
import { useWorkspace } from "./context";
import { PmSelect } from "./pm-select";
import {
  CapabilityButton,
  GateDialog,
  MethodLabel,
  PROVIDER_OPTIONS,
  PlatformView,
  ProvenanceLabel,
  SourceLinks,
  percent,
  shortId,
  signed,
  useCapability,
  usePlatformQuery,
} from "./platform-shared";
import { Empty, ErrorMessage, Field, Heading, Panel, Status, useUrlState } from "./shared";

const SERIES: Record<SourceClass, { label: string; color: string; dash?: string }> = {
  bmw_evidence: { label: "BMW evidence", color: "var(--series-bmw)" },
  public_monitoring: { label: "Public monitoring (unreviewed)", color: "var(--series-public)", dash: "6 4" },
  public_imported: { label: "Public, imported as evidence", color: "var(--series-imported)", dash: "2 3" },
};
const seriesOf = (c: string) => SERIES[c as SourceClass] ?? { label: readable(c), color: "var(--chart-2)" };
const topicLabel = (key: string) => TOPICS.find(([k]) => k === key)?.[1] ?? readable(key);
const topicOptions = TOPICS.map(([value, label]) => ({ value, label }));
const csv = (value: string) =>
  value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);

export function Signals() {
  const { scope } = useWorkspace();
  const { params, set } = useUrlState();
  const topic = params.get("topic") || "driving-experience";
  const [creating, setCreating] = useState(false);
  return (
    <>
      <Heading
        title="Signals"
        description={`Follow public feedback and sentiment for ${scope.vehicle} / ${scope.market}. Review signals before importing them as evidence.`}
        action={
          <Button onClick={() => setCreating(true)}>
            <Plus size={14} />
            New watchlist
          </Button>
        }
      />
      <div className="pm-alert">
        <Info size={16} />
        <span>
          Exa searches public pages using your watchlist terms. Search queries exclude private BMW records and customer quotes.
        </span>
      </div>
      <TopicSummaries topic={topic} onSelect={(next) => set({ topic: next })} />
      <WhatChanged topic={topic} />
      <SentimentPanel topic={topic} setTopic={(next) => set({ topic: next })} />
      <Watchlists />
      <SignalInbox topic={topic} />
      <WatchlistDialog open={creating} onOpenChange={setCreating} topic={topic} />
    </>
  );
}

function TopicSummaries({ topic, onSelect }: { topic: string; onSelect: (topic: string) => void }) {
  const { scope } = useWorkspace();
  const state = usePlatformQuery("summary", {
    queryKey: ["signals-summary", scope.vehicle, scope.market],
    queryFn: ({ signal }) => platform.summary(scope, signal),
  });
  return (
    <Panel
      title="Sentiment by topic"
      description="Average sentiment and its trend over the last eight weeks, weighted by the number of records."
    >
      <PlatformView
        state={state}
        isEmpty={(items) => !items.length}
        empty={<Empty title="No sentiment scored yet" description="Score BMW evidence or refreshed public signals to see topic sentiment." />}
      >
        {(items) => {
          const byTopic = new Map<string, TopicSummary[]>();
          for (const item of items) byTopic.set(item.topic, [...(byTopic.get(item.topic) || []), item]);
          return (
            <div className="topic-tiles">
              {[...byTopic.entries()].map(([key, rows]) => (
                <button key={key} type="button" className="topic-tile" aria-pressed={key === topic} onClick={() => onSelect(key)}>
                  <strong>{topicLabel(key)}</strong>
                  {rows.map((row, index) => (
                    <span key={`${row.sourceClass}-${index}`} className="topic-tile-row">
                      <span className="series-swatch" style={{ background: seriesOf(row.sourceClass || "bmw_evidence").color }} />
                      <span>{row.sourceClass ? seriesOf(row.sourceClass).label : "All sources"}</span>
                      <span className="tabular-nums">{signed(row.meanPolarity)}</span>
                      <Momentum value={row.momentum} />
                      <small className={row.lowN ? "low-n-flag" : "muted"}>
                        n {row.n}
                        {row.lowN ? " · few records" : ""}
                        {row.recentN !== null &&
                          ` · last ${row.momentumWeeks ?? 0} wk: ${signed(row.recentMeanPolarity)} (n ${row.recentN}${row.recentLowN ? ", few records" : ""})`}
                        {row.undatedN > 0 && ` · ${row.undatedN} dated by retrieval`}
                      </small>
                    </span>
                  ))}
                  {rows[0]?.methodVersion && <MethodLabel methodVersion={rows[0].methodVersion} compact />}
                </button>
              ))}
            </div>
          );
        }}
      </PlatformView>
    </Panel>
  );
}
/** POST /signals/summary: OpenAI drafts grounded observations; the deterministic provider returns the metrics only. */
function WhatChanged({ topic }: { topic: string }) {
  const { scope } = useWorkspace();
  const [provider, setProvider] = useState<Provider>("openai");
  const [onlyTopic, setOnlyTopic] = useState(false);
  const run = useCapability("summarise", (actor) => platform.summarise(scope, { actor, provider, ...(onlyTopic ? { topic } : {}) }), []);
  const digest = run.mutation.data as SignalsDigest | undefined;
  return (
    <Panel
      title="What changed"
      description="Summarise weekly trends with source quotes, or choose the rule-based option for metrics only."
    >
      <div className="platform-toolbar">
        <PmSelect
          aria-label="Summary scope"
          value={onlyTopic ? "topic" : "all"}
          onValueChange={(value) => setOnlyTopic(value === "topic")}
          options={[
            { value: "all", label: "All topics" },
            { value: "topic", label: `Only ${topicLabel(topic)}` },
          ]}
        />
        <span className="toolbar-spacer" />
        <PmSelect
          aria-label="Summary provider"
          value={provider}
          onValueChange={(value) => setProvider(value as Provider)}
          options={PROVIDER_OPTIONS}
        />
        <CapabilityButton capability={run}>Summarise trends</CapabilityButton>
      </div>
      {run.mutation.error ? <ErrorMessage error={gateError(run.mutation.error)} /> : null}
      {!digest ? (
        <p className="muted text-xs">Run a summary to review the latest trends.</p>
      ) : digest.provenance.generated ? (
        <section className="ai-brief">
          <ProvenanceLabel value={digest.provenance} />
          {digest.claims.length ? (
            <ul>
              {digest.claims.map((c, i) => (
                <li key={`${c.subjectId}-${i}`}>
                  {c.text}
                  <small className="muted">
                    {" "}
                    “{c.quote}” · <span className="mono">{shortId(c.subjectId)}</span>
                  </small>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted text-xs">No summary with supporting source quotes was returned for these {digest.rows.length} series.</p>
          )}
          <small className="muted">
            AI draft for review · Quotes checked against their sources.
          </small>
        </section>
      ) : (
        <p className="muted text-xs">
          <MethodLabel methodVersion={digest.provenance.methodVersion} runId={digest.runId} /> Rule-based summary: {digest.rows.length} series
          summarised as metrics (see the topic tiles); no text is generated.
        </p>
      )}
    </Panel>
  );
}
function Momentum({ value }: { value: number | null }) {
  if (value === null)
    return (
      <span className="muted text-xs" title="Trend not measured">
        –
      </span>
    );
  const Icon = value > 0.005 ? ArrowUpRight : value < -0.005 ? ArrowDownRight : Minus;
  return (
    <span className="momentum" title="8-week trend: weekly change in average sentiment">
      <Icon size={12} />
      {signed(value, 3)}
    </span>
  );
}

function SentimentPanel({ topic, setTopic }: { topic: string; setTopic: (topic: string) => void }) {
  const { scope } = useWorkspace();
  const [method, setMethod] = useState<string | null>(null);
  const [view, setView] = useState<"chart" | "table">("chart");
  const [selected, setSelected] = useState<SentimentPoint | null>(null);
  const [provider, setProvider] = useState<Provider>("openai");
  const state = usePlatformQuery("timeseries", {
    queryKey: ["sentiment-timeseries", scope.vehicle, scope.market, topic],
    queryFn: ({ signal }) => platform.timeseries(scope, topic, signal),
  });
  const score = useCapability("scoreSentiment", (actor) => platform.scoreSentiment(scope, { actor, provider }), [
    ["sentiment-timeseries"],
    ["signals-summary"],
  ]);
  const chart = useMemo(() => (state.query.data ? toSentimentChart(state.query.data, method) : null), [state.query.data, method]);
  return (
    <Panel
      title={`Sentiment over time · ${topicLabel(topic)}`}
      description="Weekly sentiment from negative (−1) to positive (+1), shown separately for each source type using the selected method."
    >
      <div className="platform-toolbar">
        <PmSelect
          aria-label="Topic"
          value={topic}
          onValueChange={(value) => {
            setTopic(value);
            setSelected(null);
          }}
          options={topicOptions}
        />
        {chart && chart.methodVersions.length > 0 && (
          <PmSelect
            aria-label="Method version"
            value={chart.methodVersion || ""}
            onValueChange={(value) => {
              setMethod(value);
              setSelected(null);
            }}
            options={chart.methodVersions.map((value) => ({ value, label: value }))}
          />
        )}
        <div className="segmented-control">
          <button type="button" aria-pressed={view === "chart"} onClick={() => setView("chart")}>
            Chart
          </button>
          <button type="button" aria-pressed={view === "table"} onClick={() => setView("table")}>
            Table
          </button>
        </div>
        <span className="toolbar-spacer" />
        <PmSelect
          aria-label="Sentiment provider"
          value={provider}
          onValueChange={(value) => setProvider(value as Provider)}
          options={PROVIDER_OPTIONS}
        />
        <CapabilityButton capability={score}>Score sentiment</CapabilityButton>
      </div>
      <PlatformView
        state={state}
        isEmpty={(points) => !points.length}
        empty={
          <Empty
            title="No weekly sentiment for this topic"
            description="Score evidence or refresh a watchlist; weeks without scored items stay empty rather than zero."
          />
        }
      >
        {() =>
          chart && (
            <>
              {chart.methodVersion && (
                <p className="chart-meta">
                  <MethodLabel methodVersion={chart.methodVersion} />{" "}
                  <span className="muted text-xs">Hollow points have fewer than 5 scored items. Select a point to open its sources.</span>
                </p>
              )}
              {view === "chart" ? (
                <SentimentLines chart={chart} onSelect={setSelected} selected={selected} />
              ) : (
                <SentimentTable chart={chart} onSelect={setSelected} />
              )}
              {selected && <PointSources point={selected} topic={topic} onClose={() => setSelected(null)} />}
            </>
          )
        }
      </PlatformView>
    </Panel>
  );
}
type DotProps = { cx?: number; cy?: number; payload?: { week?: string }; dataKey?: unknown; index?: number };
function SentimentLines({
  chart,
  selected,
  onSelect,
}: {
  chart: SentimentChart;
  selected: SentimentPoint | null;
  onSelect: (p: SentimentPoint) => void;
}) {
  const config: ChartConfig = Object.fromEntries(chart.sourceClasses.map((c) => [c, { label: seriesOf(c).label, color: seriesOf(c).color }]));
  const dot = ({ cx, cy, payload, dataKey, index }: DotProps, active: boolean) => {
    const sourceClass = String(dataKey);
    const point = payload?.week ? chart.points[`${payload.week}|${sourceClass}`] : undefined;
    if (typeof cx !== "number" || typeof cy !== "number" || !point || point.meanPolarity === null) return <g key={`${sourceClass}-${index}-empty`} />;
    const color = seriesOf(sourceClass).color;
    const isSelected = selected?.week === point.week && selected.sourceClass === point.sourceClass;
    return (
      <g
        key={`${sourceClass}-${index}`}
        className="sentiment-dot"
        role="button"
        aria-label={`${seriesOf(sourceClass).label}, ${point.label}: mean ${signed(point.meanPolarity)}, n ${point.n}${point.lowN ? ", few records" : ""}`}
        onClick={() => onSelect(point)}
      >
        <circle cx={cx} cy={cy} r={11} fill="transparent" />
        <circle
          cx={cx}
          cy={cy}
          r={active || isSelected ? 6 : 4.5}
          fill={point.lowN ? "var(--card)" : color}
          stroke={isSelected ? "var(--foreground)" : color}
          strokeWidth={2}
        />
      </g>
    );
  };
  return (
    <ChartContainer config={config} className="sentiment-chart" initialDimension={{ width: 720, height: 300 }}>
      <LineChart data={chart.rows} margin={{ top: 12, right: 18, bottom: 4, left: 0 }}>
        <CartesianGrid vertical={false} strokeDasharray="2 4" />
        <XAxis dataKey="label" tickLine={false} axisLine={false} tickMargin={8} minTickGap={18} />
        <YAxis domain={[-1, 1]} ticks={[-1, -0.5, 0, 0.5, 1]} tickLine={false} axisLine={false} width={38} />
        <ReferenceLine y={0} stroke="var(--border)" />
        <ChartTooltip
          cursor={{ strokeDasharray: "3 3" }}
          content={(props) => <SentimentTooltip chart={chart} week={(props.payload?.[0]?.payload as { week?: string } | undefined)?.week} />}
        />
        <ChartLegend content={<ChartLegendContent />} />
        {chart.sourceClasses.map((c) => (
          <Line
            key={c}
            dataKey={c}
            name={seriesOf(c).label}
            type="linear"
            stroke={seriesOf(c).color}
            strokeWidth={2}
            strokeDasharray={seriesOf(c).dash}
            connectNulls={false}
            isAnimationActive={false}
            dot={(props) => dot(props as DotProps, false)}
            activeDot={(props: unknown) => dot(props as DotProps, true)}
          />
        ))}
      </LineChart>
    </ChartContainer>
  );
}
function SentimentTooltip({ chart, week }: { chart: SentimentChart; week?: string }) {
  if (!week) return null;
  const points = chart.sourceClasses.map((c) => chart.points[`${week}|${c}`]).filter((p): p is SentimentPoint => !!p);
  if (!points.length) return null;
  return (
    <div className="chart-tooltip sentiment-tooltip">
      <strong>{chart.rows.find((r) => r.week === week)?.label ?? week}</strong>
      {points.map((p) => (
        <span key={p.sourceClass}>
          <i className="series-swatch" style={{ background: seriesOf(p.sourceClass).color }} />
          {seriesOf(p.sourceClass).label}: <b className="tabular-nums">{signed(p.meanPolarity)}</b> · n {p.n}
          {p.lowN && " · few records"} · negative {percent(p.negativeShare)}
        </span>
      ))}
    </div>
  );
}
function SentimentTable({ chart, onSelect }: { chart: SentimentChart; onSelect: (p: SentimentPoint) => void }) {
  const points = Object.values(chart.points).sort((a, b) => a.week.localeCompare(b.week) || a.sourceClass.localeCompare(b.sourceClass));
  return (
    <div className="pm-table-wrap">
      <table className="pm-table">
        <thead>
          <tr>
            <th>Week</th>
            <th>Series</th>
            <th>n</th>
            <th>Average sentiment</th>
            <th>Negative share</th>
            <th>Dated by retrieval</th>
            <th>Sources</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={`${p.week}|${p.sourceClass}`}>
              <td className="mono">{chart.rows.find((r) => r.week === p.week)?.label ?? p.week}</td>
              <td>{seriesOf(p.sourceClass).label}</td>
              <td className={p.lowN ? "low-n-flag" : ""}>
                {p.n}
                {p.lowN ? " · few records" : ""}
              </td>
              <td className="tabular-nums">{signed(p.meanPolarity)}</td>
              <td>{percent(p.negativeShare)}</td>
              <td>{p.undatedN}</td>
              <td>
                <button type="button" className="text-link" onClick={() => onSelect(p)}>
                  {p.subjectIds.length} records
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function PointSources({ point, topic, onClose }: { point: SentimentPoint; topic: string; onClose: () => void }) {
  const { scope } = useWorkspace();
  const isPublic = point.sourceClass === "public_monitoring";
  const items = usePlatformQuery("signalItems", {
    queryKey: ["signal-items", scope.vehicle, scope.market, topic, "all"],
    queryFn: ({ signal }) => platform.signalItems(scope, { topic }, signal),
    enabled: isPublic,
  });
  const byId = new Map((items.query.data?.items || []).map((item) => [item.id, item]));
  return (
    <section className="point-sources" aria-label="Sources behind the selected point">
      <div className="point-sources-heading">
        <div>
          <strong>
            {seriesOf(point.sourceClass).label} · {point.label}
          </strong>
          <span className="muted text-xs">
            n {point.n} · mean {signed(point.meanPolarity)} · negative {percent(point.negativeShare)} · {point.methodVersion}
            {point.undatedN > 0 && ` · ${point.undatedN} of ${point.n} dated by retrieval or import, not publication`}
          </span>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose}>
          Close
        </Button>
      </div>
      {!point.subjectIds.length ? (
        <p className="muted text-xs">The server did not return the record ids behind this point.</p>
      ) : isPublic ? (
        <PlatformView state={items} compact>
          {() => (
            <ul className="point-source-list">
              {point.subjectIds.map((id) => {
                const item = byId.get(id);
                return (
                  <li key={id}>
                    {item ? (
                      <>
                        <a href={item.url} target="_blank" rel="noreferrer noopener" className="text-link">
                          {item.title || item.url}
                          <ExternalLink size={12} />
                        </a>
                        <small className="muted">
                          {item.domain} ·{" "}
                          {item.date_basis === "published"
                            ? `published ${date(item.published_at)}`
                            : `retrieved ${date(item.retrieved_at)} (no publication date)`}{" "}
                          · <Status value={item.review_status} />
                        </small>
                      </>
                    ) : (
                      <span className="mono muted">Signal item {shortId(id)} (not in the loaded topic items)</span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </PlatformView>
      ) : (
        <SourceLinks refs={point.subjectIds.map((id) => ({ type: "evidence", id }))} />
      )}
    </section>
  );
}

function Watchlists() {
  const { scope } = useWorkspace();
  const state = usePlatformQuery("watchlists", {
    queryKey: ["watchlists", scope.vehicle, scope.market],
    queryFn: ({ signal }) => platform.watchlists(scope, signal),
  });
  return (
    <Panel title="Watchlists" description="Manage the topics and public sources you want to follow.">
      <PlatformView
        state={state}
        isEmpty={(page) => !page.items.length}
        empty={<Empty title="No watchlists yet" description="Create one to monitor a topic in public press, forums, social or video." />}
      >
        {(page) => (
          <div className="pm-table-wrap">
            <table className="pm-table watchlist-table">
              <thead>
                <tr>
                  <th>Watchlist</th>
                  <th>Query parts</th>
                  <th>Sources</th>
                  <th>Status</th>
                  <th>Authorised by</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((w) => (
                  <WatchlistRow key={w.id} watchlist={w} />
                ))}
              </tbody>
            </table>
            {page.total > page.items.length && (
              <p className="muted text-xs">
                Showing {page.items.length} of {page.total} watchlists.
              </p>
            )}
          </div>
        )}
      </PlatformView>
    </Panel>
  );
}
function WatchlistRow({ watchlist: w }: { watchlist: Watchlist }) {
  const client = useQueryClient();
  const [toggling, setToggling] = useState(false);
  const invalidate = [["watchlists"], ["signal-items"], ["sentiment-timeseries"], ["signals-summary"]];
  const refresh = useCapability("refreshWatchlist", (actor) => platform.refreshWatchlist(w.id, { actor }), invalidate);
  const backfill = useCapability("backfillWatchlist", (actor) => platform.backfillWatchlist(w.id, { actor, weeks: 12 }), invalidate);
  const next = w.status === "active" ? "paused" : "active";
  const toggle = useMutation({
    mutationFn: ({ actor, rationale }: { actor: string; rationale: string }) => platform.setWatchlistStatus(w.id, { status: next, actor, rationale }),
    onSuccess: () => {
      setToggling(false);
      toast.success(next === "paused" ? "Watchlist paused." : "Watchlist resumed.");
      void client.invalidateQueries({ queryKey: ["watchlists"] });
    },
  });
  return (
    <tr>
      <td>
        <strong>{w.label}</strong>
        <small>
          {topicLabel(w.topic)} · every {w.cadence_days} days · ≤ {w.max_results} results
        </small>
      </td>
      <td>
        <span className="chip-list">
          {w.query_terms.map((t) => (
            <span key={t} className="chip">
              {t}
            </span>
          ))}
          {w.competitors.map((c) => (
            <span key={c} className="chip is-muted">
              vs {c}
            </span>
          ))}
        </span>
      </td>
      <td>
        {readable(w.domain_group)}
        {!!w.domains.length && <small>{w.domains.join(", ")}</small>}
      </td>
      <td>
        <Status value={w.status} />
        {w.status_changed_by && <small>by {w.status_changed_by}</small>}
      </td>
      <td>
        <span className="mono">{w.created_by}</span>
        <small title={w.rationale}>{w.rationale}</small>
      </td>
      <td>
        <span className="row-actions">
          <CapabilityButton capability={refresh}>Refresh</CapabilityButton>
          <CapabilityButton capability={backfill}>Backfill 12 wk</CapabilityButton>
          <Button type="button" size="sm" variant="ghost" onClick={() => setToggling(true)}>
            {w.status === "active" ? "Pause" : "Resume"}
          </Button>
        </span>
        <GateDialog
          open={toggling}
          onOpenChange={setToggling}
          title={`${w.status === "active" ? "Pause" : "Resume"} “${w.label}”`}
          description={
            w.status === "active"
              ? "Pausing stops scheduled searches; items already found stay."
              : "Resuming re-authorises scheduled public searches for this watchlist."
          }
          submitLabel={w.status === "active" ? "Pause watchlist" : "Resume watchlist"}
          role="run"
          pending={toggle.isPending}
          error={toggle.error}
          onSubmit={(actor, rationale) => toggle.mutate({ actor, rationale })}
        />
      </td>
    </tr>
  );
}
function WatchlistDialog({ open, onOpenChange, topic }: { open: boolean; onOpenChange: (open: boolean) => void; topic: string }) {
  const { scope } = useWorkspace();
  const client = useQueryClient();
  const [label, setLabel] = useState("");
  const [watchTopic, setWatchTopic] = useState(topic);
  const [terms, setTerms] = useState("");
  const [competitors, setCompetitors] = useState("");
  const [group, setGroup] = useState<DomainGroup>("all");
  const [domains, setDomains] = useState("");
  const [cadence, setCadence] = useState(7);
  const [maxResults, setMaxResults] = useState(10);
  const [confirmed, setConfirmed] = useState(false);
  const termList = csv(terms);
  const tooLong = [...termList, ...csv(competitors)].filter((t) => t.length > 60);
  const create = useMutation({
    mutationFn: ({ actor, rationale }: { actor: string; rationale: string }) =>
      platform.createWatchlist({
        ...scope,
        topic: watchTopic,
        label: label.trim(),
        query_terms: termList,
        competitors: csv(competitors),
        domain_group: group,
        domains: csv(domains),
        cadence_days: cadence,
        max_results: maxResults,
        actor,
        rationale,
      }),
    onSuccess: () => {
      toast.success("Watchlist created and its authorisation recorded.");
      onOpenChange(false);
      setLabel("");
      setTerms("");
      setCompetitors("");
      setDomains("");
      setConfirmed(false);
      void client.invalidateQueries({ queryKey: ["watchlists"] });
    },
  });
  return (
    <GateDialog
      open={open}
      onOpenChange={onOpenChange}
      title="New watchlist"
      description={`Set up repeated public searches for ${scope.vehicle} / ${scope.market} and record why you are monitoring this topic.`}
      submitLabel="Create watchlist"
      role="run"
      pending={create.isPending}
      error={create.error}
      ready={!!label.trim() && termList.length > 0 && !tooLong.length && confirmed}
      onSubmit={(actor, rationale) => create.mutate({ actor, rationale })}
    >
      <Field label="Label">
        <input
          className="pm-input"
          value={label}
          maxLength={120}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="US forums on driving feel"
        />
      </Field>
      <div className="form-grid">
        <Field label="Topic">
          <PmSelect aria-label="Watchlist topic" value={watchTopic} onValueChange={setWatchTopic} options={topicOptions} />
        </Field>
        <Field label="Source group">
          <PmSelect
            aria-label="Source group"
            value={group}
            onValueChange={(value) => setGroup(value as DomainGroup)}
            options={["all", "press", "forums", "social", "video"].map((value) => ({ value, label: readable(value) }))}
          />
        </Field>
        <Field label="Cadence (days)">
          <input
            className="pm-input"
            type="number"
            min={1}
            max={90}
            value={cadence}
            onChange={(e) => setCadence(Math.min(90, Math.max(1, Number(e.target.value) || 1)))}
          />
        </Field>
      </div>
      <Field label="Query terms (comma-separated, public keywords only)">
        <input className="pm-input" value={terms} onChange={(e) => setTerms(e.target.value)} placeholder="steering feel, exhaust sound" />
      </Field>
      <Field label="Competitors (optional)">
        <input
          className="pm-input"
          value={competitors}
          onChange={(e) => setCompetitors(e.target.value)}
          placeholder="Mercedes-Benz E-Class, Audi A6"
        />
      </Field>
      <div className="form-grid">
        <Field label="Extra domains (optional)">
          <input className="pm-input" value={domains} onChange={(e) => setDomains(e.target.value)} placeholder="example.com" />
        </Field>
        <Field label="Results per search (1–10)">
          <input
            className="pm-input"
            type="number"
            min={1}
            max={10}
            value={maxResults}
            onChange={(e) => setMaxResults(Math.min(10, Math.max(1, Number(e.target.value) || 1)))}
          />
        </Field>
      </div>
      {!!tooLong.length && (
        <p className="muted text-xs" role="alert">
          Terms must be at most 60 characters: {tooLong.join(", ")}
        </p>
      )}
      <label className="muted text-xs">
        <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} /> These terms are public and nonpersonal. They
        contain no BMW records or customer verbatims (the server also rejects terms found in imported evidence).
      </label>
    </GateDialog>
  );
}

function SignalInbox({ topic }: { topic: string }) {
  const { scope } = useWorkspace();
  const { params } = useUrlState();
  const focus = params.get("item");
  const [status, setStatus] = useState(focus ? "all" : "unreviewed");
  const [allTopics, setAllTopics] = useState(true);
  const state = usePlatformQuery("signalItems", {
    queryKey: ["signal-items", scope.vehicle, scope.market, allTopics ? "" : topic, status],
    queryFn: ({ signal }) =>
      platform.signalItems(scope, { topic: allTopics ? undefined : topic, review_status: status === "all" ? undefined : status }, signal),
  });
  return (
    <Panel
      title="Signal inbox"
      description="Review public results from your watchlists and choose which to import as evidence."
      action={<Radar size={18} className="muted" />}
    >
      <div className="platform-toolbar">
        <PmSelect
          aria-label="Review status"
          value={status}
          onValueChange={setStatus}
          options={[
            { value: "unreviewed", label: "Unreviewed" },
            { value: "imported", label: "Imported" },
            { value: "dismissed", label: "Dismissed" },
            { value: "all", label: "All review states" },
          ]}
        />
        <PmSelect
          aria-label="Topic filter"
          value={allTopics ? "all" : "topic"}
          onValueChange={(value) => setAllTopics(value === "all")}
          options={[
            { value: "all", label: "All topics" },
            { value: "topic", label: `Only ${topicLabel(topic)}` },
          ]}
        />
      </div>
      <PlatformView
        state={state}
        isEmpty={(page) => !page.items.length}
        empty={<Empty title="Inbox clear" description="No signal items in this review state. Refresh a watchlist to search again." />}
      >
        {(page) => (
          <div className="signal-inbox">
            {[...page.items]
              .sort((a, b) => Number(b.id === focus) - Number(a.id === focus))
              .map((item) => (
                <SignalCard key={item.id} item={item} focused={item.id === focus} />
              ))}
            {page.total > page.items.length && (
              <p className="muted text-xs">
                Showing {page.items.length} of {page.total} items.
              </p>
            )}
          </div>
        )}
      </PlatformView>
    </Panel>
  );
}
function SignalCard({ item, focused }: { item: SignalItem; focused: boolean }) {
  const { base } = useWorkspace();
  const client = useQueryClient();
  const [action, setAction] = useState<"import" | "dismiss" | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const review = useMutation({
    mutationFn: ({ actor, rationale }: { actor: string; rationale: string }) =>
      action === "import" ? platform.importItem(item.id, { actor, rationale }) : platform.dismissItem(item.id, { actor, rationale }),
    onSuccess: () => {
      toast.success(action === "import" ? "Imported as unreviewed evidence." : "Signal dismissed.");
      setAction(null);
      void client.invalidateQueries({ queryKey: ["signal-items"] });
      void client.invalidateQueries({ queryKey: ["sentiment-timeseries"] });
    },
  });
  return (
    <article className={`signal-card ${focused ? "is-focused" : ""}`}>
      <div className="signal-card-top">
        <a href={item.url} target="_blank" rel="noreferrer noopener" className="text-link">
          {item.title || item.url}
          <ExternalLink size={12} />
        </a>
        <Status value={item.review_status} />
      </div>
      <small className="muted">
        {item.domain} · {topicLabel(item.topic)} ·{" "}
        {item.date_basis === "published" ? `published ${date(item.published_at)}` : `retrieved ${date(item.retrieved_at)} · publication date unknown`}
      </small>
      <p className="signal-excerpt">{item.excerpt}</p>
      <div className="signal-card-actions">
        <span className="muted text-xs">Untrusted public text · run {shortId(item.run_id)}</span>
        {item.evidence_id && <SourceLinks refs={[{ type: "evidence", id: item.evidence_id }]} />}
        {item.review_status === "unreviewed" && (
          <>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setConfirmed(false);
                setAction("import");
              }}
            >
              Import
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setAction("dismiss")}>
              Dismiss
            </Button>
          </>
        )}
        {item.reviewed_by && (
          <small className="muted">
            by {item.reviewed_by} · {date(item.reviewed_at)}
          </small>
        )}
      </div>
      <GateDialog
        open={action !== null}
        onOpenChange={(open) => !open && setAction(null)}
        title={action === "import" ? "Import signal as evidence" : "Dismiss signal"}
        description={
          action === "import"
            ? "Save this page snapshot as unreviewed evidence for the selected vehicle and market."
            : "Dismissed items stay on record with your rationale; they are never deleted."
        }
        submitLabel={action === "import" ? "Import selected signal" : "Dismiss signal"}
        role="run"
        pending={review.isPending}
        error={review.error}
        ready={action !== "import" || confirmed}
        onSubmit={(actor, rationale) => review.mutate({ actor, rationale })}
      >
        <blockquote className="signal-excerpt">{item.excerpt}</blockquote>
        {action === "import" && (
          <label className="muted text-xs">
            <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} /> I inspected the public source. Import it as
            unreviewed evidence for {base.split("/").slice(1).join(" / ").toUpperCase()}.
          </label>
        )}
      </GateDialog>
    </article>
  );
}
