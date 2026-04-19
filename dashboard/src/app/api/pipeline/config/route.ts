import { NextRequest } from "next/server";
import { proxyRequest } from "@/lib/proxy";

export async function GET() {
  return proxyRequest("/pipeline/config");
}

export async function PUT(req: NextRequest) {
  const body = await req.text();
  return proxyRequest("/pipeline/config", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body,
  });
}
