// Local preview host: the widget reports its fixed frame height here, as an MCP host would receive it.
const frame = document.querySelector<HTMLIFrameElement>("#frame")!;
const host = document.querySelector<HTMLDivElement>("#host")!;
const size = document.querySelector<HTMLSpanElement>("#size")!;
const controls = { app: document.querySelector<HTMLSelectElement>("#app")!, width: document.querySelector<HTMLSelectElement>("#width")!, theme: document.querySelector<HTMLSelectElement>("#theme")! };
const params = new URLSearchParams(location.search);
for (const [key, control] of Object.entries(controls)) if (params.get(key)) control.value = params.get(key)!;
function load() {
  host.style.width = `${controls.width.value}px`;
  frame.src = `./frame.html?app=${controls.app.value}&theme=${controls.theme.value}`;
}
for (const control of Object.values(controls)) control.addEventListener("change", load);
window.addEventListener("message", (event) => {
  if (event.source !== frame.contentWindow || typeof event.data?.height !== "number") return;
  frame.style.height = `${event.data.height}px`;
  size.textContent = `${controls.width.value} × ${event.data.height}`;
});
load();
