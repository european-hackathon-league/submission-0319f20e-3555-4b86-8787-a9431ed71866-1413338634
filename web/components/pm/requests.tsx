"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Info, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { allPages, date, readable } from "@/lib/api";
import { clusterRequests, platform, sortByTriage } from "@/lib/platform-api";
import {
  MARKETS,
  REQUEST_DECISIONS,
  type IntakeRequest,
  type Provider,
  type RequestAggregates,
  type RequestDetail,
  type RequestLink,
  type Triage,
} from "@/lib/platform-types";
import type { Requirement } from "@/lib/types";
import { useWorkspace } from "./context";
import { PmSelect } from "./pm-select";
import {
  CapabilityButton,
  FactorBars,
  GateDialog,
  MethodLabel,
  PROVIDER_OPTIONS,
  PlatformView,
  ProvenanceLabel,
  SimulatedBadge,
  SourceLinks,
  fixed,
  shortId,
  useCapability,
  usePlatformQuery,
} from "./platform-shared";
import { Empty, ErrorMessage, Field, Heading, Loading, Panel, Status, useUrlState } from "./shared";

const DECISION_HELP: Record<string, string> = {
  convert: "Creates a requirement proposal (or a new version of the existing vehicle × market × topic requirement) linked back to this request. It still needs PM approval.",
  link: "Links the request to an existing requirement it is already covered by.",
  decline: "Declines the request with your rationale; the regional PM can read why.",
  defer: "Keeps the request open for a later planning round.",
};
const ENTITY_TYPE: Record<string, string> = { market_conflict: "market_conflict", requirement: "requirement", finding: "finding", evidence: "evidence" };
const top = (counts: Record<string, number>, n = 3) =>
  Object.entries(counts)
    .sort(([a, x], [b, y]) => y - x || a.localeCompare(b))
    .slice(0, n);

export function Requests() {
  const { scope } = useWorkspace();
  const { params, set } = useUrlState();
  const market = params.get("rmarket") || "";
  const status = params.get("rstatus") || "";
  const selected = params.get("request") || "";
  const [provider, setProvider] = useState<Provider>("openai");
  const invalidate = [["requests"], ["request"], ["request-aggregates"]];
  const simulated = useCapability("simulatedRequests", (actor) => platform.loadSimulated({ actor }), invalidate);
  const cluster = useCapability("cluster", (actor) => platform.cluster(scope.vehicle, { actor, provider }), invalidate);
  const triage = useCapability("triage", (actor) => platform.triage(scope.vehicle, { actor, market: market || undefined }), invalidate);
  const state = usePlatformQuery("requests", {
    queryKey: ["requests", scope.vehicle, market, status],
    queryFn: ({ signal }) => platform.requests(scope.vehicle, { market: market || undefined, status: status || undefined }, signal),
  });
  return (
    <>
      <Heading
        title="Requests"
        description={`Inbound asks for ${scope.vehicle} from markets, dealers, engineering and sales, ranked by a deterministic triage score that prepares your position.`}
        action={<CapabilityButton capability={simulated}>Load simulated requests</CapabilityButton>}
      />
      <div className="pm-alert">
        <Info size={16} />
        <span>
          Triage ranks and drafts; it does not decide. Convert, link, decline and defer are human decisions. Pricing, homologation, engineering
          specifications and supplier asks are flagged as out of scope rather than processed.
        </span>
      </div>
      <AggregateTiles market={market} />
      <div className="platform-toolbar">
        <PmSelect
          aria-label="Request market"
          value={market}
          onValueChange={(value) => set({ rmarket: value || undefined })}
          options={[{ value: "", label: "All markets" }, ...MARKETS.map((m) => ({ value: m, label: m }))]}
        />
        <PmSelect
          aria-label="Request status"
          value={status}
          onValueChange={(value) => set({ rstatus: value || undefined })}
          options={[{ value: "", label: "All statuses" }, ...["new", "triaged", "linked", "converted", "declined", "deferred"].map((v) => ({ value: v, label: readable(v) }))]}
        />
        <span className="toolbar-spacer" />
        <PmSelect aria-label="Clustering provider" value={provider} onValueChange={(value) => setProvider(value as Provider)} options={PROVIDER_OPTIONS} />
        <CapabilityButton capability={cluster}>Cluster</CapabilityButton>
        <CapabilityButton capability={triage}>Triage</CapabilityButton>
      </div>
      <div className="requests-layout">
        <Panel title="Inbox" description="Sorted by triage score (untriaged last, then oldest first).">
          <PlatformView
            state={state}
            isEmpty={(page) => !page.items.length}
            empty={<Empty title="No requests" description="Load the simulated set or create requests through the API to start triage." />}
          >
            {(page) => (
              <div className="request-inbox">
                {sortByTriage(page.items).map((r) => (
                  <RequestRow key={r.id} request={r} active={r.id === selected} onSelect={() => set({ request: r.id })} />
                ))}
                {page.total > page.items.length && <p className="muted text-xs">Showing {page.items.length} of {page.total} requests.</p>}
              </div>
            )}
          </PlatformView>
        </Panel>
        {selected ? (
          <RequestDetailPanel key={selected} id={selected} onClose={() => set({ request: undefined })} />
        ) : (
          <Panel title="Clusters" description="Requests the clustering run grouped together within a vehicle and topic.">
            <PlatformView state={state} isEmpty={(page) => !page.items.some((r) => r.cluster_id)} empty={<Empty title="No clusters yet" description="Run clustering to group recurring asks across markets." />}>
              {(page) => (
                <div className="cluster-list">
                  {clusterRequests(page.items).map((c) => (
                    <article key={c.id}>
                      <div>
                        <strong>{c.title}</strong>
                        <small className="muted">
                          {c.requests.length} requests · {c.markets.join(", ")}
                          {c.topic && ` · ${readable(c.topic)}`}
                        </small>
                      </div>
                      <span className="chip-list">
                        {c.requests.map((r) => (
                          <button key={r.id} type="button" className="chip" onClick={() => set({ request: r.id })}>
                            {r.key || shortId(r.id)}
                          </button>
                        ))}
                      </span>
                    </article>
                  ))}
                </div>
              )}
            </PlatformView>
          </Panel>
        )}
      </div>
    </>
  );
}

function AggregateTiles({ market }: { market: string }) {
  const { scope } = useWorkspace();
  const state = usePlatformQuery("aggregates", {
    queryKey: ["request-aggregates", scope.vehicle, market],
    queryFn: ({ signal }) => platform.aggregates(scope.vehicle, market || undefined, signal),
  });
  return (
    <PlatformView state={state} compact>
      {(a: RequestAggregates) => {
        const total = a.total ?? (Object.keys(a.byStatus).length ? Object.values(a.byStatus).reduce((x, y) => x + y, 0) : null);
        return (
          <div className="metric-grid request-tiles" style={{ "--metric-count": 4 } as React.CSSProperties}>
            <div className="metric-cell">
              <h2 className="metric-label">Requests</h2>
              <p className="metric-value">{total ?? "–"}</p>
              <span className="muted text-xs">{top(a.byStatus, 4).map(([k, v]) => `${readable(k)} ${v}`).join(" · ") || "No status counts"}</span>
            </div>
            <div className="metric-cell">
              <h2 className="metric-label">By market</h2>
              <ul className="tile-list">
                {top(a.byMarket, 4).map(([k, v]) => (
                  <li key={k}><span>{k}</span><b>{v}</b></li>
                ))}
              </ul>
              {!Object.keys(a.byMarket).length && <span className="muted text-xs">No market counts</span>}
            </div>
            <div className="metric-cell">
              <h2 className="metric-label">By topic · demand index</h2>
              <ul className="tile-list">
                {top(a.byTopic, 4).map(([k, v]) => (
                  <li key={k}>
                    <span>{readable(k)}</span>
                    <b>{v}{a.demandIndex[k] !== undefined && <small> · {fixed(a.demandIndex[k], 2)}</small>}</b>
                  </li>
                ))}
              </ul>
              {!Object.keys(a.byTopic).length && <span className="muted text-xs">No topic counts</span>}
            </div>
            <div className="metric-cell">
              <h2 className="metric-label">SLA breaches</h2>
              <p className={`metric-value ${a.slaBreaches ? "attention-text" : ""}`}>{a.slaBreaches ?? "–"}</p>
              <span className="muted text-xs">Untriaged after 14 days · median age {a.medianAgeDays === null ? "–" : `${fixed(a.medianAgeDays)} days`}</span>
            </div>
          </div>
        );
      }}
    </PlatformView>
  );
}

function RequestRow({ request: r, active, onSelect }: { request: IntakeRequest; active: boolean; onSelect: () => void }) {
  return (
    <button type="button" className={`request-row ${active ? "is-active" : ""}`} aria-pressed={active} onClick={onSelect}>
      <span className="request-row-top">
        <span className="requirement-key">{r.key}</span>
        {r.simulated && <SimulatedBadge />}
        <Status value={r.status} />
        <span className="request-score tabular-nums" title="Triage total">
          {r.triage?.total === null || r.triage?.total === undefined ? "Not triaged" : fixed(r.triage.total, 2)}
        </span>
      </span>
      <strong>{r.title}</strong>
      <small className="muted">
        {r.market} · {readable(r.origin_type)}
        {r.origin_name && ` (${r.origin_name})`} · {r.topic ? readable(r.topic) : "topic not assigned"} · {date(r.requested_at)}
      </small>
      {!!r.scope_flags.length && (
        <span className="chip-list">
          {r.scope_flags.map((flag) => (
            <span key={flag} className="chip is-attention">Out of scope: {readable(flag)}</span>
          ))}
        </span>
      )}
      {r.triage && !!r.triage.factors.length && <FactorBars factors={r.triage.factors} compact />}
    </button>
  );
}

function RequestDetailPanel({ id, onClose }: { id: string; onClose: () => void }) {
  const state = usePlatformQuery("request", {
    queryKey: ["request", id],
    queryFn: ({ signal }) => platform.request(id, signal),
  });
  return (
    <Panel title="Request detail" description="The request as submitted, its triage breakdown and the evidence for and against." action={<Button variant="ghost" size="sm" onClick={onClose}>Close</Button>}>
      <PlatformView state={state}>{(detail) => <RequestBody detail={detail} />}</PlatformView>
    </Panel>
  );
}
function RequestBody({ detail }: { detail: RequestDetail }) {
  const { request: r } = detail;
  const [deciding, setDeciding] = useState(false);
  const forLinks = detail.links.filter((l) => l.relation === "supports" || l.relation === "addresses");
  const againstLinks = detail.links.filter((l) => l.relation === "conflicts");
  const duplicates = detail.links.filter((l) => l.relation === "duplicates");
  const final = ["converted", "declined", "linked"].includes(r.status);
  return (
    <div className="request-detail">
      <div className="request-detail-top">
        <span className="requirement-key">{r.key}</span>
        {r.simulated && <SimulatedBadge />}
        <Status value={r.status} />
        <span className="toolbar-spacer" />
        <Button disabled={final} title={final ? "A terminal decision is recorded" : undefined} onClick={() => setDeciding(true)}>
          Decide
        </Button>
      </div>
      <h3>{r.title}</h3>
      <p className="muted text-xs">
        {r.vehicle} / {r.market} · {readable(r.origin_type)} {r.origin_name && `· ${r.origin_name}`} · requested {date(r.requested_at)} · created by {r.created_by}
      </p>
      <blockquote className="request-body">{r.body}</blockquote>
      {!!r.scope_flags.length && (
        <div className="pm-alert attention">
          <ShieldAlert size={16} />
          <span>
            Out of scope for product planning: {r.scope_flags.map(readable).join(", ")}. The triage total is capped and a decline with this reason is
            suggested; the dependency belongs to its owning team.
          </span>
        </div>
      )}
      <TriageBlock triage={r.triage} history={detail.triageHistory} />
      <div className="evidence-columns">
        <LinkColumn title="Evidence for" links={forLinks} market={r.market} empty="No supporting evidence linked." />
        <LinkColumn title="Evidence against" links={againstLinks} market={r.market} empty="No conflicting evidence linked." />
      </div>
      {!!duplicates.length && <LinkColumn title="Duplicates" links={duplicates} market={r.market} empty="" />}
      {detail.position && (
        <section className="ai-brief">
          <ProvenanceLabel value={detail.position.provenance} />
          <h3>Draft position</h3>
          <div className="position-grid">
            <PositionList title="Case for" items={detail.position.caseFor} />
            <PositionList title="Case against" items={detail.position.caseAgainst} />
            <PositionList title="Open questions" items={detail.position.openQuestions} />
          </div>
          {!!detail.position.citedIds.length && (
            <p className="muted text-xs">
              Cited: <SourceLinks refs={detail.position.citedIds.map((eid) => ({ type: "evidence", id: eid }))} market={r.market} />
            </p>
          )}
          <small className="muted">A draft for the PM; spans were validated by the server before storing. It is not a decision.</small>
        </section>
      )}
      <section>
        <h3>Decisions</h3>
        {detail.decisions.length ? (
          <div className="audit-timeline">
            {[...detail.decisions].sort((a, b) => b.created_at.localeCompare(a.created_at)).map((d) => (
              <article key={d.id || d.created_at}>
                <span className="timeline-dot" />
                <div>
                  <div className="audit-event-title">
                    <strong>{readable(d.decision)}</strong>
                    {d.requirement_id && <SourceLinks refs={[{ type: "requirement", id: d.requirement_id }]} market={r.market} />}
                  </div>
                  <p>{d.rationale}</p>
                  <small>{d.actor} · {date(d.created_at)}</small>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="muted text-xs">No decision recorded yet.</p>
        )}
      </section>
      <DecisionDialog request={r} open={deciding} onOpenChange={setDeciding} />
    </div>
  );
}
function TriageBlock({ triage, history }: { triage: Triage | null; history: Triage[] }) {
  if (!triage) return <p className="muted text-xs">Not triaged yet. Run triage to score this request.</p>;
  return (
    <section className="triage-block">
      <div className="triage-heading">
        <h3>
          Triage {fixed(triage.total, 2)}
          {triage.rubricVersion && <small className="mono muted"> · {triage.rubricVersion}</small>}
        </h3>
        <MethodLabel methodVersion={triage.rubricVersion} runId={triage.runId} compact />
      </div>
      {triage.cap && <p className="attention-text text-xs">Capped: {triage.cap}</p>}
      <FactorBars factors={triage.factors} />
      <details>
        <summary>Factor inputs and source ids</summary>
        {triage.factors.map((f) => (
          <div key={f.name} className="factor-detail">
            <strong>{readable(f.name)}</strong>
            {f.formula && <code>{f.formula}</code>}
            {Object.keys(f.inputs).length > 0 && <pre className="json-record">{JSON.stringify(f.inputs, null, 2)}</pre>}
            <SourceLinks refs={f.sources} />
          </div>
        ))}
      </details>
      {history.length > 1 && <p className="muted text-xs">{history.length} triage scores on record (append-only history).</p>}
    </section>
  );
}
function LinkColumn({ title, links, market, empty }: { title: string; links: RequestLink[]; market: string; empty: string }) {
  return (
    <section className="link-column">
      <h3>{title}</h3>
      {links.length ? (
        links.map((l) => (
          <article key={l.id} className={`evidence-card ${l.relation === "conflicts" ? "conflicting" : ""} ${l.status === "removed" ? "is-removed" : ""}`}>
            {(l.quote || l.summary) && <blockquote>{l.quote || l.summary}</blockquote>}
            <span className="link-meta">
              <SourceLinks refs={[{ type: ENTITY_TYPE[l.entity_type] ?? l.entity_type, id: l.entity_id }]} market={l.market ?? market} />
              <small className="muted">
                {readable(l.relation)} · {l.created_by.startsWith("system:") || l.created_by.startsWith("ai:") ? `proposed by ${l.created_by}` : `added by ${l.created_by}`}
                {l.status === "removed" && " · removed"}
              </small>
            </span>
          </article>
        ))
      ) : (
        <p className="muted text-xs">{empty}</p>
      )}
    </section>
  );
}
function PositionList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <h4>{title}</h4>
      {items.length ? (
        <ul>
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="muted text-xs">None drafted.</p>
      )}
    </div>
  );
}
function DecisionDialog({ request, open, onOpenChange }: { request: IntakeRequest; open: boolean; onOpenChange: (open: boolean) => void }) {
  const client = useQueryClient();
  const [decision, setDecision] = useState(request.scope_flags.length ? "decline" : "");
  const [requirementId, setRequirementId] = useState("");
  const requirements = useQuery({
    queryKey: ["requirements", `vehicle=${request.vehicle}&market=${request.market}`],
    queryFn: ({ signal }) =>
      allPages<Requirement>(`/requirements?vehicle=${encodeURIComponent(request.vehicle)}&market=${encodeURIComponent(request.market)}`, signal),
    enabled: open && decision === "link",
  });
  const decide = useMutation({
    mutationFn: ({ actor, rationale }: { actor: string; rationale: string }) =>
      platform.decideRequest(request.id, { decision, actor, rationale, ...(decision === "link" ? { requirement_id: requirementId } : {}) }),
    onSuccess: () => {
      toast.success(`Decision “${readable(decision)}” recorded.`);
      onOpenChange(false);
      for (const key of [["requests"], ["request", request.id], ["request-aggregates"], ["requirements"]]) void client.invalidateQueries({ queryKey: key });
    },
  });
  return (
    <GateDialog
      open={open}
      onOpenChange={onOpenChange}
      title={`Decide ${request.key}`}
      description={`${request.title} · ${request.vehicle} / ${request.market}`}
      submitLabel="Record decision"
      role="approve"
      pending={decide.isPending}
      error={decide.error}
      ready={!!decision && (decision !== "link" || !!requirementId)}
      onSubmit={(actor, rationale) => decide.mutate({ actor, rationale })}
    >
      {request.simulated && (
        <p className="muted text-xs">
          <SimulatedBadge /> This is a simulated request; decisions on it are still recorded in the audit trail.
        </p>
      )}
      <Field label="Decision">
        <PmSelect
          aria-label="Request decision"
          value={decision}
          onValueChange={setDecision}
          options={[{ value: "", label: "Choose a decision" }, ...REQUEST_DECISIONS.map((value) => ({ value, label: readable(value) }))]}
        />
      </Field>
      {decision && <p className="muted text-xs">{DECISION_HELP[decision]}</p>}
      {decision === "link" &&
        (requirements.error ? (
          <ErrorMessage error={requirements.error} />
        ) : requirements.isPending ? (
          <Loading label="Loading requirements…" />
        ) : (
          <Field label={`Requirement in ${request.vehicle} / ${request.market}`}>
            <PmSelect
              aria-label="Requirement to link"
              value={requirementId}
              onValueChange={setRequirementId}
              options={[
                { value: "", label: requirements.data.length ? "Choose a requirement" : "No requirements in this scope" },
                ...requirements.data.map((q) => ({ value: q.id, label: `${q.key} · ${q.title}` })),
              ]}
            />
          </Field>
        ))}
    </GateDialog>
  );
}
