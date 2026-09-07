import { NextRequest } from "next/server";

export function backendOrigin() {
  return process.env.ALNOTE_API_ORIGIN ?? "http://127.0.0.1:8000";
}

function hostnameOf(host: string) {
  const trimmed = host.trim().toLowerCase().replace(/^\[|\]$/g, "");
  const withoutPort = trimmed.includes(":") && !trimmed.startsWith("[") ? trimmed.split(":")[0] : trimmed;
  return withoutPort.replace(/^\[|\]$/g, "");
}

function isUnusable(hostname: string) {
  return hostname === "0.0.0.0" || hostname === "::" || hostname === "";
}

function isLoopback(hostname: string) {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]" || hostname === "::1";
}

export function publicOrigin(request: NextRequest) {
  const proto =
    request.headers.get("x-forwarded-proto")?.split(",")[0].trim() ||
    request.nextUrl.protocol.replace(":", "") ||
    "https";
  const raw = [
    request.cookies.get("alnote_return_origin")?.value,
    request.headers.get("x-forwarded-host")?.split(",")[0].trim(),
    request.headers.get("host"),
    request.nextUrl.host,
  ].filter((value): value is string => Boolean(value));

  const parsed = raw.map((value) => {
    if (value.startsWith("http://") || value.startsWith("https://")) {
      try {
        return new URL(value).host;
      } catch {
        return value.replace(/^https?:\/\//, "");
      }
    }
    return value;
  });

  const lan = parsed.find((host) => !isUnusable(hostnameOf(host)) && !isLoopback(hostnameOf(host)));
  const usable = parsed.find((host) => !isUnusable(hostnameOf(host)));
  const host = lan || (!isLoopback(hostnameOf(usable || "")) ? usable : undefined);
  if (host) {
    return `${proto}://${host}`;
  }
  const env = (process.env.ALNOTE_PUBLIC_ORIGIN || "").replace(/\/$/, "");
  if (env) {
    return env;
  }
  return `${proto}://localhost:3001`;
}
