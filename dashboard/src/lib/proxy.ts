// Shared helper for Next.js route handlers that proxy to FastAPI.
// The API key stays server-side and never reaches the browser.

const HAWK_URL = process.env.HAWKAPI_URL ?? "http://localhost:8000";
const HAWK_KEY = process.env.HAWKAPI_KEY ?? "";

export function hawkHeaders(extra?: HeadersInit): Headers {
  const h = new Headers(extra);
  h.set("X-API-Key", HAWK_KEY);
  return h;
}

export async function proxyRequest(
  path: string,
  init?: RequestInit
): Promise<Response> {
  const url = `${HAWK_URL}${path}`;
  const headers = hawkHeaders(init?.headers as HeadersInit | undefined);

  // Forward Content-Type if present in original init
  if (init?.headers) {
    const src = new Headers(init.headers as HeadersInit);
    const ct = src.get("content-type");
    if (ct) headers.set("content-type", ct);
  }

  const res = await fetch(url, { ...init, headers });
  // Return a new Response with the same body/status so Next.js can forward it
  return new Response(res.body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
  });
}
