import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Admin refresh_token cookie is scoped to path=/api/v1/auth, so middleware cannot
 * rely on cookies for auth. Client-side AuthProvider handles redirects.
 */
export function middleware(_request: NextRequest) {
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
