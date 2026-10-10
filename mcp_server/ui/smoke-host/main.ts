import { Client, StreamableHTTPClientTransport, type CallToolResult, type Tool } from "@modelcontextprotocol/client";
import { AppBridge, PostMessageTransport, getToolUiResourceUri, RESOURCE_MIME_TYPE } from "@modelcontextprotocol/ext-apps/app-bridge";

type SmokeEvent = { time: string; event: string; detail?: unknown };
type SmokeState = { connected: boolean; initialized: boolean; ready: boolean; toolCount: number; resourceCount: number; app?: string; requirementId?: string; error?: string };
const events: SmokeEvent[] = [];
const state: SmokeState = { connected: false, initialized: false, ready: false, toolCount: 0, resourceCount: 0 };
declare global { interface Window { __mcpSmoke: { events: SmokeEvent[]; state: SmokeState } } }
window.__mcpSmoke = { events, state };

function required<T extends HTMLElement>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Missing host element: ${selector}`);
  return element;
}
const form = required<HTMLFormElement>("#load-form");
const select = required<HTMLSelectElement>("#app-select");
const requirement = required<HTMLInputElement>("#requirement-id");
const button = required<HTMLButtonElement>("#load-app");
const status = required<HTMLParagraphElement>("#status");
const container = required<HTMLElement>("#app-container");
const eventLog = required<HTMLPreElement>("#event-log");
const parameters = new URLSearchParams(location.search);
if (parameters.get("app") === "trace") select.value = "trace";
if (parameters.get("requirement_id")) requirement.value = parameters.get("requirement_id")!;

function log(event: string, detail?: unknown) {
  events.push({ time: new Date().toISOString(), event, detail });
  if (events.length > 500) events.shift();
  eventLog.textContent = events.map((entry) => `${entry.time.slice(11, 23)} ${entry.event}${entry.detail === undefined ? "" : ` ${JSON.stringify(entry.detail)}`}`).join("\n");
  eventLog.scrollTop = eventLog.scrollHeight;
  console.info(`[MCP smoke] ${event}`, detail ?? "");
}
function fail(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  state.error = message;
  state.ready = false;
  status.dataset.error = "true";
  status.textContent = message;
  log("error", message);
}

const client = new Client({ name: "bmw-local-smoke-host", version: "0.1.0" }, {
  capabilities: { experimental: { "io.modelcontextprotocol/ui": { mimeTypes: [RESOURCE_MIME_TYPE] } } },
});
client.onerror = (error) => log("mcp:error", error.message);
let tools: Tool[] = [];
let activeBridge: AppBridge | undefined;
let loading = false;

async function forwardTool(name: string, args: Record<string, unknown> = {}, source = "app"): Promise<CallToolResult> {
  // Only discovered tools from this local MCP server are forwarded. AppBridge
  // handlers never synthesize a result or bypass the API's write safeguards.
  if (!tools.some((tool) => tool.name === name)) throw new Error(`Unknown MCP tool: ${name}`);
  log("tools/call", { name, arguments: args, source });
  const result = await client.callTool({ name, arguments: args });
  log("tools/result", { name, isError: result.isError === true, contentBlocks: result.content.length, source });
  return result;
}

function sandboxHtml(html: string): string {
  // These resources are self-contained output from this repository. No remote
  // scripts, fetches, frames, fonts, or form submissions are needed by the apps.
  const policy = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">`;
  if (!/<head(?:\s[^>]*)?>/i.test(html)) throw new Error("MCP HTML resource has no document head");
  return html.replace(/<head(?:\s[^>]*)?>/i, (head) => head + policy);
}

async function loadApp() {
  if (loading || !state.connected) return;
  loading = true;
  button.disabled = true;
  state.ready = false;
  state.initialized = false;
  delete state.error;
  status.dataset.error = "false";
  const name = select.value === "trace" ? "trace_requirement" : "get_requirement";
  const args = { requirement_id: requirement.value.trim() };
  state.app = select.value;
  state.requirementId = args.requirement_id;
  status.textContent = `Loading ${name}…`;
  try {
    if (!args.requirement_id) throw new Error("Enter a requirement ID from the local fixture.");
    if (activeBridge) {
      await activeBridge.close();
      activeBridge = undefined;
    }
    container.replaceChildren();
    const tool = tools.find((candidate) => candidate.name === name);
    if (!tool) throw new Error(`MCP server does not expose ${name}`);
    const uri = getToolUiResourceUri(tool);
    if (!uri) throw new Error(`${name} has no linked MCP App resource`);
    const [result, resource] = await Promise.all([
      forwardTool(name, args, "host"),
      client.readResource({ uri }),
    ]);
    const content = resource.contents.find((item) => item.uri === uri && "text" in item);
    if (!content || !("text" in content) || content.mimeType !== RESOURCE_MIME_TYPE) {
      throw new Error(`Expected ${RESOURCE_MIME_TYPE} text resource at ${uri}`);
    }
    log("resources/read", { uri, mimeType: content.mimeType, bytes: new TextEncoder().encode(content.text).length });
    const html = sandboxHtml(content.text);
    const iframe = document.createElement("iframe");
    iframe.id = "app-frame";
    iframe.title = select.value === "trace" ? "BMW trace explorer" : "BMW scoring and decision";
    iframe.setAttribute("sandbox", "allow-scripts");
    container.append(iframe);
    if (!iframe.contentWindow) throw new Error("Could not create the app iframe window");

    // Manual forwarding keeps every request visible in the smoke log while the
    // official bridge owns protocol negotiation and validates app messages.
    const bridge = new AppBridge(null, { name: "bmw-local-smoke-host", version: "0.1.0" }, {
      serverTools: {}, serverResources: {}, logging: {}, sandbox: { csp: {} },
    }, { hostContext: {
      theme: "light", displayMode: "inline", availableDisplayModes: ["inline"],
      locale: "en-US", timeZone: "Europe/Berlin", platform: "web",
      toolInfo: { tool }, containerDimensions: { width: container.clientWidth },
    } });
    activeBridge = bridge;
    bridge.oncalltool = (params) => forwardTool(params.name, params.arguments);
    bridge.onlistresources = (params) => client.listResources(params);
    bridge.onreadresource = (params) => client.readResource(params);
    bridge.onloggingmessage = (params) => log("app:log", params);
    bridge.onerror = (error) => log("bridge:error", error.message);
    bridge.onsizechange = ({ height }) => {
      if (height && Number.isFinite(height)) iframe.style.height = `${Math.max(360, Math.min(height, 20000))}px`;
    };
    let resolveReady!: () => void;
    let rejectReady!: (error: unknown) => void;
    const ready = new Promise<void>((resolve, reject) => { resolveReady = resolve; rejectReady = reject; });
    let initialized = false;
    bridge.oninitialized = () => {
      if (initialized) return;
      initialized = true;
      state.initialized = true;
      log("ui/notifications/initialized", { app: state.app });
      void (async () => {
        await bridge.sendToolInput({ arguments: args });
        log("ui/notifications/tool-input", { name, arguments: args });
        await bridge.sendToolResult(result);
        log("ui/notifications/tool-result", { name, isError: result.isError === true });
        state.ready = true;
        status.textContent = `${state.toolCount} tools · ${state.resourceCount} resources · ${select.value} app ready`;
      })().then(resolveReady, rejectReady);
    };
    const timeout = window.setTimeout(() => rejectReady(new Error("App did not initialize within 15 seconds")), 15000);
    try {
      // srcdoc starts only after the bridge is listening. The iframe has an
      // opaque origin; PostMessageTransport verifies event.source, not origin.
      await bridge.connect(new PostMessageTransport(iframe.contentWindow, iframe.contentWindow));
      iframe.srcdoc = html;
      await ready;
    } finally {
      window.clearTimeout(timeout);
    }
  } catch (error) {
    fail(error);
  } finally {
    loading = false;
    button.disabled = false;
  }
}

form.addEventListener("submit", (event) => { event.preventDefault(); void loadApp(); });
window.addEventListener("beforeunload", () => { void activeBridge?.close(); void client.close(); });

async function start() {
  button.disabled = true;
  await client.connect(new StreamableHTTPClientTransport(new URL("/mcp", location.origin)));
  log("mcp:initialized", client.getServerVersion());
  const [toolList, resourceList] = await Promise.all([client.listTools(), client.listResources()]);
  tools = toolList.tools;
  state.toolCount = tools.length;
  state.resourceCount = resourceList.resources.length;
  state.connected = true;
  log("discovery", { tools: tools.map((tool) => tool.name), resources: resourceList.resources.map((resource) => resource.uri) });
  button.disabled = false;
  await loadApp();
}
void start().catch(fail);
