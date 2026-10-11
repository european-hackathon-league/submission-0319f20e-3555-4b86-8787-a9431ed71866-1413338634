"use client";
import { Fragment, useState } from "react";
import Link from "next/link";
import { Activity } from "lucide-react";
import { date, readable } from "@/lib/api";
import { platform, usageByCapability } from "@/lib/platform-api";
import type { Run } from "@/lib/platform-types";
import { useWorkspace } from "./context";
import { PmSelect } from "./pm-select";
import { PlatformView, ProvenanceLabel, shortId, usePlatformQuery } from "./platform-shared";
import { Empty, Panel, Status } from "./shared";

const tokens = (value: number) => new Intl.NumberFormat("en-US").format(value);
const duration = (ms: number | null) => (ms === null ? "–" : ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`);

/** Recent capability runs (GET /runs): status, method version, provider/model and OpenAI usage per capability. */
export function RunsFeed() {
  const { scope, base } = useWorkspace();
  const [market, setMarket] = useState<"scope" | "all">("scope");
  const [status, setStatus] = useState("");
  const [capability, setCapability] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const state = usePlatformQuery("runs", {
    queryKey: ["runs", scope.vehicle, market === "scope" ? scope.market : "", status, capability],
    queryFn: ({ signal }) =>
      platform.runs(
        scope.vehicle,
        { market: market === "scope" ? scope.market : undefined, status: status || undefined, capability: capability || undefined },
        signal,
      ),
  });
  const capabilities = [...new Set([...(state.query.data?.items.map((r) => r.capability) || []), ...(capability ? [capability] : [])])].sort();
  return (
    <Panel
      title="Run history"
      description="Recent activity across the workspace, with results, duration and model usage."
      action={<Activity size={18} className="muted" />}
    >
      <div className="platform-toolbar">
        <PmSelect
          aria-label="Run scope"
          value={market}
          onValueChange={(value) => setMarket(value as "scope" | "all")}
          options={[
            { value: "scope", label: `${scope.vehicle} / ${scope.market}` },
            { value: "all", label: `${scope.vehicle} · all markets` },
          ]}
        />
        <PmSelect
          aria-label="Run status"
          value={status}
          onValueChange={setStatus}
          options={[{ value: "", label: "All statuses" }, ...["running", "succeeded", "failed"].map((value) => ({ value, label: readable(value) }))]}
        />
        <PmSelect
          aria-label="Action"
          value={capability}
          onValueChange={setCapability}
          options={[{ value: "", label: "All actions" }, ...capabilities.map((value) => ({ value, label: value }))]}
        />
      </div>
      <PlatformView
        state={state}
        isEmpty={(page) => !page.items.length}
        empty={<Empty title="No runs recorded" description="Runs appear when you, an agent or a scheduled task starts work." />}
      >
        {(page) => (
          <>
            <UsageSummary runs={page.items} />
            <div className="pm-table-wrap">
              <table className="pm-table runs-table">
                <thead>
                  <tr>
                    <th>Started</th>
                    <th>Action</th>
                    <th>Method</th>
                    <th>Status</th>
                    <th>Actor</th>
                    <th>Duration</th>
                    <th>Model usage</th>
                    <th>Run</th>
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((run) => (
                    <Fragment key={run.id}>
                      <tr className={open === run.id ? "is-selected" : undefined}>
                        <td className="date-cell">{date(run.started_at)}</td>
                        <td>
                          <strong className="mono">{run.capability}</strong>
                          {(run.vehicle || run.market) && <small>{[run.vehicle, run.market].filter(Boolean).join(" / ")}</small>}
                        </td>
                        <td>
                          <RunMethod run={run} />
                        </td>
                        <td>
                          <Status value={run.status} />
                          {run.error && <small className="attention-text" title={run.error}>{run.error}</small>}
                        </td>
                        <td className="mono">{run.actor}</td>
                        <td className="tabular-nums">{duration(run.durationMs)}</td>
                        <td className="tabular-nums">
                          {run.usage ? (
                            <>
                              {tokens(run.usage.totalTokens)} tokens
                              <small>
                                {run.usage.calls} calls · {run.usage.cacheHits} cached
                              </small>
                            </>
                          ) : (
                            <span className="muted">No model call</span>
                          )}
                        </td>
                        <td>
                          <button type="button" className="text-link mono" aria-expanded={open === run.id} onClick={() => setOpen(open === run.id ? null : run.id)}>
                            {shortId(run.id)}
                          </button>
                        </td>
                      </tr>
                      {open === run.id && (
                        <tr className="run-detail-row">
                          <td colSpan={8}>
                            <RunDetail run={run} base={base} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
            {page.total > page.items.length && <p className="muted text-xs">Showing the latest {page.items.length} of {page.total} runs.</p>}
          </>
        )}
      </PlatformView>
    </Panel>
  );
}
/** A failed model run generated nothing: it is labelled as an OpenAI attempt, not as AI output. */
function RunMethod({ run }: { run: Run }) {
  if (run.status === "failed" && run.method_version.startsWith("openai:"))
    return (
      <span className="method-label" title={run.method_version}>
        OpenAI run failed
        <span className="mono">{run.method_version}</span>
      </span>
    );
  return <ProvenanceLabel value={run.provenance} />;
}
function UsageSummary({ runs }: { runs: Run[] }) {
  const rows = usageByCapability(runs).filter((row) => row.calls > 0 || row.failed > 0);
  if (!rows.length) return <p className="muted text-xs">No OpenAI calls or failures among the loaded runs.</p>;
  return (
    <div className="usage-summary" aria-label="OpenAI usage per capability (loaded runs)">
      {rows.map((row) => (
        <div key={row.capability} className="usage-cell">
          <span className="mono">{row.capability}</span>
          <strong className="tabular-nums">{tokens(row.totalTokens)}</strong>
          <small className="muted">
            tokens · {row.calls} calls · {row.cacheHits} cached · {row.runs} runs{row.failed ? ` · ${row.failed} failed` : ""}
            {row.models.length ? ` · ${row.models.join(", ")}` : ""}
          </small>
        </div>
      ))}
    </div>
  );
}
function RunDetail({ run, base }: { run: Run; base: string }) {
  return (
    <div className="run-detail">
      <dl className="record-details">
        <div>
          <dt>Run id</dt>
          <dd className="mono">{run.id}</dd>
        </div>
        <div>
          <dt>Method version</dt>
          <dd className="mono">{run.method_version || "Not recorded"}</dd>
        </div>
        <div>
          <dt>Input hash</dt>
          <dd className="mono">{run.input_hash || "Not recorded"}</dd>
        </div>
        <div>
          <dt>Finished</dt>
          <dd>{run.finished_at ? date(run.finished_at) : "Still running"}</dd>
        </div>
        {run.task_id && (
          <div>
            <dt>Task</dt>
            <dd className="mono">{run.task_id}</dd>
          </div>
        )}
      </dl>
      <div className="run-json">
        <details open>
          <summary>Inputs</summary>
          <pre className="json-record">{JSON.stringify(run.inputs, null, 2)}</pre>
        </details>
        <details>
          <summary>Outputs</summary>
          <pre className="json-record">{run.outputs ? JSON.stringify(run.outputs, null, 2) : "No outputs recorded."}</pre>
        </details>
        <details>
          <summary>Metrics</summary>
          <pre className="json-record">{JSON.stringify(run.metrics, null, 2)}</pre>
        </details>
      </div>
      <Link className="text-link" href={`${base}/audit?entity=${encodeURIComponent(run.id)}`}>
        Audit events for this run
      </Link>
    </div>
  );
}
