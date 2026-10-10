"use client";
import Link from "next/link";
import { ArrowUpRight, Info } from "lucide-react";
import { fmt } from "@/lib/api";
import { useWorkspace } from "./context";
import { Empty, ScoreLabel, Status } from "./shared";

export function Overview() {
  const { base, scope, requirements, metrics } = useWorkspace();
  const lead = [...requirements].sort((a, b) => b.priority - a.priority)[0];
  const counts = metrics?.counts || {};
  const coverage = metrics?.traceability;
  const cards = [
    {
      label: "Evidence records",
      value: counts.evidence || 0,
      note: "Original customer feedback",
      href: `${base}/evidence`,
    },
    {
      label: "Analysed findings",
      value: counts.findings || 0,
      note: "Customer signals",
      href: `${base}/evidence?mode=findings`,
    },
    {
      label: "Requirements",
      value: counts.requirements || 0,
      note: "Ranked PM proposals",
      href: `${base}/requirements`,
    },
  ];

  return (
    <>
      <section className="overview-intro demo-hero" aria-labelledby="overview-title">
        <div className="overview-intro-copy">
          <p className="overview-eyebrow">Precision in every decision</p>
          <h1 id="overview-title">Evidence to decision</h1>
          <p className="overview-description">
            Follow one customer need from original feedback to a prioritized
            requirement and a human decision.
          </p>
        </div>
        <span className="hero-scope">
          {scope.vehicle} / {scope.market}
          <small>SUCCESSOR PLANNING</small>
        </span>
      </section>

      <div className="metric-grid demo-metrics" style={{ "--metric-count": 3 } as React.CSSProperties}>
        {cards.map((card) => (
          <Link key={card.label} href={card.href} className="metric-cell metric-link">
            <h2 className="metric-label">{card.label}</h2>
            <p className="metric-value">{fmt(card.value)}</p>
            <span className="metric-comparison">
              <span className="metric-comparison-label">{card.note}</span>
              <ArrowUpRight size={13} />
            </span>
          </Link>
        ))}
      </div>

      <section className="pm-panel demo-focus" aria-labelledby="demo-focus-title">
        <div className="demo-focus-topline">
          <span className="mono">Highest current priority</span>
          {lead && <Status value={lead.status} />}
        </div>
        {lead ? (
          <>
            <div className="demo-focus-main">
              <div>
                <p className="requirement-key">{lead.key}</p>
                <h2 id="demo-focus-title">{lead.title}</h2>
                <p className="demo-focus-description">
                  Review the customer need, the exact source trace, and the
                  scoring basis before making a PM decision.
                </p>
              </div>
              <div className="demo-focus-score">
                <ScoreLabel score={lead.priority} grade={lead.evidence_grade} />
                <span>Priority / evidence grade</span>
              </div>
            </div>
            <div className="demo-focus-actions">
              <Link className="demo-primary-action" href={`${base}/requirements?requirement=${lead.id}`}>
                Open requirement <ArrowUpRight size={15} />
              </Link>
              <Link className="text-link" href={`${base}/requirements?requirement=${lead.id}&tab=evidence`}>
                Inspect source trace <ArrowUpRight size={14} />
              </Link>
            </div>
          </>
        ) : (
          <Empty title="No requirements in this scope" description="Import evidence and run analysis to prepare a proposal." />
        )}
      </section>

      <div className="demo-trace-note">
        <Info size={17} />
        <p>
          <strong>
            {coverage?.requirements_with_source_links || 0} of {coverage?.requirements || 0}
          </strong>{" "}
          current requirements link to source records. Links show provenance;
          priority and evidence quality still need separate PM review.
          {scope.vehicle === "G60" && scope.market === "US" && (
            <span className="source-concentration-note">
              In the supplied G60 / US inventory, 72.7% of unique feedback IDs
              come from Source B. Sample counts are not market prevalence.
            </span>
          )}
        </p>
        <Link href={`${base}/evidence`}>Explore evidence <ArrowUpRight size={13} /></Link>
      </div>
    </>
  );
}
