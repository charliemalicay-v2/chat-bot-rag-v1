/**
 * Same-origin proxy: the browser talks to Next (/api/*), Next talks to Django.
 *
 * A Route Handler is used instead of `rewrites()` for two reasons:
 *  - BACKEND_URL is read at *request* time, so one built image works in any
 *    environment (rewrites are frozen at build time).
 *  - The response body is piped through untouched, so the chat's server-sent
 *    events stream token by token, and a client disconnect (req.signal) is
 *    forwarded to Django, which then discards the unfinished answer.
 */
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "content-encoding",
  "content-length",
  "upgrade",
]);

function backendUrl(): string {
  return (process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/+$/, "");
}

async function proxy(req: Request): Promise<Response> {
  const incoming = new URL(req.url);
  // Django routes end in "/" and APPEND_SLASH cannot redirect a POST.
  const path = incoming.pathname.endsWith("/") ? incoming.pathname : `${incoming.pathname}/`;
  const target = `${backendUrl()}${path}${incoming.search}`;

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers: {
        "content-type": req.headers.get("content-type") ?? "application/json",
        accept: req.headers.get("accept") ?? "*/*",
      },
      body: hasBody ? await req.text() : undefined,
      signal: req.signal,
      redirect: "manual",
      cache: "no-store",
    });
  } catch (err) {
    if (req.signal.aborted) return new Response(null, { status: 499 });
    console.error(`[proxy] ${req.method} ${target} failed:`, err);
    return Response.json({ detail: "The backend is not reachable." }, { status: 502 });
  }

  const headers = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value);
  });
  // no-transform stops Next's gzip from buffering the event stream.
  headers.set("cache-control", "no-cache, no-transform");
  headers.set("x-accel-buffering", "no");
  return new Response(upstream.body, { status: upstream.status, headers });
}

export const GET = proxy;
export const POST = proxy;
export const DELETE = proxy;
