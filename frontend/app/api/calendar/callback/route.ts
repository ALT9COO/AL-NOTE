import { NextRequest, NextResponse } from "next/server";

import { backendOrigin, publicOrigin } from "@/lib/public-origin";

export async function GET(request: NextRequest) {
  const origin = publicOrigin(request);
  const target = `${backendOrigin()}/api/calendar/callback${request.nextUrl.search}`;
  const res = await fetch(target, {
    headers: { "x-alnote-origin": origin },
    redirect: "manual",
    cache: "no-store",
  });

  const location = res.headers.get("location");
  if (location && res.status >= 300 && res.status < 400) {
    try {
      const loc = new URL(location, origin);
      const here = new URL(origin);
      const loopback = loc.hostname === "localhost" || loc.hostname === "127.0.0.1" || loc.hostname === "0.0.0.0";
      if (loopback) {
        loc.protocol = here.protocol;
        loc.host = here.host;
      }
      return NextResponse.redirect(loc, res.status as 301 | 302 | 303 | 307 | 308);
    } catch {
      return NextResponse.redirect(new URL("/meetings", origin));
    }
  }

  return new NextResponse(await res.text(), { status: res.status });
}
