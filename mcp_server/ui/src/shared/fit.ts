import { el, icon } from "./shell";

/**
 * Marks a text block that may be divided across pages. `words` suits prose and quotes,
 * `lines` suits preformatted JSON. Only static text is cloned, so no listeners are lost.
 */
export function splittable<T extends HTMLElement>(node: T, by: "words" | "lines" = "words"): T {
  node.dataset.split = by;
  return node;
}

/** Marks a heading that should start the next page rather than end the current one alone. */
export function keepWithNext<T extends HTMLElement>(node: T): T {
  node.dataset.keep = "next";
  return node;
}

function overflows(viewport: HTMLElement): boolean {
  return viewport.scrollHeight > viewport.clientHeight + 1;
}

/**
 * Replace an oversized text block with the part that fits, returning a continuation for the next page.
 * Works on clones so the original item keeps its full text for later refits.
 */
function split(viewport: HTMLElement, item: HTMLElement): [HTMLElement, HTMLElement] | null {
  const by = item.dataset.split;
  const text = item.textContent ?? "";
  if (!by || !text) return null;
  const tokens = by === "lines" ? text.split(/(?<=\n)/) : text.split(/(?<=\s)/);
  if (tokens.length < 2) return null;
  const piece = item.cloneNode(false) as HTMLElement;
  viewport.replaceChild(piece, item);
  let low = 1, high = tokens.length - 1, best = 0;
  while (low <= high) {
    const middle = (low + high) >> 1;
    piece.textContent = `${tokens.slice(0, middle).join("").trimEnd()} …`;
    if (overflows(viewport)) high = middle - 1; else { best = middle; low = middle + 1; }
  }
  if (!best) { viewport.replaceChild(item, piece); return null; }
  piece.textContent = `${tokens.slice(0, best).join("").trimEnd()} …`;
  const rest = item.cloneNode(false) as HTMLElement;
  rest.textContent = `… ${tokens.slice(best).join("").trimStart()}`;
  return [piece, rest];
}

/** Distribute items across pages that each fit the viewport without scrolling. */
function paginate(viewport: HTMLElement, items: HTMLElement[]): HTMLElement[][] {
  viewport.replaceChildren();
  // Hidden or unmeasured viewports keep a single page; the observer refits once visible.
  if (viewport.clientHeight === 0) return [items];
  const pages: HTMLElement[][] = [];
  let page: HTMLElement[] = [];
  const queue = [...items];
  while (queue.length) {
    const item = queue.shift()!;
    item.classList.remove("is-clipped");
    viewport.append(item);
    if (!overflows(viewport)) { page.push(item); continue; }
    if (page.length) {
      item.remove();
      queue.unshift(item);
      // Carry trailing headings over so each starts the page with its content.
      while (page.length > 1 && page.at(-1)!.dataset.keep === "next") queue.unshift(page.pop()!);
      pages.push(page);
      page = [];
      viewport.replaceChildren();
      continue;
    }
    const parts = split(viewport, item);
    if (!parts) item.classList.add("is-clipped");
    pages.push([parts ? parts[0] : item]);
    viewport.replaceChildren();
    if (parts) queue.unshift(parts[1]);
  }
  if (page.length || !pages.length) pages.push(page);
  return pages;
}

/** A fixed-size viewport whose content turns pages instead of scrolling. */
export class Pager {
  readonly viewport = el("div", "bmw-viewport");
  readonly controls = el("div", "bmw-pager");
  private items: HTMLElement[] = [];
  private pages: HTMLElement[][] = [[]];
  private index = 0;
  private readonly previous = el("button");
  private readonly next = el("button");
  private readonly counter = el("output");
  private width = -1;
  private height = -1;

  constructor(label: string, private onPage?: (index: number) => void) {
    this.viewport.setAttribute("aria-label", label);
    this.viewport.addEventListener("keydown", (event) => {
      if (event.key === "PageDown") { event.preventDefault(); this.turn(1); }
      if (event.key === "PageUp") { event.preventDefault(); this.turn(-1); }
    });
    for (const [button, direction, name] of [[this.previous, -1, "left"], [this.next, 1, "right"]] as const) {
      button.type = "button";
      button.setAttribute("aria-label", direction < 0 ? `Previous page of ${label}` : `Next page of ${label}`);
      button.append(icon(name));
      button.addEventListener("click", () => this.turn(direction));
    }
    this.counter.setAttribute("aria-live", "polite");
    this.controls.append(this.previous, this.counter, this.next);
    if (typeof ResizeObserver !== "undefined") {
      new ResizeObserver(([entry]) => {
        const { width, height } = entry.contentRect;
        if (Math.abs(width - this.width) < 1 && Math.abs(height - this.height) < 1) return;
        this.width = width;
        this.height = height;
        this.refit();
      }).observe(this.viewport);
    }
    if (document.fonts?.ready) void document.fonts.ready.then(() => this.refit());
    this.sync();
  }

  get page(): number { return this.index; }
  get pageCount(): number { return this.pages.length; }

  set(items: HTMLElement[], page = 0): void {
    this.items = items;
    this.index = page;
    this.refit();
  }

  refit(): void {
    this.pages = paginate(this.viewport, this.items);
    this.index = Math.max(0, Math.min(this.index, this.pages.length - 1));
    this.viewport.replaceChildren(...this.pages[this.index]);
    this.sync();
  }

  private turn(direction: number): void {
    const target = Math.max(0, Math.min(this.index + direction, this.pages.length - 1));
    if (target === this.index) return;
    this.index = target;
    this.viewport.replaceChildren(...this.pages[this.index]);
    this.sync();
    this.onPage?.(this.index);
  }

  private sync(): void {
    const count = this.pages.length;
    this.controls.hidden = count < 2;
    this.counter.value = `${this.index + 1} / ${count}`;
    this.previous.disabled = this.index === 0;
    this.next.disabled = this.index >= count - 1;
  }
}
