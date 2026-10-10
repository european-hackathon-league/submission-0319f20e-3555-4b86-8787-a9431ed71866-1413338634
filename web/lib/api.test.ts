import { afterEach, describe, expect, it } from "bun:test";
import { allPages, api, canAct, pinnedTrace, write } from "./api";
import { csvCell, reqif } from "./export";
import type { Detail } from "./types";
const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
});
function mockFetch(
  fn: (url: string, init?: RequestInit) => Response | Promise<Response>,
) {
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    Promise.resolve(fn(String(input), init))) as typeof fetch;
}
describe("API boundary", () => {
  it("loads every page rather than silently truncating the register", async () => {
    mockFetch((url) =>
      Response.json(
        url.includes("offset=0")
          ? { items: [{ id: "a" }], total: 2 }
          : { items: [{ id: "b" }], total: 2 },
      ),
    );
    expect(await allPages("/requirements?vehicle=G60")).toEqual([
      { id: "a" },
      { id: "b" },
    ]);
  });
  it("rejects incomplete pagination", async () => {
    mockFetch((url) =>
      Response.json(
        url.includes("offset=0")
          ? { items: [{ id: "a" }], total: 2 }
          : { items: [], total: 2 },
      ),
    );
    await expect(allPages("/requirements")).rejects.toThrow("incomplete");
  });
  it("rejects duplicate records if the list changes between pages", async () => {
    mockFetch(() => Response.json({ items: [{ id: "a" }], total: 2 }));
    await expect(allPages("/requirements")).rejects.toThrow("Records changed");
  });
  it("does not retry a stale decision write", async () => {
    let calls = 0;
    mockFetch(() => {
      calls++;
      return Response.json({ detail: "Score changed" }, { status: 409 });
    });
    await expect(write("/requirements/id/decisions", {})).rejects.toThrow(
      "Reload and review",
    );
    expect(calls).toBe(1);
  });
  it("pins every trace page to both the visible version and score", async () => {
    let path = "";
    mockFetch((url) => {
      path = url;
      return Response.json({});
    });
    await pinnedTrace("req", "version-1", "score-2", 40);
    expect(path).toContain("version_id=version-1");
    expect(path).toContain("score_id=score-2");
    expect(path).toContain("offset=40");
  });
  it("surfaces non-JSON service failures", async () => {
    mockFetch(() => new Response("upstream unavailable", { status: 502 }));
    await expect(api("/health")).rejects.toThrow("upstream unavailable");
  });
});
describe("declared actor controls", () => {
  it("disables every decision for AI, inactive actors and viewers", () => {
    for (const actor of [
      { kind: "ai", role: "ai", active: 1 },
      { kind: "human", role: "pm", active: 0 },
      { kind: "human", role: "viewer", active: 1 },
    ])
      for (const action of [
        "approve",
        "reject",
        "postpone",
        "challenge",
        "edit",
        "score",
      ])
        expect(canAct(actor, action)).toBe(false);
  });
  it("separates PM approval and lead-PM rubric changes", () => {
    expect(canAct({ kind: "human", role: "pm", active: 1 }, "approve")).toBe(
      true,
    );
    expect(
      canAct({ kind: "human", role: "analyst", active: 1 }, "approve"),
    ).toBe(false);
    expect(
      canAct({ kind: "human", role: "analyst", active: 1 }, "challenge"),
    ).toBe(true);
    expect(canAct({ kind: "human", role: "pm", active: 1 }, "score")).toBe(
      false,
    );
  });
});
describe("portable exports", () => {
  it("neutralizes spreadsheet formula injection and escapes quotes", () => {
    expect(csvCell('=WEBSERVICE("https://example.test")')).toStartWith("\"'=");
    expect(csvCell(" \t@SUM(A1)")).toStartWith("\"'");
    expect(csvCell('text,"quoted"')).toBe('"text,""quoted"""');
  });
  it("exports the approved snapshot even when a newer proposal exists", () => {
    const req = {
      id: "r1",
      key: "REQ-QA-001",
      current_version: { statement: "UNAPPROVED" },
      approved_version: {
        id: "v1",
        title: "A & B",
        statement: "APPROVED <target>",
        created_at: "2026-10-10T00:00:00Z",
        acceptance_criteria: [],
        score: { id: "s1", total: 75, evidence_grade: "B" },
      },
    } as unknown as Detail;
    const xml = reqif([req], "2026-10-10T00:00:00Z");
    expect(xml).toContain("APPROVED &lt;target&gt;");
    expect(xml).not.toContain("UNAPPROVED");
    expect(xml).toContain("A &amp; B");
    expect(xml).toContain("version_id=v1&amp;score_id=s1");
    expect(xml).toContain("SPECIFICATION-TYPE-REF");
  });
});

describe("same-origin proxy", () => {
  it("accepts the browser Host when Next normalizes its internal origin", async () => {
    const { NextRequest } = await import("next/server");
    const { POST } = await import("../app/api/backend/[...path]/route");
    let forwarded = "";
    mockFetch((_url, init) => {
      forwarded = new TextDecoder().decode(init?.body as ArrayBuffer);
      return Response.json({ id: "workflow" }, { status: 201 });
    });
    const response = await POST(
      new NextRequest("http://localhost:3000/api/backend/workflows", {
        method: "POST",
        headers: {
          Host: "127.0.0.1:3003",
          Origin: "http://127.0.0.1:3003",
          "Content-Type": "application/json",
        },
        body: '{"kind":"initial"}',
      }),
      { params: Promise.resolve({ path: ["workflows"] }) },
    );
    expect(response.status).toBe(201);
    expect(forwarded).toBe('{"kind":"initial"}');
  });
  it("rejects a foreign browser origin before forwarding a write", async () => {
    const { NextRequest } = await import("next/server");
    const { POST } = await import("../app/api/backend/[...path]/route");
    let calls = 0;
    mockFetch(() => {
      calls++;
      return Response.json({});
    });
    const response = await POST(
      new NextRequest("http://localhost:3000/api/backend/workflows", {
        method: "POST",
        headers: {
          Host: "127.0.0.1:3003",
          Origin: "https://unrelated.example",
        },
        body: "{}",
      }),
      { params: Promise.resolve({ path: ["workflows"] }) },
    );
    expect(response.status).toBe(403);
    expect(calls).toBe(0);
  });
});
