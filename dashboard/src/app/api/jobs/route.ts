import { NextRequest } from "next/server";
import { proxyRequest } from "@/lib/proxy";

export async function GET(req: NextRequest) {
  const qs = req.nextUrl.search;
  return proxyRequest(`/jobs${qs}`);
}

export async function POST(req: NextRequest) {
  const body = await req.text();
  return proxyRequest("/jobs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
  });
}
