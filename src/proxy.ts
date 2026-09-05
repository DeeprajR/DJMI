import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { SESSION_COOKIE_NAME } from "@/lib/auth/constants";

function hasSessionCookie(request: NextRequest): boolean {
  return !!request.cookies.get(SESSION_COOKIE_NAME)?.value;
}

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const isAuthenticated = hasSessionCookie(request);

  const requiresAuth =
    pathname.startsWith("/dashboard") ||
    pathname.startsWith("/profile") ||
    pathname.startsWith("/patients") ||
    pathname.startsWith("/admissions") ||
    pathname.startsWith("/requests") ||
    pathname.startsWith("/admin");

  if (requiresAuth && !isAuthenticated) {
    const nextParam = encodeURIComponent(`${pathname}${search}`);
    return NextResponse.redirect(new URL(`/sign-in?next=${nextParam}`, request.url));
  }

  if (pathname === "/sign-in" && isAuthenticated) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/profile/:path*",
    "/patients/:path*",
    "/admissions/:path*",
    "/requests/:path*",
    "/admin/:path*",
    "/sign-in",
  ],
};
