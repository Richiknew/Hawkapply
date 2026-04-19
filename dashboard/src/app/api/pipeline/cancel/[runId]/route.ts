import { proxyRequest } from "@/lib/proxy";

export async function POST(
  _req: Request,
  { params }: { params: Promise<{ runId: string }> }
) {
  const { runId } = await params;
  return proxyRequest(`/pipeline/cancel/${runId}`, { method: "POST" });
}
