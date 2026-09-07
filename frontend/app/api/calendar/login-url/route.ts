import { NextRequest, NextResponse } from "next/server";

import { backendOrigin, publicOrigin } from "@/lib/public-origin";

export async function GET(request: NextRequest) {
  const origin = publicOrigin(request);
  const target = new URL("/api/calendar/login-url", backendOrigin());
  request.nextUrl.searchParams.forEach((value, key) => {
    target.searchParams.set(key, value);
  });
  target.searchParams.set("redirect_uri", `${origin}/api/calendar/callback`);
  target.searchParams.set("origin", origin);

  const headers: Record<string, string> = { "x-alnote-origin": origin };
  const auth = request.headers.get("authorization");
  if (auth) headers.authorization = auth;

  const res = await fetch(target, { headers, cache: "no-store" });
  const body = await res.text();
  return new NextResponse(body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") || "application/json" },
  });
}
