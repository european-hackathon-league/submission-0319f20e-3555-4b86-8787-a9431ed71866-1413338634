"use client";
import { useRef, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import Link from "next/link";
import {
  Play,
  Plus,
  FileDown,
  CheckCircle2,
  Circle,
  Loader2,
  AlertCircle,
  LockKeyhole,
  ArrowUpRight,
  Info,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { PmSelect } from "./pm-select";
import { RunsFeed } from "./runs-feed";
import { useWorkspace } from "./context";
import {
  ErrorMessage,
  Field,
  Heading,
  Loading,
  Panel,
  Status,
  Empty,
  useUrlState,
  ScoreLabel,
} from "./shared";
import { api, canAct, date, query, readable, write } from "@/lib/api";
import type { Brief, Workflow } from "@/lib/types";
export function Pipeline() {
  const { scope, actor, base, sources, refresh } = useWorkspace();
  const { params, set } = useUrlState();
  const [provider, setProvider] = useState("deterministic");
  const [kind, setKind] = useState("initial");
  const [rationale, setRationale] = useState("");
  const requestKey = useRef<string | null>(null);
  const runs = useQuery({
    queryKey: ["workflows", query(scope)],
    queryFn: ({ signal }) =>
      api<Workflow[]>(`/workflows?${query(scope)}&limit=1000`, { signal }),
  });
  const id = params.get("run") || runs.data?.[0]?.id;
  const workflow = useQuery({
    queryKey: ["workflow", id],
    queryFn: ({ signal }) => api<Workflow>(`/workflows/${id}`, { signal }),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data?.status === "running" ? 5000 : false),
  });
  const brief = useQuery({
    queryKey: ["brief", id, workflow.data?.revision],
    queryFn: ({ signal }) => api<Brief>(`/workflows/${id}/brief`, { signal }),
    enabled: !!id && !!workflow.data,
  });
  const create = useMutation({
    mutationFn: () => {
      requestKey.current ??= crypto.randomUUID();
      return write<Workflow>("/workflows", {
        ...scope,
        actor: actor!.id,
        provider,
        kind,
        request_key: requestKey.current,
      });
    },
    onSuccess: (w) => {
      requestKey.current = null;
      set({ run: w.id });
      refresh();
      toast.success("Workflow created. Start the run when ready.");
    },
  });
  const run = useMutation({
    mutationFn: () =>
      write<Workflow>(`/workflows/${id}/run`, {
        actor: actor!.id,
        expected_revision: workflow.data!.revision,
      }),
    onSuccess: (w) => {
      refresh();
      if (w.status === "failed")
        toast.error(
          w.error?.message || "The workflow failed. Inspect the run record.",
        );
      else
        toast.success(
          "Analysis complete. Review the proposed requirements.",
        );
    },
    onError: () => refresh(),
  });
  const complete = useMutation({
    mutationFn: () =>
      write<Workflow>(`/workflows/${id}/complete`, {
        actor: actor!.id,
        expected_revision: workflow.data!.revision,
        rationale,
      }),
    onSuccess: () => {
      setRationale("");
      refresh();
      toast.success("Planning record completed and frozen.");
    },
    onError: () => refresh(),
  });
  const busy = create.isPending || run.isPending || complete.isPending;
  const w = workflow.data;
  const frozen = w?.status === "completed";
  const mismatch =
    w && (w.vehicle !== scope.vehicle || w.market !== scope.market);
  const summary = brief.data?.summary;
  return (
    <>
      <Heading
        title="Pipeline"
        description="Analyse sources, review proposals and save your planning decisions."
        action={
          <Link className="text-link" href={`${base}/sources`}>
            Manage sources
            <ArrowUpRight size={14} />
          </Link>
        }
      />
      <Panel
        title="Start a planning cycle"
        description="Choose a rule-based analysis or the configured OpenAI model."
      >
        <form
          className="pipeline-create"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <Field label="Workflow">
            <PmSelect
              className="pm-select"
              value={kind}
              disabled={busy}
              onValueChange={(value) => {
                setKind(value);
                requestKey.current = null;
              }}
              options={[
                { value: "initial", label: "Initial analysis" },
                { value: "update", label: "Update with new evidence" },
              ]}
            />
          </Field>
          <Field label="Analysis provider">
            <PmSelect
              className="pm-select"
              value={provider}
              disabled={busy}
              onValueChange={(value) => {
                setProvider(value);
                requestKey.current = null;
              }}
              options={[
                { value: "deterministic", label: "Rule-based reference" },
                { value: "openai", label: "Live OpenAI" },
              ]}
            />
          </Field>
          <div className="pipeline-input-count">
            <strong>{sources.length}</strong>
            <span>available sources</span>
          </div>
          <Button
            type="submit"
            disabled={!sources.length || !canAct(actor, "run") || busy}
          >
            <Plus size={14} />
            {create.isPending ? "Creating…" : "Create workflow"}
          </Button>
        </form>
        {create.error && <ErrorMessage error={create.error} />}
      </Panel>
      {runs.error ? (
        <ErrorMessage error={runs.error} />
      ) : runs.isPending ? (
        <Loading />
      ) : !runs.data.length ? (
        <Panel title="Workflow history">
          <Empty
            title="No planning cycles yet"
            description="Create a workflow to analyse the available sources, draft requirements and prepare a decision brief."
          />
        </Panel>
      ) : (
        <>
          <div className="run-selector">
            <label htmlFor="run-selector">Planning cycle</label>
            <PmSelect
              className="pm-select"
              id="run-selector"
              value={id || ""}
              disabled={busy}
              onValueChange={(value) => {
                set({ run: value });
                setRationale("");
              }}
              options={runs.data.map((r) => ({
                value: r.id,
                label: `${date(r.created_at)} · ${readable(r.kind)} · ${readable(r.status)} · ${r.id.slice(0, 8)}`,
              }))}
            />
            {w && <Status value={w.status} />}
          </div>
          {workflow.error ? (
            <ErrorMessage error={workflow.error} />
          ) : workflow.isPending ? (
            <Loading />
          ) : mismatch ? (
            <ErrorMessage
              error={
                new Error("This workflow belongs to another vehicle or market.")
              }
            />
          ) : (
            w && (
              <>
                <section className="pipeline-stage-grid">
                  {w.stages.map((stage, i) => (
                    <article
                      key={stage.key}
                      className={`pipeline-stage stage-${stage.status}`}
                    >
                      <div className="stage-top">
                        <span className="mono">0{i + 1}</span>
                        {stage.status === "completed" ? (
                          <CheckCircle2 size={19} />
                        ) : stage.status === "running" ? (
                          <Loader2 className="animate-spin" size={19} />
                        ) : stage.status === "failed" ? (
                          <AlertCircle size={19} />
                        ) : stage.key === "human_review" ? (
                          <LockKeyhole size={18} />
                        ) : (
                          <Circle size={17} />
                        )}
                      </div>
                      <h2>{stage.label}</h2>
                      <Status value={stage.status} />
                      {stage.output && (
                        <details>
                          <summary>Stage record</summary>
                          <pre className="json-record">
                            {JSON.stringify(stage.output, null, 2)}
                          </pre>
                        </details>
                      )}
                    </article>
                  ))}
                </section>
                <div className="run-actions">
                  <div>
                    <strong>
                      {w.provider === "openai"
                        ? "Live AI analysis"
                        : "Rule-based reference analysis"}
                    </strong>
                    <p className="muted">
                      Revision {w.revision} · Updated {date(w.updated_at)}
                    </p>
                  </div>
                  {!frozen && (
                    <Button
                      disabled={!canAct(actor, "run") || busy}
                      onClick={() => run.mutate()}
                    >
                      <Play size={14} />
                      {run.isPending
                        ? "Running analysis…"
                        : w.status === "failed"
                          ? "Retry workflow"
                          : w.status === "awaiting_review"
                            ? "Process new evidence"
                            : w.status === "running"
                              ? "Recover interrupted run"
                              : "Run workflow"}
                    </Button>
                  )}
                  <a
                    className="button-link"
                    href={`/api/backend/workflows/${w.id}/brief?format=markdown`}
                  >
                    <FileDown size={14} />
                    Download brief
                  </a>
                </div>
                {run.isPending && (
                  <div className="pm-alert" role="status">
                    <Loader2 className="animate-spin" size={16} />
                    <span>
                      Analysing evidence and preparing proposals for your review.
                    </span>
                  </div>
                )}
                {w.status === "running" && (
                  <div className="pm-alert">
                    <Info size={16} />
                    <span>
                      A run is in progress and updates automatically.
                      Recovery becomes available if the run stops responding.
                    </span>
                  </div>
                )}
                {w.error && <ErrorMessage error={new Error(w.error.message)} />}{" "}
                {run.error && <ErrorMessage error={run.error} />}
                {brief.error ? (
                  <ErrorMessage error={brief.error} />
                ) : brief.isPending ? (
                  <Loading label="Preparing the decision brief…" />
                ) : (
                  brief.data && (
                    <Panel
                      title={
                        frozen ? "Completed planning record" : "Decision brief"
                      }
                      description={
                        frozen
                          ? "The versions, scores and decisions below are frozen at completion."
                          : "Review each current proposal before documenting the cycle."
                      }
                      action={
                        <span className="workspace-status">
                          {frozen ? "FROZEN SNAPSHOT" : "LIVE BRIEF"}
                        </span>
                      }
                    >
                      <div className="brief-summary">
                        <span>
                          <strong>{summary?.requirement_count}</strong>{" "}
                          requirements
                        </span>
                        <span>
                          <strong>{summary?.approved_count}</strong> approved
                        </span>
                        <span>
                          <strong>{summary?.rejected_count}</strong> rejected
                        </span>
                        <span>
                          <strong>{summary?.needs_decision_count}</strong> need
                          a decision
                        </span>
                      </div>
                      {brief.data.warnings.map((warning, i) => (
                        <div className="pm-alert attention" key={i}>
                          <Info size={16} />
                          <span>{warning}</span>
                        </div>
                      ))}
                      <div className="brief-requirements">
                        {brief.data.requirements.map((r) => (
                          <article key={r.requirement_id}>
                            <div>
                              <span className="requirement-key">
                                {r.key} · v{r.version.version}
                              </span>
                              <Link
                                className="text-link"
                                href={`${base}/requirements?requirement=${r.requirement_id}${frozen ? `&version=${r.version.id}&score=${r.score.id}&tab=evidence` : ""}`}
                              >
                                {r.version.title}
                                <ArrowUpRight size={14} />
                              </Link>
                              <p className="muted">
                                {r.decision
                                  ? `${r.decision.action} · ${r.decision.actor}`
                                  : "Awaiting approval or rejection"}
                              </p>
                              {r.checks.length > 0 && (
                                <details>
                                  <summary>
                                    {r.checks.length} readiness checks
                                  </summary>
                                  {r.checks.map((check) => (
                                    <p key={check.code}>
                                      {check.message}{" "}
                                      <span className="muted">
                                        {check.next_action}
                                      </span>
                                    </p>
                                  ))}
                                </details>
                              )}
                            </div>
                            <ScoreLabel
                              score={r.score.total}
                              grade={r.score.evidence_grade}
                            />
                          </article>
                        ))}
                      </div>
                      {!frozen && (
                        <form
                          className="complete-workflow"
                          onSubmit={(e) => {
                            e.preventDefault();
                            complete.mutate();
                          }}
                        >
                          <Field label="Completion note">
                            <textarea
                              className="pm-input"
                              value={rationale}
                              onChange={(e) => setRationale(e.target.value)}
                              required
                              placeholder="Summarise the PM decisions and any remaining validation work."
                            />
                          </Field>
                          <div className="flex items-center justify-between gap-4">
                            <span className="muted text-xs">
                              Approve or reject each current requirement before completing this cycle.
                            </span>
                            <Button
                              type="submit"
                              disabled={
                                !canAct(actor, "complete") ||
                                w.status !== "awaiting_review" ||
                                !!summary?.needs_decision_count ||
                                !summary?.requirement_count ||
                                !rationale.trim() ||
                                busy
                              }
                            >
                              Complete & freeze record
                            </Button>
                          </div>
                          {complete.error && (
                            <ErrorMessage error={complete.error} />
                          )}
                        </form>
                      )}
                    </Panel>
                  )
                )}
              </>
            )
          )}
        </>
      )}
      <RunsFeed />
    </>
  );
}
