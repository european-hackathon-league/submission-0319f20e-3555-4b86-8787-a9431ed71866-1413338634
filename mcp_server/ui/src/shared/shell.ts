import type { McpUiHostContext } from "@modelcontextprotocol/ext-apps";
import roundel from "./bmw-roundel.svg?raw";
import "./brand.css";

export type FrameMode = "landscape" | "square";
type SizeHost = { sendSizeChanged?: (params: { width?: number; height?: number }) => Promise<void> };

const LANDSCAPE_RATIO = 9 / 16;
// Below this width a 16:9 frame is too short for the PM controls, so only the square frame is offered.
const MIN_LANDSCAPE_WIDTH = 600;
const COMPACT_WIDTH = 560;
const MODE_KEY = "bmw-widget-frame";
const SVG_NS = "http://www.w3.org/2000/svg";

const ICONS = {
  pause: '<rect x="6" y="5" width="4" height="14"/><rect x="14" y="5" width="4" height="14"/>',
  play: '<polygon points="7 4 19 12 7 20 7 4"/>',
  landscape: '<rect x="2" y="6" width="20" height="12"/>',
  square: '<rect x="4" y="4" width="16" height="16"/>',
  reload: '<path d="M21 12a9 9 0 1 1-2.6-6.4L21 8"/><path d="M21 3v5h-5"/>',
  left: '<path d="m15 18-6-6 6-6"/>',
  right: '<path d="m9 18 6-6-6-6"/>',
  back: '<path d="M19 12H5"/><path d="m12 19-7-7 7-7"/>',
  open: '<path d="M7 17 17 7"/><path d="M7 7h10v10"/>',
} as const;

/** Lucide-style outline icon built from static path data. */
export function icon(name: keyof typeof ICONS): SVGSVGElement {
  const svg = document.createElementNS(SVG_NS, "svg");
  for (const [key, value] of Object.entries({ viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "1.5", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" })) svg.setAttribute(key, value);
  svg.innerHTML = ICONS[name];
  return svg;
}

export function el<K extends keyof HTMLElementTagNameMap>(tag: K, className = "", text?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function grade(value: string): HTMLElement {
  const node = el("span", `grade grade-${value || "none"}`, value || "—");
  node.title = `Evidence grade ${value || "not recorded"}. Quality is separate from priority.`;
  return node;
}

export function status(value: string): HTMLElement {
  return el("span", `status status-${value}`, value.replaceAll("_", " "));
}

function stored(): FrameMode | null {
  try { const value = localStorage.getItem(MODE_KEY); return value === "landscape" || value === "square" ? value : null; } catch { return null; }
}
function store(mode: FrameMode): void {
  try { localStorage.setItem(MODE_KEY, mode); } catch { /* Sandboxed frames may not expose storage. */ }
}

let guarded = false;
/** The widget is a fixed composition: block page zoom gestures and undo any programmatic scroll. */
function installGuards(): void {
  if (guarded) return;
  guarded = true;
  document.addEventListener("wheel", (event) => { if (event.ctrlKey || event.metaKey) event.preventDefault(); }, { passive: false });
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && ["+", "-", "=", "0"].includes(event.key)) event.preventDefault();
  });
  for (const type of ["gesturestart", "gesturechange", "gestureend"]) document.addEventListener(type, (event) => event.preventDefault(), { passive: false });
  document.addEventListener("touchmove", (event) => { if (event.touches.length > 1) event.preventDefault(); }, { passive: false });
  document.addEventListener("scroll", (event) => {
    const target = event.target instanceof Element ? event.target : document.scrollingElement;
    // Form fields keep their own caret scrolling; layout containers never scroll.
    if (target && !["TEXTAREA", "INPUT", "SELECT"].includes(target.tagName) && (target.scrollTop || target.scrollLeft)) { target.scrollTop = 0; target.scrollLeft = 0; }
  }, { capture: true, passive: true });
  if (!document.querySelector('meta[name="viewport"][content*="user-scalable"]')) {
    const meta = document.querySelector<HTMLMetaElement>('meta[name="viewport"]') ?? document.head.appendChild(el("meta"));
    meta.name = "viewport";
    meta.content = "width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no";
  }
}

/** Blue airflow ribbons ported from the workspace overview's MotionField; frame state stays outside rendering. */
function airflow(host: HTMLElement, control: HTMLButtonElement): void {
  const canvas = el("canvas");
  host.append(canvas);
  const ctx = /jsdom/i.test(navigator.userAgent) ? null : canvas.getContext("2d", { alpha: true });
  if (!ctx || typeof ResizeObserver === "undefined") { control.hidden = true; return; }
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  let paused = false, visible = true, frame = 0, previous = 0, phase = 0, width = 0, height = 0;
  const position = (u: number, lane: number, band: number) => {
    const curve = Math.sin(u * 5.5 - 1.2 + phase * 0.13);
    const fan = (lane - 0.5) * (0.12 + u * 0.46);
    return height * (0.74 - u * 0.37 + curve * 0.21 + fan + band * 0.2);
  };
  const paint = () => {
    if (width <= 0 || height <= 0) return;
    ctx.clearRect(0, 0, width, height);
    const light = ctx.createLinearGradient(0, 0, width, height * 0.3);
    light.addColorStop(0, "rgba(18,69,146,0)");
    light.addColorStop(0.35, "rgba(27,100,224,0.3)");
    light.addColorStop(0.7, "rgba(62,146,255,0.85)");
    light.addColorStop(1, "rgba(181,222,255,0.65)");
    for (let band = 0; band < 3; band++) {
      for (let row = 0; row < 18; row++) {
        const lane = row / 17;
        ctx.beginPath();
        for (let step = 0; step <= 120; step++) {
          const u = step / 120, x = u * (width + 40) - 20, y = position(u, lane, band - 1);
          if (step === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.strokeStyle = light;
        ctx.lineWidth = row === 0 || row === 17 ? 1.1 : 0.55;
        ctx.globalAlpha = band === 1 ? 0.9 : 0.35;
        ctx.stroke();
      }
      const head = (phase * 0.11 + band * 0.32) % 1.35, start = Math.max(0, head - 0.24), end = Math.min(1, head);
      if (end > start) {
        const glint = ctx.createLinearGradient(start * width, 0, end * width, 0);
        glint.addColorStop(0, "rgba(87,160,255,0)");
        glint.addColorStop(0.8, "rgba(136,203,255,0.7)");
        glint.addColorStop(1, "rgba(222,244,255,0.95)");
        ctx.beginPath();
        for (let step = 0; step <= 40; step++) {
          const u = start + (end - start) * step / 40, x = u * (width + 40) - 20, y = position(u, 0.5, band - 1);
          if (step === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.globalAlpha = 0.95;
        ctx.strokeStyle = glint;
        ctx.lineWidth = 1.8;
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
  };
  const tick = (time: number) => {
    if (time - previous >= 32) { phase += Math.min(time - previous, 50) / 1000; paint(); previous = time; }
    frame = requestAnimationFrame(tick);
  };
  const sync = () => {
    cancelAnimationFrame(frame);
    previous = 0;
    paint();
    if (!paused && !reduced.matches && visible && !document.hidden) frame = requestAnimationFrame(tick);
  };
  new ResizeObserver(([entry]) => {
    width = entry.contentRect.width;
    height = entry.contentRect.height;
    const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    sync();
  }).observe(canvas);
  if (typeof IntersectionObserver !== "undefined") new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; sync(); }).observe(canvas);
  reduced.addEventListener("change", sync);
  document.addEventListener("visibilitychange", sync);
  control.addEventListener("click", () => {
    paused = !paused;
    control.setAttribute("aria-pressed", String(paused));
    control.setAttribute("aria-label", paused ? "Play header animation" : "Pause header animation");
    control.replaceChildren(icon(paused ? "play" : "pause"));
    sync();
  });
}

export type Shell = ReturnType<typeof createShell>;

/**
 * Branded fixed frame shared by every widget: navy airflow header, square working surface,
 * and a host-reported height of exactly 16:9 (landscape) or 1:1 (square) of the frame width.
 */
export function createShell(root: HTMLElement, options: { reloadLabel: string; eyebrow: string; title: string }) {
  installGuards();
  root.classList.add("bmw-stage");
  root.replaceChildren();
  const head = el("header", "bmw-head");
  const field = el("div", "bmw-airflow");
  field.setAttribute("aria-hidden", "true");
  const bar = el("div", "bmw-bar");
  const lockup = el("div", "bmw-lockup");
  const mark = el("span", "bmw-roundel");
  mark.innerHTML = roundel.replace(/<\?xml[^>]*>/, "");
  mark.querySelector("svg")?.setAttribute("aria-hidden", "true");
  mark.querySelector("svg")?.setAttribute("width", "24");
  mark.querySelector("svg")?.setAttribute("height", "24");
  const name = el("span", "bmw-name", "BMW");
  name.append(el("small", "", "Product intelligence"));
  lockup.append(mark, name);
  const tools = el("div", "bmw-tools");
  const scope = el("span", "bmw-scope");
  scope.hidden = true;
  const segment = el("div", "bmw-segment");
  segment.setAttribute("role", "group");
  segment.setAttribute("aria-label", "Widget frame");
  const frameButtons = new Map<FrameMode, HTMLButtonElement>();
  for (const [mode, label] of [["landscape", "Landscape frame"], ["square", "Square frame"]] as const) {
    const button = el("button", "bmw-icon-button");
    button.type = "button";
    button.title = label;
    button.setAttribute("aria-label", label);
    button.append(icon(mode));
    button.addEventListener("click", () => setMode(mode, true));
    frameButtons.set(mode, button);
    segment.append(button);
  }
  const motion = el("button", "bmw-icon-button");
  motion.type = "button";
  motion.setAttribute("aria-pressed", "false");
  motion.setAttribute("aria-label", "Pause header animation");
  motion.append(icon("pause"));
  const reload = el("button", "bmw-icon-button");
  reload.type = "button";
  reload.dataset.action = "reload";
  reload.title = options.reloadLabel;
  reload.append(icon("reload"), el("span", "sr-only", options.reloadLabel));
  tools.append(scope, segment, motion, reload);
  bar.append(lockup, tools);
  const hero = el("div", "bmw-hero");
  const copy = el("div", "bmw-hero-copy");
  const eyebrow = el("p", "bmw-eyebrow", options.eyebrow);
  const title = el("h1", "", options.title);
  const subtitle = el("p", "bmw-sub");
  subtitle.hidden = true;
  copy.append(eyebrow, title, subtitle);
  const metric = el("div", "bmw-metric");
  hero.append(copy, metric);
  head.append(field, bar, hero);
  const body = el("div", "bmw-body");
  root.append(head, body);
  airflow(field, motion);

  let preferred: FrameMode = stored() ?? "landscape";
  let mode: FrameMode = preferred;
  let compact = false;
  let host: SizeHost | null = null;
  let reported = 0;
  let maxHeight = Infinity;
  const listeners: (() => void)[] = [];

  function apply(): void {
    const width = document.documentElement.clientWidth || window.innerWidth || 720;
    const landscapeAllowed = width >= MIN_LANDSCAPE_WIDTH;
    const next: FrameMode = landscapeAllowed ? preferred : "square";
    const nextCompact = width < COMPACT_WIDTH;
    const changed = next !== mode || nextCompact !== compact;
    mode = next;
    compact = nextCompact;
    frameButtons.get("landscape")!.disabled = !landscapeAllowed;
    for (const [key, button] of frameButtons) button.setAttribute("aria-pressed", String(key === mode));
    root.dataset.frame = mode;
    root.toggleAttribute("data-compact", compact);
    const height = Math.max(320, Math.min(Math.round(mode === "landscape" ? width * LANDSCAPE_RATIO : width), maxHeight));
    root.style.setProperty("--frame-height", `${height}px`);
    if (host?.sendSizeChanged && height !== reported) {
      reported = height;
      void host.sendSizeChanged({ height }).catch(() => { reported = 0; });
    }
    if (changed) for (const listener of listeners) listener();
  }
  function setMode(next: FrameMode, remember = false): void {
    preferred = next;
    if (remember) store(next);
    apply();
  }
  window.addEventListener("resize", apply);
  apply();

  return {
    root, body, reload, title, eyebrow, subtitle, metric, scope,
    get mode() { return mode; },
    /** Below the compact width the body uses a single column instead of side panels. */
    get compact() { return compact; },
    onLayoutChange(listener: () => void) { listeners.push(listener); },
    setScope(text: string) { scope.textContent = text; scope.hidden = !text; },
    setSubtitle(text: string) { subtitle.textContent = text; subtitle.hidden = !text; },
    /** Start reporting the fixed frame height once the host handshake has completed. */
    attach(app: SizeHost) { host = app; reported = 0; apply(); },
    hostContext(context: McpUiHostContext) {
      const dimensions = context.containerDimensions as { maxHeight?: number; height?: number } | undefined;
      maxHeight = dimensions?.height ?? dimensions?.maxHeight ?? Infinity;
      apply();
    },
  };
}
