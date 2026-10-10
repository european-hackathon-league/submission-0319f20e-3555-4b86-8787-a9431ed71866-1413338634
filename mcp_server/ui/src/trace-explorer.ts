import { App, applyDocumentTheme, applyHostStyleVariables, type McpUiHostContext } from "@modelcontextprotocol/ext-apps";
import { callTool, unpack } from "./shared/api";
import "./shared/styles.css";
import "./trace.css";

type RecordData = Record<string, unknown>;
type ReadTool = "trace_requirement" | "get_requirement_versions" | "get_finding" | "get_evidence" | "get_source" | "list_audit";
type Request = (name: ReadTool, args: RecordData) => Promise<unknown>;
type Source = RecordData & { id: string; title: string; reference: string; metadata: RecordData };
type Evidence = RecordData & { id: string; source_id: string; content: string; location: RecordData; metadata: RecordData };
type Finding = RecordData & { id: string; summary: string; evidence_ids: string[]; conflicting_evidence_ids: string[] };
type Version = RecordData & { id: string; requirement_id: string; version: number; finding_ids: string[]; score: RecordData | null };
type Requirement = RecordData & { id: string; current_version_id: string; approved_version_id: string | null; approved_score_id: string | null };
export type Trace = {
  requirement: Requirement;
  version: Version;
  findings: Finding[];
  sources: Source[];
  evidence: { items: Evidence[]; total: number; limit: number; offset: number };
  decisions: RecordData[];
};
const PAGE_SIZE = 12;
const AUDIT_PAGE_SIZE = 10;
const record = (value: unknown): RecordData => value !== null && typeof value === "object" && !Array.isArray(value) ? value as RecordData : {};
const list = (value: unknown): unknown[] => Array.isArray(value) ? value : [];
const strings = (value: unknown): string[] => list(value).filter((item): item is string => typeof item === "string");
const valueText = (value: unknown, fallback = "Not recorded"): string => typeof value === "string" && value.length ? value : typeof value === "number" ? String(value) : fallback;
const label = (value: unknown) => valueText(value).replaceAll("_", " ");
const pretty = (value: unknown) => JSON.stringify(value, null, 2) ?? "Not recorded";
const idOf = (value: unknown) => typeof record(value).id === "string" ? record(value).id as string : "";

export function safeSourceUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}

export function parseTrace(value: unknown): Trace {
  const data = record(value), req = record(data.requirement), version = record(data.version), evidence = record(data.evidence);
  if (!idOf(req) || !idOf(version) || version.requirement_id !== req.id || !Number.isInteger(version.version)
      || !Array.isArray(data.findings) || !Array.isArray(data.sources) || !Array.isArray(data.decisions)
      || !Array.isArray(evidence.items) || !Number.isInteger(evidence.total) || Number(evidence.total) < 0
      || !Number.isInteger(evidence.offset) || Number(evidence.offset) < 0
      || !Number.isInteger(evidence.limit) || Number(evidence.limit) < 1
      || data.findings.some((finding) => !idOf(finding)) || data.sources.some((source) => !idOf(source))
      || evidence.items.some((item) => !idOf(item) || typeof record(item).content !== "string")) {
    throw new Error("The host returned an incomplete requirement trace. Reload the trace to try again.");
  }
  return data as Trace;
}

function message(error: unknown): string {
  const detail = error instanceof Error ? error.message : valueText(error, "The request could not be completed.");
  if (/\b403\b|permission|access denied/i.test(detail)) return `Access denied. The host or API did not allow this read. ${detail}`;
  if (/\b404\b|\b409\b|stale|not found/i.test(detail)) return `This record is unavailable or has changed. Reload the trace before continuing. ${detail}`;
  return detail;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, text?: string, className?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function button(text: string, action: () => void, disabled = false): HTMLButtonElement {
  const node = el("button", text, "trace-secondary");
  node.type = "button";
  node.disabled = disabled;
  node.addEventListener("click", action);
  return node;
}
function details(title: string, open = false): [HTMLDetailsElement, HTMLElement] {
  const node = el("details");
  node.open = open;
  node.append(el("summary", title));
  const body = el("div", undefined, "trace-detail");
  node.append(body);
  return [node, body];
}
function fieldList(pairs: [string, unknown][]): HTMLDListElement {
  const node = el("dl", undefined, "trace-kv");
  for (const [name, value] of pairs) node.append(el("dt", name), el("dd", valueText(value)));
  return node;
}
function jsonDetails(title: string, data: unknown): HTMLElement {
  const [node, body] = details(title);
  body.append(el("pre", pretty(data)));
  return node;
}
function empty(text: string): HTMLElement { return el("p", text, "trace-empty"); }
function badge(text: string, extra = ""): HTMLElement { return el("span", text, `badge ${extra}`); }
function errorBox(text: string): HTMLElement {
  const node = el("div", text, "error trace-error");
  node.setAttribute("role", "alert");
  return node;
}

/** Owns one trace view. A generation check prevents slow reads replacing a newer selection. */
export class TraceExplorer {
  private trace: Trace | null = null;
  private versions: Version[] = [];
  private generation = 0;
  private busy = false;
  private connected = false;
  private error = "";
  private versionsError = "";
  private versionsBusy = false;
  private status = "Waiting for a requirement trace from the host…";
  private sources = new Map<string, Source>();
  private evidence = new Map<string, Evidence>();
  private requestedRequirement = "";
  private requestedVersion: string | null = null;
  private hostInputPending = false;
  private auditRows: RecordData[] = [];
  private auditAfter = 0;
  private auditBusy = false;
  private auditLoaded = false;
  private auditError = "";
  private auditHasMore = true;
  private auditOpen = false;
  private expanded = new Map<string, boolean>();

  constructor(private root: HTMLElement, private request: Request, private openLink?: (url: string) => Promise<unknown>) {
    this.render();
  }

  setConnected(): void { this.connected = true; this.render(); if (this.trace && !this.versions.length && !this.versionsBusy) void this.loadVersions(); }
  connectionFailed(error: unknown): void { this.error = message(error); this.status = "Host connection failed. Reopen this app to reconnect."; this.render(); }
  setInput(value: unknown): void {
    const input = record(value);
    if (typeof input.requirement_id === "string") {
      this.requestedRequirement = input.requirement_id;
      this.requestedVersion = typeof input.version_id === "string" ? input.version_id : null;
      this.hostInputPending = true;
      ++this.generation;
      this.busy = this.versionsBusy = this.auditBusy = false;
    }
  }

  receive(value: unknown): void {
    ++this.generation;
    this.busy = false;
    this.versionsBusy = false;
    this.auditBusy = false;
    this.error = "";
    try {
      const trace = parseTrace(value);
      this.requestedRequirement = trace.requirement.id;
      this.versions = [];
      this.versionsError = "";
      this.accept(trace);
      if (this.connected) void this.loadVersions();
    } catch (error) {
      this.error = message(error);
      this.status = "No new trace was loaded.";
      this.render();
    }
  }

  receiveError(error: unknown): void {
    ++this.generation;
    this.busy = false;
    this.versionsBusy = false;
    this.auditBusy = false;
    this.error = message(error);
    this.status = "The host could not load the trace.";
    this.render();
  }

  private accept(trace: Trace): void {
    const preserveOpen = this.trace?.version.id === trace.version.id;
    if (this.trace?.requirement.id !== trace.requirement.id) this.versions = [];
    this.requestedRequirement = trace.requirement.id;
    this.requestedVersion = trace.version.id;
    this.hostInputPending = false;
    this.trace = trace;
    this.sources = new Map(trace.sources.map((source) => [source.id, source]));
    this.evidence = new Map(this.pageItems().map((item) => [item.id, item]));
    this.auditRows = [];
    this.auditAfter = 0;
    this.auditBusy = false;
    this.auditLoaded = false;
    this.auditError = "";
    this.auditHasMore = true;
    this.auditOpen = false;
    this.status = "Trace loaded. Expand a finding to inspect its original evidence.";
    this.render(preserveOpen);
  }

  private pageItems(): Evidence[] { return this.trace?.evidence.items.slice(0, PAGE_SIZE) ?? []; }

  private async loadVersions(): Promise<void> {
    if (!this.trace) return;
    const generation = this.generation, requirement = this.trace.requirement.id;
    this.versionsBusy = true;
    this.versionsError = "";
    this.render();
    try {
      const data = await this.request("get_requirement_versions", { requirement_id: requirement });
      if (generation !== this.generation) return;
      if (!Array.isArray(data) || data.some((version) => !idOf(version) || record(version).requirement_id !== requirement || !Number.isInteger(record(version).version))) {
        throw new Error("The version history response is incomplete.");
      }
      this.versions = (data as Version[]).sort((a, b) => b.version - a.version);
    } catch (error) {
      if (generation === this.generation) this.versionsError = message(error);
    } finally {
      if (generation === this.generation) { this.versionsBusy = false; this.render(); }
    }
  }

  private async loadTrace(versionId: string | null, offset: number, reloadVersions = false, requirementId?: string): Promise<void> {
    const requirement = requirementId ?? this.trace?.requirement.id ?? this.requestedRequirement;
    if (!requirement || !this.connected) return;
    const generation = ++this.generation;
    this.busy = true;
    this.versionsBusy = false;
    this.auditBusy = false;
    this.error = "";
    this.status = "Loading the selected trace…";
    this.render();
    try {
      const args: RecordData = { requirement_id: requirement, limit: PAGE_SIZE, offset };
      if (versionId) args.version_id = versionId;
      const data = parseTrace(await this.request("trace_requirement", args));
      if (generation !== this.generation) return;
      if (data.requirement.id !== requirement || (versionId && data.version.id !== versionId) || data.evidence.offset !== offset) {
        throw new Error("The returned trace does not match the selected version and evidence page. Reload to try again.");
      }
      this.busy = false;
      this.accept(data);
      if (reloadVersions || this.versions.length === 0) void this.loadVersions();
    } catch (error) {
      if (generation !== this.generation) return;
      this.busy = false;
      this.error = message(error);
      this.status = this.trace ? "Showing the previous trace because the new read failed." : "No trace was loaded.";
      this.render();
    }
  }

  private versionName(id: unknown): string {
    const version = this.versions.find((item) => item.id === id) ?? (this.trace && this.trace.version.id === id ? this.trace.version : undefined);
    return version ? `Version ${version.version}` : id ? "Recorded version" : "No approved version";
  }

  private treeDetails(title: string, key: string, open = false): [HTMLDetailsElement, HTMLElement] {
    const [node, body] = details(title, this.expanded.get(key) ?? open);
    node.dataset.traceNode = key;
    const generation = this.generation;
    node.addEventListener("toggle", () => {
      if (generation === this.generation && node.isConnected) this.expanded.set(key, node.open);
    });
    return [node, body];
  }

  private render(preserveOpen = true): void {
    const trace = this.trace;
    if (preserveOpen) {
      for (const node of this.root.querySelectorAll<HTMLDetailsElement>("details[data-trace-node]")) this.expanded.set(node.dataset.traceNode!, node.open);
    } else this.expanded.clear();
    this.root.replaceChildren();
    const header = el("header", undefined, "trace-heading");
    const heading = el("div");
    heading.append(el("p", "BMW PRODUCT EVIDENCE · TRACE EXPLORER", "eyebrow"));
    heading.append(el("h1", trace ? valueText(trace.requirement.key, "Requirement trace") : "Requirement trace"));
    if (trace) heading.append(el("p", valueText(trace.version.title), "muted"));
    header.append(heading, button("Reload trace", () => void this.loadTrace(
      this.hostInputPending ? this.requestedVersion : this.trace?.version.id ?? null,
      0, true, this.hostInputPending ? this.requestedRequirement : undefined,
    ), !this.connected || this.busy || (!trace && !this.requestedRequirement)));
    this.root.append(header);
    if (trace) {
      const badges = el("div", undefined, "trace-badges");
      badges.append(badge(`${valueText(trace.requirement.vehicle)} / ${valueText(trace.requirement.market)}`), badge(label(trace.requirement.status)), badge(`Viewing version ${trace.version.version}`, "trace-current"));
      this.root.append(badges);
    }
    const status = el("p", this.status, "trace-status");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    this.root.append(status);
    if (this.error) this.root.append(errorBox(this.error));
    if (!trace) { this.root.append(empty("Open this explorer from a requirement trace to inspect its source-to-decision history.")); return; }
    const controls = el("div", undefined, "trace-controls");
    const selectLabel = el("label", "Requirement version");
    selectLabel.htmlFor = "trace-version";
    const select = el("select");
    select.id = "trace-version";
    const versions = this.versions.length ? this.versions : [trace.version];
    for (const version of versions) {
      const tags = [version.id === trace.requirement.current_version_id ? "current" : "", version.id === trace.requirement.approved_version_id ? "approved" : ""].filter(Boolean);
      const option = el("option", `Version ${version.version}${tags.length ? ` · ${tags.join(" · ")}` : ""}`);
      option.value = version.id;
      option.selected = version.id === trace.version.id;
      select.append(option);
    }
    select.disabled = !this.connected || this.busy || this.versionsBusy;
    select.addEventListener("change", () => void this.loadTrace(select.value, 0));
    controls.append(selectLabel, select, el("span", this.versionsBusy ? "Loading history…" : "Newest first", "muted"));
    if (trace.version.id !== trace.requirement.current_version_id) controls.append(button("View current version", () => void this.loadTrace(null, 0, true), this.busy || !this.connected));
    this.root.append(controls);
    if (this.versionsError) {
      const error = errorBox(`Version history: ${this.versionsError}`);
      error.append(button("Retry version history", () => void this.loadVersions(), this.versionsBusy || !this.connected));
      this.root.append(error);
    }
    const flow = el("ol", undefined, "trace-flow");
    for (const text of ["Requirement version", "Findings", "Exact evidence", "Source", "Score & decision"]) flow.append(el("li", text));
    this.root.append(flow, this.renderVersion(trace), this.renderFindings(trace), this.renderScore(trace), this.renderDecisions(trace), this.renderAudit());
  }

  private renderVersion(trace: Trace): HTMLElement {
    const section = el("section", undefined, "card");
    section.append(el("h2", "Requirement & baseline"));
    const states = el("div", undefined, "trace-state-grid");
    for (const [name, id] of [["Current proposal", trace.requirement.current_version_id], ["Approved baseline", trace.requirement.approved_version_id]]) {
      const state = el("div");
      state.append(el("span", name as string), el("strong", this.versionName(id)));
      states.append(state);
    }
    section.append(states, el("p", valueText(trace.version.statement)));
    const [detail, body] = this.treeDetails("Version details, criteria & assumptions", "version");
    body.append(fieldList([["Customer need", trace.version.customer_need], ["Created", trace.version.created_at], ["Author", trace.version.actor], ["Rationale", trace.version.rationale]]));
    body.append(el("h3", "Acceptance criteria"));
    const criteria = list(trace.version.acceptance_criteria);
    for (const raw of criteria) {
      const criterion = record(raw);
      body.append(fieldList([["Metric", criterion.metric], ["Target", `${valueText(criterion.target)}${criterion.unit ? ` ${valueText(criterion.unit)}` : ""}`], ["Basis", criterion.basis], ["Source references", strings(criterion.source_ids).join(", ") || "None recorded"]]));
    }
    if (!criteria.length) body.append(empty("No acceptance criteria recorded."));
    body.append(el("h3", "Assumptions"));
    const assumptions = strings(trace.version.assumptions);
    if (assumptions.length) {
      const items = el("ul");
      for (const text of assumptions) items.append(el("li", text));
      body.append(items);
    } else body.append(empty("No assumptions recorded."));
    body.append(fieldList([["Requirement ID", trace.requirement.id], ["Viewing version ID", trace.version.id], ["Current version ID", trace.requirement.current_version_id], ["Approved version ID", trace.requirement.approved_version_id], ["Approved score ID", trace.requirement.approved_score_id]]));
    section.append(detail);
    return section;
  }

  private renderFindings(trace: Trace): HTMLElement {
    const section = el("section", undefined, "card");
    section.append(el("h2", `Findings & evidence · ${trace.findings.length} finding${trace.findings.length === 1 ? "" : "s"}`));
    section.append(el("p", "Expand a finding, then an evidence record to read its exact text and source location. Supporting and conflicting links remain distinct.", "muted"));
    if (!trace.findings.length) section.append(empty("No findings are linked to this version."));
    for (const finding of trace.findings) {
      const [node, body] = this.treeDetails(valueText(finding.summary, "Finding"), `finding:${finding.id}`);
      node.classList.add("trace-finding");
      const badges = el("span", undefined, "trace-badges");
      badges.append(badge(label(finding.kind)));
      if (typeof finding.confidence === "number") badges.append(badge(`${Math.round(finding.confidence * 100)}% confidence`));
      body.append(badges);
      this.renderFindingBody(body, finding);
      const generation = this.generation;
      const refresh = button("Reload finding", async () => {
        refresh.disabled = true;
        try {
          const data = await this.request("get_finding", { finding_id: finding.id });
          if (generation !== this.generation || !body.isConnected) return;
          if (idOf(data) !== finding.id) throw new Error("The finding response did not match the selected record.");
          body.replaceChildren();
          this.renderFindingBody(body, data as Finding);
          body.append(refresh);
        } catch (error) { if (generation === this.generation && body.isConnected) body.append(errorBox(message(error))); }
        finally { refresh.disabled = !this.connected; }
      }, !this.connected);
      body.append(refresh);
      section.append(node);
    }
    const page = trace.evidence, count = this.pageItems().length;
    const pagination = el("div", undefined, "trace-pagination");
    pagination.append(el("p", count ? `Evidence ${page.offset + 1}–${page.offset + count} of ${page.total}` : `No evidence on this page · ${page.total} linked in total`));
    const actions = el("div");
    actions.append(button("Previous evidence", () => void this.loadTrace(trace.version.id, Math.max(0, page.offset - PAGE_SIZE)), !this.connected || this.busy || page.offset === 0));
    actions.append(button("Next evidence", () => void this.loadTrace(trace.version.id, page.offset + count), !this.connected || this.busy || !count || page.offset + count >= page.total));
    pagination.append(actions);
    section.append(pagination);
    return section;
  }

  private renderFindingBody(body: HTMLElement, finding: Finding): void {
    body.append(fieldList([["Topic", finding.topic], ["Interpretation", finding.summary], ["Recorded", finding.created_at]]));
    let shown = 0, linked = 0;
    for (const [relation, ids] of [["Supports", strings(finding.evidence_ids)], ["Conflicts", strings(finding.conflicting_evidence_ids)]] as const) {
      linked += ids.length;
      for (const id of ids) {
        const evidence = this.evidence.get(id);
        if (evidence) { body.append(this.renderEvidence(evidence, relation, finding.id)); shown++; }
      }
    }
    if (!linked) body.append(empty("No evidence links recorded for this finding."));
    else if (linked > shown) body.append(el("p", `${linked - shown} linked evidence record${linked - shown === 1 ? " is" : "s are"} on other pages. Use the evidence page controls below.`, "trace-note"));
  }

  private renderEvidence(evidence: Evidence, relation: string, findingId: string): HTMLElement {
    const source = this.sources.get(evidence.source_id);
    const occurrence = `${findingId}:${relation}:${evidence.id}`;
    const [node, body] = this.treeDetails(`${relation} · ${valueText(source?.title, "Evidence record")}`, `evidence:${occurrence}`);
    node.classList.add("trace-evidence");
    let rendered = false;
    const generation = this.generation;
    node.addEventListener("toggle", () => {
      if (!node.open || rendered || generation !== this.generation || !node.isConnected) return;
      rendered = true;
      const renderRecord = (item: Evidence) => {
        body.replaceChildren(el("p", "EXACT SOURCE TEXT", "eyebrow"), el("blockquote", item.content, "trace-quote"));
        body.append(el("h3", "Source location"));
        const location = record(item.location);
        const entries = Object.entries(location);
        body.append(entries.length ? fieldList(entries.map(([key, value]) => [label(key), typeof value === "object" ? pretty(value) : value])) : empty("No location was recorded."));
        body.append(this.dateContext(item), jsonDetails("Full evidence metadata", item.metadata ?? {}), fieldList([["Evidence ID", item.id], ["Source ID", item.source_id]]));
        const refresh = button("Reload evidence", async () => {
          refresh.disabled = true;
          try {
            const result = await this.request("get_evidence", { evidence_id: item.id });
            if (generation !== this.generation || !body.isConnected) return;
            if (idOf(result) !== item.id || typeof record(result).content !== "string") throw new Error("The evidence response did not match the selected record.");
            renderRecord(result as Evidence);
          } catch (error) { if (generation === this.generation && body.isConnected) body.append(errorBox(message(error))); }
          finally { refresh.disabled = !this.connected; }
        }, !this.connected);
        body.append(refresh);
        body.append(this.renderSource(item.source_id, source, generation, occurrence));
      };
      renderRecord(evidence);
    });
    return node;
  }

  private dateContext(item: RecordData): HTMLElement {
    const wrapper = el("div");
    const metadata = record(item.metadata), web = record(metadata.web_evidence);
    wrapper.append(fieldList([["Observed", item.observed_at], ["Published", web.publication_date], ["Retrieved", web.retrieved_at], ["Stored", item.created_at]]));
    if (!item.observed_at) wrapper.append(el("p", "Observation date is unknown. Publication, retrieval and storage dates are separate and do not establish when the customer experience occurred.", "trace-note"));
    const uncertainty = [...strings(web.uncertainties), ...strings(web.warnings)];
    if (uncertainty.length) wrapper.append(el("p", uncertainty.join("\n"), "trace-note"));
    if (metadata.review_status || web.review_status) wrapper.append(el("p", `Evidence review status: ${valueText(metadata.review_status ?? web.review_status)}.`, "muted"));
    return wrapper;
  }

  private renderSource(sourceId: string, known: Source | undefined, generation: number, occurrence: string): HTMLElement {
    const [node, body] = this.treeDetails(`Source · ${valueText(known?.title, "Open source record")}`, `source:${occurrence}:${sourceId}`);
    let loading = false, loaded = false;
    const renderSource = (source: Source) => {
      body.replaceChildren();
      body.append(fieldList([["Title", source.title], ["Kind", source.kind], ["Scope", `${valueText(source.vehicle)} / ${valueText(source.market)}`]]));
      const url = safeSourceUrl(source.reference);
      if (url) {
        const link = el("a", source.reference);
        link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer";
        if (this.openLink) link.addEventListener("click", (event) => {
          event.preventDefault();
          void this.openLink!(url).catch((error: unknown) => { if (generation === this.generation && body.isConnected) body.append(errorBox(message(error))); });
        });
        body.append(link);
      } else body.append(fieldList([["Reference", source.reference]]));
      body.append(this.dateContext(source), jsonDetails("Full source metadata", source.metadata ?? {}), fieldList([["Source ID", source.id], ["Snapshot hash", source.content_hash]]));
    };
    if (known) renderSource(known);
    const load = async () => {
      if (loading || !this.connected) return;
      loading = true;
      try {
        const result = await this.request("get_source", { source_id: sourceId });
        if (generation !== this.generation || !body.isConnected) return;
        if (idOf(result) !== sourceId) throw new Error("The source response did not match the selected record.");
        loaded = true;
        this.sources.set(sourceId, result as Source);
        renderSource(result as Source);
      } catch (error) {
        if (generation !== this.generation || !body.isConnected) return;
        body.append(errorBox(message(error)), button("Retry source", () => void load()));
      } finally { loading = false; }
    };
    node.addEventListener("toggle", () => { if (node.open && !loaded && generation === this.generation && node.isConnected) void load(); });
    return node;
  }

  private renderScore(trace: Trace): HTMLElement {
    const section = el("section", undefined, "card");
    const [node, body] = this.treeDetails("Recorded priority & evidence quality", "score");
    const score = record(trace.version.score);
    if (!idOf(score)) { body.append(empty("No score is recorded for this version.")); section.append(node); return section; }
    const total = el("div", undefined, "trace-score");
    total.append(el("strong", valueText(score.total)), el("span", "/ 100", "muted"), badge(`Evidence grade ${valueText(score.evidence_grade)}`));
    body.append(total);
    if (trace.version.id === trace.requirement.approved_version_id && score.id !== trace.requirement.approved_score_id) body.append(el("p", "This is the latest recorded score for the selected version. The approved baseline is tied to a different score; compare its recorded score ID in decisions and audit history.", "trace-note"));
    const factors = record(score.factors), weights = record(score.weights), explanation = record(score.explanation), contributions = record(explanation.contributions);
    const wrap = el("div", undefined, "trace-table-wrap"), table = el("table", undefined, "trace-table");
    const caption = el("caption", "Recorded scoring inputs");
    const head = el("thead"), row = el("tr");
    for (const name of ["Factor", "Judgment / 5", "Weight", "Contribution"]) { const cell = el("th", name); cell.scope = "col"; row.append(cell); }
    head.append(row); table.append(caption, head);
    const rows = el("tbody");
    for (const [key, factor] of Object.entries(factors)) {
      const row = el("tr");
      for (const value of [label(key), valueText(factor), typeof weights[key] === "number" ? `${Math.round(Number(weights[key]) * 100)}%` : "Not recorded", valueText(contributions[key])]) row.append(el("td", value));
      rows.append(row);
    }
    table.append(rows); wrap.append(table); body.append(wrap);
    body.append(fieldList([["Formula", explanation.formula], ["Rubric", score.rubric_version], ["Created", score.created_at], ["Score ID", score.id], ["Version ID", score.version_id]]));
    const limitations = strings(explanation.limitations);
    for (const text of limitations) body.append(el("p", text, "trace-note"));
    body.append(jsonDetails("Full score explanation", score.explanation ?? {}));
    section.append(node);
    return section;
  }

  private renderDecisions(trace: Trace): HTMLElement {
    const section = el("section", undefined, "card");
    const [node, body] = this.treeDetails(`Decisions for version ${trace.version.version} · ${trace.decisions.length}`, "decisions", true);
    if (!trace.decisions.length) body.append(empty("No decisions have been recorded for this version."));
    const history = el("ol", undefined, "trace-history");
    for (const decision of [...trace.decisions].reverse()) {
      const item = el("li"), line = el("div", undefined, "trace-badges");
      line.append(badge(label(decision.action)), el("strong", valueText(decision.actor)), el("small", valueText(decision.created_at)));
      item.append(line, el("p", valueText(decision.rationale)));
      const [refs, refsBody] = details("Exact decision references");
      refsBody.append(fieldList([["Decision ID", decision.id], ["Version ID", decision.version_id], ["Score ID", decision.score_id]]));
      item.append(refs); history.append(item);
    }
    body.append(history); section.append(node);
    return section;
  }

  private renderAudit(): HTMLElement {
    const section = el("section", undefined, "card");
    const [node, body] = details("Requirement audit history", this.auditOpen);
    const generation = this.generation;
    node.addEventListener("toggle", () => {
      if (generation !== this.generation || !node.isConnected) return;
      this.auditOpen = node.open;
      if (node.open && !this.auditLoaded && !this.auditBusy && !this.auditError) void this.loadAudit();
    });
    body.append(el("p", "History covers all versions of this requirement, ordered from earliest to latest. Open an event to inspect its recorded state.", "muted"));
    const history = el("ol", undefined, "trace-history");
    for (const event of this.auditRows) {
      const item = el("li"), [entry, entryBody] = details(`${valueText(event.sequence)} · ${valueText(event.action)}`);
      entryBody.append(fieldList([["Actor", event.actor], ["When", event.created_at], ["Rationale", event.rationale]]), jsonDetails("Before state", event.before_state), jsonDetails("After state", event.after_state), jsonDetails("Event metadata", event.metadata));
      item.append(entry); history.append(item);
    }
    body.append(history);
    if (this.auditError) body.append(errorBox(this.auditError));
    if (this.auditLoaded && !this.auditRows.length) body.append(empty("No audit events are recorded for this requirement."));
    const loadLabel = this.auditBusy ? "Loading history…" : this.auditError ? "Retry audit history" : !this.auditLoaded ? "Load audit history" : this.auditHasMore ? "Load more history" : "Check for newer events";
    body.append(button(loadLabel, () => void this.loadAudit(), !this.connected || this.auditBusy || this.busy));
    section.append(node);
    return section;
  }

  private async loadAudit(): Promise<void> {
    if (!this.trace || !this.connected || this.auditBusy) return;
    const generation = this.generation, requirement = this.trace.requirement.id, after = this.auditAfter;
    this.auditBusy = true;
    this.auditError = "";
    this.auditOpen = true;
    this.render();
    try {
      const data = record(await this.request("list_audit", { entity_id: requirement, after, limit: AUDIT_PAGE_SIZE }));
      if (generation !== this.generation) return;
      if (!Array.isArray(data.items) || !Number.isInteger(data.next_after) || Number(data.next_after) < after
          || data.items.some((item) => !Number.isInteger(record(item).sequence) || Number(record(item).sequence) <= after || record(item).entity_id !== requirement)
          || (data.items.length > 0 && Number(data.next_after) !== Number(record(data.items.at(-1)).sequence))) throw new Error("The audit response did not contain a valid history cursor.");
      const seen = new Set(this.auditRows.map((item) => item.sequence));
      this.auditRows.push(...data.items.map(record).filter((item) => !seen.has(item.sequence)));
      this.auditAfter = Number(data.next_after);
      this.auditLoaded = true;
      this.auditHasMore = data.items.length === AUDIT_PAGE_SIZE;
    } catch (error) { if (generation === this.generation) this.auditError = message(error); }
    finally { if (generation === this.generation) { this.auditBusy = false; this.render(); } }
  }
}

function applyTheme(context: McpUiHostContext): void {
  if (context.theme) applyDocumentTheme(context.theme);
  if (context.styles?.variables) applyHostStyleVariables(context.styles.variables);
}

const root = document.getElementById("trace-app");
if (root) {
  const app = new App({ name: "BMW requirement trace explorer", version: "0.1.0" });
  const explorer = new TraceExplorer(root, (name, args) => callTool(app, name, args), async (url) => {
    const result = await app.openLink({ url });
    if (result.isError) throw new Error("The host could not open this source link.");
    return result;
  });
  app.ontoolinput = (input) => explorer.setInput(input.arguments);
  app.ontoolresult = (result) => {
    try { explorer.receive(unpack(result)); }
    catch (error) { explorer.receiveError(error); }
  };
  app.ontoolcancelled = () => explorer.receiveError(new Error("The host cancelled this trace request. Reload to try again."));
  app.onhostcontextchanged = applyTheme;
  void app.connect().then(() => {
    const context = app.getHostContext();
    if (context) applyTheme(context);
    explorer.setConnected();
  }).catch((error: unknown) => explorer.connectionFailed(error));
}
