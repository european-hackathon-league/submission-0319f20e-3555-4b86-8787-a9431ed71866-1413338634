import type { App } from "@modelcontextprotocol/ext-apps";

function listEnvelope(value: unknown): unknown {
  // The Python SDK may wrap list returns for object-only structuredContent.
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const envelope = value as Record<string, unknown>;
    if (Object.keys(envelope).length === 1 && Array.isArray(envelope.result)) return envelope.result;
  }
  return value;
}

/** Preserve server errors and decode the unchanged MCP tool result in either encoding. */
export function unpack(result: unknown): unknown {
  if (!result || typeof result !== "object") throw new Error("The host returned an invalid tool response.");
  const payload = result as Record<string, unknown>;
  const texts = Array.isArray(payload.content)
    ? payload.content.flatMap((item: unknown) => {
        if (!item || typeof item !== "object") return [];
        const block = item as Record<string, unknown>;
        return block.type === "text" && typeof block.text === "string" ? [block.text] : [];
      })
    : [];
  if (payload.isError === true) throw new Error(texts.join("\n") || "The server rejected this request.");
  if (payload.structuredContent !== undefined && payload.structuredContent !== null) {
    return listEnvelope(payload.structuredContent);
  }
  for (const text of texts) {
    try { return listEnvelope(JSON.parse(text)); } catch { /* Other content blocks may contain the JSON. */ }
  }
  throw new Error("The tool response did not contain readable JSON data.");
}

export async function callTool<T>(app: App, name: string, args: Record<string, unknown>): Promise<T> {
  return unpack(await app.callServerTool({ name, arguments: args })) as T;
}
