import { proxyRequest } from "@/lib/proxy";

export async function GET() {
  return proxyRequest("/pipeline/runs");
}
