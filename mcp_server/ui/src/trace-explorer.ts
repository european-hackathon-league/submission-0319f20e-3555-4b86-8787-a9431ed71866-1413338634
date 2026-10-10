import { App, applyDocumentTheme, type McpUiHostContext } from "@modelcontextprotocol/ext-apps";
import { callTool, unpack } from "./shared/api";
import { keepWithNext, Pager, splittable } from "./shared/fit";
import { createShell, el, grade, icon, status as statusChip, type Shell } from "./shared/shell";
import "./trace-explorer.css";

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
type Step = "requirement" | "findings" | "evidence" | "score" | "decisions" | "audit";
type Focus = { finding?: string; evidence?: { id: string; relation: string; finding: string }; audit?: number };
type SourceState = { loading: boolean; loaded: boolean; error: string };
const PAGE_SIZE = 12;
const AUDIT_PAGE_SIZE = 10;
const STEPS: [Step, string][] = [["requirement", "Requirement"], ["findings", "Findings"], ["evidence", "Evidence"], ["score", "Score"], ["decisions", "Decisions"], ["audit", "Audit"]];
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

function button(text: string, action: () => void, disabled = false, className = "btn"): HTMLButtonElement {
  const node = el("button", className, text);
  node.type = "button";
  node.disabled = disabled;
  node.addEventListener("click", action);
  return node;
}
function fieldList(pairs: [string, unknown][], className = "kv"): HTMLDListElement {
  const node = el("dl", className);
  for (const [name, value] of pairs) node.append(el("dt", "", name), el("dd", "", valueText(value)));
  return node;
}
function heading(text: string): HTMLElement { return keepWithNext(el("p", "bmw-label", text)); }
function code(data: unknown): HTMLElement { return splittable(el("pre", "code", pretty(data)), "lines"); }
function empty(text: string): HTMLElement { return el("p", "bmw-empty", text); }
function note(text: string): HTMLElement { return splittable(el("p", "bmw-note", text)); }
function alert(text: string): HTMLElement {
  const node = el("div", "bmw-alert", text);
  node.setAttribute("role", "alert");
  node.title = text;
  return node;
}
function row(title: string, excerpt: string, meta: (string | HTMLElement)[], action: () => void): HTMLButtonElement {
  const node = el("button", "row-button");
  node.type = "button";
  const body = el("span");
  body.append(el("span", "row-title", title));
  if (excerpt) body.append(el("span", "row-excerpt", excerpt));
  if (meta.length) {
    const line = el("span", "row-meta");
    for (const item of meta) line.append(typeof item === "string" ? el("span", "", item) : item);
    body.append(line);
  }
  node.append(body, icon("right"));
  node.addEventListener("click", action);
  return node;
}

/** Owns one trace view. A generation check prevents slow reads replacing a newer selection. */
export class TraceExplorer {
  readonly shell: Shell;
  private trace: Trace | null = null;
  private versions: Version[] = [];
  private generation = 0;
  private busy = false;
  private connected = false;
  private error = "";
  private localError = "";
  private versionsError = "";
  private versionsBusy = false;
  private status = "Waiting for a requirement trace from the host…";
  private sources = new Map<string, Source>();
  private sourceStates = new Map<string, SourceState>();
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
  private step: Step = "requirement";
  private focus: Focus = {};
  private pages = new Map<string, number>();
  private recordBusy = false;
  private readonly rail = el("nav", "bmw-panel tx-rail");
  private readonly paneTitle = el("h2", "tx-pane-title");
  private readonly paneLead = el("div", "tx-pane-lead");
  private readonly paneActions = el("div", "bmw-footer-actions");
  private readonly alerts = el("div", "tx-alerts");
  private readonly statusLine = el("p", "bmw-status");
  private readonly footerActions = el("div", "bmw-footer-actions");
  private readonly pager: Pager;

  constructor(root: HTMLElement, private request: Request, private openLink?: (url: string) => Promise<unknown>) {
    this.shell = createShell(root, { reloadLabel: "Reload trace", eyebrow: "BMW product evidence · Trace explorer", title: "Requirement trace" });
    root.classList.add("tx-stage");
    this.shell.reload.addEventListener("click", () => void this.loadTrace(
      this.hostInputPending ? this.requestedVersion : this.trace?.version.id ?? null,
      0, true, this.hostInputPending ? this.requestedRequirement : undefined,
    ));
    this.rail.setAttribute("aria-label", "Trace steps");
    this.pager = new Pager("trace detail", (page) => this.pages.set(this.pageKey(), page));
    const pane = el("section", "bmw-panel tx-pane");
    const head = el("div", "bmw-panel-head");
    head.append(this.paneLead, this.paneActions);
    this.statusLine.setAttribute("role", "status");
    this.statusLine.setAttribute("aria-live", "polite");
    const body = el("div", "bmw-pane");
    const footer = el("div", "bmw-footer");
    footer.append(this.statusLine, this.pager.controls, this.footerActions);
    body.append(this.alerts, this.pager.viewport, footer);
    pane.append(head, body);
    this.shell.body.append(this.rail, pane);
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
      this.busy = this.versionsBusy = this.auditBusy = this.recordBusy = false;
    }
  }

  receive(value: unknown): void {
    ++this.generation;
    this.busy = this.versionsBusy = this.auditBusy = this.recordBusy = false;
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
    this.busy = this.versionsBusy = this.auditBusy = this.recordBusy = false;
    this.error = message(error);
    this.status = "The host could not load the trace.";
    this.render();
  }

  private accept(trace: Trace): void {
    const sameVersion = this.trace?.version.id === trace.version.id;
    if (this.trace?.requirement.id !== trace.requirement.id) { this.versions = []; this.step = "requirement"; }
    this.requestedRequirement = trace.requirement.id;
    this.requestedVersion = trace.version.id;
    this.hostInputPending = false;
    this.trace = trace;
    this.sources = new Map(trace.sources.map((source) => [source.id, source]));
    this.sourceStates.clear();
    this.evidence = new Map(this.pageItems().map((item) => [item.id, item]));
    this.auditRows = [];
    this.auditAfter = 0;
    this.auditBusy = false;
    this.auditLoaded = false;
    this.auditError = "";
    this.auditHasMore = true;
    this.localError = "";
    // A same-version reload keeps the reader's place when the focused records still exist.
    const keep = sameVersion && (!this.focus.finding || trace.findings.some((item) => item.id === this.focus.finding))
      && (!this.focus.evidence || this.evidence.has(this.focus.evidence.id)) && this.focus.audit === undefined;
    if (!keep) { this.focus = {}; this.pages.clear(); }
    if (this.step === "audit") this.focus = {};
    this.status = "Trace loaded. Open a finding to inspect its original evidence.";
    this.render();
  }

  private pageItems(): Evidence[] { return this.trace?.evidence.items.slice(0, PAGE_SIZE) ?? []; }
  private pageKey(): string { return [this.step, this.focus.finding ?? "", this.focus.evidence?.id ?? "", this.focus.audit ?? ""].join("|"); }

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
    this.versionsBusy = this.auditBusy = this.recordBusy = false;
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

  /** Re-read one record in place; stale responses from an older selection are ignored. */
  private async reloadRecord<T extends RecordData>(name: ReadTool, args: RecordData, id: string, valid: (value: RecordData) => boolean, store: (value: T) => void): Promise<void> {
    if (this.recordBusy || !this.connected) return;
    const generation = this.generation;
    this.recordBusy = true;
    this.localError = "";
    this.render();
    try {
      const result = record(await this.request(name, args));
      if (generation !== this.generation) return;
      if (idOf(result) !== id || !valid(result)) throw new Error("The response did not match the selected record.");
      store(result as T);
    } catch (error) { if (generation === this.generation) this.localError = message(error); }
    finally { if (generation === this.generation) { this.recordBusy = false; this.render(); } }
  }

  private async loadSource(sourceId: string): Promise<void> {
    const state = this.sourceStates.get(sourceId) ?? { loading: false, loaded: false, error: "" };
    if (state.loading || !this.connected) return;
    const generation = this.generation;
    this.sourceStates.set(sourceId, { ...state, loading: true, error: "" });
    this.render();
    try {
      const result = await this.request("get_source", { source_id: sourceId });
      if (generation !== this.generation) return;
      if (idOf(result) !== sourceId) throw new Error("The source response did not match the selected record.");
      this.sources.set(sourceId, result as Source);
      this.sourceStates.set(sourceId, { loading: false, loaded: true, error: "" });
    } catch (error) {
      if (generation === this.generation) this.sourceStates.set(sourceId, { loading: false, loaded: false, error: message(error) });
    } finally { if (generation === this.generation) this.render(); }
  }

  private async loadAudit(): Promise<void> {
    if (!this.trace || !this.connected || this.auditBusy) return;
    const generation = this.generation, requirement = this.trace.requirement.id, after = this.auditAfter;
    this.auditBusy = true;
    this.auditError = "";
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

  private go(step: Step, focus: Focus = {}): void {
    this.step = step;
    this.focus = focus;
    this.localError = "";
    if (step === "audit" && !focus.audit && !this.auditLoaded && !this.auditBusy && !this.auditError) void this.loadAudit();
    if (focus.evidence) {
      const evidence = this.evidence.get(focus.evidence.id);
      const state = evidence && this.sourceStates.get(evidence.source_id);
      if (evidence && !state?.loaded && !state?.loading && !state?.error) void this.loadSource(evidence.source_id);
    }
    this.render();
  }

  private versionName(id: unknown): string {
    const version = this.versions.find((item) => item.id === id) ?? (this.trace && this.trace.version.id === id ? this.trace.version : undefined);
    return version ? `Version ${version.version}` : id ? "Recorded version" : "No approved version";
  }

  private render(): void {
    const trace = this.trace;
    const shell = this.shell;
    shell.reload.disabled = !this.connected || this.busy || (!trace && !this.requestedRequirement);
    shell.root.setAttribute("aria-busy", String(this.busy));
    shell.root.dataset.step = this.step;
    shell.eyebrow.textContent = trace ? `Trace explorer · Viewing version ${trace.version.version}` : "BMW product evidence · Trace explorer";
    shell.title.textContent = trace ? valueText(trace.requirement.key, "Requirement trace") : "Requirement trace";
    shell.setSubtitle(trace ? valueText(trace.version.title, "") : "");
    shell.setScope(trace ? `${valueText(trace.requirement.vehicle)} / ${valueText(trace.requirement.market)}` : "");
    shell.metric.replaceChildren();
    const score = record(trace?.version.score);
    if (trace && idOf(score)) {
      const value = el("div", "bmw-metric-value", valueText(score.total));
      value.append(el("small", "", "/ 100"), grade(valueText(score.evidence_grade, "")));
      shell.metric.append(el("p", "bmw-metric-label", `Priority · version ${trace.version.version}`), value);
    }
    this.renderRail(trace);
    this.statusLine.textContent = this.status;
    this.statusLine.title = this.status;
    this.alerts.replaceChildren();
    if (this.error) this.alerts.append(alert(this.error));
    if (this.localError) this.alerts.append(alert(this.localError));
    this.paneLead.replaceChildren();
    this.paneActions.replaceChildren();
    this.footerActions.replaceChildren();
    if (!trace) {
      this.paneTitle.textContent = "Requirement trace";
      this.paneLead.append(this.paneTitle);
      this.pager.set([empty("Open this explorer from a requirement trace to inspect its source-to-decision history.")]);
      return;
    }
    const items = this.paneItems(trace);
    this.pager.set(items, this.pages.get(this.pageKey()) ?? 0);
  }

  private renderRail(trace: Trace | null): void {
    this.rail.replaceChildren();
    const steps = el("ul", "tx-steps");
    const counts: Record<Step, string> = {
      requirement: trace ? `V${trace.version.version}` : "",
      findings: trace ? String(trace.findings.length) : "",
      evidence: trace ? String(trace.evidence.total) : "",
      score: trace && idOf(trace.version.score) ? valueText(record(trace.version.score).total) : trace ? "—" : "",
      decisions: trace ? String(trace.decisions.length) : "",
      audit: this.auditLoaded ? `${this.auditRows.length}${this.auditHasMore ? "+" : ""}` : "",
    };
    for (const [step, name] of STEPS) {
      const item = el("li");
      const node = button("", () => this.go(step), !trace, "tx-step");
      node.append(el("span", "", name), el("span", "tx-count", counts[step]));
      if (step === this.step) node.setAttribute("aria-current", "step");
      item.append(node);
      steps.append(item);
    }
    this.rail.append(el("p", "bmw-label tx-rail-label", "Source to decision"), steps);
    if (!trace) return;
    const versionBlock = el("div", "tx-version");
    const selectLabel = el("label", "bmw-label", "Requirement version");
    selectLabel.htmlFor = "trace-version";
    const select = el("select");
    select.id = "trace-version";
    for (const version of this.versions.length ? this.versions : [trace.version]) {
      const tags = [version.id === trace.requirement.current_version_id ? "current" : "", version.id === trace.requirement.approved_version_id ? "approved" : ""].filter(Boolean);
      const option = el("option", "", `Version ${version.version}${tags.length ? ` · ${tags.join(" · ")}` : ""}`);
      option.value = version.id;
      option.selected = version.id === trace.version.id;
      select.append(option);
    }
    select.disabled = !this.connected || this.busy || this.versionsBusy;
    select.addEventListener("change", () => void this.loadTrace(select.value, 0));
    versionBlock.append(selectLabel, select, el("span", "tx-version-note", this.versionsBusy ? "Loading history…" : "Newest first"));
    if (trace.version.id !== trace.requirement.current_version_id) versionBlock.append(button("View current version", () => void this.loadTrace(null, 0, true), this.busy || !this.connected, "btn btn-link"));
    this.rail.append(versionBlock);
  }

  private lead(title: string, back?: [string, () => void]): void {
    this.paneTitle.textContent = title;
    if (back) {
      const node = button("", back[1], false, "tx-back");
      node.append(icon("back"), el("span", "", back[0]));
      node.setAttribute("aria-label", `Back to ${back[0].toLowerCase()}`);
      this.paneLead.append(node, el("span", "tx-crumb", "/"));
    }
    this.paneLead.append(this.paneTitle);
  }

  private evidencePaging(trace: Trace): void {
    const page = trace.evidence, count = this.pageItems().length;
    const group = el("div", "tx-server-pages");
    const pageButton = (text: string, name: "left" | "right", action: () => void, disabled: boolean) => {
      const node = button("", action, disabled, "tx-server-button");
      node.title = text;
      node.append(icon(name), el("span", "sr-only", text));
      return node;
    };
    group.append(
      el("span", "tx-range", count ? `Evidence ${page.offset + 1}–${page.offset + count} of ${page.total}` : `No evidence on this page · ${page.total} linked in total`),
      pageButton("Previous evidence", "left", () => void this.loadTrace(trace.version.id, Math.max(0, page.offset - PAGE_SIZE)), !this.connected || this.busy || page.offset === 0),
      pageButton("Next evidence", "right", () => void this.loadTrace(trace.version.id, page.offset + count), !this.connected || this.busy || !count || page.offset + count >= page.total));
    this.footerActions.append(group);
  }

  private paneItems(trace: Trace): HTMLElement[] {
    if (this.step === "findings") return this.focus.evidence ? this.evidenceItems(trace) : this.focus.finding ? this.findingItems(trace) : this.findingList(trace);
    if (this.step === "evidence") return this.focus.evidence ? this.evidenceItems(trace) : this.evidenceList(trace);
    if (this.step === "score") return this.scoreItems(trace);
    if (this.step === "decisions") return this.decisionItems(trace);
    if (this.step === "audit") return this.focus.audit !== undefined ? this.auditEvent() : this.auditList();
    return this.requirementItems(trace);
  }

  private requirementItems(trace: Trace): HTMLElement[] {
    this.lead("Requirement & baseline");
    const items: HTMLElement[] = [];
    if (this.versionsError) {
      const box = alert(`Version history: ${this.versionsError}`);
      this.paneActions.append(button("Retry version history", () => void this.loadVersions(), this.versionsBusy || !this.connected, "btn btn-link"));
      items.push(box);
    }
    const states = el("div", "tx-states");
    for (const [name, id] of [["Current proposal", trace.requirement.current_version_id], ["Approved baseline", trace.requirement.approved_version_id]] as const) {
      const state = el("div");
      state.append(el("span", "bmw-label", name), el("strong", "", this.versionName(id)));
      states.append(state);
    }
    const chips = el("div", "chips");
    chips.append(statusChip(valueText(trace.requirement.status, "unknown")), el("span", "status status-current", `Viewing version ${trace.version.version}`));
    items.push(states, chips, splittable(el("p", "prose", valueText(trace.version.statement))));
    if (trace.version.customer_need) items.push(heading("Customer need"), splittable(el("p", "bullet", valueText(trace.version.customer_need))));
    items.push(heading("Acceptance criteria"));
    const criteria = list(trace.version.acceptance_criteria);
    for (const raw of criteria) {
      const criterion = record(raw);
      items.push(fieldList([["Metric", criterion.metric], ["Target", `${valueText(criterion.target)}${criterion.unit ? ` ${valueText(criterion.unit)}` : ""}`], ["Basis", criterion.basis], ["Source references", strings(criterion.source_ids).join(", ") || "None recorded"]]));
    }
    if (!criteria.length) items.push(empty("No acceptance criteria recorded."));
    items.push(heading("Assumptions"));
    const assumptions = strings(trace.version.assumptions);
    for (const text of assumptions) items.push(splittable(el("p", "bullet muted", text)));
    if (!assumptions.length) items.push(empty("No assumptions recorded."));
    items.push(heading("Version record"), fieldList([["Created", trace.version.created_at], ["Author", trace.version.actor], ["Rationale", trace.version.rationale]]));
    items.push(heading("Record IDs"), fieldList([["Requirement ID", trace.requirement.id], ["Viewing version ID", trace.version.id], ["Current version ID", trace.requirement.current_version_id], ["Approved version ID", trace.requirement.approved_version_id], ["Approved score ID", trace.requirement.approved_score_id]], "kv ids"));
    return items;
  }

  private findingList(trace: Trace): HTMLElement[] {
    this.lead(`Findings · ${trace.findings.length}`);
    if (!trace.findings.length) return [empty("No findings are linked to this version.")];
    return [
      el("p", "tx-intro tx-hint", "Open a finding to read its exact evidence and source. Supporting and conflicting links stay distinct."),
      ...trace.findings.map((finding) => {
        const supports = strings(finding.evidence_ids).length, conflicts = strings(finding.conflicting_evidence_ids).length;
        const meta: (string | HTMLElement)[] = [statusChip(valueText(finding.kind, "finding"))];
        if (typeof finding.confidence === "number") meta.push(`${Math.round(finding.confidence * 100)}% confidence`);
        meta.push(`${supports} support${supports === 1 ? "s" : ""} · ${conflicts} conflict${conflicts === 1 ? "" : "s"}`);
        return row(valueText(finding.summary, "Finding"), "", meta, () => this.go("findings", { finding: finding.id }));
      }),
    ];
  }

  private evidenceRow(evidence: Evidence, relation: string, finding: string): HTMLButtonElement {
    const source = this.sources.get(evidence.source_id);
    const location = record(evidence.location);
    const where = Object.entries(location).filter(([key]) => key !== "header_row").map(([key, value]) => `${label(key)} ${valueText(value)}`).join(" · ");
    const meta: (string | HTMLElement)[] = [];
    if (relation) meta.push(statusChip(relation === "Supports" ? "supports" : "conflicts"));
    if (where) meta.push(where);
    return row(valueText(source?.title, "Evidence record"), evidence.content, meta, () => this.go(this.step, { finding: finding || undefined, evidence: { id: evidence.id, relation, finding } }));
  }

  private findingItems(trace: Trace): HTMLElement[] {
    const finding = trace.findings.find((item) => item.id === this.focus.finding);
    if (!finding) { this.focus = {}; return this.findingList(trace); }
    this.lead("Finding", ["Findings", () => this.go("findings")]);
    this.paneActions.append(button(this.recordBusy ? "Reloading…" : "Reload finding", () => void this.reloadRecord<Finding>("get_finding", { finding_id: finding.id }, finding.id, () => true, (data) => {
      if (this.trace) this.trace.findings = this.trace.findings.map((item) => item.id === data.id ? data : item);
    }), this.recordBusy || !this.connected, "btn btn-link"));
    const chips = el("div", "chips");
    chips.append(statusChip(valueText(finding.kind, "finding")));
    if (typeof finding.confidence === "number") chips.append(el("span", "status", `${Math.round(finding.confidence * 100)}% confidence`));
    chips.append(el("span", "tx-meta", `${label(finding.topic)} · recorded ${valueText(finding.created_at)}`));
    const items: HTMLElement[] = [splittable(el("p", "prose", valueText(finding.summary, "Finding"))), chips];
    let shown = 0, linked = 0;
    for (const [relation, ids] of [["Supports", strings(finding.evidence_ids)], ["Conflicts", strings(finding.conflicting_evidence_ids)]] as const) {
      linked += ids.length;
      const rows = ids.flatMap((id) => { const evidence = this.evidence.get(id); return evidence ? [this.evidenceRow(evidence, relation, finding.id)] : []; });
      if (rows.length) items.push(heading(relation === "Supports" ? "Supporting evidence on this page" : "Conflicting evidence on this page"), ...rows);
      shown += rows.length;
    }
    if (!linked) items.push(empty("No evidence links recorded for this finding."));
    else if (linked > shown) items.push(note(`${linked - shown} linked evidence record${linked - shown === 1 ? " is" : "s are"} on other evidence pages. Use the evidence page controls below.`));
    this.evidencePaging(trace);
    return items;
  }

  private evidenceList(trace: Trace): HTMLElement[] {
    this.lead(`Evidence · ${trace.evidence.total}`);
    this.evidencePaging(trace);
    const items = this.pageItems();
    if (!items.length) return [empty("No evidence on this page.")];
    const relation = (id: string) => trace.findings.some((item) => strings(item.conflicting_evidence_ids).includes(id)) ? "Conflicts" : trace.findings.some((item) => strings(item.evidence_ids).includes(id)) ? "Supports" : "";
    return items.map((item) => this.evidenceRow(item, relation(item.id), ""));
  }

  private dateContext(item: RecordData): HTMLElement[] {
    const metadata = record(item.metadata), web = record(metadata.web_evidence);
    const items: HTMLElement[] = [fieldList([["Observed", item.observed_at], ["Published", web.publication_date], ["Retrieved", web.retrieved_at], ["Stored", item.created_at]])];
    if (!item.observed_at) items.push(note("Observation date is unknown. Publication, retrieval and storage dates are separate and do not establish when the customer experience occurred."));
    const uncertainty = [...strings(web.uncertainties), ...strings(web.warnings)];
    if (uncertainty.length) items.push(note(uncertainty.join("\n")));
    if (metadata.review_status || web.review_status) items.push(el("p", "tx-intro", `Evidence review status: ${valueText(metadata.review_status ?? web.review_status)}.`));
    return items;
  }

  private evidenceItems(trace: Trace): HTMLElement[] {
    const focus = this.focus.evidence!;
    const evidence = this.evidence.get(focus.id);
    if (!evidence) { this.focus = { finding: this.focus.finding }; return this.paneItems(trace); }
    const back: [string, () => void] = this.step === "findings" && focus.finding ? ["Finding", () => this.go("findings", { finding: focus.finding })] : ["Evidence", () => this.go("evidence")];
    this.lead(focus.relation ? `${focus.relation} · exact evidence` : "Exact evidence", back);
    this.paneActions.append(button(this.recordBusy ? "Reloading…" : "Reload evidence", () => void this.reloadRecord<Evidence>("get_evidence", { evidence_id: evidence.id }, evidence.id, (data) => typeof data.content === "string", (data) => { this.evidence.set(data.id, data); }), this.recordBusy || !this.connected, "btn btn-link"));
    const location = Object.entries(record(evidence.location));
    const items: HTMLElement[] = [heading("Exact source text"), splittable(el("blockquote", "quote", evidence.content)), heading("Source location")];
    items.push(location.length ? fieldList(location.map(([key, value]) => [label(key), typeof value === "object" ? pretty(value) : value])) : empty("No location was recorded."));
    items.push(...this.dateContext(evidence), heading("Evidence metadata"), code(evidence.metadata ?? {}), fieldList([["Evidence ID", evidence.id], ["Source ID", evidence.source_id]], "kv ids"));
    items.push(...this.sourceItems(evidence.source_id));
    return items;
  }

  private sourceItems(sourceId: string): HTMLElement[] {
    const source = this.sources.get(sourceId);
    const state = this.sourceStates.get(sourceId);
    const items: HTMLElement[] = [heading(`Source · ${valueText(source?.title, "Source record")}`)];
    if (source) {
      items.push(fieldList([["Title", source.title], ["Kind", source.kind], ["Scope", `${valueText(source.vehicle)} / ${valueText(source.market)}`]]));
      const url = safeSourceUrl(source.reference);
      if (url) {
        const link = el("a", "tx-link", source.reference);
        link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer";
        if (this.openLink) {
          const generation = this.generation;
          link.addEventListener("click", (event) => {
            event.preventDefault();
            void this.openLink!(url).catch((error: unknown) => { if (generation === this.generation) { this.localError = message(error); this.render(); } });
          });
        }
        items.push(link);
      } else items.push(fieldList([["Reference", source.reference]]));
      items.push(...this.dateContext(source), heading("Source metadata"), code(source.metadata ?? {}), fieldList([["Source ID", source.id], ["Snapshot hash", source.content_hash]], "kv ids"));
    }
    if (state?.loading) items.push(el("p", "tx-intro", "Loading the full source record…"));
    if (state?.error) {
      items.push(alert(state.error));
      this.paneActions.append(button("Retry source", () => void this.loadSource(sourceId), state.loading || !this.connected, "btn btn-link"));
    }
    return items;
  }

  private scoreItems(trace: Trace): HTMLElement[] {
    this.lead("Recorded priority & evidence quality");
    const score = record(trace.version.score);
    if (!idOf(score)) return [empty("No score is recorded for this version.")];
    const total = el("div", "tx-score");
    total.append(el("strong", "", valueText(score.total)), el("span", "muted", "/ 100"), grade(valueText(score.evidence_grade, "")), el("span", "tx-intro", `Evidence grade ${valueText(score.evidence_grade)} · separate from priority`));
    const items: HTMLElement[] = [total];
    if (trace.version.id === trace.requirement.approved_version_id && score.id !== trace.requirement.approved_score_id) items.push(note("This is the latest recorded score for the selected version. The approved baseline is tied to a different score; compare its recorded score ID in decisions and audit history."));
    const factors = record(score.factors), weights = record(score.weights), explanation = record(score.explanation), contributions = record(explanation.contributions);
    const table = el("table", "tx-table");
    table.append(el("caption", "sr-only", "Recorded scoring inputs"));
    const head = el("thead"), headRow = el("tr");
    for (const name of ["Factor", "Judgment / 5", "Weight", "Contribution"]) { const cell = el("th", "", name); cell.scope = "col"; headRow.append(cell); }
    head.append(headRow);
    const rows = el("tbody");
    for (const [key, factor] of Object.entries(factors)) {
      const line = el("tr");
      for (const value of [label(key), valueText(factor), typeof weights[key] === "number" ? `${Math.round(Number(weights[key]) * 100)}%` : "Not recorded", valueText(contributions[key])]) line.append(el("td", "", value));
      rows.append(line);
    }
    table.append(head, rows);
    items.push(table, fieldList([["Formula", explanation.formula], ["Rubric", score.rubric_version], ["Created", score.created_at], ["Score ID", score.id], ["Version ID", score.version_id]]));
    for (const text of strings(explanation.limitations)) items.push(note(text));
    items.push(heading("Full score explanation"), code(score.explanation ?? {}));
    return items;
  }

  private decisionItems(trace: Trace): HTMLElement[] {
    this.lead(`Decisions for version ${trace.version.version} · ${trace.decisions.length}`);
    if (!trace.decisions.length) return [empty("No decisions have been recorded for this version.")];
    return [...trace.decisions].reverse().map((decision) => {
      const item = el("article", "tx-decision");
      const line = el("div", "chips");
      line.append(statusChip(valueText(decision.action, "decision")), el("strong", "", valueText(decision.actor)), el("small", "muted", valueText(decision.created_at)));
      item.append(line, el("p", "tx-rationale", valueText(decision.rationale)), fieldList([["Decision ID", decision.id], ["Version ID", decision.version_id], ["Score ID", decision.score_id]], "kv ids"));
      return item;
    });
  }

  private auditList(): HTMLElement[] {
    this.lead("Requirement audit history");
    const loadLabel = this.auditBusy ? "Loading history…" : this.auditError ? "Retry audit history" : !this.auditLoaded ? "Load audit history" : this.auditHasMore ? "Load more history" : "Check for newer events";
    this.footerActions.append(button(loadLabel, () => void this.loadAudit(), !this.connected || this.auditBusy || this.busy, "btn btn-link"));
    const items: HTMLElement[] = [el("p", "tx-intro tx-hint", "History covers all versions of this requirement, earliest to latest. Open an event to inspect its recorded state.")];
    if (this.auditError) items.push(alert(this.auditError));
    if (this.auditLoaded && !this.auditRows.length) items.push(empty("No audit events are recorded for this requirement."));
    for (const event of this.auditRows) {
      items.push(row(`${valueText(event.sequence)} · ${label(event.action)}`, "", [valueText(event.actor), valueText(event.created_at)], () => this.go("audit", { audit: Number(event.sequence) })));
    }
    return items;
  }

  private auditEvent(): HTMLElement[] {
    const event = this.auditRows.find((item) => Number(item.sequence) === this.focus.audit);
    if (!event) { this.focus = {}; return this.auditList(); }
    this.lead(`Event ${valueText(event.sequence)} · ${label(event.action)}`, ["Audit", () => this.go("audit")]);
    return [fieldList([["Actor", event.actor], ["When", event.created_at], ["Rationale", event.rationale]]), heading("Before state"), code(event.before_state), heading("After state"), code(event.after_state), heading("Event metadata"), code(event.metadata)];
  }
}

function applyTheme(explorer: TraceExplorer, context: McpUiHostContext): void {
  // The host picks light or dark; BMW tokens replace host style variables so widgets match the workspace.
  if (context.theme) applyDocumentTheme(context.theme);
  explorer.shell.hostContext(context);
}

const root = document.getElementById("trace-app");
if (root) {
  // The shell reports a fixed frame height, so the SDK's content-height auto-resize is disabled.
  const app = new App({ name: "BMW requirement trace explorer", version: "0.1.0" }, {}, { autoResize: false });
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
  app.onhostcontextchanged = (context) => applyTheme(explorer, context);
  void app.connect().then(() => {
    const context = app.getHostContext();
    if (context) applyTheme(explorer, context);
    explorer.shell.attach(app);
    explorer.setConnected();
  }).catch((error: unknown) => explorer.connectionFailed(error));
}
