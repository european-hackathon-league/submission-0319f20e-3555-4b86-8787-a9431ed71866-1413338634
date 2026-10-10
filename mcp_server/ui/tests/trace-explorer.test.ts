// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { parseTrace, safeSourceUrl, TraceExplorer, type Trace } from "../src/trace-explorer";

const version = (number = 1, requirement = "req-1") => ({
  id: `${requirement}-v${number}`, requirement_id: requirement, version: number, title: `Trace title ${number}`,
  statement: "Improve climate control discoverability.", customer_need: "A clear control while driving.",
  acceptance_criteria: [{ metric: "Task time", target: "5", unit: "seconds", basis: "PM assumption", source_ids: [] }],
  assumptions: ["PM target requires validation."], factors: { customer_impact: 4 }, actor: "Alex", rationale: "Customer feedback", created_at: "2026-10-01T10:00:00Z",
  finding_ids: ["finding-1"], score: {
    id: "score-latest", version_id: `${requirement}-v${number}`, total: 80, evidence_grade: "C", factors: { customer_impact: 4 }, weights: { customer_impact: 1 }, rubric_version: "customer-priority-v1", created_at: "2026-10-02",
    explanation: { contributions: { customer_impact: 80 }, formula: "sum(factor × weight × 20)", limitations: ["Sample counts are not market prevalence."] },
  },
});
const source = (reference = "https://example.com/research") => ({
  id: "source-1", title: "Customer feedback", kind: "web", vehicle: "G60", market: "US", reference, created_at: "2026-10-02", observed_at: null,
  metadata: { review_status: "unreviewed", web_evidence: { publication_date: "2026-09-01", retrieved_at: "2026-10-01T08:00:00Z", uncertainties: ["Applicability to the requested market is unverified."] } },
});
const evidence = (index: number, content = `Exact customer quote ${index}`) => ({
  id: `evidence-${index}`, source_id: "source-1", content, vehicle: "G60", market: "US", observed_at: null, created_at: "2026-10-02",
  location: { sheet: "G60 US", row: index + 2, column: "C" }, metadata: source().metadata,
});
function trace(options: { number?: number; requirement?: string; offset?: number; total?: number; reference?: string; content?: string } = {}): Trace {
  const { number = 1, requirement = "req-1", offset = 0, total = 13 } = options;
  const items = Array.from({ length: Math.max(0, Math.min(12, total - offset)) }, (_, index) => evidence(offset + index, options.content));
  return {
    requirement: { id: requirement, key: requirement === "req-1" ? "REQ-G60-US-001" : "REQ-G60-US-002", vehicle: "G60", market: "US", topic: "climate", status: "needs_review", current_version_id: `${requirement}-v2`, approved_version_id: `${requirement}-v1`, approved_score_id: "score-approved" },
    version: version(number, requirement), findings: [{ id: "finding-1", summary: "Climate control needs clearer entry points.", kind: "need", topic: "climate", confidence: .8, created_at: "2026-10-02", evidence_ids: Array.from({ length: total }, (_, i) => `evidence-${i}`), conflicting_evidence_ids: [] }],
    sources: [source(options.reference)], evidence: { items, offset, total, limit: 12 },
    decisions: [{ id: "decision-1", version_id: `${requirement}-v1`, score_id: "score-approved", action: "approve", actor: "Alex", rationale: "Reviewed the evidence", created_at: "2026-10-01" }],
  };
}
function mounted(request: (name: string, args: Record<string, unknown>) => Promise<unknown>, openLink?: (url: string) => Promise<unknown>) {
  const root = document.createElement("main");
  root.className = "trace-app";
  document.body.append(root);
  const explorer = new TraceExplorer(root, request, openLink);
  explorer.setConnected();
  return { root, explorer };
}
function getButton(root: HTMLElement, name: string): HTMLButtonElement {
  const result = [...root.querySelectorAll("button")].find((item) => item.textContent === name);
  if (!result) throw new Error(`Missing button ${name}`);
  return result;
}
function expand(root: HTMLElement, title: string): HTMLDetailsElement {
  const node = [...root.querySelectorAll("details")].find((item) => item.querySelector(":scope > summary")?.textContent?.startsWith(title));
  if (!node) throw new Error(`Missing details ${title}`);
  node.open = true;
  node.dispatchEvent(new Event("toggle"));
  return node;
}
async function ready(root: HTMLElement) {
  await vi.waitFor(() => expect(root.querySelector<HTMLSelectElement>("#trace-version")?.disabled).toBe(false));
}
afterEach(() => { document.body.replaceChildren(); vi.restoreAllMocks(); });

describe("trace explorer", () => {
  it("uses the readable key and sorts history newest first while keeping an older version selected across pages", async () => {
    const request = vi.fn(async (name: string, args: Record<string, unknown>) => name === "get_requirement_versions"
      ? [version(1), version(2)] : trace({ offset: Number(args.offset) }));
    const { root, explorer } = mounted(request);
    explorer.receive(trace());
    await ready(root);
    expect(root.querySelector("h1")?.textContent).toBe("REQ-G60-US-001");
    const select = root.querySelector<HTMLSelectElement>("#trace-version")!;
    expect([...select.options].map((option) => option.value)).toEqual(["req-1-v2", "req-1-v1"]);
    expect(select.value).toBe("req-1-v1");
    getButton(root, "Next evidence").click();
    await vi.waitFor(() => expect(root.textContent).toContain("Evidence 13–13 of 13"));
    expect(request).toHaveBeenCalledWith("trace_requirement", { requirement_id: "req-1", version_id: "req-1-v1", limit: 12, offset: 12 });
    expect(root.querySelector<HTMLSelectElement>("#trace-version")?.value).toBe("req-1-v1");
    expect(getButton(root, "Next evidence").disabled).toBe(true);
    getButton(root, "Previous evidence").click();
    await vi.waitFor(() => expect(root.textContent).toContain("Evidence 1–12 of 13"));
    expect(request).toHaveBeenLastCalledWith("trace_requirement", { requirement_id: "req-1", version_id: "req-1-v1", limit: 12, offset: 0 });
  });

  it("drops a late page response after the host selects another requirement", async () => {
    let resolvePage!: (value: unknown) => void;
    const request = vi.fn((name: string, args: Record<string, unknown>) => name === "get_requirement_versions"
      ? Promise.resolve([version(1, String(args.requirement_id)), version(2, String(args.requirement_id))])
      : new Promise((resolve) => { resolvePage = resolve; }));
    const { root, explorer } = mounted(request);
    explorer.receive(trace()); await ready(root);
    getButton(root, "Next evidence").click();
    explorer.receive(trace({ requirement: "req-2", number: 2 })); await ready(root);
    resolvePage(trace({ offset: 12 }));
    await Promise.resolve();
    expect(root.querySelector("h1")?.textContent).toBe("REQ-G60-US-002");
    expect(root.querySelector<HTMLSelectElement>("#trace-version")?.value).toBe("req-2-v2");
    expect(root.textContent).toContain("Evidence 1–12 of 13");
  });

  it("does not silently swap a selected version when the response is mismatched", async () => {
    const request = vi.fn(async (name: string) => name === "get_requirement_versions" ? [version(1), version(2)] : trace({ number: 2, offset: 12 }));
    const { root, explorer } = mounted(request);
    explorer.receive(trace()); await ready(root);
    getButton(root, "Next evidence").click();
    await vi.waitFor(() => expect(root.querySelector('[role="alert"]')?.textContent).toContain("does not match the selected version"));
    expect(root.querySelector<HTMLSelectElement>("#trace-version")?.value).toBe("req-1-v1");
    expect(root.textContent).toContain("Showing the previous trace");
  });

  it("keeps quotes inert, preserves exact locations and distinguishes all recorded dates", async () => {
    const quote = '<img src=x onerror="alert(1)">\nExact text with  two spaces.';
    const request = vi.fn(async (name: string) => name === "get_requirement_versions" ? [version(1)] : source("javascript:alert(1)"));
    const { root, explorer } = mounted(request);
    explorer.receive(trace({ total: 1, content: quote, reference: "javascript:alert(1)" })); await ready(root);
    expand(root, "Supports ·");
    expect(root.querySelector("blockquote")?.textContent).toBe(quote);
    expect(root.querySelector("img")).toBeNull();
    expect(root.textContent).toContain("G60 US");
    expect(root.textContent).toContain("Observation date is unknown");
    expect(root.textContent).toContain("2026-09-01");
    expect(root.textContent).toContain("2026-10-01T08:00:00Z");
    expect(root.textContent).toContain("Applicability to the requested market is unverified.");
    expand(root, "Source ·");
    await vi.waitFor(() => expect(request).toHaveBeenCalledWith("get_source", { source_id: "source-1" }));
    expect(root.querySelector("a")).toBeNull();
    expect(root.textContent).toContain("javascript:alert(1)");
  });

  it("shows a denied source read with explicit retry and opens a valid link through the host", async () => {
    let denied = true;
    const openLink = vi.fn(async () => ({}));
    const request = vi.fn(async (name: string) => {
      if (name === "get_requirement_versions") return [version(1)];
      if (denied) throw new Error("API returned HTTP 403: inactive actor");
      return source();
    });
    const { root, explorer } = mounted(request, openLink);
    explorer.receive(trace({ total: 1 })); await ready(root);
    expand(root, "Supports ·"); expand(root, "Source ·");
    await vi.waitFor(() => expect(root.querySelector('[role="alert"]')?.textContent).toContain("Access denied"));
    denied = false;
    getButton(root, "Retry source").click();
    await vi.waitFor(() => expect(root.querySelector('[role="alert"]')).toBeNull());
    root.querySelector<HTMLAnchorElement>("a")!.click();
    expect(openLink).toHaveBeenCalledWith("https://example.com/research");
  });

  it("reads audit history with the server next_after cursor and only on demand", async () => {
    const request = vi.fn(async (name: string, args: Record<string, unknown>) => {
      if (name === "get_requirement_versions") return [version(1)];
      return args.after === 0
        ? { items: Array.from({ length: 10 }, (_, i) => ({ sequence: i + 32, entity_id: "req-1", action: "requirement.scored", actor: "Alex", rationale: "Reviewed", after_state: { id: "score-approved", total: 78 } })), next_after: 41 }
        : { items: [], next_after: 41 };
    });
    const { root, explorer } = mounted(request);
    explorer.receive(trace()); await ready(root);
    expect(request.mock.calls.map(([name]) => name)).toEqual(["get_requirement_versions"]);
    expand(root, "Requirement audit history");
    await vi.waitFor(() => expect(getButton(root, "Load more history").disabled).toBe(false));
    expect(request).toHaveBeenCalledWith("list_audit", { entity_id: "req-1", after: 0, limit: 10 });
    getButton(root, "Load more history").click();
    await vi.waitFor(() => expect(getButton(root, "Check for newer events").disabled).toBe(false));
    expect(request).toHaveBeenLastCalledWith("list_audit", { entity_id: "req-1", after: 41, limit: 10 });
    expect(root.textContent).toContain("score-approved");
  });

  it("labels the latest version score separately from the exact approved decision score", async () => {
    const { root, explorer } = mounted(async () => [version(1), version(2)]);
    explorer.receive(trace()); await ready(root);
    expect(root.textContent).toContain("The approved baseline is tied to a different score");
    expect(root.textContent).toContain("score-approved");
    expect(root.textContent).toContain("score-latest");
    expect(root.textContent).toContain("Version 2");
    expect(root.textContent).toContain("Version 1");
  });

  it("handles empty pages, malformed host data and connection ordering", async () => {
    const request = vi.fn(async () => [version(1)]);
    const root = document.createElement("main"); document.body.append(root);
    const explorer = new TraceExplorer(root, request);
    explorer.receive(trace({ total: 0 }));
    expect(request).not.toHaveBeenCalled();
    explorer.setConnected(); await ready(root);
    expect(getButton(root, "Next evidence").disabled).toBe(true);
    expect(root.textContent).toContain("No evidence on this page");
    explorer.receive({ requirement: { id: "broken" } });
    expect(root.querySelector('[role="alert"]')?.textContent).toContain("incomplete requirement trace");
    expect(root.querySelector("h1")?.textContent).toBe("REQ-G60-US-001");
  });
});

describe("trace guards", () => {
  it("only permits absolute http/https source URLs without embedded credentials", () => {
    for (const url of ["javascript:alert(1)", "data:text/html,hello", "file:///tmp/a", "/sources/1", "https://user:secret@example.com/"]) expect(safeSourceUrl(url)).toBeNull();
    expect(safeSourceUrl("https://example.com/a#page=2")).toBe("https://example.com/a#page=2");
    expect(safeSourceUrl("http://example.com/")).toBe("http://example.com/");
  });
  it("rejects cross-requirement data and invalid evidence pagination", () => {
    expect(() => parseTrace({ ...trace(), version: version(1, "another-requirement") })).toThrow("incomplete");
    expect(() => parseTrace({ ...trace(), evidence: { items: [], total: 5, limit: 0, offset: -1 } })).toThrow("incomplete");
  });
});
