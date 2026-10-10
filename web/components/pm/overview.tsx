"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowUpRight,
  ShieldCheck,
  Info,
  GitBranch,
  ChevronRight,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { MotionField } from "@/components/motion-field";
import { useWorkspace } from "./context";
import {
  Panel,
  MoreLink,
  RequirementLink,
  ScoreLabel,
  Status,
  Empty,
  ErrorMessage,
} from "./shared";
import { allPages, query, fmt } from "@/lib/api";
import type { Finding } from "@/lib/types";
export function Overview() {
  const { base, scope, requirements, metrics, sources } = useWorkspace();
  const findings = useQuery({
    queryKey: ["findings", query(scope)],
    queryFn: ({ signal }) =>
      allPages<Finding>(`/findings?${query(scope)}`, signal),
  });
  const counts = metrics?.counts || {};
  const groups = ["problem", "need", "strength", "context"].map((kind) => ({
    kind,
    count: findings.data?.filter((f) => f.kind === kind).length || 0,
  }));
  const ranked = requirements.map((r, i) => ({
    ...r,
    rank: i + 1,
    short: r.key.split("-").at(-1),
  }));
  const cards = [
    {
      label: "Requirements",
      value: counts.requirements || 0,
      note: "Current scoped proposals",
      href: `${base}/requirements`,
    },
    {
      label: "Evidence records",
      value: counts.evidence || 0,
      note: `Across ${sources.length} imported ${sources.length === 1 ? "source" : "sources"}`,
      href: `${base}/evidence`,
    },
    {
      label: "Approved",
      value: metrics?.requirement_statuses.approved || 0,
      note: "Human decisions recorded",
      href: `${base}/requirements?status=approved`,
    },
    {
      label: "Needs review",
      value: counts.open_reviews || 0,
      note: "Open evidence change alerts",
      href: `${base}/reviews`,
    },
  ];
  return (
    <>
      <section className="overview-intro" aria-labelledby="overview-title">
        <MotionField />
        <div className="overview-intro-copy">
          <p className="overview-eyebrow">Precision in every decision</p>
          <h1 id="overview-title">Overview</h1>
          <p className="overview-description">
            From customer evidence to your next generation of product decisions.
          </p>
        </div>
        <span className="hero-scope">
          {scope.vehicle} / {scope.market}
          <small>SUCCESSOR PLANNING</small>
        </span>
      </section>
      <div className="overview-toolbar">
        <h2>Portfolio performance</h2>
        <MoreLink href={`${base}/pipeline`}>Open pipeline</MoreLink>
      </div>
      <div>
        <div
          className="metric-grid"
          style={{ "--metric-count": 4 } as React.CSSProperties}
        >
          {cards.map((card) => (
            <Link
              key={card.label}
              href={card.href}
              className="metric-cell metric-link"
            >
              <h3 className="metric-label">{card.label}</h3>
              <p className="metric-value">{fmt(card.value)}</p>
              <span className="metric-comparison">
                <span className="metric-comparison-label">{card.note}</span>
                <ArrowUpRight size={13} />
              </span>
            </Link>
          ))}
        </div>
        <p className="metric-note">
          Counts reflect {scope.vehicle} / {scope.market} records in this
          workspace. Priority and evidence quality are assessed separately.
        </p>
      </div>
      <Panel
        title="Priority landscape"
        description="Current requirements, ordered by recorded priority. Select a requirement below to inspect its scoring and evidence."
        action={<span className="panel-meta">SCORE / 100</span>}
      >
        {ranked.length ? (
          <div className="priority-chart">
            <ResponsiveContainer width="100%" height={255}>
              <AreaChart
                data={ranked}
                margin={{ top: 12, right: 14, left: -15, bottom: 0 }}
              >
                <defs>
                  <linearGradient
                    id="priority-fill"
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop offset="0%" stopColor="#1c69d4" stopOpacity={0.2} />
                    <stop
                      offset="100%"
                      stopColor="#1c69d4"
                      stopOpacity={0.035}
                    />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  strokeDasharray="3 5"
                  vertical={false}
                  stroke="var(--border)"
                />
                <XAxis
                  dataKey="short"
                  tickLine={false}
                  axisLine={false}
                  tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
                  tickFormatter={(v) => `REQ ${v}`}
                />
                <YAxis
                  domain={[0, 100]}
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    const r = payload?.[0]?.payload;
                    return active && r ? (
                      <div className="chart-tooltip">
                        <strong>{r.title}</strong>
                        <span>
                          Priority {r.priority.toFixed(1)} · Evidence{" "}
                          {r.evidence_grade}
                        </span>
                        <small>{r.key}</small>
                      </div>
                    ) : null;
                  }}
                />
                <Area
                  type="linear"
                  dataKey="priority"
                  stroke="#1c69d4"
                  strokeWidth={2}
                  fill="url(#priority-fill)"
                  dot={{ r: 3, fill: "var(--card)", strokeWidth: 2 }}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <Empty />
        )}
        <div className="priority-shortlist">
          {ranked.slice(0, 4).map((r) => (
            <div key={r.id}>
              <span className="rank-number">0{r.rank}</span>
              <RequirementLink id={r.id}>{r.title}</RequirementLink>
              <ScoreLabel score={r.priority} grade={r.evidence_grade} />
            </div>
          ))}
        </div>
      </Panel>
      <div className="overview-two-col">
        <Panel
          title="From evidence to decision"
          description="One traceable chain, with a human decision at the end."
          action={<GitBranch size={18} className="text-muted-foreground" />}
        >
          <div className="pipeline-summary">
            {[
              { title: "Sources", value: counts.sources || 0, path: "sources" },
              {
                title: "Evidence",
                value: counts.evidence || 0,
                path: "evidence",
              },
              {
                title: "Findings",
                value: counts.findings || 0,
                path: "evidence?mode=findings",
              },
              {
                title: "Requirements",
                value: counts.requirements || 0,
                path: "requirements",
              },
              {
                title: "Decisions",
                value: counts.decisions || 0,
                path: "audit",
              },
            ].map((item, i) => (
              <Link key={item.title} href={`${base}/${item.path}`}>
                <span className="stage-index">0{i + 1}</span>
                <strong>{fmt(item.value)}</strong>
                <span>{item.title}</span>
                <ChevronRight size={13} />
              </Link>
            ))}
          </div>
          <div className="panel-bottom">
            <ShieldCheck size={16} />
            <span>
              Approvals preserve exact requirement and score versions.
            </span>
          </div>
        </Panel>
        <Panel
          title="Evidence coverage"
          description="Linked sources support traceability, not a claim of semantic accuracy."
          action={<MoreLink href={`${base}/sources`}>Inspect</MoreLink>}
        >
          <div className="coverage-number">
            {metrics?.traceability.coverage == null
              ? "No requirements"
              : `${Math.round(metrics.traceability.coverage * 100)}%`}
            <span>
              {metrics?.traceability.requirements_with_source_links || 0} of{" "}
              {requirements.length} current requirements have supporting source
              links
            </span>
          </div>
          <div className="pm-alert">
            <Info size={16} />
            <span>
              {scope.vehicle === "G60" && scope.market === "US"
                ? "The supplied G60 / US feedback inventory attributes 72.7% of unique feedback IDs to Source B. This sample is uneven."
                : "Source counts and provenance labels do not establish representative market coverage."}
            </span>
          </div>
        </Panel>
      </div>
      <div className="overview-two-col">
        <Panel
          title="Customer signals"
          description="All persisted findings in this scope, including earlier analysis runs."
          action={
            <MoreLink href={`${base}/evidence?mode=findings`}>Explore</MoreLink>
          }
        >
          {findings.error ? (
            <ErrorMessage error={findings.error} />
          ) : (
            <div className="signal-list">
              {groups.map((g) => (
                <Link
                  key={g.kind}
                  href={`${base}/evidence?mode=findings&kind=${g.kind}`}
                >
                  <span className={`signal-mark ${g.kind}`} />
                  <span>
                    {g.kind === "strength"
                      ? "Loves to preserve"
                      : g.kind === "problem"
                        ? "Pains to fix"
                        : g.kind === "need"
                          ? "Needs to address"
                          : "Market context"}
                  </span>
                  <strong>{g.count}</strong>
                  <ArrowUpRight size={14} />
                </Link>
              ))}
            </div>
          )}
        </Panel>
        <Panel
          title="Your decision queue"
          description="Highest-priority proposals awaiting a PM decision."
          action={
            <MoreLink href={`${base}/requirements?status=proposed`}>
              View register
            </MoreLink>
          }
        >
          {requirements
            .filter((r) => !["approved", "rejected"].includes(r.status))
            .slice(0, 4)
            .map((r) => (
              <div className="decision-queue-row" key={r.id}>
                <div>
                  <RequirementLink id={r.id}>{r.title}</RequirementLink>
                  <small>{r.key}</small>
                </div>
                <Status value={r.status} />
              </div>
            ))}
          {!requirements.some(
            (r) => !["approved", "rejected"].includes(r.status),
          ) && (
            <Empty
              title="Your queue is clear"
              description="New proposals and evidence changes will appear here."
            />
          )}
        </Panel>
      </div>
    </>
  );
}
