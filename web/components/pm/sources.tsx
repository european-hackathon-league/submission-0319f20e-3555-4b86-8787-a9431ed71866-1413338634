"use client";
import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  ArrowUpRight,
  FileText,
  Search,
  Upload,
  Globe2,
  HardDrive,
  Info,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { PmSelect } from "./pm-select";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { useWorkspace } from "./context";
import {
  Heading,
  Panel,
  Field,
  ErrorMessage,
  Loading,
  Empty,
  Status,
  RequirementLink,
  useUrlState,
} from "./shared";
import {
  api,
  allPages,
  canAct,
  date,
  fmt,
  locationLabel,
  query,
  readable,
  write,
} from "@/lib/api";
import type { Detail, Evidence, Finding, Page } from "@/lib/types";
import { ExaResearch } from "./exa-research";
import { PublicConnectors, SourceMixPanel } from "./source-mix";
export function EvidenceExplorer() {
  const { scope, base, sources } = useWorkspace();
  const { params, set } = useUrlState();
  const mode = params.get("mode") || "evidence";
  const q = params.get("q") || "";
  const source = params.get("source") || "";
  const kind = params.get("kind") || "";
  const topic = params.get("topic") || "";
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const selectedId = params.get("evidence") || "";
  const selected = useQuery({
    queryKey: ["evidence-record", selectedId],
    queryFn: ({ signal }) =>
      api<Evidence>(`/evidence/${encodeURIComponent(selectedId)}`, { signal }),
    enabled: !!selectedId,
  });
  const records = useQuery({
    queryKey: ["evidence", query(scope), q, source, offset],
    queryFn: ({ signal }) =>
      api<Page<Evidence>>(
        `/evidence?${query(scope, { q, source_id: source, limit: 25, offset })}`,
        { signal },
      ),
    enabled: mode === "evidence",
  });
  const findings = useQuery({
    queryKey: ["findings", query(scope)],
    queryFn: ({ signal }) =>
      allPages<Finding>(`/findings?${query(scope)}`, signal),
    enabled: mode === "findings",
  });
  const sourceMap = new Map(sources.map((s) => [s.id, s]));
  const filtered = (findings.data || []).filter(
    (f) =>
      (!kind || f.kind === kind) &&
      (!topic || f.topic === topic) &&
      (!q || `${f.summary} ${f.topic}`.toLowerCase().includes(q.toLowerCase())),
  );
  return (
    <>
      <Heading
        title="Evidence explorer"
        description="Browse original feedback and the requirements it supports."
      />
      <div className="evidence-controls">
        <div className="segmented-control">
          <button
            aria-pressed={mode === "evidence"}
            onClick={() => set({ mode: undefined, offset: undefined })}
          >
            Evidence records
          </button>
          <button
            aria-pressed={mode === "findings"}
            onClick={() => set({ mode: "findings", offset: undefined })}
          >
            Analysed findings
          </button>
        </div>
        <span className="muted text-xs">
          {scope.vehicle} / {scope.market} · Source-linked records
        </span>
      </div>
      <div className="register-toolbar">
        <div className="search-input">
          <Search size={15} />
          <input
            aria-label="Search evidence"
            placeholder="Search customer evidence…"
            value={q}
            onChange={(e) => set({ q: e.target.value, offset: undefined })}
          />
        </div>
        {mode === "evidence" ? (
          <PmSelect
            aria-label="Evidence source"
            value={source}
            onValueChange={(value) => set({ source: value, offset: undefined })}
            options={[
              { value: "", label: "All sources" },
              ...sources.map((s) => ({ value: s.id, label: s.title })),
            ]}
          />
        ) : (
          <>
            <PmSelect
              aria-label="Finding kind"
              value={kind}
              onValueChange={(value) => set({ kind: value })}
              options={[
                { value: "", label: "All finding kinds" },
                ...["need", "problem", "strength", "context"].map((k) => ({ value: k, label: readable(k) })),
              ]}
            />
            <PmSelect
              aria-label="Finding topic"
              value={topic}
              onValueChange={(value) => set({ topic: value })}
              options={[
                { value: "", label: "All topics" },
                ...[...new Set(findings.data?.map((f) => f.topic) || [])].sort().map((t) => ({ value: t, label: readable(t) })),
              ]}
            />
          </>
        )}
      </div>
      {mode === "evidence" ? (
        records.error ? (
          <ErrorMessage error={records.error} />
        ) : records.isPending ? (
          <Loading />
        ) : (
          <>
            <div className="record-count">
              {fmt(records.data.total)} evidence records ·{" "}
              {records.data.total ? offset + 1 : 0}–
              {Math.min(offset + 25, records.data.total)} shown
            </div>
            <div className="evidence-explorer-list">
              {records.data.items.map((e) => (
                <article key={e.id}>
                  <div className="evidence-file-icon">
                    <FileText size={20} />
                  </div>
                  <div className="evidence-explorer-body">
                    <div className="flex flex-wrap items-center gap-3">
                      <strong>
                        {sourceMap.get(e.source_id)?.title || e.source_id}
                      </strong>
                      <span className="mono muted">
                        {locationLabel(e.location)}
                      </span>
                    </div>
                    <p>{e.content}</p>
                    <div className="evidence-meta">
                      <span>
                        {String(
                          e.metadata.record_type || "Source record",
                        ).replaceAll("_", " ")}
                      </span>
                      <span>
                        {String(
                          e.metadata.provenance || "Source type not recorded",
                        )}
                      </span>
                      <span>{date(e.observed_at)}</span>
                    </div>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => set({ evidence: e.id }, true)}
                  >
                    Where used
                    <ArrowUpRight size={13} />
                  </Button>
                </article>
              ))}
            </div>
            {!records.data.items.length && (
              <Empty
                title="No matching evidence"
                description="Try another search or source filter."
              />
            )}
            <div className="pagination">
              <Button
                variant="outline"
                disabled={!offset}
                onClick={() =>
                  set({ offset: String(Math.max(0, offset - 25)) })
                }
              >
                Previous
              </Button>
              <span>Page {Math.floor(offset / 25) + 1}</span>
              <Button
                variant="outline"
                disabled={offset + 25 >= records.data.total}
                onClick={() => set({ offset: String(offset + 25) })}
              >
                Next
              </Button>
            </div>
          </>
        )
      ) : findings.error ? (
        <ErrorMessage error={findings.error} />
      ) : findings.isPending ? (
        <Loading />
      ) : (
        <>
          <p className="muted text-xs">
            {filtered.length} findings across persisted analysis runs. Earlier
            analyses remain in the record.
          </p>
          <div className="finding-grid">
            {filtered.map((f) => (
              <article className="pm-panel" key={f.id}>
                <div className="flex items-center justify-between">
                  <Status value={f.kind} />
                  <span className="mono muted">{readable(f.topic)}</span>
                </div>
                <p>{f.summary}</p>
                <div className="finding-counts">
                  <span>{f.evidence_ids.length} supporting</span>
                  <span>{f.conflicting_evidence_ids.length} conflicting</span>
                  <span>Confidence {f.confidence}</span>
                </div>
                <details>
                  <summary>Analysis details</summary>
                  <p className="mono break-all">
                    Finding: {f.id}
                    <br />
                    Analysis: {f.run_id}
                  </p>
                </details>
                <Link
                  className="text-link"
                  href={`${base}/requirements?topic=${encodeURIComponent(f.topic)}`}
                >
                  Related topic requirements
                  <ArrowUpRight size={13} />
                </Link>
              </article>
            ))}
          </div>
          {!filtered.length && (
            <Empty
              title="No matching findings"
              description="Change the filters or run evidence analysis."
            />
          )}
        </>
      )}
      <Dialog
        open={!!selectedId}
        onOpenChange={(open) => {
          if (!open) set({ evidence: undefined });
        }}
      >
        <DialogContent className="edit-dialog">
          <DialogTitle>Evidence & where used</DialogTitle>
          <DialogDescription>
            Reverse trace through current requirement versions.
          </DialogDescription>
          {selected.error ? (
            <ErrorMessage error={selected.error} />
          ) : selected.isPending ? (
            <Loading />
          ) : selected.data.vehicle !== scope.vehicle ||
            selected.data.market !== scope.market ? (
            <ErrorMessage
              error={
                new Error(
                  "This evidence is outside the current vehicle and market.",
                )
              }
            />
          ) : (
            <EvidenceUsage key={selected.data.id} evidence={selected.data} />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
function EvidenceUsage({ evidence }: { evidence: Evidence }) {
  const { scope, requirements, sources } = useWorkspace();
  const source = sources.find((s) => s.id === evidence.source_id);
  const findings = useQuery({
    queryKey: ["findings", query(scope)],
    queryFn: ({ signal }) =>
      allPages<Finding>(`/findings?${query(scope)}`, signal),
  });
  const details = useQuery({
    queryKey: [
      "reverse-details",
      query(scope),
      requirements.map((r) => r.current_version_id).join(","),
    ],
    queryFn: ({ signal }) =>
      Promise.all(
        requirements.map((r) =>
          api<Detail>(`/requirements/${r.id}`, { signal }),
        ),
      ),
  });
  const linked =
    findings.data?.filter(
      (f) =>
        f.evidence_ids.includes(evidence.id) ||
        f.conflicting_evidence_ids.includes(evidence.id),
    ) || [];
  const used =
    details.data?.filter((d) =>
      d.current_version.finding_ids.some((id) =>
        linked.some((f) => f.id === id),
      ),
    ) || [];
  return (
    <>
      <blockquote className="requirement-statement">
        {evidence.content}
      </blockquote>
      <dl className="record-details">
        <dt>Original source</dt>
        <dd>{source?.title}</dd>
        <dt>Location</dt>
        <dd>{locationLabel(evidence.location)}</dd>
        <dt>Observation date</dt>
        <dd>{date(evidence.observed_at)}</dd>
        <dt>Evidence ID</dt>
        <dd>{evidence.id}</dd>
      </dl>
      {source?.original_path && (
        <a
          className="text-link"
          target="_blank"
          rel="noreferrer"
          href={`/api/backend/sources/${source.id}/original`}
        >
          Open original
          <ArrowUpRight size={14} />
        </a>
      )}
      {details.error || findings.error ? (
        <ErrorMessage error={(details.error || findings.error)!} />
      ) : details.isPending || findings.isPending ? (
        <Loading label="Tracing current uses…" />
      ) : (
        <>
          <h3>{used.length} current requirements cite this record</h3>
          {used.map((r) => (
            <div key={r.id} className="usage-row">
              <RequirementLink id={r.id} tab="evidence">
                {r.key} · {r.current_version.title}
              </RequirementLink>
              <Status value={r.status} />
            </div>
          ))}
          {!used.length && (
            <p className="muted">
              No current requirement cites this record. Historical uses may
              still exist in version history.
            </p>
          )}
          <h3>{linked.length} linked findings</h3>
          {linked.map((f) => (
            <div key={f.id} className="usage-row">
              <Status
                value={
                  f.conflicting_evidence_ids.includes(evidence.id)
                    ? "conflicts"
                    : "supports"
                }
              />
              <span>
                {readable(f.topic)} · {f.kind}
              </span>
            </div>
          ))}
        </>
      )}
      <details>
        <summary>Full source metadata</summary>
        <pre className="json-record">
          {JSON.stringify(evidence.metadata, null, 2)}
        </pre>
      </details>
    </>
  );
}
export function Sources() {
  const { sources, base, scope, refresh } = useWorkspace();
  const [importOpen, setImportOpen] = useState(false);
  return (
    <>
      <Heading
        title="Sources & imports"
        description="Manage original files and public sources, with links to every imported record."
        action={
          <Button onClick={() => setImportOpen(true)}>
            <Upload size={14} />
            Import evidence
          </Button>
        }
      />
      <div className="pm-alert">
        <Info size={16} />
        <span>
          Importing preserves the original and deduplicates identical content.
          Run a cumulative update to assess its impact on approved decisions.
        </span>
      </div>
      <PublicConnectors />
      <SourceMixPanel />
      <Panel
        title="Source registry"
        description={`${sources.length} imported sources · ${scope.vehicle} / ${scope.market}`}
      >
        {!sources.length ? (
          <Empty />
        ) : (
          <div className="source-list">
            {sources.map((s) => (
              <article key={s.id}>
                <div className="source-icon">
                  <FileText size={24} />
                </div>
                <div className="source-body">
                  <div className="source-heading">
                    <h3>{s.title}</h3>
                    <Status value={s.kind} />
                  </div>
                  <p>{s.reference}</p>
                  <div className="source-meta">
                    <span>Imported {date(s.created_at)}</span>
                    <span>Observed: {date(s.observed_at)}</span>
                  </div>
                  <details>
                    <summary>Checksum & import metadata</summary>
                    <dl className="record-details">
                      <dt>Source ID</dt>
                      <dd>{s.id}</dd>
                      <dt>SHA-256</dt>
                      <dd>{s.content_hash || "Not recorded"}</dd>
                    </dl>
                    <pre className="json-record">
                      {JSON.stringify(s.metadata, null, 2)}
                    </pre>
                  </details>
                </div>
                <div className="source-actions">
                  <Link
                    className="text-link"
                    href={`${base}/evidence?source=${s.id}`}
                  >
                    Explore records
                    <ArrowUpRight size={14} />
                  </Link>
                  {s.original_path && (
                    <a
                      className="text-link"
                      href={`/api/backend/sources/${s.id}/original`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open original
                      <ArrowUpRight size={14} />
                    </a>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </Panel>
      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent className="edit-dialog">
          <DialogTitle>Import evidence</DialogTitle>
          <DialogDescription>
            Preserve source evidence for {scope.vehicle} / {scope.market}.
          </DialogDescription>
          {importOpen && (
            <ImportForm
              onDone={() => {
                setImportOpen(false);
                refresh();
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
function ImportForm({ onDone }: { onDone: () => void }) {
  const { scope, actor } = useWorkspace();
  const [mode, setMode] = useState("upload");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const mutation = useMutation({
    mutationFn: async (form: FormData) => {
      if (!actor) throw new Error("Select a reviewer first.");
      const title = String(form.get("title") || "").trim();
      const kind = String(form.get("kind") || "document");
      if (mode === "upload") {
        if (!file) throw new Error("Choose a file.");
        if (file.size > 25 * 1024 * 1024)
          throw new Error("Files must be at most 25 MiB.");
        const body = new FormData();
        body.set("file", file);
        body.set("vehicle", scope.vehicle);
        body.set("market", scope.market);
        body.set("actor", actor.id);
        body.set("kind", kind);
        if (title) body.set("title", title);
        return api<{ record_count: number; deduplicated: boolean }>(
          "/imports/files",
          { method: "POST", body },
        );
      }
      const common = { ...scope, actor: actor.id };
      if (mode === "local")
        return write<{ record_count: number; deduplicated: boolean }>(
          "/imports/local",
          {
            ...common,
            path: String(form.get("path")),
            kind,
            ...(title ? { title } : {}),
          },
        );
      return write<{ record_count: number; deduplicated: boolean }>(
        "/imports/web",
        {
          ...common,
          title,
          url: String(form.get("url")),
          content: String(form.get("content")),
          observed_at: form.get("observed_at") || null,
        },
      );
    },
    onSuccess: (result) => {
      toast.success(
        `${result.deduplicated ? "Already imported" : "Imported"}: ${fmt(result.record_count)} evidence records.`,
      );
      onDone();
    },
  });
  return (
    <form
      className="pm-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (mode === "exa") return;
        setError(null);
        mutation.mutate(new FormData(e.currentTarget));
      }}
    >
      <div className="segmented-control">
        {[
          { id: "upload", label: "Upload file", icon: Upload },
          { id: "local", label: "Local input", icon: HardDrive },
          { id: "web", label: "Web snapshot", icon: Globe2 },
          { id: "exa", label: "Exa research", icon: Search },
        ].map((m) => (
          <button
            key={m.id}
            type="button"
            aria-pressed={mode === m.id}
            onClick={() => setMode(m.id)}
          >
            <m.icon size={13} />
            {m.label}
          </button>
        ))}
      </div>
      {mode === "exa" ? <ExaResearch onDone={onDone} /> : <>
      <Field label="Source title">
        <input
          className="pm-input"
          name="title"
          required={mode === "web"}
          placeholder={
            mode === "web"
              ? "Research snapshot title"
              : "Defaults to the original filename"
          }
        />
      </Field>
      {mode !== "web" && (
        <Field label="Source kind">
          <PmSelect
            className="pm-select"
            name="kind"
            defaultValue="feedback"
            options={[
              { value: "feedback", label: "Customer feedback" },
              { value: "study", label: "Study" },
              { value: "sales", label: "Sales context" },
              { value: "document", label: "Document" },
              { value: "other", label: "Other" },
            ]}
          />
        </Field>
      )}
      {mode === "upload" && (
        <label className="upload-area">
          <Upload size={26} />
          <strong>{file?.name || "Choose a source file"}</strong>
          <span>XLSX, CSV or PDF · up to 25 MiB</span>
          <input
            aria-label="Source file"
            type="file"
            accept=".xlsx,.csv,.pdf"
            required
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        </label>
      )}
      {mode === "local" && (
        <Field label="Path relative to the API data directory">
          <input
            name="path"
            className="pm-input"
            required
            placeholder="G60_feedback_hackathon.xlsx"
          />
        </Field>
      )}
      {mode === "web" && (
        <>
          <Field label="Source URL">
            <input
              className="pm-input"
              name="url"
              type="url"
              required
              placeholder="https://…"
            />
          </Field>
          <Field label="Observation date (leave empty if unknown)">
            <input className="pm-input" name="observed_at" type="date" />
          </Field>
          <Field label="Selected page text">
            <textarea
              className="pm-input"
              name="content"
              rows={7}
              required
              placeholder="Paste the original source text."
            />
          </Field>
        </>
      )}
      {(mutation.error || error) && (
        <ErrorMessage error={(mutation.error || error)!} />
      )}
      <Button
        type="submit"
        disabled={!canAct(actor, "import") || mutation.isPending}
      >
        {mutation.isPending ? "Importing…" : "Import source"}
      </Button>
      <p className="muted text-xs">
        {actor
          ? `Recorded as ${actor.display_name}.`
          : "Select an active human reviewer in the header before importing."}{" "}
        Analysis runs separately from import.
      </p>
      </>}
    </form>
  );
}
