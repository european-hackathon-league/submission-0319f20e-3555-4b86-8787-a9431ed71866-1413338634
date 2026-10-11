"use client";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
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
  Loading,
  ErrorMessage,
  Empty,
  useUrlState,
  Field,
} from "./shared";
import { allAudit, date, readable } from "@/lib/api";
import { download } from "@/lib/export";
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
        title="Activity"
        description="Decisions, proposals, imports and source access across all vehicles and markets."
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
          description="Latest activity first, including brief views and downloads."
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
                    <summary>Event details</summary>
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
          description="Choose the name recorded on your decisions in this local workspace. Enterprise sign-in is not configured."
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
          <span className="workspace-status">Connected to the API</span>
        </div>
        <div className="setting-row">
          <span>
            <strong>Vehicle and market</strong>
            <small>
              Selected for this workspace
            </small>
          </span>
          <span className="mono">
            {scope.vehicle} / {scope.market}
          </span>
        </div>
      </Panel>
      <Panel title="How decisions are saved">
        <div className="boundary-grid">
          <div>
            <ShieldCheck size={22} />
            <h3>Human approval</h3>
            <p>
              PMs approve or reject each proposal.
            </p>
          </div>
          <div>
            <FileBoundary />
            <h3>Version history</h3>
            <p>
              Approved versions remain available when new proposals arrive.
            </p>
          </div>
          <div>
            <Monitor size={22} />
            <h3>Local workspace</h3>
            <p>
              Enterprise sign-in and external notifications require deployment setup.
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
