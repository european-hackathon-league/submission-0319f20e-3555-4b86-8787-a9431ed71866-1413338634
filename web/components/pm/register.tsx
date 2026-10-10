"use client";
import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  Search,
  ArrowDownWideNarrow,
  ArrowUpRight,
  Bookmark,
  X,
  ListFilter,
  Plus,
} from "lucide-react";
import { toast } from "sonner";
import { useWorkspace } from "./context";
import {
  Heading,
  Panel,
  Empty,
  ScoreLabel,
  Status,
  RequirementLink,
  useUrlState,
  Loading,
  ErrorMessage,
} from "./shared";
import { Button } from "@/components/ui/button";
import { api, date, query, readable } from "@/lib/api";
import { csv, download, registerRows, reqif } from "@/lib/export";
import type { Detail, Review } from "@/lib/types";
import { CreateRequirement } from "./requirement";
import { useStoredValue } from "@/hooks/use-stored-value";
export function Register() {
  const { requirements, base, scope, compact, setCompact } = useWorkspace();
  const { params, set } = useUrlState();
  const q = params.get("q") || "";
  const status = params.get("status") || "";
  const grade = params.get("grade") || "";
  const topic = params.get("topic") || "";
  const sort = params.get("sort") || "-score";
  const [exporting, setExporting] = useState(false);
  const [creating, setCreating] = useState(false);
  const storage = `bmw-pm-views:${scope.vehicle}:${scope.market}`;
  const [savedJson, setSavedJson] = useStoredValue(storage, "[]");
  let saved: { name: string; query: string }[] = [];
  try {
    saved = JSON.parse(savedJson);
  } catch {}
  const setSaved = (items: typeof saved) => setSavedJson(JSON.stringify(items));
  const filtered = requirements
    .filter(
      (r) =>
        (!q ||
          `${r.title} ${r.key} ${r.topic}`
            .toLowerCase()
            .includes(q.toLowerCase())) &&
        (!status ||
          (status === "needs_review" ? r.needs_review : r.status === status)) &&
        (!grade || r.evidence_grade === grade) &&
        (!topic || r.topic === topic),
    )
    .sort((a, b) =>
      sort === "title"
        ? a.title.localeCompare(b.title)
        : sort === "score"
          ? a.priority - b.priority
          : sort === "updated"
            ? b.updated_at.localeCompare(a.updated_at)
            : b.priority - a.priority,
    );
  const pages = Math.max(1, Math.ceil(filtered.length / 25));
  const page = Math.min(pages, Math.max(1, Number(params.get("page")) || 1));
  const rows = filtered.slice((page - 1) * 25, page * 25);
  const filter = (values: Record<string, string | undefined>) =>
    set({ ...values, page: undefined });
  async function exportAs(format: string) {
    setExporting(true);
    try {
      if (format === "reqif") {
        const ids = filtered.filter((r) => r.approved_version_id);
        if (!ids.length)
          throw new Error("No approved snapshots in this selection.");
        const details = await Promise.all(
          ids.map((r) => api<Detail>(`/requirements/${r.id}`)),
        );
        download(
          `approved-${scope.vehicle}-${scope.market}.reqif`,
          reqif(details),
          "application/xml",
        );
      } else {
        const rows = registerRows(filtered);
        download(
          `requirements-${scope.vehicle}-${scope.market}.${format}`,
          format === "csv" ? csv(rows) : JSON.stringify(rows, null, 2),
          format === "csv" ? "text/csv;charset=utf-8" : "application/json",
        );
      }
      toast.success("Export downloaded from the current selection.");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setExporting(false);
    }
  }
  return (
    <>
      <Heading
        title="Prioritized requirements"
        description="Open a proposal to inspect its evidence, score, and human decision."
      />
      <div className="register-toolbar">
        <div className="search-input">
          <Search size={15} />
          <input
            aria-label="Search requirements"
            placeholder="Search a title, topic or requirement key"
            value={q}
            onChange={(e) => filter({ q: e.target.value })}
          />
        </div>
      </div>
      <details className="register-advanced" open={!!(status || topic || grade || sort !== "-score") || undefined}>
        <summary>
          <ListFilter size={14} />
          Filters and tools
          {(status || topic || grade) && <span className="register-active-filter">Active filters</span>}
        </summary>
        <div className="register-toolbar register-filters">
          <select
            aria-label="Requirement status"
            value={status}
            onChange={(e) => filter({ status: e.target.value })}
          >
            <option value="">All statuses</option>
            {["proposed", "approved", "needs_review", "postponed", "rejected"].map((s) => (
              <option key={s} value={s}>{readable(s)}</option>
            ))}
          </select>
          <select
            aria-label="Topic"
            value={topic}
            onChange={(e) => filter({ topic: e.target.value })}
          >
            <option value="">All topics</option>
            {[...new Set(requirements.map((r) => r.topic))].sort().map((t) => (
              <option key={t} value={t}>{readable(t)}</option>
            ))}
          </select>
          <select
            aria-label="Evidence grade"
            value={grade}
            onChange={(e) => filter({ grade: e.target.value })}
          >
            <option value="">All evidence grades</option>
            {["A", "B", "C", "D"].map((g) => (
              <option key={g} value={g}>Grade {g}</option>
            ))}
          </select>
          <button
            className="icon-button"
            aria-label="Clear filters"
            onClick={() => set({ q: undefined, status: undefined, topic: undefined, grade: undefined, page: undefined })}
          >
            <X size={16} />
          </button>
        </div>
        <div className="register-tools">
          <Button onClick={() => setCreating(true)} variant="outline" size="sm">
            <Plus size={14} /> New requirement
          </Button>
          <button
            className="text-link"
            onClick={() => {
              const name = [
                status || "All",
                topic && readable(topic),
                grade && `Grade ${grade}`,
                q,
              ]
                .filter(Boolean)
                .join(" · ");
              const views = [
                ...saved.filter((v) => v.name !== name),
                { name, query: params.toString() },
              ];
              setSaved(views);
              toast.success("View saved in this browser");
            }}
          >
            <Bookmark size={13} /> Save view
          </button>
          <button className="text-link" onClick={() => setCompact(!compact)}>
            <ListFilter size={13} />
            {compact ? "Comfortable" : "Compact"}
          </button>
          <select
            aria-label="Export requirements"
            disabled={exporting || !filtered.length}
            value=""
            onChange={(e) => void exportAs(e.target.value)}
          >
            <option value="">
              {exporting ? "Exporting…" : "Export selection"}
            </option>
            <option value="csv">CSV</option>
            <option value="json">JSON</option>
            <option value="reqif">ReqIF · approved snapshots</option>
          </select>
        </div>
        {saved.length > 0 && (
          <div className="saved-views">
            {saved.map((v) => (
              <span key={v.name}>
                <Link href={`${base}/requirements?${v.query}`}>{v.name}</Link>
                <button
                  aria-label={`Remove saved view ${v.name}`}
                  onClick={() => setSaved(saved.filter((s) => s.name !== v.name))}
                >
                  <X size={12} />
                </button>
              </span>
            ))}
          </div>
        )}
      </details>
      <div className="register-summary">
        <span>{filtered.length} requirements <span className="muted">/ {scope.vehicle} · {scope.market}</span></span>
        <span className="muted">Priority score and evidence grade are separate judgments.</span>
      </div>
      <div className="pm-table-wrap">
        <table className="pm-table">
          <thead>
            <tr>
              <th className="pin-column">Requirement</th>
              <th>Status</th>
              <th>
                <button
                  onClick={() =>
                    filter({ sort: sort === "-score" ? "score" : "-score" })
                  }
                >
                  Priority / evidence <ArrowDownWideNarrow size={13} />
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="pin-column">
                  <RequirementLink id={r.id}>
                    <small className="requirement-key">{r.key}</small>
                    <strong>{r.title}</strong>
                  </RequirementLink>
                </td>
                <td>
                  <Status value={r.status} />
                  {r.needs_review && r.status !== "needs_review" && (
                    <small className="review-flag">Open review</small>
                  )}
                </td>
                <td>
                  <RequirementLink id={r.id} tab="score">
                    <ScoreLabel score={r.priority} grade={r.evidence_grade} />
                  </RequirementLink>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && (
          <Empty
            title="No requirements match"
            description="Clear a filter or import and analyse evidence for this scope."
          />
        )}
        <div className="table-footer">
          <span>
            Scores range from 0 to 100. A high score can still have weak
            evidence.
          </span>
          <div>
            <Button
              size="sm"
              variant="outline"
              disabled={page <= 1}
              onClick={() => set({ page: String(page - 1) })}
            >
              Previous
            </Button>
            <span>
              {page} / {pages}
            </span>
            <Button
              size="sm"
              variant="outline"
              disabled={page >= pages}
              onClick={() => set({ page: String(page + 1) })}
            >
              Next
            </Button>
          </div>
        </div>
      </div>
      <p className="muted text-xs">
        Approval is a per-requirement human decision. Local exports retain
        version and score IDs; dedicated export audit events are not available
        in the current API.
      </p>
      <CreateRequirement open={creating} onClose={() => setCreating(false)} />
    </>
  );
}
export function Reviews() {
  const { scope, requirements } = useWorkspace();
  const { params, set } = useUrlState();
  const selected = params.get("requirement");
  const result = useQuery({
    queryKey: ["reviews", query(scope)],
    queryFn: ({ signal }) =>
      api<Review[]>(`/reviews?${query(scope)}`, { signal }),
  });
  const reviews = (result.data || []).sort(
    (a, b) =>
      (requirements.find((r) => r.id === b.requirement_id)?.priority || 0) -
      (requirements.find((r) => r.id === a.requirement_id)?.priority || 0),
  );
  const [focus, setFocus] = useState(0);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (
        selected ||
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLSelectElement
      )
        return;
      if (e.key === "j") {
        e.preventDefault();
        setFocus((v) => Math.min(reviews.length - 1, v + 1));
      }
      if (e.key === "k") {
        e.preventDefault();
        setFocus((v) => Math.max(0, v - 1));
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [reviews.length, selected]);
  return (
    <>
      <Heading
        title="Needs review"
        description="Understand what changed, compare the approved baseline and make the next decision."
        action={
          <span className="workspace-status">
            J / K to select · Open to inspect
          </span>
        }
      />
      {result.error ? (
        <ErrorMessage error={result.error} />
      ) : result.isPending ? (
        <Loading />
      ) : !reviews.length ? (
        <Panel title="All caught up">
          <Empty
            title="No open review items"
            description="Meaningful changes to evidence, priorities or approved requirements will appear here."
          />
        </Panel>
      ) : (
        <div className="review-inbox">
          {reviews.map((review, i) => {
            const req = requirements.find(
              (r) => r.id === review.requirement_id,
            );
            return (
              <article key={review.id} className={i === focus ? "focused" : ""}>
                <div className="review-index">
                  {String(i + 1).padStart(2, "0")}
                </div>
                <div className="review-body">
                  <span className="requirement-key">
                    {req?.key || review.requirement_id}
                  </span>
                  <h2>{req?.title || "Requirement review"}</h2>
                  <p>{review.reason}</p>
                  <div className="review-meta">
                    <Status value="needs_review" />
                    <span>{date(review.created_at)}</span>
                    {req && (
                      <ScoreLabel
                        score={req.priority}
                        grade={req.evidence_grade}
                      />
                    )}
                  </div>
                  <details>
                    <summary>Recorded changes</summary>
                    <pre className="json-record">
                      {JSON.stringify(review.changes, null, 2)}
                    </pre>
                  </details>
                </div>
                <Button
                  variant="outline"
                  onClick={() =>
                    set(
                      { requirement: review.requirement_id, tab: "versions" },
                      true,
                    )
                  }
                >
                  Open review
                  <ArrowUpRight size={14} />
                </Button>
              </article>
            );
          })}
        </div>
      )}
    </>
  );
}
