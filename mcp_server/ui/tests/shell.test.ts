// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { keepWithNext, Pager, splittable } from "../src/shared/fit";
import { createShell } from "../src/shared/shell";

function width(value: number) {
  Object.defineProperty(window, "innerWidth", { configurable: true, value });
  window.dispatchEvent(new Event("resize"));
}
function frameButton(root: HTMLElement, name: string) { return root.querySelector<HTMLButtonElement>(`[aria-label="${name}"]`)!; }
// Node's experimental localStorage global can shadow jsdom's, so tests use an explicit memory store.
const memory = new Map<string, string>();
beforeEach(() => {
  memory.clear();
  vi.stubGlobal("localStorage", { getItem: (key: string) => memory.get(key) ?? null, setItem: (key: string, value: string) => void memory.set(key, value) });
});
afterEach(() => { document.body.replaceChildren(); vi.unstubAllGlobals(); width(1024); });

describe("fixed widget frame", () => {
  it("reports exactly 16:9 or 1:1 of the frame width and remembers the choice", async () => {
    width(800);
    const root = document.createElement("main"); document.body.append(root);
    const shell = createShell(root, { reloadLabel: "Reload", eyebrow: "BMW", title: "Widget" });
    const host = { sendSizeChanged: vi.fn().mockResolvedValue(undefined) };
    shell.attach(host);
    expect(host.sendSizeChanged).toHaveBeenLastCalledWith({ height: 450 });
    expect(root.dataset.frame).toBe("landscape");
    expect(root.style.getPropertyValue("--frame-height")).toBe("450px");
    frameButton(root, "Square frame").click();
    expect(host.sendSizeChanged).toHaveBeenLastCalledWith({ height: 800 });
    expect(root.dataset.frame).toBe("square");
    expect(frameButton(root, "Square frame").getAttribute("aria-pressed")).toBe("true");
    expect(localStorage.getItem("bmw-widget-frame")).toBe("square");
  });

  it("offers only the square frame when landscape would be too short, and respects a host height cap", () => {
    width(480);
    const root = document.createElement("main"); document.body.append(root);
    const shell = createShell(root, { reloadLabel: "Reload", eyebrow: "BMW", title: "Widget" });
    const host = { sendSizeChanged: vi.fn().mockResolvedValue(undefined) };
    shell.attach(host);
    expect(root.dataset.frame).toBe("square");
    expect(frameButton(root, "Landscape frame").disabled).toBe(true);
    expect(host.sendSizeChanged).toHaveBeenLastCalledWith({ height: 480 });
    width(900);
    expect(root.dataset.frame).toBe("landscape");
    shell.hostContext({ containerDimensions: { maxHeight: 400 } });
    expect(host.sendSizeChanged).toHaveBeenLastCalledWith({ height: 400 });
  });

  it("blocks zoom gestures inside the frame", () => {
    const root = document.createElement("main"); document.body.append(root);
    createShell(root, { reloadLabel: "Reload", eyebrow: "BMW", title: "Widget" });
    const wheel = new WheelEvent("wheel", { ctrlKey: true, cancelable: true });
    document.dispatchEvent(wheel);
    expect(wheel.defaultPrevented).toBe(true);
    const key = new KeyboardEvent("keydown", { key: "+", metaKey: true, cancelable: true });
    document.dispatchEvent(key);
    expect(key.defaultPrevented).toBe(true);
    expect(document.querySelector<HTMLMetaElement>('meta[name="viewport"]')?.content).toContain("user-scalable=no");
  });
});

/** jsdom has no layout, so heights come from data-h or, for text, 10px per 20 characters. */
function measured(height: number) {
  const pager = new Pager("test");
  const viewport = pager.viewport;
  Object.defineProperty(viewport, "clientHeight", { configurable: true, get: () => height });
  Object.defineProperty(viewport, "scrollHeight", { configurable: true, get: () => [...viewport.children].reduce((sum, child) => sum + (Number((child as HTMLElement).dataset.h) || Math.ceil((child.textContent?.length ?? 0) / 20) * 10), 0) });
  return pager;
}
function block(text: string, h?: number) {
  const node = document.createElement("p");
  node.textContent = text;
  if (h) node.dataset.h = String(h);
  return node;
}

describe("fit pager", () => {
  it("turns pages instead of overflowing", () => {
    const pager = measured(100);
    const items = [block("A", 40), block("B", 40), block("C", 40)];
    pager.set(items);
    expect(pager.pageCount).toBe(2);
    expect(pager.viewport.textContent).toBe("AB");
    expect(pager.controls.hidden).toBe(false);
    pager.controls.querySelector<HTMLButtonElement>('[aria-label="Next page of test"]')!.click();
    expect(pager.viewport.textContent).toBe("C");
    expect(pager.page).toBe(1);
  });

  it("keeps headings with the content that follows them", () => {
    const pager = measured(100);
    pager.set([block("A", 50), keepWithNext(block("Heading", 20)), block("B", 50)]);
    expect(pager.pageCount).toBe(2);
    expect(pager.viewport.textContent).toBe("A");
    pager.set([block("A", 50), keepWithNext(block("Heading", 20)), block("B", 50)], 1);
    expect(pager.viewport.textContent).toBe("HeadingB");
  });

  it("splits long text across pages without losing words and keeps the original intact", () => {
    const pager = measured(100);
    const words = Array.from({ length: 80 }, (_, index) => `word${index}`).join(" ");
    const item = splittable(block(words));
    pager.set([item]);
    expect(pager.pageCount).toBeGreaterThan(1);
    const pages: string[] = [];
    for (let page = 0; page < pager.pageCount; page++) { pager.set([item], page); pages.push(pager.viewport.textContent ?? ""); }
    expect(pages[0].endsWith("…")).toBe(true);
    expect(pages.join(" ").replaceAll("…", " ").split(/\s+/).filter(Boolean)).toEqual(words.split(" "));
    expect(item.textContent).toBe(words);
  });
});
