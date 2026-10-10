// Read-only checks for the G60 / US presentation path through the frontend proxy.
import assert from "node:assert/strict";

const origin = process.argv[2] || "http://127.0.0.1:3003";
const url = new URL(origin);
if (!["127.0.0.1", "localhost"].includes(url.hostname))
  throw new Error("Demo preflight must use a local frontend URL.");

async function get(path) {
  const response = await fetch(new URL(path, origin));
  if (!response.ok)
    throw new Error(`${path}: HTTP ${response.status}. Rebuild the current API and web services before the demo.`);
  return response;
}

await get("/g60/us");
const [health, actors, metrics, register] = await Promise.all([
  get("/api/backend/health").then((r) => r.json()),
  get("/api/backend/actors").then((r) => r.json()),
  get("/api/backend/metrics?vehicle=G60&market=US").then((r) => r.json()),
  get("/api/backend/requirements?vehicle=G60&market=US&limit=1&offset=0").then((r) => r.json()),
]);
assert.equal(health.status, "ok");
assert.ok(actors.some((actor) => actor.kind === "human" && actor.active && ["pm", "lead_pm"].includes(actor.role)), "No active PM reviewer");
assert.ok(metrics.counts.evidence > 0, "No G60 / US evidence");
assert.ok(register.total > 0 && register.items[0], "No G60 / US requirement");

const requirement = register.items[0];
const detail = await get(`/api/backend/requirements/${encodeURIComponent(requirement.id)}`).then((r) => r.json());
const version = detail.current_version;
assert.ok(version?.id && version.score?.id, "Requirement version or score missing");
const search = new URLSearchParams({ version_id: version.id, score_id: version.score.id, limit: "1" });
const trace = await get(`/api/backend/requirements/${encodeURIComponent(requirement.id)}/trace?${search}`).then((r) => r.json());
assert.ok(trace.evidence?.total > 0 && trace.evidence.items?.[0]?.location, "Exact source trace missing");

console.log(`PASS · ${metrics.counts.evidence} evidence records · ${register.total} requirements · ${requirement.key} trace and reviewer ready`);
