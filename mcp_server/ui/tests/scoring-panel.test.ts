// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { App } from "@modelcontextprotocol/ext-apps";
import { mountScoringPanel } from "../src/scoring-panel";

const weights = { customer_impact: .35, market_relevance: .25, strategic_fit: .2, differentiation: .1, feasibility: .1 };
const factors = { customer_impact: 4, market_relevance: 3, strategic_fit: 4, differentiation: 2, feasibility: 3 };
function requirement(version = 1, scoreId = `s${version}`, changes = {}) {
  return {
    id: "r1", key: "REQ-G60-US-001", vehicle: "G60", market: "US", status: "proposed", current_version_id: `v${version}`,
    approved_version_id: null, approved_score_id: null, approved_version: null, needs_review: false, reviews: [],
    current_version: { id: `v${version}`, requirement_id: "r1", version, title: "Improve cabin controls", statement: "Make controls easier to find.", customer_need: "Quick access", acceptance_criteria: [{ metric: "Task time", target: 5, unit: "s", basis: "PM assumption" }], assumptions: [], factors,
      score: { id: scoreId, version_id: `v${version}`, weights, total: 69, evidence_grade: "C", explanation: { limitations: ["PM judgment"] } },
    }, ...changes,
  };
}
function result(value: unknown) { return { content: [{ type: "text", text: JSON.stringify(value) }] }; }
function failure(text: string) { return { isError: true, content: [{ type: "text", text }] }; }
function setup(initial = requirement()) {
  const host = { callServerTool: vi.fn(), updateModelContext: vi.fn().mockResolvedValue({}), connect: vi.fn().mockResolvedValue(undefined), getHostContext: () => ({ theme: "light" }), ontoolresult: undefined as unknown, onhostcontextchanged: undefined as unknown };
  const root = document.createElement("main"); document.body.append(root);
  const panel = mountScoringPanel(host as unknown as App, root);
  (host.ontoolresult as (value: unknown) => void)(result(initial));
  return { host, root, panel };
}
function input(id: string, value: string) {
  const node = document.getElementById(id) as HTMLInputElement;
  node.value = value; node.dispatchEvent(new Event("input", { bubbles: true })); return node;
}
function button(action: string) { return document.querySelector<HTMLButtonElement>(`[data-action="${action}"]`)!; }
function credentials() { input("actor", "Alex Muller"); input("rationale", "PM reviewed customer priorities."); }
function confirmSavedReview() {
  const node = document.getElementById("reviewed-saved-state") as HTMLInputElement;
  node.checked = true; node.dispatchEvent(new Event("change", { bubbles: true }));
}
async function settled() { await vi.waitFor(() => expect(document.querySelector('[aria-busy="true"]')).toBeNull()); }
beforeEach(() => { document.body.replaceChildren(); });

describe("scoring and decision transitions", () => {
  it("uses text nodes for untrusted text and requires human actor and rationale", () => {
    const data = requirement(); data.current_version.title = '<img src=x onerror="alert(1)">';
    const { root } = setup(data);
    expect(root.querySelector("img")).toBeNull(); expect(root.textContent).toContain("<img");
    expect(button("decide").disabled).toBe(true);
    input("actor", " AI:openai "); input("rationale", "Reviewed");
    expect(button("decide").disabled).toBe(true); expect(root.textContent).toContain("human actor");
    input("actor", "System:reference"); expect(button("decide").disabled).toBe(true);
    input("actor", "Alex Muller"); expect(button("decide").disabled).toBe(false);
    input("rationale", "   "); expect(button("decide").disabled).toBe(true);
  });
  it("blocks dirty decisions and all writes when weights do not total one", () => {
    const { host, root } = setup(); credentials();
    input("factor-customer_impact", "4.5");
    expect(root.textContent).toContain("Preview · unsaved"); expect(button("decide").disabled).toBe(true); expect(button("save-factors").disabled).toBe(false);
    input("weight-customer_impact", ".4");
    expect(button("save-factors").disabled).toBe(true); expect(button("save-weights").disabled).toBe(true);
    button("decide").click(); expect(host.callServerTool).not.toHaveBeenCalled();
    button("discard").click(); expect(button("decide").disabled).toBe(false);
  });
  it("saves factors and weights as separate writes, then decides using freshly reloaded IDs", async () => {
    const { host } = setup(); credentials();
    input("factor-customer_impact", "4.5"); input("weight-customer_impact", ".4"); input("weight-market_relevance", ".2");
    const second = requirement(2); second.current_version.factors = { ...factors, customer_impact: 4.5 };
    host.callServerTool.mockResolvedValueOnce(result(second)).mockResolvedValueOnce(result(second));
    button("save-factors").click(); await settled();
    expect(host.callServerTool.mock.calls[0][0]).toEqual({ name: "edit_requirement", arguments: { requirement_id: "r1", expected_version_id: "v1", actor: "Alex Muller", rationale: "PM reviewed customer priorities.", factors: { ...factors, customer_impact: 4.5 } } });
    expect(host.callServerTool.mock.calls[1][0]).toEqual({ name: "get_requirement", arguments: { requirement_id: "r1" } });
    expect(button("save-weights").disabled).toBe(false); expect(button("decide").disabled).toBe(true);
    const third = requirement(2, "s3"); third.current_version.factors = second.current_version.factors;
    third.current_version.score.weights = { ...weights, customer_impact: .4, market_relevance: .2 };
    host.callServerTool.mockResolvedValueOnce(result(third.current_version.score)).mockResolvedValueOnce(result(third));
    button("save-weights").click(); await settled();
    expect(host.callServerTool.mock.calls[2][0]).toEqual({ name: "score_requirement", arguments: { requirement_id: "r1", expected_version_id: "v2", expected_score_id: "s2", actor: "Alex Muller", rationale: "PM reviewed customer priorities.", weights: third.current_version.score.weights } });
    expect(host.callServerTool.mock.calls.filter(([request]) => request.name === "decide_requirement")).toHaveLength(0);
    expect(button("decide").disabled).toBe(true); confirmSavedReview();
    host.callServerTool.mockResolvedValueOnce(result({ decision_id: "d1", requirement: third })).mockResolvedValueOnce(result(third));
    button("decide").click(); await settled();
    expect(host.callServerTool.mock.calls[4][0]).toEqual({ name: "decide_requirement", arguments: { requirement_id: "r1", version_id: "v2", score_id: "s3", action: "approve", actor: "Alex Muller", rationale: "PM reviewed customer priorities." } });
    expect(host.updateModelContext).toHaveBeenCalledOnce();
    expect(host.updateModelContext.mock.calls[0][0].content[0].text).toContain('"action":"approve"');
  });
  it("reloads a stale proposal once, clears its preview, and never retries the write", async () => {
    const { host, root } = setup(); credentials(); input("factor-customer_impact", "4.5");
    host.callServerTool.mockResolvedValueOnce(failure("API returned HTTP 409: Requirement changed; reload before editing")).mockResolvedValueOnce(result(requirement(3)));
    button("save-factors").click(); await settled();
    expect(host.callServerTool).toHaveBeenCalledTimes(2); expect(root.textContent).toContain("nothing was retried"); expect(root.textContent).toContain("version 1 → 3");
    expect((document.getElementById("factor-customer_impact") as HTMLInputElement).value).toBe("4");
    expect(button("decide").disabled).toBe(true);
  });
  it("keeps rejected input after 403 and blocks repeated writes after a transport failure", async () => {
    const { host, root } = setup(); credentials(); input("factor-customer_impact", "4.5");
    host.callServerTool.mockResolvedValueOnce(failure("API returned HTTP 403: actor is inactive"));
    button("save-factors").click(); await settled();
    expect(root.textContent).toContain("Permission denied"); expect(button("save-factors").disabled).toBe(false);
    host.callServerTool.mockRejectedValueOnce(new Error("connection closed"));
    button("save-factors").click(); await settled();
    expect(host.callServerTool).toHaveBeenCalledTimes(2); expect(root.textContent).toContain("result of this write is unknown");
    expect(button("save-factors").disabled).toBe(true); expect(button("decide").disabled).toBe(true); expect(button("reload").disabled).toBe(false);
  });
  it("distinguishes a recorded change from a failed reload and blocks duplicate clicks while busy", async () => {
    const { host, root } = setup(); credentials(); input("factor-customer_impact", "4.5");
    let finish: (value: unknown) => void = () => undefined;
    host.callServerTool.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; })).mockRejectedValueOnce(new Error("read timed out"));
    button("save-factors").click(); button("save-factors").click(); expect(host.callServerTool).toHaveBeenCalledOnce();
    expect(button("decide").disabled).toBe(true); finish(result(requirement(2))); await settled();
    expect(root.textContent).toContain("change was recorded"); expect(button("save-factors").disabled).toBe(true);
  });
  it("shows the approved baseline and disables decisions without a score", () => {
    const current = requirement(2); const baseline = requirement(1).current_version;
    const { root } = setup({ ...current, approved_version: baseline, approved_version_id: "v1", approved_score_id: "s1", needs_review: true, reviews: [{ status: "open", reason: "Customer evidence changed" }], current_version: { ...current.current_version, score: null } } as unknown as ReturnType<typeof requirement>);
    credentials(); expect(button("decide").disabled).toBe(true); expect(root.textContent).toContain("Approved baseline: version 1"); expect(root.textContent).toContain("Customer evidence changed");
    expect(document.getElementById("priority-score")?.textContent).toContain("—");
  });
  it.each(["reject", "postpone", "challenge"])("sends an explicit %s decision and reports it even if refresh fails", async (selectedAction) => {
    const { host, root } = setup(); credentials();
    const select = document.getElementById("decision-action") as HTMLSelectElement;
    select.value = selectedAction; select.dispatchEvent(new Event("change", { bubbles: true }));
    host.callServerTool.mockResolvedValueOnce(result({ decision_id: "d1" })).mockRejectedValueOnce(new Error("refresh timed out"));
    button("decide").click(); await settled();
    expect(host.callServerTool.mock.calls[0][0].arguments.action).toBe(selectedAction);
    expect(host.updateModelContext).toHaveBeenCalledOnce();
    expect(root.textContent).toContain("decision was recorded"); expect(button("decide").disabled).toBe(true);
  });
  it("registers the tool-result handler before connecting and adopts host theme", async () => {
    const { host, panel } = setup();
    host.connect.mockImplementationOnce(async () => { expect(host.ontoolresult).toBeTypeOf("function"); });
    await panel.connect();
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
