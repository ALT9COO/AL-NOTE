import { NextRequest, NextResponse } from "next/server";

import { publicOrigin } from "@/lib/public-origin";

export function middleware(request: NextRequest) {
  const origin = publicOrigin(request);
  const hostname = new URL(origin).hostname;
  const res = NextResponse.next();
  if (hostname && hostname !== "localhost" && hostname !== "127.0.0.1" && hostname !== "0.0.0.0") {
    res.cookies.set("alnote_return_origin", origin, {
      path: "/",
      sameSite: "lax",
      secure: true,
      maxAge: 60 * 30,
    });
  }
  return res;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/).*)"],
};
