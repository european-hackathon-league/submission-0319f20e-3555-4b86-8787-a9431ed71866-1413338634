# Local MCP Apps smoke host

Run the synthetic Compose fixture with MCP on `127.0.0.1:18001`, including the
built scoring and trace HTML resources. From `mcp_server/ui`, run `npm ci`, then
`npm run smoke:host` (or `node smoke-host/serve.mjs`). Open
<http://127.0.0.1:18180/>. The default requirement ID is the local smoke fixture;
replace it with another requirement from that fixture when needed.

The host initializes the official MCP Client over Streamable HTTP, discovers
tools and resources, executes the selected read tool, and reads the linked HTML
resource. It connects the official AppBridge and PostMessageTransport before
loading a sandboxed `allow-scripts` iframe. Tool input and result are delivered
after the app's initialized notification. App tool calls go back through the
real MCP Client; writes therefore reach the local fixture database.

This is a development test harness for the trusted, locally built resources.
The opaque iframe origin is intentional: the SDK verifies the sender window,
and the app cannot access the host DOM. An injected CSP disallows network access
from the iframe. This host is not a general-purpose host for third-party apps.
It binds only to loopback, proxies `/mcp` locally, and needs no API keys or tunnel.

`?app=trace&requirement_id=<id>` selects a view and fixture on load. Host discovery,
initialization, delivery, and tool forwarding appear in the event log and in
`window.__mcpSmoke` for browser automation. `state.ready` means that input and
result were delivered after app initialization, not that every app interaction
has passed. Inspect rendered content and perform the intended actions as well.

Validation from `mcp_server/ui`:

```sh
npx tsc --noEmit -p smoke-host/tsconfig.json
npx vite build --config smoke-host/vite.config.mjs --outDir /tmp/bmw-mcp-smoke-host-build
```
