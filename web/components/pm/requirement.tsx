"use client";
import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  ArrowUpRight,
  Check,
  Edit3,
  GitBranch,
  Info,
  Link2,
  Save,
  ShieldCheck,
  X,
} from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { PmMultiSelect, PmSelect } from "./pm-select";
import {
  api,
  write,
  pinnedTrace,
  allAudit,
  allPages,
  query,
  canAct,
  readable,
  date,
  locationLabel,
  ApiError,
} from "@/lib/api";
import type {
  Criterion,
  Detail,
  Factors,
  Finding,
  Schema,
  Trace,
  Version,
} from "@/lib/types";
import { useWorkspace } from "./context";
import { ReviewChangeSummary } from "./review-changes";
import {
  Empty,
  ErrorMessage,
  Field,
  Grade,
  Loading,
  ScoreLabel,
  Status,
  useUrlState,
} from "./shared";
import { RequirementSourceMix } from "./source-mix";
function criterionTarget(c: Criterion) {
  const unit = String(c.target).trim().endsWith("%")
    ? (c.unit || "").replace(/^%\s*/, "")
    : c.unit || "";
  return `${c.target} ${unit}`.trim();
}
const tabs = ["requirement", "evidence", "score", "versions", "history"];
export function RequirementDrawer({
  deepRequirement,
  deepTab,
}: {
  deepRequirement?: string;
  deepTab?: string;
}) {
  const { params, set } = useUrlState();
  const { base, requirements, loading } = useWorkspace();
  const router = useRouter();
  const chosen = params.get("requirement") || deepRequirement;
  const item = requirements.find((r) => r.id === chosen || r.key === chosen);
  const id = chosen?.startsWith("REQ-") ? item?.id : chosen;
  const tab =
    params.get("tab") ||
    (deepTab === "trace" ? "evidence" : deepTab) ||
    "requirement";
  const close = () => {
    if (deepRequirement) router.push(`${base}/requirements`);
    else
      set({
        requirement: undefined,
        tab: undefined,
        version: undefined,
        score: undefined,
        workflow: undefined,
      });
  };
  return (
    <Sheet
      open={!!chosen}
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <SheetContent className="requirement-drawer" showCloseButton={false}>
        <SheetHeader className="drawer-topline">
          <div>
            <SheetTitle>Requirement workspace</SheetTitle>
            <SheetDescription>
              Source → finding → version → score → decision
            </SheetDescription>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Close requirement"
            onClick={close}
          >
            <X size={18} />
          </Button>
        </SheetHeader>
        {chosen &&
          !id &&
          (loading ? (
            <Loading label="Resolving requirement key…" />
          ) : (
            <ErrorMessage
              error={
                new Error(
                  "No requirement with this key exists in the selected scope.",
                )
              }
            />
          ))}
        {id && (
          <RequirementDetail
            key={`${id}:${params.get("version") || "current"}:${params.get("score") || ""}`}
            id={id}
            tab={tabs.includes(tab) ? tab : "requirement"}
            onTab={(tab) => set({ tab })}
            versionId={params.get("version") || undefined}
            scoreId={params.get("score") || undefined}
          />
        )}
      </SheetContent>
    </Sheet>
  );
}
function RequirementDetail({
  id,
  tab,
  onTab,
  versionId,
  scoreId,
}: {
  id: string;
  tab: string;
  onTab: (tab: string) => void;
  versionId?: string;
  scoreId?: string;
}) {
  const { scope, actor, refresh } = useWorkspace();
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState(false);
  const detail = useQuery({
    queryKey: ["requirement", id],
    queryFn: ({ signal }) =>
      api<Detail>(`/requirements/${encodeURIComponent(id)}`, { signal }),
    staleTime: 0,
  });
  const version = versionId || detail.data?.current_version.id;
  const score =
    scoreId || (!versionId ? detail.data?.current_version.score.id : undefined);
  const trace = useQuery({
    queryKey: ["trace", id, version, score, offset],
    queryFn: ({ signal }) => pinnedTrace(id, version!, score!, offset, signal),
    enabled: !!version && !!score,
    staleTime: 0,
  });
  if (detail.error)
    return (
      <ErrorMessage error={detail.error} retry={() => void detail.refetch()} />
    );
  if (detail.isPending || (!trace.data && trace.isFetching))
    return (
      <Loading label="Opening the exact requirement and score versions…" />
    );
  const req = detail.data;
  if (!req) return null;
  if (req.vehicle !== scope.vehicle || req.market !== scope.market)
    return (
      <ErrorMessage
        error={
          new Error(
            "This requirement is outside the selected vehicle and market. Open it in its own scope.",
          )
        }
      />
    );
  if (trace.error)
    return (
      <ErrorMessage error={trace.error} retry={() => void trace.refetch()} />
    );
  if (!trace.data)
    return (
      <ErrorMessage
        error={
          new Error(
            "A historical view requires both version and score IDs. Open it from the versions tab.",
          )
        }
      />
    );
  const t = trace.data;
  const v = t.version;
  const archived = !!versionId;
  return (
    <>
      <div className="requirement-hero">
        <div className="flex items-center justify-between gap-3">
          <span className="requirement-key">
            {req.key} · VERSION {v.version}
          </span>
          <ScoreLabel score={v.score.total} grade={v.score.evidence_grade} />
        </div>
        <h2>{v.title}</h2>
        <div className="flex flex-wrap items-center gap-3">
          <Status value={archived ? "historical_snapshot" : req.status} />
          <span className="origin-badge">
            {(v.actor || v.created_by || "").toLowerCase().startsWith("ai:")
              ? "AI proposal"
              : (v.actor || v.created_by || "")
                    .toLowerCase()
                    .startsWith("system:")
                ? "System generated"
                : v.actor || v.created_by || "Recorded proposal"}
          </span>
          <span className="muted">{readable(req.topic)}</span>
          <button
            className="text-link ml-auto"
            onClick={() => {
              navigator.clipboard
                .writeText(window.location.href)
                .then(() => toast.success("Requirement link copied"))
                .catch(() =>
                  toast.error("Copy the page URL to share this view."),
                );
            }}
          >
            <Link2 size={13} />
            Copy link
          </button>
        </div>
      </div>
      <nav className="detail-tabs" aria-label="Requirement sections">
        {tabs.map((key) => (
          <button
            key={key}
            aria-current={tab === key ? "page" : undefined}
            onClick={() => onTab(key)}
          >
            {key === "requirement"
              ? "Requirement"
              : key === "evidence"
                ? "Evidence trace"
                : readable(key)}
          </button>
        ))}
      </nav>
      <div className="detail-body">
        {archived && (
          <div className="pm-alert">
            <ShieldCheck size={16} />
            <span>
              Historical snapshot. Decisions remain attached to the version and
              score shown here.
            </span>
          </div>
        )}
        {!archived &&
          req.reviews
            .filter((r) => r.status === "open")
            .map((r) => (
              <div key={r.id} className="pm-alert attention">
                <Info size={16} />
                <span>{r.reason}</span>
              </div>
            ))}
        {tab === "requirement" && (
          <>
            <section className="detail-section">
              <h3>Customer-facing requirement</h3>
              <p className="requirement-statement">{v.statement}</p>
              <h3>Customer need</h3>
              <p>{v.customer_need}</p>
            </section>
            <section className="detail-section">
              <h3>Measurable acceptance criteria</h3>
              <div className="criteria-list">
                {v.acceptance_criteria.map((c, i) => (
                  <div key={i}>
                    <span className="criterion-number">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <div>
                      <strong>{c.metric}</strong>
                      <p>{criterionTarget(c)}</p>
                      <span
                        className={`criterion-basis ${c.basis === "source" ? "source" : ""}`}
                      >
                        {c.basis === "source"
                          ? "Source-supported target"
                          : "PM assumption · requires validation"}
                      </span>
                      {c.source_ids.length > 0 && (
                        <p className="mono break-all">
                          Citations: {c.source_ids.join(", ")}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </section>
            <section className="detail-section">
              <h3>Assumptions & uncertainties</h3>
              {v.assumptions.length ? (
                <ul className="assumption-list">
                  {v.assumptions.map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                </ul>
              ) : (
                <p className="muted">No additional assumptions recorded.</p>
              )}
            </section>
            <div className="trace-ribbon">
              <FilesCount title="Source files" value={t.sources.length} />
              <FilesCount title="Findings" value={t.findings.length} />
              <FilesCount title="Evidence records" value={t.evidence.total} />
              <button className="text-link" onClick={() => onTab("evidence")}>
                Inspect full trace
                <ArrowUpRight size={14} />
              </button>
            </div>
          </>
        )}
        {tab === "evidence" && (
          <TraceView
            trace={t}
            offset={offset}
            onOffset={setOffset}
            loading={trace.isFetching}
          />
        )}
        {tab === "score" && (
          <ScoreView
            key={v.score.id}
            version={v}
            requirementId={id}
            readOnly={archived}
          />
        )}
        {tab === "versions" && <Versions req={req} />}
        {tab === "history" && <RequirementHistory id={id} />}
      </div>
      {archived ? (
        <div className="decision-footer">
          <span>Read-only historical version.</span>
        </div>
      ) : (
        <DecisionPanel
          key={`${v.id}:${v.score.id}`}
          req={req}
          version={v}
          onEdit={() => setEditing(true)}
        />
      )}
      <Dialog open={editing} onOpenChange={setEditing}>
        <DialogContent className="edit-dialog">
          <DialogTitle>Edit requirement</DialogTitle>
          <DialogDescription>
            A new proposal is created and re-scored. The approved baseline stays
            intact.
          </DialogDescription>
          <EditForm
            key={v.id}
            version={v}
            id={id}
            actorId={actor?.id || ""}
            onDone={() => {
              setEditing(false);
              refresh();
            }}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}
function FilesCount({ title, value }: { title: string; value: number }) {
  return (
    <span>
      <strong>{value}</strong>
      {title}
    </span>
  );
}
function TraceView({
  trace,
  offset,
  onOffset,
  loading,
}: {
  trace: Trace;
  offset: number;
  onOffset: (n: number) => void;
  loading: boolean;
}) {
  const sources = new Map(trace.sources.map((s) => [s.id, s]));
  const [filter, setFilter] = useState("all");
  const rows = trace.evidence.items.filter(
    (e) =>
      filter === "all" ||
      trace.findings.some((f) =>
        (filter === "conflicts"
          ? f.conflicting_evidence_ids
          : f.evidence_ids
        ).includes(e.id),
      ),
  );
  return (
    <>
      <div className="trace-chain">
        <span>{trace.sources.length} sources</span>
        <GitBranch size={14} />
        <span>{trace.findings.length} findings</span>
        <GitBranch size={14} />
        <span>Version {trace.version.version}</span>
        <GitBranch size={14} />
        <span>{trace.decisions.length} decisions on this score</span>
      </div>
      <RequirementSourceMix
        requirementId={trace.requirement.id}
        versionId={trace.version.id}
      />
      <section className="detail-section">
        <h3>Linked findings</h3>
        {trace.findings.map((f) => (
          <details className="finding-row" key={f.id}>
            <summary>
              <Status value={f.kind} />
              <span>{readable(f.topic)}</span>
              <small>
                {f.evidence_ids.length} supporting ·{" "}
                {f.conflicting_evidence_ids.length} conflicting
              </small>
            </summary>
            <p>{f.summary}</p>
            <span className="mono muted">
              Finding {f.id} · confidence {f.confidence}
            </span>
          </details>
        ))}
      </section>
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-medium">Exact evidence locations</h3>
        <PmSelect
          className="pm-select"
          aria-label="Evidence relationship on this page"
          value={filter}
          onValueChange={setFilter}
          options={[
            { value: "all", label: "All links on this page" },
            { value: "supports", label: "Supporting" },
            { value: "conflicts", label: "Conflicting" },
          ]}
        />
      </div>
      <p className="muted text-xs">
        {trace.evidence.total} linked records. This page shows {offset + 1}–
        {Math.min(offset + 40, trace.evidence.total)}; relationship filters
        apply to these records.
      </p>
      {rows.map((e) => {
        const source = sources.get(e.source_id);
        const supports = trace.findings.filter((f) =>
          f.evidence_ids.includes(e.id),
        );
        const conflicts = trace.findings.filter((f) =>
          f.conflicting_evidence_ids.includes(e.id),
        );
        return (
          <article
            key={e.id}
            className={`evidence-card ${conflicts.length ? "conflicting" : ""}`}
          >
            <div className="evidence-card-heading">
              <div>
                {supports.length > 0 && <Status value="supports" />}
                {conflicts.length > 0 && <Status value="conflicts" />}
              </div>
              <span>{date(e.observed_at)}</span>
            </div>
            <blockquote>{e.content}</blockquote>
            <div className="evidence-source">
              <strong>{source?.title || e.source_id}</strong>
              <span>{locationLabel(e.location)}</span>
              {source?.original_path && (
                <a
                  className="text-link"
                  href={`/api/backend/sources/${e.source_id}/original`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open preserved original
                  <ArrowUpRight size={13} />
                </a>
              )}
            </div>
            <details>
              <summary>Record provenance</summary>
              <dl className="record-details">
                <dt>Evidence ID</dt>
                <dd>{e.id}</dd>
                <dt>Source ID</dt>
                <dd>{e.source_id}</dd>
                <dt>Finding IDs</dt>
                <dd>
                  {[...supports, ...conflicts].map((f) => f.id).join(", ")}
                </dd>
                <dt>Content hash</dt>
                <dd>{e.content_hash}</dd>
              </dl>
              <pre className="json-record">
                {JSON.stringify(e.metadata, null, 2)}
              </pre>
            </details>
          </article>
        );
      })}
      {!rows.length && (
        <Empty
          title="No matching links on this page"
          description="Change the relationship filter or continue to the next evidence page."
        />
      )}
      <div className="pagination">
        <Button
          variant="outline"
          disabled={offset === 0 || loading}
          onClick={() => onOffset(Math.max(0, offset - 40))}
        >
          Previous 40
        </Button>
        <span>
          {Math.floor(offset / 40) + 1} /{" "}
          {Math.max(1, Math.ceil(trace.evidence.total / 40))}
        </span>
        <Button
          variant="outline"
          disabled={offset + 40 >= trace.evidence.total || loading}
          onClick={() => onOffset(offset + 40)}
        >
          Next 40
        </Button>
      </div>
    </>
  );
}
function DecisionPanel({
  req,
  version,
  onEdit,
}: {
  req: Detail;
  version: Version;
  onEdit: () => void;
}) {
  const { actor, actors, setActor, refresh } = useWorkspace();
  const [action, setAction] =
    useState<Schema["DecisionRequest"]["action"]>("approve");
  const [rationale, setRationale] = useState("");
  const [stale, setStale] = useState(false);
  const mutation = useMutation({
    mutationFn: () =>
      write(`/requirements/${req.id}/decisions`, {
        version_id: version.id,
        score_id: version.score.id,
        actor: actor!.id,
        action,
        rationale: rationale.trim(),
      } satisfies Schema["DecisionRequest"]),
    onSuccess: () => {
      setRationale("");
      toast.success("Decision recorded with its version, score and rationale.");
      refresh();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) setStale(true);
    },
  });
  const allowed = canAct(actor, action);
  return (
    <form
      className="decision-footer"
      onSubmit={(e) => {
        e.preventDefault();
        if (allowed && !stale && rationale.trim()) mutation.mutate();
      }}
    >
      <div className="decision-heading">
        <strong>Human decision</strong>
        <span>
          v{version.version} · score {version.score.total.toFixed(1)} · evidence{" "}
          {version.score.evidence_grade}
        </span>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={!canAct(actor, "edit") || mutation.isPending || stale}
          onClick={onEdit}
        >
          <Edit3 size={13} />
          Edit proposal
        </Button>
      </div>
      {mutation.error && (
        <ErrorMessage
          error={mutation.error}
          retry={stale ? refresh : undefined}
        />
      )}
      <label className="sr-only" htmlFor="decision-rationale">
        Decision rationale
      </label>
      <textarea
        id="decision-rationale"
        className="pm-input"
        placeholder="Explain your decision and how you weighed the evidence…"
        required
        value={rationale}
        onChange={(e) => setRationale(e.target.value)}
        disabled={mutation.isPending || stale}
        rows={2}
      />
      <div className="decision-actions">
        <PmSelect
          className="pm-select"
          aria-label="Reviewer for decision"
          value={actor?.id || ""}
          onValueChange={setActor}
          disabled={mutation.isPending || stale}
          options={[
            { value: "", label: "Select reviewer" },
            ...actors.map((person) => ({ value: person.id, label: `${person.display_name} · ${readable(person.role)}` })),
          ]}
        />
        <PmSelect
          className="pm-select"
          aria-label="Decision action"
          value={action}
          onValueChange={(value) =>
            setAction(value as Schema["DecisionRequest"]["action"])
          }
          disabled={mutation.isPending || stale}
          options={["approve", "reject", "postpone", "challenge"].map((a) => ({
            value: a,
            label: `${readable(a)}${!canAct(actor, a) ? " · role required" : ""}`,
            disabled: !canAct(actor, a),
          }))}
        />
        <Button
          type="submit"
          disabled={
            !allowed || !rationale.trim() || mutation.isPending || stale
          }
        >
          {mutation.isPending ? "Recording…" : "Record decision"}
          <Check size={14} />
        </Button>
      </div>
    </form>
  );
}
function ScoreView({
  version,
  requirementId,
  readOnly,
}: {
  version: Version;
  requirementId: string;
  readOnly: boolean;
}) {
  const { actor, refresh, requirements } = useWorkspace();
  const score = version.score;
  const [weights, setWeights] = useState<Factors>(score.weights);
  const [rationale, setRationale] = useState("");
  const [stale, setStale] = useState(false);
  const keys = Object.keys(weights) as (keyof Factors)[];
  const sum = Object.values(weights).reduce((a, b) => a + b, 0);
  const normalized = Object.fromEntries(
    keys.map((k) => [k, sum ? weights[k] / sum : 0]),
  ) as Factors;
  const simulated =
    20 *
    keys.reduce(
      (total, key) => total + score.factors[key] * normalized[key],
      0,
    );
  const changed = keys.some(
    (k) => Math.abs(normalized[k] - score.weights[k]) > 1e-6,
  );
  const mutation = useMutation({
    mutationFn: () =>
      write(`/requirements/${requirementId}/scores`, {
        expected_version_id: version.id,
        expected_score_id: score.id,
        weights: normalized,
        actor: actor!.id,
        rationale,
      } satisfies Schema["ScoreRequest"]),
    onSuccess: () => {
      toast.success("New score recorded. Review it before deciding.");
      refresh();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) setStale(true);
    },
  });
  return (
    <>
      <section className="detail-section">
        <div className="score-overview">
          <strong>
            {score.total.toFixed(1)}
            <small>RECORDED PRIORITY / 100</small>
          </strong>
          <div>
            <Grade value={score.evidence_grade} />
            <p>Evidence quality is independent of priority.</p>
          </div>
        </div>
        <p className="muted">{score.explanation.formula}</p>
        {keys.map((k) => (
          <div className="factor-row" key={k}>
            <span>{readable(k)}</span>
            <span>{score.factors[k]} / 5</span>
            <span>× {(score.weights[k] * 100).toFixed(0)}%</span>
            <div
              className={`factor-track ${["C", "D"].includes(score.evidence_grade) ? "weak" : ""}`}
            >
              <i
                style={{
                  width: `${(score.explanation.contributions[k] / 35) * 100}%`,
                }}
              />
            </div>
            <strong>{score.explanation.contributions[k].toFixed(1)}</strong>
          </div>
        ))}
        <p className="muted text-xs">
          Rubric {score.rubric_version || "recorded"} · Score ID{" "}
          <span className="mono break-all">{score.id}</span>
        </p>
      </section>
      <section className="detail-section">
        <h3>Evidence grade & limitations</h3>
        <p>{score.explanation.evidence_grade_rubric}</p>
        <ul className="assumption-list">
          {score.explanation.limitations?.map((l, i) => (
            <li key={i}>{l}</li>
          ))}
        </ul>
      </section>
      <section className="simulation">
        <div className="flex items-center justify-between">
          <h3>What-if scoring</h3>
          <span className="workspace-status">Simulation · not saved</span>
        </div>
        <p className="muted">
          Adjust relative weights. They normalize to 100%. Other requirements
          keep their recorded scores.
        </p>
        {keys.map((k) => (
          <label className="weight-row" key={k}>
            <span>{readable(k)}</span>
            <input
              aria-label={`${readable(k)} weight`}
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={weights[k]}
              onChange={(e) =>
                setWeights({ ...weights, [k]: Number(e.target.value) })
              }
            />
            <output>{(normalized[k] * 100).toFixed(0)}%</output>
          </label>
        ))}
        <div className="simulation-result">
          <strong>{simulated.toFixed(1)}</strong>
          <span>
            Simulated score · would rank #
            {1 +
              requirements.filter(
                (r) => r.id !== requirementId && r.priority > simulated,
              ).length}{" "}
            against recorded priorities
          </span>
        </div>
        <Button variant="outline" onClick={() => setWeights(score.weights)}>
          Reset weights
        </Button>
        {!readOnly && (
          <form
            className="mt-4 space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              mutation.mutate();
            }}
          >
            <Field label="Why should the rubric change?">
              <input
                className="pm-input"
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                placeholder="A rationale is required to save"
              />
            </Field>
            {mutation.error && <ErrorMessage error={mutation.error} />}
            <Button
              disabled={
                !canAct(actor, "score") ||
                !changed ||
                !sum ||
                !rationale.trim() ||
                mutation.isPending ||
                stale
              }
              type="submit"
            >
              <Save size={14} />
              Save new score
            </Button>
            <p className="muted text-xs">
              Saving weights requires a lead PM. Approval remains a separate
              decision.
            </p>
          </form>
        )}
      </section>
    </>
  );
}
function Versions({ req }: { req: Detail }) {
  const { set } = useUrlState();
  const activeReview = req.reviews.find((review) => review.status === "open");
  const result = useQuery({
    queryKey: ["versions", req.id],
    queryFn: ({ signal }) =>
      api<Version[]>(`/requirements/${req.id}/versions`, { signal }),
  });
  return (
    <>
      {activeReview && <ReviewChangeSummary review={activeReview} />}
      <div className="version-comparison">
        <section>
          <span className="mono">APPROVED BASELINE</span>
          {req.approved_version ? (
            <>
              <h3>
                v{req.approved_version.version} · {req.approved_version.title}
              </h3>
              <p>{req.approved_version.statement}</p>
              <ScoreLabel
                score={req.approved_version.score.total}
                grade={req.approved_version.score.evidence_grade}
              />
              <ul>
                {req.approved_version.acceptance_criteria.map((c, i) => (
                  <li key={i}>
                    {c.metric}: {criterionTarget(c)} · {c.basis}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="muted">No approved baseline yet.</p>
          )}
        </section>
        <section>
          <span className="mono">CURRENT PROPOSAL</span>
          <h3>
            v{req.current_version.version} · {req.current_version.title}
          </h3>
          <p>{req.current_version.statement}</p>
          <ScoreLabel
            score={req.current_version.score.total}
            grade={req.current_version.score.evidence_grade}
          />
          <ul>
            {req.current_version.acceptance_criteria.map((c, i) => (
              <li key={i}>
                {c.metric}: {criterionTarget(c)} · {c.basis}
              </li>
            ))}
          </ul>
        </section>
      </div>
      <h3>Immutable version history</h3>
      {result.error ? (
        <ErrorMessage error={result.error} />
      ) : result.isPending ? (
        <Loading />
      ) : (
        result.data
          ?.slice()
          .reverse()
          .map((v) => (
            <article className="version-row" key={v.id}>
              <div>
                <strong>Version {v.version}</strong>
                <p>{v.title}</p>
                <small>
                  {date(v.created_at)} · {v.actor || v.created_by}
                </small>
                <p className="muted">{v.rationale}</p>
              </div>
              <Button
                variant="outline"
                onClick={() =>
                  set({ version: v.id, score: v.score.id, tab: "evidence" })
                }
              >
                Open snapshot
                <ArrowUpRight size={14} />
              </Button>
            </article>
          ))
      )}
    </>
  );
}
function RequirementHistory({ id }: { id: string }) {
  const result = useQuery({
    queryKey: ["history", id],
    queryFn: ({ signal }) => allAudit(id, signal),
  });
  return (
    <>
      {result.error ? (
        <ErrorMessage error={result.error} />
      ) : result.isPending ? (
        <Loading />
      ) : (
        <div className="audit-timeline">
          {result.data?.map((event) => (
            <article key={event.id}>
              <span className="timeline-dot" />
              <div>
                <strong>{readable(event.action)}</strong>
                <p>{event.rationale}</p>
                <small>
                  {event.actor} · {date(event.created_at)} · #{event.sequence}
                </small>
                <details>
                  <summary>Audit record</summary>
                  <pre className="json-record">
                    {JSON.stringify(event, null, 2)}
                  </pre>
                </details>
              </div>
            </article>
          ))}
        </div>
      )}
      <p className="muted text-xs">
        Events are recorded in the database hash chain. Chain verification is
        not exposed by the current HTTP API.
      </p>
    </>
  );
}
function EditForm({
  version,
  id,
  actorId,
  onDone,
}: {
  version: Version;
  id: string;
  actorId: string;
  onDone: () => void;
}) {
  const [title, setTitle] = useState(version.title);
  const [statement, setStatement] = useState(version.statement);
  const [need, setNeed] = useState(version.customer_need);
  const [criteria, setCriteria] = useState<Criterion[]>(
    version.acceptance_criteria,
  );
  const [assumptions, setAssumptions] = useState(
    version.assumptions.join("\n"),
  );
  const [rationale, setRationale] = useState("");
  const [stale, setStale] = useState(false);
  const mutation = useMutation({
    mutationFn: async () => {
      const parsed = criteria;
      if (!parsed.length)
        throw new Error("At least one acceptance criterion is required.");
      return write(
        `/requirements/${id}`,
        {
          expected_version_id: version.id,
          actor: actorId,
          rationale,
          title,
          statement,
          customer_need: need,
          acceptance_criteria: parsed,
          assumptions: assumptions.split("\n").filter((x) => x.trim()),
        } satisfies Schema["RequirementEdit"],
        "PATCH",
      );
    },
    onSuccess: onDone,
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) setStale(true);
    },
  });
  return (
    <form
      className="pm-form"
      onSubmit={(e) => {
        e.preventDefault();
        mutation.mutate();
      }}
    >
      <Field label="Title">
        <input
          className="pm-input"
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </Field>
      <Field label="Requirement statement">
        <textarea
          className="pm-input"
          required
          rows={4}
          value={statement}
          onChange={(e) => setStatement(e.target.value)}
        />
      </Field>
      <Field label="Customer need">
        <textarea
          className="pm-input"
          required
          value={need}
          onChange={(e) => setNeed(e.target.value)}
        />
      </Field>
      <fieldset className="criteria-editor">
        <legend>Measurable acceptance criteria</legend>
        {criteria.map((criterion, index) => (
          <div className="criterion-editor" key={index}>
            <div className="flex items-center justify-between">
              <strong>Criterion {index + 1}</strong>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={criteria.length === 1}
                onClick={() =>
                  setCriteria(criteria.filter((_, i) => i !== index))
                }
              >
                Remove
              </Button>
            </div>
            <div className="form-grid">
              {(["metric", "target", "unit"] as const).map((key) => (
                <Field key={key} label={readable(key)}>
                  <input
                    className="pm-input"
                    required={key !== "unit"}
                    value={criterion[key] || ""}
                    onChange={(e) =>
                      setCriteria(
                        criteria.map((c, i) =>
                          i === index ? { ...c, [key]: e.target.value } : c,
                        ),
                      )
                    }
                  />
                </Field>
              ))}
            </div>
            <Field label="Target basis">
              <PmSelect
                className="pm-select"
                value={criterion.basis}
                onValueChange={(value) =>
                  setCriteria(
                    criteria.map((c, i) =>
                      i === index
                        ? {
                            ...c,
                            basis: value as Criterion["basis"],
                            source_ids: [],
                          }
                        : c,
                    ),
                  )
                }
                options={[
                  { value: "PM assumption", label: "PM assumption · requires validation" },
                  { value: "source", label: "Source-supported target" },
                ]}
              />
            </Field>
            {criterion.basis === "source" && (
              <Field label="Supporting evidence IDs, separated by commas">
                <textarea
                  className="pm-input mono"
                  required
                  value={criterion.source_ids.join(", ")}
                  onChange={(e) =>
                    setCriteria(
                      criteria.map((c, i) =>
                        i === index
                          ? {
                              ...c,
                              source_ids: e.target.value
                                .split(",")
                                .map((v) => v.trim()),
                            }
                          : c,
                      ),
                    )
                  }
                />
              </Field>
            )}
          </div>
        ))}
        <Button
          type="button"
          variant="outline"
          onClick={() =>
            setCriteria([
              ...criteria,
              {
                metric: "",
                target: "",
                unit: null,
                basis: "PM assumption",
                source_ids: [],
              },
            ])
          }
        >
          Add criterion
        </Button>
      </fieldset>
      <p className="muted text-xs">
        Source-supported targets must cite the exact evidence IDs shown in the
        trace. The API validates that the target is grounded in those records.
      </p>
      <Field label="Assumptions, one per line">
        <textarea
          className="pm-input"
          value={assumptions}
          onChange={(e) => setAssumptions(e.target.value)}
        />
      </Field>
      <Field label="Edit rationale">
        <textarea
          className="pm-input"
          required
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
        />
      </Field>
      {mutation.error && <ErrorMessage error={mutation.error} />}
      <Button
        type="submit"
        disabled={!rationale.trim() || mutation.isPending || stale}
      >
        {mutation.isPending ? "Saving…" : "Create version & re-score"}
      </Button>
    </form>
  );
}
export function CreateRequirement({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!value) onClose();
      }}
    >
      <DialogContent className="edit-dialog">
        <DialogTitle>New customer requirement</DialogTitle>
        <DialogDescription>
          Link findings and record explicit targets before creating a scored
          proposal.
        </DialogDescription>
        {open && <CreateForm onDone={onClose} />}
      </DialogContent>
    </Dialog>
  );
}
function CreateForm({ onDone }: { onDone: () => void }) {
  const { scope, actor, refresh } = useWorkspace();
  const [selected, setSelected] = useState<string[]>([]);
  const [factors, setFactors] = useState<Factors>({
    customer_impact: 3,
    market_relevance: 3,
    strategic_fit: 3,
    differentiation: 3,
    feasibility: 3,
  });
  const findings = useQuery({
    queryKey: ["findings", query(scope)],
    queryFn: ({ signal }) =>
      allPages<Finding>(`/findings?${query(scope)}`, signal),
  });
  const [error, setError] = useState<Error | null>(null);
  const mutation = useMutation({
    mutationFn: (body: Schema["RequirementCreate"]) =>
      write("/requirements", body),
    onSuccess: () => {
      toast.success("Evidence-linked proposal created.");
      refresh();
      onDone();
    },
  });
  return (
    <form
      className="pm-form"
      onSubmit={(e) => {
        e.preventDefault();
        const form = new FormData(e.currentTarget);
        const value = (key: string) => String(form.get(key) || "").trim();
        if (!actor) return;
        const chosen = (findings.data || []).filter((f) =>
          selected.includes(f.id),
        );
        if (new Set(chosen.map((f) => f.topic)).size !== 1) {
          setError(new Error("Select findings within one topic."));
          return;
        }
        mutation.mutate({
          ...scope,
          actor: actor.id,
          title: value("title"),
          statement: value("statement"),
          customer_need: value("need"),
          topic: chosen[0].topic,
          finding_ids: selected,
          rationale: value("rationale"),
          factors,
          assumptions: [
            "Factor judgments and numeric target are PM assumptions.",
          ],
          acceptance_criteria: [
            {
              metric: value("metric"),
              target: value("target"),
              unit: value("unit") || null,
              basis: "PM assumption",
              source_ids: [],
            },
          ],
        });
      }}
    >
      {["title", "statement", "need"].map((name) => (
        <Field
          key={name}
          label={name === "need" ? "Customer need" : readable(name)}
        >
          <textarea
            className="pm-input"
            name={name}
            required
            rows={name === "statement" ? 3 : 1}
          />
        </Field>
      ))}
      <div className="form-grid">
        {["metric", "target", "unit"].map((name) => (
          <Field key={name} label={readable(name)}>
            <input
              className="pm-input"
              name={name}
              required={name !== "unit"}
            />
          </Field>
        ))}
      </div>
      <p className="muted text-xs">
        This manual target is explicitly a PM assumption. Source-supported
        targets can be added in the proposal editor.
      </p>
      <Field label="Supporting findings (select within one topic)">
        <PmMultiSelect
          className="pm-input finding-select"
          aria-label="Supporting findings"
          required
          value={selected}
          onValueChange={setSelected}
          options={(findings.data || [])
            .filter((f) => f.kind !== "context")
            .map((f) => ({ value: f.id, label: `${readable(f.topic)} · ${f.kind} · ${f.summary.slice(0, 90)}` }))}
        />
      </Field>
      {findings.error && <ErrorMessage error={findings.error} />}
      <h3>PM factor judgments (0–5)</h3>
      <div className="form-grid">
        {(Object.keys(factors) as (keyof Factors)[]).map((key) => (
          <Field key={key} label={readable(key)}>
            <input
              className="pm-input"
              type="number"
              min="0"
              max="5"
              step="0.1"
              value={factors[key]}
              onChange={(e) =>
                setFactors({ ...factors, [key]: Number(e.target.value) })
              }
            />
          </Field>
        ))}
      </div>
      <Field label="Creation rationale">
        <textarea className="pm-input" required name="rationale" />
      </Field>
      {(error || mutation.error) && (
        <ErrorMessage error={(error || mutation.error)!} />
      )}
      <Button
        disabled={
          !canAct(actor, "edit") || !selected.length || mutation.isPending
        }
        type="submit"
      >
        Create & score proposal
      </Button>
      {!canAct(actor, "edit") && (
        <p className="muted">
          Select an active PM reviewer to create a proposal.
        </p>
      )}
    </form>
  );
}
