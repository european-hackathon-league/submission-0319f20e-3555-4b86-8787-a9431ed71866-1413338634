import { App, applyDocumentTheme, applyHostStyleVariables, type McpUiHostContext } from "@modelcontextprotocol/ext-apps";
import { callTool, unpack } from "./shared/api";
import "./shared/styles.css";

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
function element<K extends keyof HTMLElementTagNameMap>(tag: K, className = "", text = ""): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}
function same(a: Values, b: Values): boolean { return FACTORS.every(([key]) => Math.abs(a[key] - b[key]) < 1e-9); }
function errorText(error: unknown): string { return error instanceof Error ? error.message : "The host could not complete the request."; }
function weightSum(weights: Values): number { return FACTORS.reduce((sum, [key]) => sum + weights[key], 0); }

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
  root.replaceChildren();
  const style = element("style");
  style.textContent = `
    .scoring-header{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;margin-bottom:18px}.scoring-header h1{margin:7px 0 10px}
    .scoring-layout{display:grid;grid-template-columns:minmax(0,1fr) 225px;gap:16px}.scoring-stack{display:grid;gap:16px}.scoring-details{display:grid;gap:12px}
    .scoring-score{font-size:3.5rem;letter-spacing:-.065em;line-height:1.15;font-weight:650}.scoring-score small{font-size:1rem;letter-spacing:0;color:var(--color-text-secondary)}
    .scoring-summary{background:var(--color-background-secondary);display:flex;flex-direction:column;gap:14px;align-self:start}.scoring-saved{font-size:.88rem}
    .scoring-table{display:grid;gap:17px;margin:20px 0}.scoring-row{display:grid;grid-template-columns:minmax(100px,1fr) minmax(75px,1fr) 45px minmax(65px,.8fr) 42px;gap:10px;align-items:center}
    .scoring-row input{width:100%}.scoring-row output{font-variant-numeric:tabular-nums;text-align:right;font-size:.85rem}.scoring-column{font-size:.75rem;color:var(--color-text-secondary)}
    .scoring-controls{display:grid;gap:12px}.scoring-inputs{display:grid;grid-template-columns:1fr 1fr;gap:14px}.scoring-label{display:grid;gap:6px;font-size:.85rem;font-weight:600}.scoring-label input,.scoring-label select{width:100%}
    .scoring-ids{display:grid;gap:7px;margin-top:12px}.scoring-ids div{display:grid;gap:3px}.scoring-message{margin:14px 0;font-size:.88rem}.scoring-criteria{padding-left:20px;display:grid;gap:7px;margin:8px 0 0}
    .scoring-statusline{display:flex;gap:7px;flex-wrap:wrap}.scoring-weight-warning{color:var(--color-text-danger)}.scoring-footnote{font-size:.78rem}.scoring-actions{margin-top:14px}
    @media(max-width:650px){.scoring-layout{grid-template-columns:1fr}.scoring-summary{grid-row:1;display:grid;grid-template-columns:1fr 1fr;gap:9px 20px}.scoring-header{gap:8px}.scoring-row{grid-template-columns:minmax(90px,1fr) minmax(65px,1fr) 32px minmax(60px,.8fr) 36px;gap:7px}.scoring-row label{font-size:.8rem}}
    @media(max-width:380px){.scoring-inputs{grid-template-columns:1fr}.scoring-row{grid-template-columns:minmax(80px,1fr) minmax(42px,.7fr) 28px minmax(40px,.7fr) 33px;gap:4px}}
  `;
  root.append(style);
  const header = element("header", "scoring-header");
  const heading = element("div");
  const key = element("p", "eyebrow", "BMW · Product evidence");
  const title = element("h1", "", "Scoring & decision");
  const badges = element("div", "scoring-statusline");
  heading.append(key, title, badges);
  const refresh = element("button", "", "Reload");
  refresh.type = "button";
  refresh.dataset.action = "reload";
  header.append(heading, refresh);
  const status = element("p", "scoring-message muted");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const error = element("p", "error");
  error.setAttribute("role", "alert");
  const layout = element("div", "scoring-layout");
  const stack = element("div", "scoring-stack");
  const details = element("section", "card scoring-details");
  const statement = element("p");
  const need = element("p", "muted");
  const criteria = element("ul", "scoring-criteria");
  const criterionWrap = element("details");
  criterionWrap.append(element("summary", "", "Acceptance criteria & assumptions"), criteria);
  details.append(statement, need, criterionWrap);
  const factors = element("section", "card");
  factors.append(element("h2", "", "Priority factors"), element("p", "muted scoring-footnote", "Adjust judgments from 0–5 and allocate a total weight of 100%."));
  const table = element("div", "scoring-table");
  const columns = element("div", "scoring-row scoring-column");
  columns.append(element("span", "", "Factor"), element("span", "", "Rating"), element("span"), element("span", "", "Weight"), element("span"));
  table.append(columns);
  const inputs = new Map<FactorKey, { factor: HTMLInputElement; weight: HTMLInputElement; factorOut: HTMLOutputElement; weightOut: HTMLOutputElement }>();
  for (const [factorKey, labelText] of FACTORS) {
    const row = element("div", "scoring-row");
    const label = element("label", "", labelText);
    const factor = element("input");
    factor.type = "range"; factor.min = "0"; factor.max = "5"; factor.step = ".1"; factor.id = `factor-${factorKey}`;
    factor.setAttribute("aria-label", `${labelText} factor`); label.htmlFor = factor.id;
    const factorOut = element("output"); factorOut.htmlFor = factor.id;
    const weight = element("input");
    weight.type = "range"; weight.min = "0"; weight.max = "1"; weight.step = ".01"; weight.id = `weight-${factorKey}`;
    weight.setAttribute("aria-label", `${labelText} weight`);
    const weightOut = element("output"); weightOut.htmlFor = weight.id;
    factor.addEventListener("input", () => { draftFactors[factorKey] = Number(factor.value); update(); });
    weight.addEventListener("input", () => { draftWeights[factorKey] = Number(weight.value); update(); });
    inputs.set(factorKey, { factor, weight, factorOut, weightOut });
    row.append(label, factor, factorOut, weight, weightOut); table.append(row);
  }
  const weightMessage = element("p", "scoring-footnote");
  weightMessage.id = "weight-total";
  weightMessage.setAttribute("aria-live", "polite");
  const saves = element("div", "toolbar scoring-actions");
  const saveFactors = element("button", "", "Save factors"); saveFactors.type = "button"; saveFactors.dataset.action = "save-factors";
  const saveWeights = element("button", "", "Save weights"); saveWeights.type = "button"; saveWeights.dataset.action = "save-weights";
  const discard = element("button", "", "Discard preview"); discard.type = "button"; discard.dataset.action = "discard";
  saves.append(saveFactors, saveWeights, discard);
  factors.append(table, weightMessage, saves);
  const governance = element("section", "card scoring-controls");
  governance.append(element("h2", "", "PM review"), element("p", "muted scoring-footnote", "Your name and rationale are recorded for each save or decision. Check spelling: a new name registers a new human actor."));
  const formFields = element("div", "scoring-inputs");
  const actorLabel = element("label", "scoring-label", "Your name / actor ID");
  const actor = element("input"); actor.id = "actor"; actor.autocomplete = "name"; actor.placeholder = "e.g. Alex Muller"; actor.maxLength = 200;
  actorLabel.append(actor);
  const actionLabel = element("label", "scoring-label", "Decision");
  const action = element("select"); action.id = "decision-action";
  for (const [value, label] of [["approve", "Approve"], ["reject", "Reject"], ["postpone", "Postpone"], ["challenge", "Challenge"]]) {
    const option = element("option", "", label); option.value = value; action.append(option);
  }
  actionLabel.append(action); formFields.append(actorLabel, actionLabel);
  const rationaleLabel = element("label", "scoring-label", "Rationale");
  const rationale = element("textarea"); rationale.id = "rationale"; rationale.placeholder = "Explain this change or decision…"; rationale.maxLength = 10000;
  rationaleLabel.append(rationale);
  const validation = element("p", "muted scoring-footnote"); validation.id = "write-validation"; validation.setAttribute("aria-live", "polite");
  const reviewedLabel = element("label", "toolbar scoring-footnote");
  const reviewed = element("input"); reviewed.type = "checkbox"; reviewed.id = "reviewed-saved-state";
  reviewedLabel.append(reviewed, document.createTextNode("I reviewed the saved version and score shown above."));
  const decide = element("button", "primary", "Record approval"); decide.type = "button"; decide.dataset.action = "decide";
  decide.setAttribute("aria-describedby", "write-validation");
  governance.append(formFields, rationaleLabel, validation, reviewedLabel, decide);
  const summary = element("aside", "card scoring-summary");
  const priorityHeading = element("p", "eyebrow", "Saved priority");
  const total = element("div", "scoring-score"); total.id = "priority-score";
  const saved = element("p", "scoring-saved muted");
  const grade = element("p", "scoring-footnote muted");
  const approved = element("p", "scoring-footnote");
  const reviewStatus = element("p", "scoring-footnote");
  const limitations = element("p", "scoring-footnote muted");
  const ids = element("details");
  ids.append(element("summary", "scoring-footnote", "Version & score IDs"));
  const idList = element("div", "scoring-ids"); ids.append(idList);
  summary.append(priorityHeading, total, saved, grade, approved, reviewStatus, limitations, ids);
  stack.append(details, factors, governance); layout.append(stack, summary);
  root.append(header, error, status, layout);

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
    layout.hidden = !current;
    refresh.disabled = busy || !current;
    status.textContent = busy ? "Working… Please wait for the saved state." : message;
    error.textContent = failure; error.hidden = !failure;
    root.setAttribute("aria-busy", String(busy));
    for (const [factorKey, control] of inputs) {
      control.factor.value = String(draftFactors[factorKey]); control.weight.value = String(draftWeights[factorKey]);
      control.factor.disabled = busy || !current || requiresReload; control.weight.disabled = busy || !current || requiresReload;
      control.factorOut.value = draftFactors[factorKey].toFixed(1); control.weightOut.value = `${Math.round(draftWeights[factorKey] * 100)}%`;
    }
    weightMessage.textContent = `Weight total: ${(weightSum(draftWeights) * 100).toFixed(0)}%${validWeights ? " · ready" : " · must equal 100% before saving or deciding"}`;
    weightMessage.className = `scoring-footnote${validWeights ? "" : " scoring-weight-warning"}`;
    const writeBlocked = busy || requiresReload || !hasIds || !!guard || !validWeights;
    saveFactors.disabled = writeBlocked || !dirtyFactors(); saveWeights.disabled = writeBlocked || !dirtyWeights() || dirtyFactors();
    saveWeights.title = dirtyFactors() ? "Save changed factors first; your weight preview will be retained." : "Save weights for the current version and score.";
    discard.disabled = busy || !dirty || requiresReload;
    actor.disabled = busy; rationale.disabled = busy; action.disabled = busy;
    decide.disabled = writeBlocked || dirty || (awaitingDecisionReview && !reviewed.checked);
    reviewedLabel.hidden = !awaitingDecisionReview; reviewed.disabled = busy || dirty || requiresReload;
    decide.textContent = `Record ${action.value === "approve" ? "approval" : action.value === "reject" ? "rejection" : action.value === "postpone" ? "postponement" : "challenge"}`;
    validation.textContent = requiresReload ? "Reload the current state before making another change." : !hasIds ? "A saved version and score are required." : !validWeights ? "Weights must total 100%." : dirty ? "Save your preview, then review the saved state before recording a decision." : guard || (awaitingDecisionReview && !reviewed.checked ? "Review the freshly saved state and tick the confirmation below." : "This decision applies to the exact saved version and score shown above.");
    priorityHeading.textContent = dirty ? "Preview · unsaved" : "Saved priority";
    const preview = FACTORS.reduce((sum, [factorKey]) => sum + draftFactors[factorKey] * draftWeights[factorKey] * 20, 0);
    total.replaceChildren(document.createTextNode(validWeights && current?.current_version.score ? (dirty ? preview : current.current_version.score.total).toFixed(1) : "—"), element("small", "", " / 100"));
    saved.textContent = current?.current_version.score ? `Saved: ${current.current_version.score.total.toFixed(1)} / 100 · version ${current.current_version.version}` : "No saved score is available.";
  }
  function load(value: unknown, retainWeights?: Values) {
    const parsed = parseRequirement(value);
    current = parsed;
    requiresReload = false;
    draftFactors = { ...parsed.current_version.factors };
    draftWeights = { ...(retainWeights ?? parsed.current_version.score?.weights ?? DEFAULT_WEIGHTS) };
    key.textContent = `${parsed.key} · ${parsed.vehicle} / ${parsed.market}`;
    title.textContent = parsed.current_version.title || "Untitled requirement";
    badges.replaceChildren(element("span", "badge", parsed.status.replaceAll("_", " ")), element("span", "badge info", parsed.needs_review ? "Needs review" : "No open review"));
    statement.textContent = parsed.current_version.statement;
    need.textContent = parsed.current_version.customer_need;
    criteria.replaceChildren();
    for (const criterion of parsed.current_version.acceptance_criteria) criteria.append(element("li", "", `${valueText(criterion.metric)}: ${valueText(criterion.target)} ${valueText(criterion.unit)} · ${valueText(criterion.basis)}`.trim()));
    for (const assumption of parsed.current_version.assumptions) criteria.append(element("li", "muted", `Assumption: ${assumption}`));
    grade.textContent = parsed.current_version.score ? `Evidence grade ${parsed.current_version.score.evidence_grade || "—"} · separate from priority` : "No evidence grade available.";
    const approvedScore = parsed.approved_version?.score && typeof parsed.approved_version.score === "object" ? record(parsed.approved_version.score) : null;
    approved.textContent = parsed.approved_version ? `Approved baseline: version ${valueText(parsed.approved_version.version)} · ${valueText(approvedScore?.total) || "—"} / 100` : "No approved baseline yet.";
    const open = parsed.reviews.filter((item) => item.status === "open");
    reviewStatus.textContent = parsed.needs_review ? `Needs review${open.length ? `: ${open.map((item) => valueText(item.reason)).filter(Boolean).join("; ")}` : "."}` : "No open review items.";
    const limits = parsed.current_version.score?.explanation.limitations;
    limitations.textContent = Array.isArray(limits) ? limits.map(valueText).join(" ") : "Priority reflects recorded judgments; evidence grade is separate.";
    idList.replaceChildren();
    for (const [label, value] of [["Current version", parsed.current_version.id], ["Current score", parsed.current_version.score?.id ?? "Missing"], ["Approved version", parsed.approved_version_id ?? "None"], ["Approved score", parsed.approved_score_id ?? "None"]]) {
      const row = element("div"); row.append(element("span", "muted scoring-footnote", label), element("code", "", value)); idList.append(row);
    }
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
    } finally { if (epoch === requestEpoch) { busy = false; update(); } }
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
    if (context.theme) applyDocumentTheme(context.theme);
    if (context.styles?.variables) applyHostStyleVariables(context.styles.variables);
  }
  app.onhostcontextchanged = hostTheme;
  update();
  return {
    async connect() {
      try { await app.connect(); const context = app.getHostContext(); if (context) hostTheme(context); }
      catch (cause) { requiresReload = true; failure = `Could not connect to the MCP host. ${errorText(cause)}`; update(); }
    },
  };
}

const root = document.getElementById("app");
if (root) void mountScoringPanel(new App({ name: "BMW scoring and decision", version: "0.1.0" }), root).connect();
