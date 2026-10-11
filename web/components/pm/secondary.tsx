"use client";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import Link from "next/link";
import {
  Download,
  Search,
  ShieldCheck,
  ArrowUpRight,
  Monitor,
  Info,
} from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { PmSelect } from "./pm-select";
import { useWorkspace } from "./context";
import {
  Heading,
  Panel,
  ScoreLabel,
  Status,
  Loading,
  ErrorMessage,
  Empty,
  useUrlState,
  Field,
} from "./shared";
import { allAudit, allPages, date, readable } from "@/lib/api";
import { download } from "@/lib/export";
import type { Requirement } from "@/lib/types";
export function AuditPage() {
  const { params, set } = useUrlState();
  const { actors } = useWorkspace();
  const [page, setPage] = useState(1);
  const actor = params.get("actor") || "";
  const action = params.get("action") || "";
  const entity = params.get("entity") || "";
  const q = params.get("q") || "";
  const from = params.get("from") || "";
  const to = params.get("to") || "";
  const result = useQuery({
    queryKey: ["audit", entity],
    queryFn: ({ signal }) => allAudit(entity || undefined, signal),
  });
  const filtered = (result.data || []).filter(
    (e) =>
      (!actor || e.actor === actor) &&
      (!action || e.action === action) &&
      (!q ||
        `${e.rationale} ${e.entity_id} ${e.actor} ${e.action}`
          .toLowerCase()
          .includes(q.toLowerCase())) &&
      (!from || e.created_at.slice(0, 10) >= from) &&
      (!to || e.created_at.slice(0, 10) <= to),
  );
  const pages = Math.max(1, Math.ceil(filtered.length / 40));
  const current = Math.min(page, pages);
  const visible = filtered.slice((current - 1) * 40, current * 40);
  return (
    <>
      <Heading
        title="Audit trail"
        description="An append-only record of human decisions, proposals, imports and evidence access across all scopes."
        action={
          <Button
            variant="outline"
            disabled={!result.data}
            onClick={() =>
              download("audit-events.json", JSON.stringify(filtered, null, 2))
            }
          >
            <Download size={14} />
            Export JSON
          </Button>
        }
      />
      <div className="pm-alert">
        <ShieldCheck size={17} />
        <span>
          Events carry a tamper-evident hash chain in the database. Full chain
          verification is available through the database CLI; the API does not
          expose a verification result.
        </span>
      </div>
      <div className="register-toolbar">
        <div className="search-input">
          <Search size={15} />
          <input
            aria-label="Search audit"
            value={q}
            placeholder="Search actor, entity or rationale"
            onChange={(e) => {
              set({ q: e.target.value });
              setPage(1);
            }}
          />
        </div>
        <PmSelect
          aria-label="Audit actor"
          value={actor}
          onValueChange={(value) => {
            set({ actor: value });
            setPage(1);
          }}
          options={[
            { value: "", label: "All actors" },
            ...[...new Set(result.data?.map((e) => e.actor) || [])].sort().map((a) => ({
              value: a, label: actors.find((x) => x.id === a)?.display_name || a,
            })),
          ]}
        />
        <PmSelect
          aria-label="Audit action"
          value={action}
          onValueChange={(value) => {
            set({ action: value });
            setPage(1);
          }}
          options={[
            { value: "", label: "All actions" },
            ...[...new Set(result.data?.map((e) => e.action) || [])].sort().map((a) => ({ value: a, label: readable(a) })),
          ]}
        />
      </div>
      <div className="audit-filters">
        <Field label="Entity ID">
          <input
            className="pm-input"
            value={entity}
            placeholder="Any source, requirement or workflow ID"
            onChange={(e) => {
              set({ entity: e.target.value });
              setPage(1);
            }}
          />
        </Field>
        <Field label="From (UTC date)">
          <input
            type="date"
            className="pm-input"
            value={from}
            onChange={(e) => set({ from: e.target.value })}
          />
        </Field>
        <Field label="Through (UTC date)">
          <input
            type="date"
            className="pm-input"
            value={to}
            onChange={(e) => set({ to: e.target.value })}
          />
        </Field>
      </div>
      {result.error ? (
        <ErrorMessage error={result.error} />
      ) : result.isPending ? (
        <Loading />
      ) : (
        <Panel
          title={`${filtered.length} audit events`}
          description="Newest first. Detail views and exports of planning briefs are access events."
        >
          <div className="audit-timeline">
            {visible.map((event) => (
              <article key={event.id}>
                <span className="timeline-dot" />
                <div>
                  <div className="audit-event-title">
                    <strong>{readable(event.action)}</strong>
                    <span className="mono muted">#{event.sequence}</span>
                  </div>
                  <p>{event.rationale}</p>
                  <small>
                    {event.actor} · {date(event.created_at)} ·{" "}
                    {event.entity_type}
                  </small>
                  <details>
                    <summary>Inspect event, entity and hashes</summary>
                    <pre className="json-record">
                      {JSON.stringify(event, null, 2)}
                    </pre>
                  </details>
                </div>
              </article>
            ))}
          </div>
          {!visible.length && (
            <Empty
              title="No matching audit events"
              description="Change your actor, action, entity or date filters."
            />
          )}
          <div className="pagination">
            <Button
              variant="outline"
              disabled={current === 1}
              onClick={() => setPage(current - 1)}
            >
              Previous
            </Button>
            <span>
              {current} / {pages}
            </span>
            <Button
              variant="outline"
              disabled={current === pages}
              onClick={() => setPage(current + 1)}
            >
              Next
            </Button>
          </div>
        </Panel>
      )}
    </>
  );
}
export function Markets() {
  const { scope, workspace } = useWorkspace();
  const result = useQuery({
    queryKey: ["market-requirements", scope.vehicle],
    queryFn: ({ signal }) =>
      allPages<Requirement>(
        `/requirements?vehicle=${encodeURIComponent(scope.vehicle)}`,
        signal,
      ),
  });
  const topics = [...new Set(result.data?.map((r) => r.topic) || [])].sort();
  const markets = [
    ...new Set([
      "US",
      "CN",
      "EU",
      ...(workspace?.available_scopes
        .filter((s) => s.vehicle === scope.vehicle)
        .map((s) => s.market) || []),
    ]),
  ];
  return (
    <>
      <Heading
        title="Market comparison"
        description={`Compare ${scope.vehicle} customer priorities across markets, with missing evidence left visible.`}
      />
      <div className="pm-alert">
        <Info size={16} />
        <span>
          Scores use each market’s recorded rubric and evidence. An empty market
          is missing data, not evidence of no customer need.
        </span>
      </div>
      {result.error ? (
        <ErrorMessage error={result.error} />
      ) : result.isPending ? (
        <Loading />
      ) : !topics.length ? (
        <Panel title="Market priorities">
          <Empty
            title="No market requirements yet"
            description="Import market-specific evidence and run the pipeline to compare priorities."
          />
        </Panel>
      ) : (
        <div className="pm-table-wrap">
          <table className="pm-table market-table">
            <thead>
              <tr>
                <th className="pin-column">Customer topic</th>
                {markets.map((m) => (
                  <th key={m}>
                    {m}
                    <small>
                      {result.data.filter((r) => r.market === m).length}{" "}
                      requirements
                    </small>
                  </th>
                ))}
                <th>Priority spread</th>
              </tr>
            </thead>
            <tbody>
              {topics.map((topic) => {
                const values = result.data.filter((r) => r.topic === topic);
                const scores = values.map((r) => r.priority);
                const spread =
                  scores.length > 1
                    ? Math.max(...scores) - Math.min(...scores)
                    : null;
                return (
                  <tr key={topic}>
                    <td className="pin-column">
                      <strong>{readable(topic)}</strong>
                    </td>
                    {markets.map((m) => (
                      <td key={m}>
                        {values.filter((r) => r.market === m).length ? (
                          values
                            .filter((r) => r.market === m)
                            .map((r) => (
                              <Link
                                key={r.id}
                                className="market-cell"
                                href={`/${scope.vehicle.toLowerCase()}/${m.toLowerCase()}/requirements?requirement=${r.id}`}
                              >
                                <ScoreLabel
                                  score={r.priority}
                                  grade={r.evidence_grade}
                                />
                                <span>{r.title}</span>
                                <Status value={r.status} />
                              </Link>
                            ))
                        ) : (
                          <span className="market-missing">
                            No requirement data
                          </span>
                        )}
                      </td>
                    ))}
                    <td>
                      {spread == null ? (
                        <span className="muted">One market only</span>
                      ) : (
                        <span className={spread >= 15 ? "spread-high" : ""}>
                          {spread.toFixed(1)} points
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
export function SettingsPage() {
  const { actor, actors, setActor, compact, setCompact, scope } =
    useWorkspace();
  const { setTheme, resolvedTheme } = useTheme();
  return (
    <>
      <Heading
        title="Workspace settings"
        description="Your viewing preferences and the people responsible for each decision."
      />
      <div className="settings-grid">
        <Panel
          title="Appearance"
          description="Preferences are stored in this browser."
        >
          <div className="setting-row">
            <span>Color theme</span>
            <PmSelect
              aria-label="Color theme"
              className="pm-select"
              value={resolvedTheme || "light"}
              onValueChange={setTheme}
              options={[{ value: "light", label: "Light" }, { value: "dark", label: "Dark" }]}
            />
          </div>
          <div className="setting-row">
            <span>Table density</span>
            <PmSelect
              aria-label="Table density"
              className="pm-select"
              value={compact ? "compact" : "comfortable"}
              onValueChange={(value) => setCompact(value === "compact")}
              options={[{ value: "comfortable", label: "Comfortable" }, { value: "compact", label: "Compact" }]}
            />
          </div>
        </Panel>
        <Panel
          title="Declared reviewer"
          description="This local prototype records a declared identity. It does not authenticate enterprise accounts."
        >
          <Field label="Acting reviewer">
            <PmSelect
              aria-label="Settings reviewer"
              className="pm-select"
              value={actor?.id || ""}
              onValueChange={setActor}
              options={[
                { value: "", label: "Select reviewer" },
                ...actors.map((a) => ({ value: a.id, label: `${a.display_name} · ${readable(a.role)}` })),
              ]}
            />
          </Field>
          <p className="muted mt-4">
            Approve, reject and complete require a PM. Viewers are read-only.
            The API and database enforce their own decision gates.
          </p>
        </Panel>
      </div>
      <Panel
        title="Connected services"
        description="The browser and MCP clients share the same backend workflow and records."
      >
        <div className="setting-row">
          <span>
            <strong>FastAPI</strong>
            <small>
              Source import, analysis, versioned requirements and PM decisions
            </small>
          </span>
          <a
            className="text-link"
            href="/api/backend/openapi.json"
            target="_blank"
            rel="noreferrer"
          >
            Open API contract
            <ArrowUpRight size={14} />
          </a>
        </div>
        <div className="setting-row">
          <span>
            <strong>MCP</strong>
            <small>
              Evidence, requirements, scoring, workflow and trace tools for AI
              clients
            </small>
          </span>
          <span className="workspace-status">Same governed API</span>
        </div>
        <div className="setting-row">
          <span>
            <strong>Active scope</strong>
            <small>
              Predecessor evidence informs successor product planning
            </small>
          </span>
          <span className="mono">
            {scope.vehicle} / {scope.market}
          </span>
        </div>
      </Panel>
      <Panel title="Decision boundaries">
        <div className="boundary-grid">
          <div>
            <ShieldCheck size={22} />
            <h3>Human approval</h3>
            <p>
              AI and system actors can propose. Human PMs own approval and
              rejection.
            </p>
          </div>
          <div>
            <FileBoundary />
            <h3>Immutable history</h3>
            <p>
              New evidence creates proposals. The last approved version remains
              available.
            </p>
          </div>
          <div>
            <Monitor size={22} />
            <h3>Local workspace</h3>
            <p>
              SSO, external notifications and enterprise connectors remain
              deployment work.
            </p>
          </div>
        </div>
      </Panel>
    </>
  );
}
function FileBoundary() {
  return <Info size={22} />;
}
