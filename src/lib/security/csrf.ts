function firstHeaderValue(value: string | null): string | null {
  if (!value) {
    return null;
  }
  return value.split(",")[0]?.trim() || null;
}

function protocolWithoutColon(protocol: string): string {
  return protocol.endsWith(":") ? protocol.slice(0, -1).toLowerCase() : protocol.toLowerCase();
}

export function isTrustedPostOrigin(request: Request): boolean {
  const origin = firstHeaderValue(request.headers.get("origin"));
  if (!origin) {
    return false;
  }

  let originUrl: URL;
  try {
    originUrl = new URL(origin);
  } catch {
    return false;
  }

  const host =
    firstHeaderValue(request.headers.get("x-forwarded-host")) ??
    firstHeaderValue(request.headers.get("host"));
  if (!host) {
    return false;
  }

  const forwardedProto = firstHeaderValue(request.headers.get("x-forwarded-proto"));
  let requestProtocol = forwardedProto ? protocolWithoutColon(forwardedProto) : "";

  if (!requestProtocol) {
    try {
      requestProtocol = protocolWithoutColon(new URL(request.url).protocol);
    } catch {
      requestProtocol = "https";
    }
  }

  return (
    originUrl.host.toLowerCase() === host.toLowerCase() &&
    protocolWithoutColon(originUrl.protocol) === requestProtocol
  );
}
