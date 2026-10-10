import { App, applyDocumentTheme, type McpUiHostContext } from "@modelcontextprotocol/ext-apps";
import { callTool, unpack } from "./shared/api";
import { keepWithNext, Pager, splittable } from "./shared/fit";
import { createShell, el, grade, status as statusChip } from "./shared/shell";
import "./scoring-panel.css";

const FACTORS = [
  ["customer_impact", "Customer impact"],
  ["market_relevance", "Market relevance"],
  ["strategic_fit", "Strategic fit"],
  ["differentiation", "Differentiation"],
  ["feasibility", "Feasibility"],
] as const;
type FactorKey = typeof FACTORS[number][0];
type Values = Record<FactorKey, number>;
type Action = "approve" | "reject" | "postpone" | "challenge";
type RecordValue = Record<string, unknown>;
type Score = { id: string; version_id: string; total: number; weights: Values; evidence_grade: string; explanation: RecordValue };
type Version = { id: string; version: number; title: string; statement: string; customer_need: string; acceptance_criteria: RecordValue[]; assumptions: string[]; factors: Values; score: Score | null };
type Requirement = { id: string; key: string; vehicle: string; market: string; status: string; current_version: Version; approved_version: RecordValue | null; approved_version_id: string | null; approved_score_id: string | null; needs_review: boolean; reviews: RecordValue[] };
type Tab = "brief" | "priority" | "decide" | "signoff";
const DEFAULT_WEIGHTS: Values = { customer_impact: .35, market_relevance: .25, strategic_fit: .2, differentiation: .1, feasibility: .1 };

function record(value: unknown): RecordValue {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("The requirement response has an invalid shape. Reload before writing.");
  return value as RecordValue;
}
function valueText(value: unknown): string { return typeof value === "string" || typeof value === "number" ? String(value) : ""; }
function records(value: unknown): RecordValue[] { return Array.isArray(value) ? value.filter((item) => item && typeof item === "object" && !Array.isArray(item)) as RecordValue[] : []; }
function values(value: unknown, max: number): Values {
  const source = record(value);
  for (const [key] of FACTORS) {
    if (typeof source[key] !== "number" || !Number.isFinite(source[key]) || source[key] < 0 || source[key] > max) {
      throw new Error(`The saved ${max === 5 ? "factors" : "weights"} are invalid. Reload before writing.`);
    }
  }
  return Object.fromEntries(FACTORS.map(([key]) => [key, source[key]])) as Values;
}
function parseRequirement(value: unknown): Requirement {
  const input = record(value);
  const version = record(input.current_version);
  if (!valueText(input.id) || !valueText(version.id) || version.id !== input.current_version_id || (version.requirement_id && version.requirement_id !== input.id)) {
    throw new Error("The response has no consistent current requirement version. Reload before writing.");
  }
  let score: Score | null = null;
  if (version.score) {
    const rawScore = record(version.score);
    if (!valueText(rawScore.id) || rawScore.version_id !== version.id || typeof rawScore.total !== "number" || !Number.isFinite(rawScore.total)) {
      throw new Error("The saved score does not match this requirement version. Reload before writing.");
    }
    score = { id: valueText(rawScore.id), version_id: valueText(rawScore.version_id), total: rawScore.total, weights: values(rawScore.weights, 1), evidence_grade: valueText(rawScore.evidence_grade), explanation: rawScore.explanation ? record(rawScore.explanation) : {} };
  }
  return {
    id: valueText(input.id), key: valueText(input.key) || "Requirement", vehicle: valueText(input.vehicle), market: valueText(input.market), status: valueText(input.status),
    current_version: {
      id: valueText(version.id), version: Number(version.version) || 0, title: valueText(version.title), statement: valueText(version.statement), customer_need: valueText(version.customer_need),
      acceptance_criteria: records(version.acceptance_criteria), assumptions: Array.isArray(version.assumptions) ? version.assumptions.map(valueText) : [], factors: values(version.factors, 5), score,
    },
    approved_version: input.approved_version ? record(input.approved_version) : null,
    approved_version_id: valueText(input.approved_version_id) || null, approved_score_id: valueText(input.approved_score_id) || null,
    needs_review: input.needs_review === true, reviews: records(input.reviews),
  };
}
function same(a: Values, b: Values): boolean { return FACTORS.every(([key]) => Math.abs(a[key] - b[key]) < 1e-9); }
function errorText(error: unknown): string { return error instanceof Error ? error.message : "The host could not complete the request."; }
function weightSum(weights: Values): number { return FACTORS.reduce((sum, [key]) => sum + weights[key], 0); }
function field(label: string, control: HTMLElement): HTMLLabelElement {
  const node = el("label", "field");
  node.append(el("span", "", label), control);
  return node;
}
function pane(name: string): HTMLElement {
  const node = el("div", `bmw-pane sp-pane-${name}`);
  node.id = `pane-${name}`;
  return node;
}

/** The only writes are explicit button actions; after every write the user reviews a fresh read. */
export function mountScoringPanel(app: App, root: HTMLElement) {
  let current: Requirement | null = null;
  let draftFactors: Values = { customer_impact: 0, market_relevance: 0, strategic_fit: 0, differentiation: 0, feasibility: 0 };
  let draftWeights: Values = { ...DEFAULT_WEIGHTS };
  let busy = false;
  let requiresReload = false;
  let awaitingDecisionReview = false;
  let message = "Waiting for the requirement from your host…";
  let failure = "";
  let requestEpoch = 0;
  let tab: Tab = "priority";
  let briefPage = 0;

  const shell = createShell(root, { reloadLabel: "Reload requirement", eyebrow: "BMW · Product evidence", title: "Scoring & decision" });
  root.classList.add("sp-stage");
  const refresh = shell.reload;

  // Header metric: the saved priority, or a clearly labelled unsaved preview.
  const priorityHeading = el("p", "bmw-metric-label", "Saved priority");
  const total = el("div", "bmw-metric-value"); total.id = "priority-score";
  shell.metric.append(priorityHeading, total);

  // Main panel: tabbed brief, priority factors and decision panes.
  const main = el("section", "bmw-panel sp-main");
  const mainHead = el("div", "bmw-panel-head");
  const tabs = el("div", "bmw-tabs"); tabs.setAttribute("role", "tablist"); tabs.setAttribute("aria-label", "Requirement review");
  const versionLabel = el("span", "bmw-label");
  mainHead.append(tabs, versionLabel);
  const tabButtons = new Map<Tab, HTMLButtonElement>();
  for (const [name, label] of [["brief", "Brief"], ["priority", "Priority"], ["decide", "Decide"], ["signoff", "Sign-off"]] as const) {
    const button = el("button", "bmw-tab", label);
    button.type = "button"; button.id = `tab-${name}`;
    button.setAttribute("role", "tab"); button.setAttribute("aria-controls", `pane-${name}`);
    button.addEventListener("click", () => { tab = name; layout(); });
    tabButtons.set(name, button); tabs.append(button);
  }
  const error = el("p", "bmw-alert");
  error.setAttribute("role", "alert");
  const statusLine = el("p", "bmw-status sp-status");
  statusLine.setAttribute("role", "status");
  statusLine.setAttribute("aria-live", "polite");

  // Brief pane: paged, never scrolled.
  const briefPane = pane("brief");
  const briefPager = new Pager("requirement brief", (page) => { briefPage = page; });
  const briefFoot = el("div", "bmw-footer");
  const briefCaption = el("span", "bmw-label", "Requirement brief");
  briefFoot.append(briefCaption, briefPager.controls);
  briefPane.append(briefPager.viewport, briefFoot);

  // Priority pane: five factor judgments and their weights.
  const priorityPane = pane("priority");
  const table = el("div", "sp-table");
  const columns = el("div", "sp-row sp-columns");
  columns.append(el("span", "", "Factor"), el("span", "", "Rating 0–5"), el("span"), el("span", "", "Weight"), el("span"));
  table.append(columns);
  const inputs = new Map<FactorKey, { factor: HTMLInputElement; weight: HTMLInputElement; factorOut: HTMLOutputElement; weightOut: HTMLOutputElement }>();
  for (const [factorKey, labelText] of FACTORS) {
    const row = el("div", "sp-row");
    const label = el("label", "", labelText);
    const factor = el("input");
    factor.type = "range"; factor.min = "0"; factor.max = "5"; factor.step = ".1"; factor.id = `factor-${factorKey}`;
    factor.setAttribute("aria-label", `${labelText} factor`); label.htmlFor = factor.id;
    const factorOut = el("output"); factorOut.htmlFor = factor.id;
    const weight = el("input");
    weight.type = "range"; weight.min = "0"; weight.max = "1"; weight.step = ".01"; weight.id = `weight-${factorKey}`;
    weight.setAttribute("aria-label", `${labelText} weight`);
    const weightOut = el("output"); weightOut.htmlFor = weight.id;
    factor.addEventListener("input", () => { draftFactors[factorKey] = Number(factor.value); update(); });
    weight.addEventListener("input", () => { draftWeights[factorKey] = Number(weight.value); update(); });
    inputs.set(factorKey, { factor, weight, factorOut, weightOut });
    row.append(label, factor, factorOut, weight, weightOut); table.append(row);
  }
  const weightMessage = el("p", "sp-hint");
  weightMessage.id = "weight-total";
  weightMessage.setAttribute("aria-live", "polite");
  const saves = el("div", "bmw-footer-actions");
  const discard = el("button", "btn btn-link", "Discard"); discard.type = "button"; discard.dataset.action = "discard";
  const saveFactors = el("button", "btn", "Save factors"); saveFactors.type = "button"; saveFactors.dataset.action = "save-factors";
  const saveWeights = el("button", "btn", "Save weights"); saveWeights.type = "button"; saveWeights.dataset.action = "save-weights";
  saves.append(discard, saveFactors, saveWeights);
  const priorityFoot = el("div", "bmw-footer");
  priorityFoot.append(weightMessage, saves);
  priorityPane.append(table, priorityFoot);

  // Decide pane: the exact saved version and score, its baseline, and the explicit decision.
  const decidePane = pane("decide");
  const action = el("select"); action.id = "decision-action";
  for (const [value, label] of [["approve", "Approve"], ["reject", "Reject"], ["postpone", "Postpone"], ["challenge", "Challenge"]]) {
    const option = el("option", "", label); option.value = value; action.append(option);
  }
  const facts = el("dl", "kv sp-facts");
  const saved = el("dd"), approved = el("dd"), reviewStatus = el("dd"), gradeText = el("dd");
  facts.append(el("dt", "", "Applies to"), saved, el("dt", "", "Baseline"), approved, el("dt", "", "Review"), reviewStatus, el("dt", "", "Evidence"), gradeText);
  const decideTop = el("div", "sp-decide-top");
  decideTop.append(field("Decision", action), facts);
  const reviewedLabel = el("label", "sp-check");
  const reviewed = el("input"); reviewed.type = "checkbox"; reviewed.id = "reviewed-saved-state";
  reviewedLabel.append(reviewed, document.createTextNode("I reviewed the saved version and score shown above."));
  const validation = el("p", "sp-hint"); validation.id = "write-validation"; validation.setAttribute("aria-live", "polite");
  const decide = el("button", "btn btn-primary", "Record approval"); decide.type = "button"; decide.dataset.action = "decide";
  decide.setAttribute("aria-describedby", "write-validation");
  const decideFoot = el("div", "bmw-footer");
  decideFoot.append(validation, decide);
  decidePane.append(decideTop, reviewedLabel, decideFoot);

  // Sign-off column: every save and decision records this human name and rationale.
  const signoff = el("section", "bmw-panel sp-signoff");
  const signoffHead = el("div", "bmw-panel-head");
  signoffHead.append(el("span", "bmw-label brand", "PM sign-off"));
  const signoffPane = pane("signoff");
  const actor = el("input"); actor.type = "text"; actor.id = "actor"; actor.autocomplete = "name"; actor.placeholder = "e.g. Alex Muller"; actor.maxLength = 200;
  const rationale = el("textarea"); rationale.id = "rationale"; rationale.placeholder = "Explain this change or decision…"; rationale.maxLength = 10000;
  const rationaleField = field("Rationale", rationale); rationaleField.classList.add("sp-rationale");
  signoffPane.append(field("Your name / actor ID", actor), rationaleField, el("p", "sp-note", "Recorded with each save or decision. Check spelling: a new name registers a new human actor."));
  signoff.append(signoffHead, signoffPane);

  // The square frame has room to keep the brief in its own panel beside the controls.
  const briefPanel = el("section", "bmw-panel sp-brief");
  const briefHead = el("div", "bmw-panel-head");
  briefHead.append(el("span", "bmw-label brand", "Requirement brief"));
  briefPanel.append(briefHead);

  const panes = el("div", "sp-panes");
  panes.append(briefPane, priorityPane, decidePane);
  const mainFoot = el("div", "sp-main-foot");
  mainFoot.append(error, statusLine);
  main.append(mainHead, panes, mainFoot);

  function layout() {
    const square = shell.mode === "square" && !shell.compact;
    const compact = shell.compact;
    if (square && tab === "brief") tab = "priority";
    if (!compact && tab === "signoff") tab = "decide";
    if (square) briefPanel.append(briefPane); else panes.prepend(briefPane);
    if (compact) panes.append(signoffPane); else signoff.append(signoffPane);
    briefCaption.hidden = square;
    tabButtons.get("brief")!.hidden = square;
    tabButtons.get("signoff")!.hidden = !compact;
    shell.body.replaceChildren(...(compact ? [main] : square ? [briefPanel, main, signoff] : [main, signoff]));
    for (const [name, button] of tabButtons) {
      const selected = name === tab;
      button.setAttribute("aria-selected", String(selected));
      button.tabIndex = selected ? 0 : -1;
    }
    briefPane.hidden = !square && tab !== "brief";
    priorityPane.hidden = tab !== "priority";
    decidePane.hidden = tab !== "decide";
    signoffPane.hidden = compact && tab !== "signoff";
    if (!briefPane.hidden) briefPager.refit();
  }
  shell.onLayoutChange(layout);
  layout();

  function dirtyFactors() { return !!current && !same(draftFactors, current.current_version.factors); }
  function dirtyWeights() { return !!current && !same(draftWeights, current.current_version.score?.weights ?? DEFAULT_WEIGHTS); }
  function humanError() {
    const identity = actor.value.trim();
    if (!identity) return "Enter your human name or registered actor ID.";
    if (/^(ai|system)\s*:/i.test(identity)) return "Decisions require a human actor; AI and system identities are not allowed.";
    if (/[\r\n\t\x00-\x1f]/.test(identity) || identity.length < 2) return "Enter a valid human name or actor ID and check its spelling.";
    if (!rationale.value.trim()) return "Add a rationale before saving or deciding.";
    return "";
  }
  function update() {
    const dirty = dirtyFactors() || dirtyWeights();
    const validWeights = Math.abs(weightSum(draftWeights) - 1) <= 1e-6;
    const hasIds = !!current?.current_version.id && !!current.current_version.score?.id;
    const guard = humanError();
    refresh.disabled = busy || !current;
    statusLine.textContent = busy ? "Working… Please wait for the saved state." : message;
    statusLine.title = statusLine.textContent;
    error.textContent = failure; error.hidden = !failure; error.title = failure;
    root.setAttribute("aria-busy", String(busy));
    for (const [factorKey, control] of inputs) {
      control.factor.value = String(draftFactors[factorKey]); control.weight.value = String(draftWeights[factorKey]);
      control.factor.disabled = busy || !current || requiresReload; control.weight.disabled = busy || !current || requiresReload;
      control.factor.style.setProperty("--fill", `${draftFactors[factorKey] / 5 * 100}%`); control.weight.style.setProperty("--fill", `${draftWeights[factorKey] * 100}%`);
      control.factorOut.value = draftFactors[factorKey].toFixed(1); control.weightOut.value = `${Math.round(draftWeights[factorKey] * 100)}%`;
    }
    weightMessage.textContent = `Weight total: ${(weightSum(draftWeights) * 100).toFixed(0)}%${validWeights ? " · ready" : " · must equal 100% before saving or deciding"}`;
    weightMessage.classList.toggle("sp-warning", !validWeights);
    const writeBlocked = busy || requiresReload || !hasIds || !!guard || !validWeights;
    saveFactors.disabled = writeBlocked || !dirtyFactors(); saveWeights.disabled = writeBlocked || !dirtyWeights() || dirtyFactors();
    saveFactors.classList.toggle("btn-primary", !saveFactors.disabled);
    saveWeights.classList.toggle("btn-primary", !saveWeights.disabled);
    saveFactors.title = guard && dirtyFactors() ? guard : "Save factors as a new requirement version.";
    saveWeights.title = dirtyFactors() ? "Save changed factors first; your weight preview will be retained." : guard && dirtyWeights() ? guard : "Save weights for the current version and score.";
    discard.disabled = busy || !dirty || requiresReload;
    actor.disabled = busy; rationale.disabled = busy; action.disabled = busy;
    decide.disabled = writeBlocked || dirty || (awaitingDecisionReview && !reviewed.checked);
    reviewedLabel.hidden = !awaitingDecisionReview; reviewed.disabled = busy || dirty || requiresReload;
    decide.textContent = `Record ${action.value === "approve" ? "approval" : action.value === "reject" ? "rejection" : action.value === "postpone" ? "postponement" : "challenge"}`;
    validation.textContent = requiresReload ? "Reload the current state before making another change." : !hasIds ? "A saved version and score are required." : !validWeights ? "Weights must total 100%." : dirty ? "Save your preview, then review the saved state before recording a decision." : guard || (awaitingDecisionReview && !reviewed.checked ? "Review the freshly saved state and tick the confirmation." : "This decision applies to the exact saved version and score shown.");
    validation.title = validation.textContent;
    priorityHeading.textContent = dirty ? "Preview · unsaved" : "Saved priority";
    shell.metric.classList.toggle("is-preview", dirty);
    const preview = FACTORS.reduce((sum, [factorKey]) => sum + draftFactors[factorKey] * draftWeights[factorKey] * 20, 0);
    const score = current?.current_version.score;
    total.replaceChildren(document.createTextNode(validWeights && score ? (dirty ? preview : score.total).toFixed(1) : "—"), el("small", "", "/ 100"));
    if (score) total.append(grade(score.evidence_grade));
    saved.textContent = score ? `Saved: ${score.total.toFixed(1)} / 100 · version ${current!.current_version.version}` : "No saved score is available.";
  }
  function briefItems(parsed: Requirement): HTMLElement[] {
    const version = parsed.current_version;
    const chips = el("div", "chips");
    chips.append(statusChip(parsed.status));
    if (parsed.status !== "needs_review") chips.append(el("span", `status${parsed.needs_review ? " status-needs_review" : ""}`, parsed.needs_review ? "Needs review" : "No open review"));
    const items: HTMLElement[] = [chips, splittable(el("p", "prose", version.statement))];
    if (version.customer_need) items.push(keepWithNext(el("p", "bmw-label", "Customer need")), splittable(el("p", "bullet", version.customer_need)));
    if (version.acceptance_criteria.length) items.push(keepWithNext(el("p", "bmw-label", "Acceptance criteria")));
    for (const criterion of version.acceptance_criteria) items.push(splittable(el("p", "bullet", `${valueText(criterion.metric)}: ${valueText(criterion.target)} ${valueText(criterion.unit)} · ${valueText(criterion.basis)}`.trim())));
    if (version.assumptions.length) items.push(keepWithNext(el("p", "bmw-label", "Assumptions")));
    for (const assumption of version.assumptions) items.push(splittable(el("p", "bullet muted", `Assumption: ${assumption}`)));
    const limits = version.score?.explanation.limitations;
    items.push(splittable(el("p", "bmw-note", Array.isArray(limits) ? limits.map(valueText).join(" ") : "Priority reflects recorded judgments; evidence grade is separate.")));
    const ids = el("dl", "kv ids");
    for (const [label, value] of [["Current version", version.id], ["Current score", version.score?.id ?? "Missing"], ["Approved version", parsed.approved_version_id ?? "None"], ["Approved score", parsed.approved_score_id ?? "None"]]) ids.append(el("dt", "", label), el("dd", "", value));
    items.push(keepWithNext(el("p", "bmw-label", "Version & score IDs")), ids);
    return items;
  }
  function load(value: unknown, retainWeights?: Values) {
    const parsed = parseRequirement(value);
    const sameRequirement = current?.id === parsed.id;
    current = parsed;
    requiresReload = false;
    draftFactors = { ...parsed.current_version.factors };
    draftWeights = { ...(retainWeights ?? parsed.current_version.score?.weights ?? DEFAULT_WEIGHTS) };
    shell.eyebrow.textContent = `${parsed.key} · Scoring & decision`;
    shell.title.textContent = parsed.current_version.title || "Untitled requirement";
    shell.setSubtitle(parsed.current_version.customer_need || parsed.current_version.statement);
    shell.setScope([parsed.vehicle, parsed.market].filter(Boolean).join(" / "));
    versionLabel.textContent = `Version ${parsed.current_version.version}`;
    briefPager.set(briefItems(parsed), sameRequirement ? briefPage : 0);
    const score = parsed.current_version.score;
    gradeText.textContent = score ? `Grade ${score.evidence_grade || "—"} · separate from priority` : "No evidence grade available.";
    const approvedScore = parsed.approved_version?.score && typeof parsed.approved_version.score === "object" ? record(parsed.approved_version.score) : null;
    approved.textContent = parsed.approved_version ? `Approved baseline: version ${valueText(parsed.approved_version.version)} · ${valueText(approvedScore?.total) || "—"} / 100` : "No approved baseline yet.";
    const open = parsed.reviews.filter((item) => item.status === "open");
    reviewStatus.textContent = parsed.needs_review ? `Needs review${open.length ? `: ${open.map((item) => valueText(item.reason)).filter(Boolean).join("; ")}` : "."}` : "No open review items.";
    reviewStatus.classList.toggle("sp-attention", parsed.needs_review);
    update();
  }
  async function reload() {
    if (!current || busy) return;
    busy = true; failure = ""; update();
    const epoch = ++requestEpoch;
    try {
      const data = await callTool<unknown>(app, "get_requirement", { requirement_id: current.id });
      if (epoch !== requestEpoch) return;
      load(data); awaitingDecisionReview = true; reviewed.checked = false;
      message = "Latest saved state loaded. Unsaved previews were cleared; review the current version and score.";
    } catch (cause) { requiresReload = true; failure = `Could not reload: ${errorText(cause)}`; }
    finally { if (epoch === requestEpoch) { busy = false; update(); } }
  }
  async function write(kind: "factors" | "weights" | "decision") {
    const button = kind === "factors" ? saveFactors : kind === "weights" ? saveWeights : decide;
    if (button.disabled || !current?.current_version.score) return;
    const requirementId = current.id;
    const versionId = current.current_version.id;
    const scoreId = current.current_version.score.id;
    const previousVersion = current.current_version.version;
    const previousTotal = current.current_version.score.total;
    const identity = actor.value.trim();
    const reason = rationale.value.trim();
    const selectedAction = action.value as Action;
    const retainedWeights = kind === "factors" && dirtyWeights() ? { ...draftWeights } : undefined;
    const base = { requirement_id: requirementId, actor: identity, rationale: reason };
    const command = kind === "factors" ? { ...base, expected_version_id: versionId, factors: { ...draftFactors } }
      : kind === "weights" ? { ...base, expected_version_id: versionId, expected_score_id: scoreId, weights: { ...draftWeights } }
      : { ...base, version_id: versionId, score_id: scoreId, action: selectedAction };
    const name = kind === "factors" ? "edit_requirement" : kind === "weights" ? "score_requirement" : "decide_requirement";
    busy = true; failure = ""; update();
    const epoch = ++requestEpoch;
    let recorded = false;
    let contextWarning = "";
    try {
      await callTool<unknown>(app, name, command);
      recorded = true;
      requiresReload = true;
      if (kind === "decision") {
        // A confirmed decision remains recorded even if a later read or host update fails.
        rationale.value = "";
        try {
          await app.updateModelContext({ content: [{ type: "text", text: JSON.stringify({ event: "pm_decision_recorded", requirement_id: requirementId, version_id: versionId, score_id: scoreId, action: selectedAction, actor: identity, rationale: reason }) }] });
        } catch { contextWarning = " The host could not receive the context update; the decision remains recorded."; }
      }
      // These reads never retry the write. We deliberately do not chain a decision after a save.
      load(await callTool<unknown>(app, "get_requirement", { requirement_id: requirementId }), retainedWeights);
      awaitingDecisionReview = kind !== "decision"; reviewed.checked = false;
      // After a save, the next step is reviewing the fresh state in the decision pane.
      if (kind !== "decision") tab = "decide";
      message = kind === "decision" ? `Decision recorded: ${selectedAction}, by ${identity}.${contextWarning}` : `${kind === "factors" ? "Factors" : "Weights"} saved. Review the new version and score${retainedWeights ? "; your weight preview is still unsaved" : ""} before deciding.`;
    } catch (cause) {
      const detail = errorText(cause);
      if (!recorded && /\b409\b|changed; reload|stale/i.test(detail)) {
        requiresReload = true;
        try {
          load(await callTool<unknown>(app, "get_requirement", { requirement_id: requirementId }));
          awaitingDecisionReview = true; reviewed.checked = false;
          failure = `${detail} Latest saved state loaded: version ${previousVersion} → ${current.current_version.version}, priority ${previousTotal.toFixed(1)} → ${current.current_version.score?.total.toFixed(1) ?? "missing"}. The version and score IDs were refreshed and the previous preview was cleared. Review the changes; nothing was retried.`;
        } catch (reloadCause) { failure = `${detail} Reload failed: ${errorText(reloadCause)}. Reload before trying again.`; }
      } else if (!recorded && /\b403\b|forbidden|permission|human actor|inactive actor/i.test(detail)) {
        failure = `Permission denied. Check your human actor identity and role. ${detail}`;
      } else if (!recorded && /\b(?:400|404|422)\b/.test(detail)) {
        failure = `The server rejected the change. ${detail}`;
      } else {
        requiresReload = true;
        failure = recorded ? `The ${kind === "decision" ? "decision" : "change"} was recorded, but the latest state could not be loaded. ${detail} Reload before another write.${contextWarning}` : `The result of this write is unknown. ${detail} Reload and inspect the saved state before trying again.`;
      }
    } finally { if (epoch === requestEpoch) { busy = false; layout(); update(); } }
  }
  actor.addEventListener("input", update); rationale.addEventListener("input", update); action.addEventListener("change", update); reviewed.addEventListener("change", update);
  refresh.addEventListener("click", () => void reload());
  saveFactors.addEventListener("click", () => void write("factors")); saveWeights.addEventListener("click", () => void write("weights")); decide.addEventListener("click", () => void write("decision"));
  discard.addEventListener("click", () => { if (!current || busy) return; draftFactors = { ...current.current_version.factors }; draftWeights = { ...(current.current_version.score?.weights ?? DEFAULT_WEIGHTS) }; message = "Preview discarded. Showing the saved priority."; update(); });
  app.ontoolresult = (result) => {
    if (busy) return;
    try {
      const hadPreview = dirtyFactors() || dirtyWeights();
      load(unpack(result)); failure = ""; message = hadPreview ? "The host loaded a saved requirement. Your previous unsaved preview was cleared." : "Review the requirement, adjust its priority, and record your decision.";
    } catch (cause) { requiresReload = true; failure = errorText(cause); }
    update();
  };
  function hostTheme(context: McpUiHostContext) {
    // The host picks light or dark; BMW tokens replace host style variables so widgets match the workspace.
    if (context.theme) applyDocumentTheme(context.theme);
    shell.hostContext(context);
  }
  app.onhostcontextchanged = hostTheme;
  update();
  return {
    async connect() {
      try { await app.connect(); const context = app.getHostContext(); if (context) hostTheme(context); shell.attach(app); }
      catch (cause) { requiresReload = true; failure = `Could not connect to the MCP host. ${errorText(cause)}`; update(); }
    },
  };
}

const root = document.getElementById("app");
// The shell reports a fixed frame height, so the SDK's content-height auto-resize is disabled.
if (root) void mountScoringPanel(new App({ name: "BMW scoring and decision", version: "0.1.0" }, {}, { autoResize: false }), root).connect();
