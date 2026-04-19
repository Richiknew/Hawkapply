import { NextRequest } from "next/server";
import { proxyRequest } from "@/lib/proxy";

export async function POST(req: NextRequest) {
  const body = await req.text();
  return proxyRequest("/match/run", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
  });
}
