"use client";
import { useState } from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { HeartHandshake, Info, SlidersHorizontal } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { date, readable } from "@/lib/api";
import { describeWrite, mergeExplanation, mergeSensitivity, platform } from "@/lib/platform-api";
import type { FactorView, Portfolio, Provider, Ranking, RankingExplanation, RankingRow, RubricState, Stability } from "@/lib/platform-types";
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
  fixed,
  shortId,
  useCapability,
  usePlatformQuery,
} from "./platform-shared";
import { Empty, Field, Grade, Heading, Panel, RequirementLink, Status } from "./shared";

const V1 = "customer-priority-v1";

export function Priorities() {
  const { scope } = useWorkspace();
  const [switching, setSwitching] = useState(false);
  const rubrics = usePlatformQuery("rubrics", {
    queryKey: ["priority-rubrics", scope.vehicle, scope.market],
    queryFn: ({ signal }) => platform.rubrics(scope, signal),
  });
  return (
    <>
      <Heading
        title="Priorities"
        description={`Ranked requirements for ${scope.vehicle} / ${scope.market}, with the evidence and calculations behind each score.`}
        action={
          <Button disabled={rubrics.unavailable || !rubrics.query.data} onClick={() => setSwitching(true)}>
            <SlidersHorizontal size={14} />
            Change scoring method
          </Button>
        }
      />
      <div className="pm-alert">
        <Info size={16} />
        <span>
          Scores use recorded data and fixed rules. Missing factors receive a neutral value of 2.5 and a “not measured” label.
        </span>
      </div>
      <Panel
        title="Active scoring method"
        description="Choose how requirements are scored. Changing the method recalculates scores and flags approved requirements for review."
      >
        <PlatformView state={rubrics}>{(state) => <RubricSummary state={state} />}</PlatformView>
      </Panel>
      <RankingPanel />
      <PortfolioPanel />
      {rubrics.query.data && <RubricDialog state={rubrics.query.data} open={switching} onOpenChange={setSwitching} />}
    </>
  );
}
function RubricSummary({ state }: { state: RubricState }) {
  const current = state.current;
  return (
    <div className="rubric-summary">
      <div>
        <span className="mono muted">Current</span>
        <strong>
          {current?.rubric_version ?? V1}
          {(!current || current.isDefault) && <small className="muted"> · default, no PM switch recorded</small>}
        </strong>
        {current && !current.isDefault && (
          <small className="muted">
            Switched by {current.actor} · {date(current.created_at)} · “{current.rationale}”
          </small>
        )}
      </div>
      {current && (
        <span className="chip-list">
          {Object.entries(current.weights).map(([factor, weight]) => (
            <span key={factor} className="chip">
              {readable(factor)} {weight.toFixed(2)}
            </span>
          ))}
        </span>
      )}
      {state.available
        .filter((r) => r.derived.length)
        .map((r) => (
          <details key={r.version} className="rubric-derived">
            <summary>How {r.version} calculates its factors</summary>
            {r.derived.map((d) => (
              <div key={d.factor} className="factor-detail">
                <strong>
                  {readable(d.factor)} <span className="mono muted">{d.methodVersion}</span>
                </strong>
                {d.formula && <code>{d.formula}</code>}
              </div>
            ))}
          </details>
        ))}
      <small className="muted">
        {state.available.length} scoring method{state.available.length === 1 ? "" : "s"} available · {state.history.length} recorded switch
        {state.history.length === 1 ? "" : "es"}
      </small>
    </div>
  );
}

function RankingPanel() {
  const { scope } = useWorkspace();
  const ranking = usePlatformQuery("ranking", {
    queryKey: ["priority-ranking", scope.vehicle, scope.market],
    queryFn: ({ signal }) => platform.ranking(scope, signal),
  });
  const derive = useCapability("deriveInputs", (actor) => platform.deriveInputs(scope, { actor }), [["priority-ranking"]]);
  const sensitivity = useCapability("sensitivity", (actor) => platform.sensitivity(scope, { actor }), [["priority-ranking"]]);
  const [provider, setProvider] = useState<Provider>("openai");
  const explain = useCapability("explain", (actor) => platform.explain(scope, { actor, provider, limit: 10 }), []);
  const explanation = explain.mutation.data as RankingExplanation | undefined;
  return (
    <Panel
      title="Ranking"
      description="Compare scores and factors, customer strengths to preserve, and how ranks change when weights vary by 20%."
      action={
        <span className="row-actions">
          <CapabilityButton capability={derive}>Calculate factors</CapabilityButton>
          <CapabilityButton capability={sensitivity}>Check rank stability</CapabilityButton>
          <PmSelect
            aria-label="Explanation provider"
            value={provider}
            onValueChange={(value) => setProvider(value as Provider)}
            options={PROVIDER_OPTIONS}
          />
          <CapabilityButton capability={explain}>Explain top 10</CapabilityButton>
        </span>
      }
    >
      <PlatformView
        state={ranking}
        isEmpty={(data) => !data.rows.length}
        empty={<Empty title="No ranked requirements" description="Generate requirements for this vehicle and market, then calculate their scoring factors." />}
      >
        {(data) => <RankingList ranking={data} sensitivity={sensitivity.mutation.data} explanation={explanation} />}
      </PlatformView>
    </Panel>
  );
}
function RankingList({ ranking, sensitivity, explanation }: { ranking: Ranking; sensitivity: unknown; explanation?: RankingExplanation }) {
  const rows = mergeExplanation(sensitivity ? mergeSensitivity(ranking.rows, sensitivity) : ranking.rows, explanation);
  const n = rows.length;
  return (
    <>
      <p className="chart-meta">
        <span className="mono">{ranking.rubricVersion ?? "scoring method not recorded"}</span>
        <MethodLabel methodVersion={ranking.methodVersion} runId={ranking.runId} />
      </p>
      {explanation?.summary && (
        <div className="ai-brief is-inline">
          <ProvenanceLabel value={explanation.provenance} />
          <p>{explanation.summary}</p>
        </div>
      )}
      {ranking.warnings.map((warning) => (
        <div key={warning} className="pm-alert attention">
          <Info size={16} />
          <span>{warning}</span>
        </div>
      ))}
      <div className="ranking-list">
        {rows.map((row, index) => (
          <RankingItem key={row.requirementId} row={row} position={row.rank ?? index + 1} count={n} />
        ))}
      </div>
    </>
  );
}
function RankingItem({ row, position, count }: { row: RankingRow; position: number; count: number }) {
  const contributions = row.factors.every((f) => f.contribution !== null) ? row.factors : [];
  const contributionTotal = contributions.reduce((sum, f) => sum + (f.contribution ?? 0), 0);
  return (
    <article className="ranking-item">
      <div className="ranking-rank">
        <span className="rank-number">{position}</span>
        <StabilityBand stability={row.stability} count={count} />
      </div>
      <div className="ranking-main">
        <div className="ranking-title">
          {row.key && <span className="requirement-key">{row.key}</span>}
          <RequirementLink id={row.requirementId} tab="score">
            {row.title}
          </RequirementLink>
          {row.status && <Status value={row.status} />}
          {row.needsReview && <Status value="needs_review" />}
        </div>
        <small className="muted">
          {row.topic ? readable(row.topic) : "Topic not stated"}
          {row.rubricVersion && ` · scored with ${row.rubricVersion}`}
          {row.v2PreviewTotal !== null && ` · v2 preview ${fixed(row.v2PreviewTotal)} (not stored)`}
        </small>
        {contributions.length > 0 && contributionTotal > 0 && (
          <div className="contribution-bar" aria-label="Factor contributions to the score">
            {contributions.map((f, i) => (
              <span
                key={f.name}
                className={f.notMeasured ? "not-measured" : ""}
                style={{ width: `${((f.contribution ?? 0) / contributionTotal) * 100}%`, opacity: 1 - (i % 4) * 0.18 }}
                title={`${readable(f.name)}: ${fixed(f.contribution, 2)}`}
              />
            ))}
          </div>
        )}
        <div className="factor-chips">
          {row.factors.map((f) => (
            <DerivationPopover key={f.name} factor={f} />
          ))}
        </div>
        {row.preserveWarnings.map((w, i) => (
          <div key={i} className="preserve-warning">
            <HeartHandshake size={14} />
            <span>
              {w.label && <strong>{w.label}: </strong>}
              {w.message || "Preserve this attribute that customers value."}
            </span>
            {!!w.evidenceIds.length && <SourceLinks refs={w.evidenceIds.map((id) => ({ type: "evidence", id }))} />}
          </div>
        ))}
        {row.explanation && (
          <div className="ai-brief is-inline">
            <ProvenanceLabel value={row.explanation.provenance} />
            <p>{row.explanation.text}</p>
            {!!row.explanation.citedIds.length && <small className="muted mono">Cites {row.explanation.citedIds.map(shortId).join(", ")}</small>}
          </div>
        )}
      </div>
      <div className="ranking-score">
        <span className="tabular-nums">{fixed(row.total)}</span>
        {row.evidenceGrade && <Grade value={row.evidenceGrade} />}
      </div>
    </article>
  );
}
function StabilityBand({ stability, count }: { stability: Stability | null; count: number }) {
  if (!stability || stability.minRank === null || stability.maxRank === null)
    return (
      <small className="muted stability-label" title={stability?.reason ?? undefined}>
        {stability?.reason ? "Stability outdated" : "Stability not computed"}
      </small>
    );
  const span = Math.max(1, count - 1);
  const left = ((stability.minRank - 1) / span) * 100;
  const width = Math.max(4, ((stability.maxRank - stability.minRank) / span) * 100);
  const dot = stability.rank === null ? null : ((stability.rank - 1) / span) * 100;
  return (
    <span className="stability" title={`Rank ${stability.minRank}–${stability.maxRank} when scoring weights change`}>
      <span className="stability-track">
        <span
          className={`stability-band ${stability.stable ? "is-stable" : "is-sensitive"}`}
          style={{ left: `${left}%`, width: `${Math.min(100 - left, width)}%` }}
        />
        {dot !== null && <span className="stability-dot" style={{ left: `${dot}%` }} />}
      </span>
      <small className={stability.stable ? "stability-label" : "stability-label attention-text"}>
        {stability.stable === null ? "" : stability.stable ? "Stable" : "Sensitive"} · {stability.minRank}–{stability.maxRank}
        {!stability.current && " · outdated"}
      </small>
    </span>
  );
}
function DerivationPopover({ factor: f }: { factor: FactorView }) {
  return (
    <Popover>
      <PopoverTrigger className={`factor-chip ${f.notMeasured ? "not-measured" : ""}`}>
        <span>{readable(f.name)}</span>
        <b className="tabular-nums">{f.value === null ? "–" : f.value.toFixed(1)}</b>
        {f.notMeasured && <small>Not measured</small>}
      </PopoverTrigger>
      <PopoverContent className="derivation-popover" align="start">
        <strong>{readable(f.name)}</strong>
        <dl className="record-details">
          <div>
            <dt>Value (0–5)</dt>
            <dd>
              {f.value === null ? "Not recorded" : f.value.toFixed(2)}
              {f.notMeasured && " · neutral, not measured"}
            </dd>
          </div>
          <div>
            <dt>Weight</dt>
            <dd>{f.weight === null ? "Not recorded" : f.weight.toFixed(2)}</dd>
          </div>
          {f.contribution !== null && (
            <div>
              <dt>Contribution</dt>
              <dd>{f.contribution.toFixed(2)}</dd>
            </div>
          )}
        </dl>
        {f.formula && <code className="derivation-formula">{f.formula}</code>}
        {Object.keys(f.inputs).length > 0 && <pre className="json-record">{JSON.stringify(f.inputs, null, 2)}</pre>}
        {!!f.notes.length && <p className="muted text-xs">{f.notes.join(" · ")}</p>}
        <SourceLinks refs={f.sources} />
        {(f.methodVersion || f.runId) && <MethodLabel methodVersion={f.methodVersion} runId={f.runId} />}
      </PopoverContent>
    </Popover>
  );
}

function RubricDialog({ state, open, onOpenChange }: { state: RubricState; open: boolean; onOpenChange: (open: boolean) => void }) {
  const { scope } = useWorkspace();
  const client = useQueryClient();
  const initial = state.available.find((r) => r.version !== (state.current?.rubric_version ?? V1)) ?? state.available[0];
  const [version, setVersion] = useState(initial?.version ?? "");
  const definition = state.available.find((r) => r.version === version);
  const [weights, setWeights] = useState<Record<string, string>>(() =>
    Object.fromEntries(Object.entries(definition?.weights ?? {}).map(([k, v]) => [k, String(v)])),
  );
  const parsed = Object.fromEntries(Object.entries(weights).map(([k, v]) => [k, Number(v)]));
  const sum = Object.values(parsed).reduce((a, b) => a + b, 0);
  const valid = Object.keys(parsed).length > 0 && Object.values(parsed).every((v) => Number.isFinite(v) && v >= 0) && Math.abs(sum - 1) <= 0.001;
  const change = useMutation({
    mutationFn: ({ actor, rationale }: { actor: string; rationale: string }) =>
      platform.switchRubric({ ...scope, rubric_version: version, weights: parsed, actor, rationale }),
    onSuccess: (value) => {
      toast.success(`Scoring method updated. ${describeWrite(value)}`);
      onOpenChange(false);
      for (const key of [["priority-rubrics"], ["priority-ranking"], ["requirements"], ["metrics"], ["workspace"]])
        void client.invalidateQueries({ queryKey: key });
    },
  });
  return (
    <GateDialog
      open={open}
      onOpenChange={onOpenChange}
      title={`Change scoring method for ${scope.vehicle} / ${scope.market}`}
      description="Recalculate current scores using this method and its weights. Approved requirements with changed scores return to review."
      submitLabel="Change scoring method"
      role="score"
      pending={change.isPending}
      error={change.error}
      ready={!!version && valid}
      onSubmit={(actor, rationale) => change.mutate({ actor, rationale })}
    >
      <Field label="Scoring method">
        <PmSelect
          aria-label="Scoring method version"
          value={version}
          onValueChange={(next) => {
            setVersion(next);
            const def = state.available.find((r) => r.version === next);
            setWeights(Object.fromEntries(Object.entries(def?.weights ?? {}).map(([k, v]) => [k, String(v)])));
          }}
          options={state.available.map((r) => ({ value: r.version, label: r.version }))}
        />
        {state.available.find((r) => r.version === version)?.description ? (
          <span className="field-hint">{state.available.find((r) => r.version === version)?.description}</span>
        ) : null}
      </Field>
      {Object.keys(weights).length ? (
        <div className="weight-grid">
          {Object.entries(weights).map(([factor, value]) => (
            <Field key={factor} label={readable(factor)}>
              <input
                className="pm-input"
                type="number"
                min={0}
                max={1}
                step={0.01}
                value={value}
                onChange={(e) => setWeights({ ...weights, [factor]: e.target.value })}
              />
            </Field>
          ))}
        </div>
      ) : (
        <p className="muted text-xs">No default weights are available for this scoring method.</p>
      )}
      <p className={`text-xs ${valid ? "muted" : "attention-text"}`}>
        Weights sum to {Number.isFinite(sum) ? sum.toFixed(3) : "–"}; they must sum to 1.
      </p>
      {state.current && (
        <p className="muted text-xs">
          Current: {state.current.rubric_version} since {date(state.current.created_at)} (switch {shortId(state.current.id)}).
        </p>
      )}
    </GateDialog>
  );
}

/** GET /priorities/portfolio: which topics look global and which market-specific (a hint, not a decision). */
function PortfolioPanel() {
  const { scope } = useWorkspace();
  const state = usePlatformQuery("portfolio", {
    queryKey: ["priority-portfolio", scope.vehicle],
    queryFn: ({ signal }) => platform.portfolio(scope.vehicle, signal),
  });
  return (
    <Panel
      title={`Priorities across markets · ${scope.vehicle}`}
      description="Compare v2 topic scores, sales-weighted demand and open market conflicts. Markets using v1 show a v2 preview."
    >
      <PlatformView
        state={state}
        isEmpty={(data) => !data.topics.length}
        empty={<Empty title="No requirements for this vehicle" description="Generate requirements in at least one market to see the portfolio." />}
      >
        {(data) => <PortfolioTable data={data} />}
      </PlatformView>
    </Panel>
  );
}
function PortfolioTable({ data }: { data: Portfolio }) {
  return (
    <>
      <p className="chart-meta">
        <MethodLabel methodVersion={data.methodVersion} />
        <span className="muted">
          Shares:{" "}
          {data.shareBasis === "market_weights" ? `sales weights${data.sharesPeriod ? ` ${data.sharesPeriod}` : ""}` : "equal (no sales weights)"}
        </span>
      </p>
      {data.warnings.map((warning) => (
        <div key={warning} className="pm-alert attention">
          <Info size={16} />
          <span>{warning}</span>
        </div>
      ))}
      <div className="pm-table-wrap">
        <table className="pm-table market-table portfolio-table">
          <thead>
            <tr>
              <th className="pin-column">Topic</th>
              {data.markets.map((m) => (
                <th key={m}>
                  {m}
                  <small>
                    {data.marketShares[m] !== undefined ? `share ${(data.marketShares[m] * 100).toFixed(0)}%` : "no sales share"}
                    {data.rubrics[m] && ` · ${data.rubrics[m]}`}
                  </small>
                </th>
              ))}
              <th>Global demand</th>
            </tr>
          </thead>
          <tbody>
            {data.topics.map((t) => (
              <tr key={t.topic}>
                <td className="pin-column">
                  <strong>{t.label ?? readable(t.topic)}</strong>
                  {t.pattern && <small>Pattern hint: {readable(t.pattern)}</small>}
                  {!!t.conflicts.length && (
                    <small>
                      {t.conflicts.map((c) => (
                        <Link
                          key={c.id}
                          className="text-link"
                          href={`/${data.vehicle.toLowerCase()}/${(data.markets[0] ?? "us").toLowerCase()}/markets?conflict=${encodeURIComponent(c.id)}`}
                        >
                          {c.severity} {readable(c.conflictType)} ({c.markets.join("/")})
                        </Link>
                      ))}
                    </small>
                  )}
                </td>
                {data.markets.map((m) => {
                  const cell = t.cells[m];
                  return (
                    <td key={m}>
                      {cell ? (
                        <Link
                          className="market-cell"
                          href={`/${data.vehicle.toLowerCase()}/${m.toLowerCase()}/requirements?requirement=${encodeURIComponent(cell.requirementId)}`}
                        >
                          <span className="tabular-nums portfolio-total">{fixed(cell.v2Total)}</span>
                          <small>
                            {cell.v2Basis === "preview"
                              ? `v2 preview · stored ${cell.rubricVersion ?? "score"} ${fixed(cell.total)}`
                              : "current v2 score"}
                            {!!cell.notMeasured.length && ` · not measured: ${cell.notMeasured.map(readable).join(", ")}`}
                          </small>
                          {cell.status && <Status value={cell.status} />}
                        </Link>
                      ) : (
                        <span className="market-missing">No requirement</span>
                      )}
                    </td>
                  );
                })}
                <td>
                  {t.demandMeasured && t.globalDemandIndex !== null ? (
                    <span className="tabular-nums">{fixed(t.globalDemandIndex, 2)}</span>
                  ) : (
                    <span className="market-missing">Not measured</span>
                  )}
                  {!!t.demandFlags.length && <small className="muted">{t.demandFlags.map(readable).join(", ")}</small>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.patternRule && <p className="muted text-xs">{data.patternRule}</p>}
    </>
  );
}
