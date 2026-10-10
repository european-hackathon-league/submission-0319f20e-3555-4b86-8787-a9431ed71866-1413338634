// Test only via the frontend proxy, in a dedicated synthetic scope. Never decide real BMW requirements.
import assert from "node:assert/strict";
const origin = process.argv[2] || "http://127.0.0.1:3003";
if (!["127.0.0.1", "localhost"].includes(new URL(origin).hostname))
  throw new Error("Use an isolated local workspace.");
const vehicle = `WEBQA${Date.now().toString(36).toUpperCase()}`;
const scope = { vehicle, market: "US" };
const actor = "PM";
async function call(path, body, method = "POST", expected = 200) {
  const r = await fetch(`${origin}/api/backend${path}`, {
    method: body === undefined ? "GET" : method,
    headers: body
      ? { "Content-Type": "application/json", Origin: origin }
      : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json();
  assert.equal(r.status, expected, JSON.stringify(data));
  return data;
}
await call(
  "/imports/records",
  {
    ...scope,
    title: "Synthetic frontend verification",
    kind: "feedback",
    reference: "frontend-qa",
    actor,
    records: [
      {
        ...scope,
        content:
          "Synthetic record: the seat is uncomfortable on long journeys.",
        location: { sheet: "QA", row: 2 },
        metadata: {
          topic: "comfort",
          sentiment: "negative",
          provenance: "QA A",
        },
        observed_at: "2026-10-01",
      },
      {
        ...scope,
        content: "Synthetic record: I want more comfortable seats.",
        location: { sheet: "QA", row: 3 },
        metadata: {
          topic: "comfort",
          sentiment: "negative",
          provenance: "QA B",
        },
        observed_at: "2026-10-02",
      },
    ],
  },
  "POST",
  201,
);
// Exercise the multipart and preserved-original proxy paths as well.
const upload = new FormData();
upload.set(
  "file",
  new Blob(["Feedback,Date\nSynthetic neutral QA record,2026-10-01\n"], {
    type: "text/csv",
  }),
  "frontend-qa.csv",
);
for (const [key, value] of Object.entries({
  ...scope,
  actor,
  kind: "feedback",
}))
  upload.set(key, value);
const uploaded = await fetch(`${origin}/api/backend/imports/files`, {
  method: "POST",
  headers: { Origin: origin },
  body: upload,
});
assert.equal(uploaded.status, 201, await uploaded.clone().text());
const uploadedSource = await uploaded.json();
assert.equal(uploadedSource.record_count, 1);
const sourceList = await call(`/sources?vehicle=${vehicle}&market=US`);
const archivedSource = sourceList.find((s) => s.original_path);
assert.ok(archivedSource);
const originalDownload = await fetch(
  `${origin}/api/backend/sources/${archivedSource.id}/original`,
);
assert.equal(originalDownload.status, 200);
assert.ok(
  (await originalDownload.text()).includes("Synthetic neutral QA record"),
);
let flow = await call(
  "/workflows",
  {
    ...scope,
    actor,
    kind: "initial",
    provider: "deterministic",
    request_key: crypto.randomUUID(),
  },
  "POST",
  201,
);
flow = await call(`/workflows/${flow.id}/run`, {
  actor,
  expected_revision: flow.revision,
});
assert.equal(flow.status, "awaiting_review");
const register = await call(`/requirements?vehicle=${vehicle}&market=US`);
assert.ok(register.items.length);
for (const row of register.items) {
  let detail = await call(`/requirements/${row.id}`);
  const original = detail.current_version;
  const trace = await call(
    `/requirements/${row.id}/trace?version_id=${original.id}&score_id=${original.score.id}&limit=1`,
  );
  assert.equal(trace.evidence.items[0].location.sheet, "QA");
  detail = await call(
    `/requirements/${row.id}`,
    {
      actor,
      expected_version_id: original.id,
      title: "Synthetic frontend seat comfort validation",
      rationale: "Synthetic UI integration check",
    },
    "PATCH",
  );
  assert.notEqual(detail.current_version.id, original.id);
  await call(
    `/requirements/${row.id}/decisions`,
    {
      actor,
      version_id: original.id,
      score_id: original.score.id,
      action: "approve",
      rationale: "Stale synthetic request",
    },
    "POST",
    409,
  );
  const v = detail.current_version;
  await call(
    `/requirements/${row.id}/decisions`,
    {
      actor,
      version_id: v.id,
      score_id: v.score.id,
      action: "approve",
      rationale:
        "Synthetic test only; exact trace and PM assumptions reviewed.",
    },
    "POST",
    201,
  );
}
flow = await call(`/workflows/${flow.id}`);
flow = await call(`/workflows/${flow.id}/complete`, {
  actor,
  expected_revision: flow.revision,
  rationale: "Synthetic frontend verification complete.",
});
assert.equal(flow.status, "completed");
const frozen = await call(`/workflows/${flow.id}/brief`);
assert.equal(frozen.snapshot, "completed");
const exported = await fetch(
  `${origin}/api/backend/workflows/${flow.id}/brief?format=markdown`,
);
assert.equal(exported.status, 200);
assert.ok(exported.headers.get("content-disposition")?.includes("attachment"));
assert.ok(
  (await exported.text()).includes(
    "Synthetic frontend seat comfort validation",
  ),
);
const r = register.items[0];
const before = await call(`/requirements/${r.id}`);
await call(
  `/requirements/${r.id}`,
  {
    actor,
    expected_version_id: before.current_version.id,
    statement:
      before.current_version.statement + " Additional synthetic validation.",
    rationale: "Verify approved baseline preservation",
  },
  "PATCH",
);
const after = await call(`/requirements/${r.id}`);
assert.equal(after.approved_version.id, before.approved_version.id);
assert.notEqual(after.current_version.id, after.approved_version.id);
const stillFrozen = await call(`/workflows/${flow.id}/brief`);
assert.deepEqual(stillFrozen.requirements, frozen.requirements);
const audit = await call(`/audit?entity_id=${r.id}`);
assert.ok(audit.items.some((e) => e.action === "requirement.approve"));
console.log(
  JSON.stringify(
    {
      result: "PASS",
      scope,
      workflow: flow.id,
      requirement: r.id,
      checks: [
        "proxy import",
        "multipart upload and original download",
        "initial workflow",
        "exact source location",
        "edit and re-score",
        "stale decision 409",
        "approval",
        "completion",
        "Markdown attachment",
        "baseline preserved",
        "frozen brief unchanged",
        "audit event",
      ],
    },
    null,
    2,
  ),
);
