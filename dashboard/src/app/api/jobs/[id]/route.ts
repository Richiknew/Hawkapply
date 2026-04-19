import { NextRequest } from "next/server";
import { proxyRequest } from "@/lib/proxy";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  return proxyRequest(`/jobs/${id}`);
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = await req.text();
  return proxyRequest(`/jobs/${id}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body,
  });
}
