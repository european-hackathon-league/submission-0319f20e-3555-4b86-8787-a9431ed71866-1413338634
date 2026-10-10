"use strict";

// Same-origin API only. All imported and generated text is rendered as text nodes.
const $ = (id) => document.getElementById(id);
const state = {scope: {vehicle: "G60", market: "US"}, actors: [], sources: [], workflows: [], workflow: null,
  requirements: [], selected: null, detail: null, trace: null, brief: null, busy: false, selection: 0};
const processStages = [
  ["situation_analysis", "Situation analysis", "Establish the evidence base"],
  ["structure_context", "Structure & context", "Connect customer findings"],
  ["requirements_definition", "Requirements definition", "Define measurable outcomes"],
  ["prioritization", "Prioritization", "Explain the trade-offs"],
  ["human_review", "Human review", "PM decision required"],
  ["documentation", "Documentation", "Preserve the decision record"],
];

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) element.textContent = String(text);
  if (className) element.className = className;
  return element;
}
function add(parent, ...children) { parent.append(...children.filter(Boolean)); return parent; }
function readable(value) { return String(value || "pending").replaceAll("_", " "); }
function badge(value) { return node("span", readable(value), "badge " + String(value || "pending").replace(/[^a-z_]/g, "")); }
function date(value) { return value ? new Date(value).toLocaleString(undefined, {dateStyle: "medium", timeStyle: "short"}) : "Date unavailable"; }
function json(value) { return JSON.stringify(value, null, 2); }
function actor() { if (!$("actor").value) throw new Error("Select an active human actor before continuing."); return $("actor").value; }
function scopeQuery() { return new URLSearchParams(state.scope).toString(); }
function endpoint(id) { return "/workflows/" + encodeURIComponent(id); }
function reqEndpoint(id) { return "/requirements/" + encodeURIComponent(id); }
function announce(message) { $("notice").textContent = message; $("notice").hidden = !message; }
function showError(error) { announce(""); $("error").textContent = error.message || String(error); $("error").hidden = false; }

async function api(path, options = {}) {
  const init = {...options};
  if (init.body && !(init.body instanceof FormData)) {
    init.headers = {"Content-Type": "application/json"};
    init.body = JSON.stringify(init.body);
  }
  const response = await fetch(path, init);
  const text = await response.text();
  let body;
  try { body = JSON.parse(text); } catch { body = text; }
  if (!response.ok) {
    const detail = body?.detail || body || response.statusText;
    let message = typeof detail === "string" ? detail : Array.isArray(detail)
      ? detail.map((item) => `${(item.loc || []).join(" / ")}: ${item.msg}`).join("; ") : json(detail);
    if (response.status === 409) message += " Refresh the workspace and review the latest version before retrying.";
    throw new Error(message);
  }
  return body;
}

function updateControls() {
  document.body.setAttribute("aria-busy", String(state.busy));
  document.querySelectorAll("main button, main input, main select, main textarea").forEach((el) => { el.disabled = state.busy; });
  const human = state.actors.find((item) => item.id === $("actor").value);
  const canAct = Boolean(human && human.active && human.kind === "human");
  ["import-submit", "create-workflow"].forEach((id) => { $(id).disabled = state.busy || !canAct; });
  $("create-workflow").disabled ||= !state.sources.length;
  $("run-workflow").disabled = state.busy || !canAct || !state.workflow || state.workflow.status === "completed";
  $("complete-workflow").disabled = state.busy || !canAct || !["pm", "lead_pm"].includes(human?.role) || state.workflow?.status !== "awaiting_review";
  $("export-brief").disabled = state.busy || !state.workflow;
  if ($("decision-submit")) $("decision-submit").disabled = state.busy || !canAct || state.workflow?.status === "completed";
  if ($("edit-submit")) $("edit-submit").disabled = state.busy || !canAct || state.workflow?.status === "completed";
  if ($("decision-action")) {
    Array.from($("decision-action").options).forEach((option) => { option.disabled = ["approve", "reject"].includes(option.value) && !["pm", "lead_pm"].includes(human?.role); });
    if ($("decision-action").selectedOptions[0]?.disabled) $("decision-action").value = "challenge";
  }
}

async function action(work) {
  if (state.busy) return;
  state.busy = true;
  $("error").hidden = true;
  updateControls();
  try { await work(); } catch (error) { showError(error); }
  finally { state.busy = false; updateControls(); }
}

async function listRequirements() {
  const items = [];
  let page;
  do {
    page = await api(`/requirements?${scopeQuery()}&limit=1000&offset=${items.length}`);
    items.push(...page.items);
  } while (items.length < page.total && page.items.length);
  return items;
}

async function refreshWorkspace(preferred = state.workflow?.id) {
  state.selection++;
  const [sources, workflows, requirements] = await Promise.all([
    api("/sources?" + scopeQuery()), api("/workflows?" + scopeQuery()), listRequirements(),
  ]);
  state.sources = sources;
  state.workflows = (Array.isArray(workflows) ? workflows : workflows.items).sort((a, b) => b.created_at.localeCompare(a.created_at));
  state.requirements = requirements;
  renderSources();
  state.selected = state.selected && requirements.some((item) => item.id === state.selected) ? state.selected : null;
  state.detail = null; state.trace = null; renderDetail();
  const id = state.workflows.find((item) => item.id === preferred)?.id || state.workflows[0]?.id;
  if (id) {
    [state.workflow, state.brief] = await Promise.all([api(endpoint(id)), api(endpoint(id) + "/brief")]);
  } else { state.workflow = null; state.brief = null; }
  renderWorkflow();
  renderRequirements();
  if (state.selected && visibleRequirements().some((item) => item.id === state.selected)) await selectRequirement(state.selected);
  else { state.selected = null; state.detail = null; state.trace = null; renderDetail(); }
  updateControls();
}

function renderSources() {
  $("source-count").replaceChildren(document.createTextNode(String(state.sources.length)), node("small", "sources"));
  $("source-register-count").textContent = `(${state.sources.length})`;
  const list = $("source-list");
  list.replaceChildren();
  if (!state.sources.length) list.append(node("li", "No sources in this scope yet. Import a file or add feedback to begin."));
  for (const source of state.sources) {
    const item = add(node("li"), node("strong", source.title), node("small", `${readable(source.kind)} · ${source.reference}`));
    if (source.original_path) {
      const link = node("a", "Open preserved original");
      link.href = "/sources/" + encodeURIComponent(source.id) + "/original";
      link.target = "_blank"; link.rel = "noopener";
      item.append(link);
    }
    list.append(item);
  }
}

function renderWorkflow() {
  const workflow = state.workflow;
  $("workflow-status").replaceWith(Object.assign(badge(workflow?.status || "no workflow selected"), {id: "workflow-status"}));
  const select = $("workflow-select");
  select.replaceChildren();
  if (!state.workflows.length) select.append(new Option("Create a workflow below", ""));
  for (const item of state.workflows) select.append(new Option(`${date(item.created_at)} · ${readable(item.kind)} · ${readable(item.status)} · ${item.id.slice(0, 8)}`, item.id));
  select.value = workflow?.id || "";
  const stages = $("stages");
  stages.replaceChildren();
  const values = workflow?.stages?.length ? workflow.stages : processStages.map(([key, label, description]) => ({key, label, description, status: "pending"}));
  values.forEach((stage, index) => {
    const item = node("li", null, "stage " + stage.status);
    add(item, node("div", `0${index + 1} / ${readable(stage.status).toUpperCase()}`, "stage-number"), node("h3", stage.label || readable(stage.key)), node("p", stage.description || processStages[index]?.[2] || ""));
    if (stage.output && Object.keys(stage.output).length) {
      const details = node("details");
      add(details, node("summary", "Stage record"), node("pre", json(stage.output)));
      item.append(details);
    }
    stages.append(item);
  });
  $("workflow-error").hidden = !workflow?.error;
  $("workflow-error").textContent = workflow?.error ? `${workflow.error.message || json(workflow.error)}${workflow.error.retryable ? " Resolve the cause, then retry the workflow." : ""}` : "";
  $("run-workflow").hidden = !workflow || workflow.status === "completed";
  $("run-workflow").textContent = workflow?.status === "failed" ? "Retry workflow" : workflow?.status === "awaiting_review" ? "Process new evidence" : workflow?.status === "running" ? "Retry interrupted workflow" : "Run workflow";
  $("workflow-meta").textContent = workflow ? `${workflow.vehicle} / ${workflow.market} · ${readable(workflow.kind)} · ${workflow.provider === "openai" ? "Live OpenAI analysis" : "Deterministic reference analysis"} · Revision ${workflow.revision} · Updated ${date(workflow.updated_at)}` : "Automatic analysis and prioritization stop at mandatory human review.";
  const summary = state.brief?.summary;
  if (workflow?.status === "running") $("workflow-meta").textContent += " · A worker may still be active. Refresh to check progress; retry recovers an interrupted run after its lease expires. The server prevents overlapping runs.";
  $("completion-hint").textContent = workflow?.status === "completed" ? "Completed decision record. Start an ongoing update when new evidence arrives." : summary ? `${summary.approved_count} approved · ${summary.rejected_count} rejected · ${summary.needs_decision_count} still need a decision${summary.attention_count ? ` · ${summary.attention_count} checks need attention` : ""}. The brief includes evidence and recorded assumptions.` : "Choose a workflow to prepare the decision brief.";
  if (state.brief?.warnings?.length) $("completion-hint").textContent += " " + state.brief.warnings.join(" ");
}

function visibleRequirements() {
  if (!state.workflow) return [];
  // The server gates completion on the entire scoped requirement set, including existing work.
  // Completed runs show their frozen decision brief even if a newer cycle changes the same requirement.
  const items = state.workflow.status === "completed" ? (state.brief?.requirements || []).map((item) => ({
    id: item.requirement_id, key: item.key, title: item.version.title, version: item.version.version,
    status: item.decision?.action === "approve" ? "approved" : "rejected", needs_review: false,
    priority: item.score.total, evidence_grade: item.score.evidence_grade,
  })).sort((a, b) => b.priority - a.priority) : state.requirements;
  return items.filter((item) => !$("needs-review").checked || !["approved", "rejected"].includes(item.status) || item.needs_review);
}

function renderRequirements() {
  const list = $("requirement-list");
  list.replaceChildren();
  const items = visibleRequirements();
  $("requirements-context").textContent = state.workflow ? `${state.scope.vehicle} / ${state.scope.market} · ${items.length} shown · Ordered by priority, 0–100. Evidence grade is separate from priority.${state.workflow.status === "completed" ? " Completed workflow: the exported brief preserves the final snapshots." : " All requirements in this scope enter the human review gate."}` : "Select a workflow to review its requirements.";
  if (!items.length) {
    list.append(node("p", $("needs-review").checked ? "No requirements match this filter." : "Import evidence and run a workflow to see customer requirements here.", "empty-state"));
    return;
  }
  for (const req of items) {
    const button = node("button", null, "requirement-choice");
    button.type = "button";
    button.dataset.requirementId = req.id;
    button.setAttribute("aria-pressed", String(req.id === state.selected));
    add(button, add(node("div", null, "req-topline"), node("span", req.key || req.id), node("span", `v${req.version}`)), node("h3", req.title),
      add(node("div", null, "req-bottom"), badge(req.status), node("span", `${Number(req.priority).toFixed(1)} / 100`, "priority"), node("span", `Evidence ${req.evidence_grade}`)));
    button.addEventListener("click", () => action(async () => { await selectRequirement(req.id); if (window.innerWidth < 760) $("requirement-detail").scrollIntoView({behavior: "smooth"}); }));
    list.append(button);
  }
}

async function selectRequirement(id) {
  const token = ++state.selection;
  const workflowId = state.workflow?.id;
  const frozen = state.workflow?.status === "completed" ? state.brief?.requirements.find((item) => item.requirement_id === id) : null;
  // Clear the previous actionable detail immediately: failed loads must never leave
  // a form for a different workflow or requirement on screen.
  state.selected = null; state.detail = null; state.trace = null;
  renderRequirements(); renderDetail();
  let detail, trace;
  if (state.workflow?.status === "completed" && !frozen) throw new Error("This requirement is absent from the completed brief. Refresh the workflow.");
  if (frozen) {
    detail = {id, key: frozen.key};
    trace = {version: {...frozen.version, score: frozen.score}, findings: frozen.findings,
      sources: frozen.sources, evidence: {items: frozen.evidence, total: frozen.evidence.length},
      decisions: frozen.decision ? [frozen.decision] : []};
  } else {
    detail = await api(reqEndpoint(id));
    const version = detail.current_version;
    const traceQuery = "?version_id=" + encodeURIComponent(version.id) + "&score_id=" + encodeURIComponent(version.score.id) + "&limit=1000";
    trace = await api(reqEndpoint(id) + "/trace" + traceQuery);
    // Pin all pages to the displayed version AND score, including concurrent rescoring.
    while (trace.evidence.items.length < trace.evidence.total) {
      const page = await api(reqEndpoint(id) + "/trace" + traceQuery + "&offset=" + trace.evidence.items.length);
      if (!page.evidence.items.length) throw new Error("Evidence pagination ended early. Refresh before making a decision.");
      trace.evidence.items.push(...page.evidence.items);
    }
  }
  if (token !== state.selection || workflowId !== state.workflow?.id) return;
  state.selected = id; state.detail = detail; state.trace = trace;
  renderRequirements(); renderDetail(); updateControls();
}

function section(title) { return add(node("section", null, "detail-section"), node("h4", title)); }
function textList(items) { return add(node("ul", null, "plain-list"), ...items.map((item) => node("li", typeof item === "string" ? item : json(item)))); }
function field(labelText, element) { return add(node("label", labelText), element); }
function input(value, required = true) { const el = node("input"); el.value = value ?? ""; el.required = required; return el; }

function renderDetail() {
  const root = $("requirement-detail");
  root.replaceChildren();
  if (!state.detail) {
    root.append(add(node("div", null, "empty-state"), node("span", "↖"), node("h3", "Your evidence, in context."), node("p", "Select a requirement to inspect its priority, measurable targets and the sources behind it.")));
    return;
  }
  const req = state.detail;
  const version = state.trace.version;
  const score = version.score;
  const archived = state.workflow?.status === "completed";
  const briefReq = state.brief?.requirements?.find((item) => item.requirement_id === req.id);
  const heading = add(node("div", null, "detail-heading"), add(node("div"), node("p", `${req.key || req.id} · VERSION ${version.version}`, "eyebrow"), node("h3", version.title), badge(archived ? briefReq?.decision?.action || "completed" : req.status)),
    add(node("div", Number(score.total).toFixed(1), "score"), node("small", "PRIORITY / 100"), node("small", `EVIDENCE ${score.evidence_grade}`)));
  add(root, heading, node("p", version.statement, "statement"));
  if (archived) root.append(node("p", "This workflow is complete. Its requirement version is shown for reference; the decision brief preserves the final score, evidence and decisions.", "notice"));
  if (!archived && req.approved_version && req.approved_version.id !== version.id) {
    const baseline = add(node("details", null, "detail-section"), node("summary", `Compare approved baseline · v${req.approved_version.version}`), node("p", req.approved_version.title), node("p", req.approved_version.statement, "muted small"));
    root.append(baseline);
  }
  if (briefReq?.checks?.length) {
    const checks = section("Readiness checks");
    for (const check of briefReq.checks) checks.append(node("p", `${check.message}${check.next_action ? " " + check.next_action : ""}`, "notice " + (check.severity === "attention" ? "attention" : "")));
    root.append(checks);
  }
  if (!archived && req.reviews?.some((review) => review.status === "open")) root.append(add(section("Why this needs review"), textList(req.reviews.filter((review) => review.status === "open").map((review) => review.reason))));
  const criteria = section("Customer need & measurable targets");
  criteria.append(node("p", version.customer_need, "muted small"));
  const criteriaList = node("ol", null, "criteria-list");
  for (const criterion of version.acceptance_criteria) {
    criteriaList.append(add(node("li", `${criterion.metric}: ${criterion.target}${criterion.unit ? " " + criterion.unit : ""}`), node("small", criterion.basis === "source" ? "Target basis: source evidence · " + criterion.source_ids.join(", ") : "Target basis: PM assumption — validate before commitment")));
  }
  add(root, add(criteria, criteriaList));
  if (version.assumptions?.length) root.append(add(section("Assumptions & uncertainties"), textList(version.assumptions)));
  const priority = section("Why this priority");
  priority.append(node("p", score.explanation.formula, "muted small"));
  for (const [key, contribution] of Object.entries(score.explanation.contributions || {})) {
    const bar = node("div", null, "factor-bar"); bar.style.width = Math.min(100, Math.max(0, Number(contribution))) + "%";
    const row = add(node("div", null, "factor"), node("span", readable(key)), add(node("div", null, "factor-track"), bar), node("span", Number(contribution).toFixed(1), "factor-value"));
    row.title = `Factor ${score.factors[key]} / 5 × weight ${score.weights[key]} × 20`;
    priority.append(row);
  }
  add(priority, node("p", score.explanation.evidence_grade_rubric, "muted small"), textList(score.explanation.limitations || []));
  root.append(priority);
  const findings = section("Findings behind this requirement");
  for (const finding of state.trace.findings) findings.append(add(node("p", finding.summary, "small"), node("small", `${readable(finding.kind)} · confidence ${finding.confidence}`)));
  root.append(findings);
  const evidence = section(`Exact source trace · ${state.trace.evidence.total} records`);
  for (const item of state.trace.evidence.items) {
    const source = state.trace.sources.find((source) => source.id === item.source_id);
    const supports = state.trace.findings.some((finding) => finding.evidence_ids?.includes(item.id));
    const conflicts = state.trace.findings.some((finding) => finding.conflicting_evidence_ids?.includes(item.id));
    const card = add(node("div", null, "evidence-card"), node("div", source?.title || item.source_id, "evidence-source"), node("small", source?.reference || ""), badge(conflicts ? (supports ? "supports and conflicts" : "conflicting evidence") : "supporting evidence"));
    add(card, node("blockquote", item.content), node("div", json(item.location), "location"), node("small", `Observed: ${item.observed_at || "not recorded"} · Evidence ID: ${item.id}`));
    if (source?.original_path) {
      const link = node("a", "Open preserved original"); link.href = "/sources/" + encodeURIComponent(source.id) + "/original"; link.target = "_blank"; link.rel = "noopener";
      card.append(add(node("p", null, "small"), link));
    }
    evidence.append(card);
  }
  root.append(evidence);
  if (!archived) { root.append(editForm(req, version)); root.append(decisionForm(req, version)); }
  const history = section("Decision audit trail");
  const decisions = node("ol", null, "decision-history");
  for (const decision of state.trace.decisions) decisions.append(add(node("li", `${readable(decision.action)} · ${decision.rationale}`), node("small", `${decision.actor} · ${date(decision.created_at)} · Score ${decision.score_id}`)));
  history.append(state.trace.decisions.length ? decisions : node("p", "No human decision recorded for this version yet.", "muted small"));
  root.append(history);
}

function decisionForm(req, version) {
  const form = node("form", null, "stack decision-form"); form.id = "decision-form";
  const rationale = node("textarea"); rationale.id = "decision-rationale"; rationale.required = true; rationale.rows = 3; rationale.maxLength = 10000; rationale.placeholder = "Record the evidence you considered and why this is the right decision.";
  const select = node("select"); select.id = "decision-action";
  for (const [value, label] of [["approve", "Approve"], ["reject", "Reject"], ["postpone", "Postpone"], ["challenge", "Challenge"]]) select.append(new Option(label, value));
  const submit = node("button", "Record decision"); submit.id = "decision-submit"; submit.type = "submit";
  add(form, field("Decision rationale", rationale), add(node("div", null, "two-col"), field("Decision", select), add(node("div", null, "stack"), node("span", " "), submit)));
  form.addEventListener("submit", (event) => { event.preventDefault(); action(async () => {
    const selectedActor = actor();
    await api(reqEndpoint(req.id) + "/decisions", {method: "POST", body: {actor: selectedActor, action: select.value, rationale: rationale.value.trim(), version_id: version.id, score_id: version.score.id}});
    await refreshWorkspace();
    announce("Decision recorded with the exact requirement version, score, actor and rationale.");
  }); });
  return add(section("Human decision · mandatory gate"), node("p", "Approve and reject require a PM role. Challenge or postpone keeps this requirement open for further work.", "muted small"), form);
}

function editForm(req, version) {
  const details = node("details", null, "detail-section"); details.id = "edit-requirement";
  details.append(node("summary", "Edit requirement & measurable targets"));
  const form = node("form", null, "stack");
  const title = input(version.title); title.id = "edit-title"; title.maxLength = 300;
  const statement = node("textarea"); statement.id = "edit-statement"; statement.value = version.statement; statement.required = true; statement.rows = 3; statement.maxLength = 10000;
  const rationale = node("textarea"); rationale.id = "edit-rationale"; rationale.required = true; rationale.rows = 2; rationale.maxLength = 10000;
  add(form, field("Title", title), field("Customer-facing requirement", statement), node("p", "Edits create a new version and recalculate its priority. Changed targets are labeled as PM assumptions for validation.", "muted small"));
  const criteria = version.acceptance_criteria.map((criterion, index) => {
    const metric = input(criterion.metric); const target = input(criterion.target); const unit = input(criterion.unit, false);
    add(form, field(`Target ${index + 1} · metric`, metric), add(node("div", null, "two-col"), field("Target value", target), field("Unit (optional)", unit)));
    return {criterion, metric, target, unit};
  });
  const submit = node("button", "Save revised requirement", "secondary"); submit.id = "edit-submit"; submit.type = "submit";
  add(form, field("Reason for the change", rationale), submit);
  form.addEventListener("submit", (event) => { event.preventDefault(); action(async () => {
    const updatedCriteria = criteria.map(({criterion, metric, target, unit}) => {
      const updated = {metric: metric.value.trim(), target: target.value.trim(), unit: unit.value.trim() || null};
      const unchanged = updated.metric === criterion.metric && updated.target === String(criterion.target) && updated.unit === (criterion.unit || null);
      return unchanged ? criterion : {...updated, basis: "PM assumption", source_ids: []};
    });
    await api(reqEndpoint(req.id), {method: "PATCH", body: {expected_version_id: version.id, actor: actor(), rationale: rationale.value.trim(), title: title.value.trim(), statement: statement.value.trim(), acceptance_criteria: updatedCriteria}});
    await refreshWorkspace();
    announce("New requirement version saved and rescored. Review its evidence and record a decision on this version.");
  }); });
  details.append(form);
  return details;
}

async function runWorkflow() {
  if (!state.workflow) throw new Error("Create or select a workflow first.");
  const id = state.workflow.id;
  const command = {expected_revision: state.workflow.revision, actor: actor()};
  announce("Agent workflow running. Stages are saved as they complete; human decisions remain yours.");
  let polling = false;
  let ended = false;
  const timer = setInterval(async () => {
    if (polling) return;
    polling = true;
    try { const current = await api(endpoint(id)); if (!ended && state.workflow?.id === id) { state.workflow = current; renderWorkflow(); updateControls(); } } catch { /* The main request reports actionable failures. */ }
    finally { polling = false; }
  }, 2500);
  let result;
  let runError;
  try { result = await api(endpoint(id) + "/run", {method: "POST", body: command}); }
  catch (error) { runError = error; }
  finally { ended = true; clearInterval(timer); }
  // A disconnected run can still have persisted stages or completed on the server.
  // Reload durable state before surfacing the request failure.
  try { await refreshWorkspace(id); } catch (error) { if (!runError) throw error; }
  if (runError) throw runError;
  if (result.status === "failed") throw new Error(result.error?.message || "Workflow failed. Inspect the stage record, resolve the cause and retry.");
  announce(result.status === "awaiting_review" ? "Proposals and priorities are ready. Inspect the sources and record your decisions." : "Workflow state refreshed.");
}

function requestBriefDownload() {
  if (!state.workflow) throw new Error("Select a workflow before requesting its decision brief.");
  // Keep the browser's native download path and the server's Content-Disposition
  // filename. A blob URL cannot be handled reliably by every embedded browser.
  const link = node("a");
  link.href = endpoint(state.workflow.id) + "/brief?format=markdown";
  link.download = "";
  link.target = "_blank"; link.rel = "noopener";
  document.body.append(link); link.click(); link.remove();
  announce(state.workflow.status === "completed" ? "Completed decision brief download requested. Check your browser’s downloads." : "Working decision brief download requested. Check your browser’s downloads; open decisions and assumptions remain visible.");
}

$("scope-form").addEventListener("submit", (event) => { event.preventDefault(); action(async () => {
  state.scope = {vehicle: $("vehicle").value.trim().toUpperCase(), market: $("market").value.trim().toUpperCase()};
  state.scope.market = {USA: "US", "UNITED STATES": "US", EUROPE: "EU", CHINA: "CN"}[state.scope.market] || state.scope.market;
  $("vehicle").value = state.scope.vehicle; $("market").value = state.scope.market;
  state.selected = null; state.workflow = null; state.brief = null; state.detail = null; state.trace = null;
  state.sources = []; state.workflows = []; state.requirements = []; state.selection++;
  renderSources(); renderWorkflow(); renderRequirements(); renderDetail();
  await refreshWorkspace(); announce(`Workspace set to ${state.scope.vehicle} / ${state.scope.market}.`);
}); });
$("actor").addEventListener("change", updateControls);
$("refresh").addEventListener("click", () => action(async () => { await refreshWorkspace(); announce("Workspace refreshed from the durable record."); }));
$("workflow-select").addEventListener("change", () => action(async () => { state.selected = null; await refreshWorkspace($("workflow-select").value); }));
$("needs-review").addEventListener("change", () => { renderRequirements(); updateControls(); });
$("run-workflow").addEventListener("click", () => action(runWorkflow));
$("provider").addEventListener("change", () => { $("provider-note").textContent = $("provider").value === "openai" ? "Live AI uses the server’s configured OpenAI credentials and model. If unavailable, the run fails visibly; it never silently substitutes reference analysis." : "Reference mode uses repeatable rules and heuristic scores. It demonstrates the process; it does not establish AI quality."; });
$("import-mode").addEventListener("change", () => {
  const mode = $("import-mode").value;
  $("file-fields").hidden = mode !== "file"; $("local-fields").hidden = mode !== "local"; $("feedback-fields").hidden = mode !== "feedback"; $("kind-field").hidden = mode === "feedback";
});
$("import-form").addEventListener("submit", (event) => { event.preventDefault(); action(async () => {
  const mode = $("import-mode").value;
  const selectedActor = actor();
  const title = $("import-title").value.trim();
  let result;
  if (mode === "file") {
    const file = $("import-file").files[0];
    if (!file) throw new Error("Select an input file to import.");
    if (file.size > 25 * 1024 * 1024) throw new Error("Choose a file no larger than 25 MiB.");
    const body = new FormData();
    body.append("file", file); body.append("actor", selectedActor); body.append("vehicle", state.scope.vehicle); body.append("market", state.scope.market); body.append("kind", $("import-kind").value);
    if (title) body.append("title", title);
    result = await api("/imports/files", {method: "POST", body});
  } else if (mode === "local") {
    const path = $("import-path").value.trim(); if (!path) throw new Error("Enter a file path inside the server’s data folder.");
    result = await api("/imports/local", {method: "POST", body: {...state.scope, actor: selectedActor, path, kind: $("import-kind").value, ...(title ? {title} : {})}});
  } else {
    const content = $("feedback-content").value.trim(); const reference = $("feedback-reference").value.trim(); const demo = $("feedback-demo").checked;
    if (!title || !reference || !content) throw new Error("Feedback requires a source title, a reference and customer feedback text.");
    result = await api("/imports/records", {method: "POST", body: {...state.scope, actor: selectedActor, title: (demo ? "SIMULATED DEMO · " : "") + title, reference: (demo ? "demo:" : "") + reference, kind: "feedback", metadata: {simulated_demo: demo}, records: [{content, location: {entry: 1, input: "PM feedback entry"}, observed_at: $("feedback-date").value || null, metadata: {simulated_demo: demo}}]}});
  }
  await refreshWorkspace();
  announce(`${result.deduplicated ? "Existing source recognized" : "Evidence imported"}: ${result.record_count} records. ${state.workflow ? "Process new evidence or start an ongoing update to assess its impact." : "Create an initial workflow to begin the analysis."}`);
}); });
$("workflow-form").addEventListener("submit", (event) => { event.preventDefault(); action(async () => {
  const created = await api("/workflows", {method: "POST", body: {...state.scope, kind: $("workflow-kind").value, provider: $("provider").value, actor: actor(), request_key: crypto.randomUUID()}});
  state.workflow = created;
  await refreshWorkspace(created.id);
  await runWorkflow();
}); });
$("complete-form").addEventListener("submit", (event) => { event.preventDefault(); action(async () => {
  if (!state.workflow || state.workflow.status !== "awaiting_review") throw new Error("Select a workflow awaiting human review before completing it.");
  const id = state.workflow.id;
  await api(endpoint(id) + "/complete", {method: "POST", body: {expected_revision: state.workflow.revision, actor: actor(), rationale: $("complete-rationale").value.trim()}});
  await refreshWorkspace(id); announce("Workflow completed. The decision brief preserves the approved and rejected requirement snapshots for handover.");
}); });
$("export-brief").addEventListener("click", () => action(requestBriefDownload));

renderWorkflow();
action(async () => {
  const result = await api("/actors");
  state.actors = (Array.isArray(result) ? result : result.items).filter((item) => item.kind === "human" && item.active);
  $("actor").replaceChildren(...state.actors.map((item) => new Option(`${item.display_name} · ${readable(item.role)}`, item.id)));
  if (state.actors.some((item) => item.id === "PM")) $("actor").value = "PM";
  if (!state.actors.length) $("actor").append(new Option("No active human actors available", ""));
  await refreshWorkspace();
});
