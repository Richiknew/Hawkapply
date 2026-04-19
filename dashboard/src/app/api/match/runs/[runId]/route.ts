import { NextRequest } from "next/server";
import { proxyRequest } from "@/lib/proxy";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ runId: string }> }
) {
  const { runId } = await params;
  return proxyRequest(`/match/runs/${runId}`);
}
