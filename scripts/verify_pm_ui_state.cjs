"use strict";
// Run with Node; these checks exercise UI request/state behavior without a server.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const source = fs.readFileSync(path.join(__dirname, "../server/pm_static/app.js"), "utf8");
const context = vm.createContext({URLSearchParams, console, setInterval, clearInterval});
vm.runInContext(source.slice(0, source.indexOf('$("scope-form").addEventListener')), context);
const run = (code) => vm.runInContext(code, context);
run(`renderRequirements = renderDetail = updateControls = () => {};
state.workflow = {id: "live", status: "awaiting_review"};
state.detail = {id: "old"}; state.selected = "old";
var calls = [];
api = async (url) => {
  calls.push(url);
  if (!url.includes("/trace")) return {id: "req", current_version: {id: "v1", score: {id: "s1"}}};
  return {version: {id: "v1", score: {id: "s1"}}, evidence: {items: [{id: "e"}], total: 1}};
};`);
(async () => {
  await run('selectRequirement("req")');
  assert.deepEqual(Array.from(run("calls")), ["/requirements/req", "/requirements/req/trace?version_id=v1&score_id=s1&limit=1000"]);
  assert.equal(run("state.selected"), "req");

  run(`api = async () => { throw new Error("disconnected"); };`);
  await assert.rejects(run('selectRequirement("different")'), /disconnected/);
  assert.equal(run("state.detail"), null, "failed selection clears old decision/edit forms");
  assert.equal(run("state.selected"), null);

  run(`state.workflow = {id: "completed", status: "completed"};
state.brief = {requirements: [{requirement_id: "req", key: "R-1", version: {id: "v1"}, score: {id: "s1"}, evidence: [{id: "e1", content: "<script>bad()</script>"}], findings: [], sources: [], decision: {id: "d1"}}]};`);
  await run('selectRequirement("req")');
  assert.equal(run("state.trace.version.score.id"), "s1");
  assert.equal(run("state.trace.decisions[0].id"), "d1");
  assert.equal(run("state.trace.evidence.items[0].content"), "<script>bad()</script>");

  run(`state.workflow = {id: "live", status: "awaiting_review"};
var release;
api = async (url) => {
  if (!url.includes("/trace")) return await new Promise(resolve => {release = resolve;});
  return {evidence: {items: [], total: 0}};
};`);
  const pending = run('selectRequirement("req")');
  run(`state.workflow = {id: "other", status: "awaiting_review"};
release({id: "req", current_version: {id: "v1", score: {id: "s1"}}});`);
  await pending;
  assert.equal(run("state.detail"), null, "late response cannot populate another workflow");

  run(`state.workflow = {id: "live", status: "awaiting_review"};
api = async (url) => url.includes("/trace") ? {evidence: {items: [], total: 1}} : {current_version: {id: "v1", score: {id: "s1"}}};`);
  await assert.rejects(run('selectRequirement("req")'), /pagination ended early/);
  assert.equal(run("state.detail"), null);
  run(`state.workflow = {id: "interrupted", status: "running", revision: 2};
actor = () => "PM"; announce = () => {};
var refreshed = null;
refreshWorkspace = async (id) => {refreshed = id; state.workflow.status = "awaiting_review";};
api = async () => {throw new Error("connection lost");};`);
  await assert.rejects(run("runWorkflow()"), /connection lost/);
  assert.equal(run("refreshed"), "interrupted", "failed run reloads durable state before reporting failure");
  assert.equal(run("state.workflow.status"), "awaiting_review");
  context.document = {body: {append: () => {}}};
  run(`var downloadLink, downloadNotice;
node = () => (downloadLink = {click() {this.clicked = true;}, remove() {this.removed = true;}});
announce = message => {downloadNotice = message;};
state.workflow = {id: "completed/id", status: "completed"};
requestBriefDownload();`);
  assert.equal(run("downloadLink.href"), "/workflows/completed%2Fid/brief?format=markdown");
  assert.equal(run("downloadLink.download"), "", "server controls the attachment filename");
  assert.equal(run("downloadLink.clicked && downloadLink.removed"), true);
  assert.match(run("downloadNotice"), /download requested/);
  assert.doesNotMatch(run("downloadNotice"), /exported/);
  console.log("PM UI state checks passed: pinned trace, failed selection, frozen brief, late response, incomplete evidence, interrupted-run refresh, native download request.");
})().catch(error => {console.error(error); process.exitCode = 1;});
