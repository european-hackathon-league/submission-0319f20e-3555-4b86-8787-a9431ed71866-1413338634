import { describe, expect, it, vi } from "vitest";
import type { App } from "@modelcontextprotocol/ext-apps";
import { callTool, unpack } from "../src/shared/api";

describe("MCP result decoding", () => {
  it("reads unchanged Python dict text and structured results", () => {
    expect(unpack({ content: [{ type: "text", text: '{"key":"REQ-G60-US-001"}' }] })).toEqual({ key: "REQ-G60-US-001" });
    expect(unpack({ structuredContent: { id: "one" }, content: [] })).toEqual({ id: "one" });
    expect(unpack({ structuredContent: { result: [{ id: "one" }] } })).toEqual([{ id: "one" }]);
    expect(unpack({ content: [{ type: "text", text: '{"result":[{"id":"one"}]}' }] })).toEqual([{ id: "one" }]);
    expect(unpack({ structuredContent: { result: [], metadata: "keep" } })).toEqual({ result: [], metadata: "keep" });
  });
  it("never accepts structured data from an MCP error", () => {
    expect(() => unpack({ isError: true, structuredContent: { id: "fake" }, content: [{ type: "text", text: "API returned HTTP 403: inactive actor" }] })).toThrow("HTTP 403: inactive actor");
    expect(() => unpack({ content: [{ type: "text", text: "not JSON" }] })).toThrow("readable JSON");
  });
  it("forwards exact arguments once and preserves transport failures", async () => {
    const callServerTool = vi.fn().mockRejectedValue(new Error("connection closed"));
    await expect(callTool({ callServerTool } as unknown as App, "get_requirement", { requirement_id: "r1" })).rejects.toThrow("connection closed");
    expect(callServerTool).toHaveBeenCalledExactlyOnceWith({ name: "get_requirement", arguments: { requirement_id: "r1" } });
  });
});
