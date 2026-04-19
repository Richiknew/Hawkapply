import { proxyRequest } from "@/lib/proxy";

export async function POST() {
  return proxyRequest("/pipeline/run", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: "{}",
  });
}
