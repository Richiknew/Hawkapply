import { NextRequest } from "next/server";

const HAWK_URL = process.env.HAWKAPI_URL ?? "http://localhost:8000";
const HAWK_KEY = process.env.HAWKAPI_KEY ?? "";

export async function POST(req: NextRequest) {
  // Forward multipart form data directly — don't parse it, just stream it
  const formData = await req.formData();
  const fetchForm = new FormData();
  const file = formData.get("file");
  if (file) fetchForm.append("file", file as Blob, (file as File).name);

  const res = await fetch(`${HAWK_URL}/resume/upload`, {
    method: "POST",
    headers: { "X-API-Key": HAWK_KEY },
    body: fetchForm,
  });

  return new Response(res.body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
  });
}
