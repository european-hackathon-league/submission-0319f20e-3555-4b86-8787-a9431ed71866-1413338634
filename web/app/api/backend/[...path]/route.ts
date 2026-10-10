import type { NextRequest } from "next/server";
const roots = new Set([
  "health",
  "workspace",
  "metrics",
  "actors",
  "sources",
  "evidence",
  "findings",
  "analyses",
  "requirements",
  "reviews",
  "audit",
  "workflows",
  "imports",
  "pipeline",
  "updates",
  "openapi.json",
  "docs",
]);
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  if (
    !roots.has(path[0]) ||
    path.some(
      (p) => p === ".." || p === "." || p.includes("/") || p.includes("\\"),
    )
  )
    return Response.json({ detail: "Unknown API route" }, { status: 404 });
  const incomingOrigin = request.headers.get("origin");
  if (request.method !== "GET" && incomingOrigin) {
    let sameOrigin = false;
    try {
      const origin = new URL(incomingOrigin);
      sameOrigin =
        ["http:", "https:"].includes(origin.protocol) &&
        origin.host === request.headers.get("host");
    } catch {
      /* Invalid origins are denied. */
    }
    if (!sameOrigin)
      return Response.json(
        { detail: "Cross-origin writes are not allowed" },
        { status: 403 },
      );
  }
  const base = process.env.EHL_API_URL || "http://127.0.0.1:8000";
  const url = `${base.replace(/\/$/, "")}/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  try {
    const headers = new Headers();
    if (request.headers.has("content-type"))
      headers.set("content-type", request.headers.get("content-type")!);
    const response = await fetch(url, {
      method: request.method,
      headers,
      body: request.method === "GET" ? undefined : await request.arrayBuffer(),
      cache: "no-store",
      signal: AbortSignal.timeout(240_000),
      redirect: "manual",
    });
    const outgoing = new Headers({ "Cache-Control": "no-store" });
    for (const key of ["content-type", "content-disposition"])
      if (response.headers.has(key))
        outgoing.set(key, response.headers.get(key)!);
    return new Response(response.body, {
      status: response.status,
      headers: outgoing,
    });
  } catch {
    return Response.json(
      {
        detail:
          "The API is unavailable or the request timed out. Refresh persisted state before retrying a write.",
      },
      { status: 502 },
    );
  }
}
export { proxy as GET, proxy as POST, proxy as PATCH };
