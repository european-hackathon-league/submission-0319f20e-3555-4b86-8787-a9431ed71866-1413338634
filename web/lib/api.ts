import type { Audit, Page, Scope, Trace } from "./types";
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api/backend${path}`, {
    ...options,
    cache: "no-store",
  });
  const text = await response.text();
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    value = text;
  }
  if (!response.ok) {
    const detail =
      typeof value === "object" && value && "detail" in value
        ? value.detail
        : value;
    const message =
      typeof detail === "string" ? detail : JSON.stringify(detail);
    throw new ApiError(
      `${message || response.statusText}${response.status === 409 ? " Reload and review the current version before submitting again." : ""}`,
      response.status,
    );
  }
  return value as T;
}
export function write<T>(path: string, body: unknown, method = "POST") {
  return api<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
export function query(
  scope: Scope,
  extra: Record<string, string | number | undefined> = {},
) {
  const params = new URLSearchParams(scope);
  for (const [key, value] of Object.entries(extra))
    if (value !== undefined && value !== "") params.set(key, String(value));
  return params.toString();
}
export async function allPages<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T[]> {
  const items: T[] = [];
  const seen = new Set<string>();
  while (true) {
    const page = await api<Page<T>>(
      `${path}${path.includes("?") ? "&" : "?"}limit=500&offset=${items.length}`,
      { signal },
    );
    if (!Array.isArray(page.items))
      throw new Error("The server returned an invalid page.");
    if (items.length < page.total && !page.items.length)
      throw new Error(
        "The server returned incomplete results. Reload before continuing.",
      );
    for (const item of page.items) {
      const id = String((item as { id: string }).id);
      if (seen.has(id))
        throw new Error(
          "Records changed during pagination. Reload to get a consistent list.",
        );
      seen.add(id);
    }
    items.push(...page.items);
    if (items.length >= page.total) return items;
  }
}
export async function allAudit(entity?: string, signal?: AbortSignal) {
  const items: Audit[] = [];
  let after = 0;
  while (true) {
    const page = await api<{ items: Audit[]; next_after: number }>(
      `/audit?limit=1000&after=${after}${entity ? `&entity_id=${encodeURIComponent(entity)}` : ""}`,
      { signal },
    );
    items.push(...page.items);
    if (page.items.length < 1000) return items.reverse();
    if (page.next_after <= after)
      throw new Error("Audit pagination did not advance.");
    after = page.next_after;
  }
}
export async function pinnedTrace(
  id: string,
  version: string,
  score: string,
  offset = 0,
  signal?: AbortSignal,
) {
  const search = new URLSearchParams({
    version_id: version,
    score_id: score,
    limit: "40",
    offset: String(offset),
  });
  return api<Trace>(`/requirements/${encodeURIComponent(id)}/trace?${search}`, {
    signal,
  });
}
export const readable = (value: string) =>
  value.replaceAll("_", " ").replaceAll("-", " ");
export const fmt = (value: number) =>
  new Intl.NumberFormat("en-US").format(value);
export const date = (value?: string | null) =>
  value
    ? new Date(value).toLocaleString("en-GB", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Europe/Madrid",
      })
    : "Date not recorded";
export function locationLabel(location: Record<string, unknown>) {
  return (
    Object.entries(location)
      .filter(([k]) => k !== "header_row")
      .map(
        ([key, value]) =>
          `${readable(key)} ${typeof value === "object" ? JSON.stringify(value) : String(value)}`,
      )
      .join(" · ") || "Location not recorded"
  );
}
export function canAct(
  actor: { kind: string; role: string; active: number } | undefined,
  action: string,
) {
  if (!actor?.active || actor.kind !== "human" || actor.role === "viewer")
    return false;
  if (["approve", "reject", "complete", "edit"].includes(action))
    return ["pm", "lead_pm"].includes(actor.role);
  if (action === "score") return actor.role === "lead_pm";
  return true;
}
