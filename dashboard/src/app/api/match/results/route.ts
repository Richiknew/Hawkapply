import { NextRequest } from "next/server";
import { proxyRequest } from "@/lib/proxy";

export async function GET(req: NextRequest) {
  const qs = req.nextUrl.search;
  return proxyRequest(`/match/results${qs}`);
}
