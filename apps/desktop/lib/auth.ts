/**
 * Desktop authentication helpers.
 * Talks to admin-api for OAuth login and token management.
 * When NEXT_PUBLIC_AUTH_API_URL is not set, auth is disabled (Community mode).
 */

const AUTH_API =
  process.env.NEXT_PUBLIC_AUTH_API_URL || "";

const TOKEN_KEY = "pnlclaw_access_token";

export function isAuthEnabled(): boolean {
  return AUTH_API.length > 0;
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setAccessToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function getTokenPayload(): Record<string, unknown> | null {
  const token = getAccessToken();
  if (!token) return null;
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    return JSON.parse(atob(parts[1]));
  } catch {
    return null;
  }
}

export function getUserRole(): string {
  const payload = getTokenPayload();
  return (payload?.role as string) ?? "user";
}

export function getUserId(): string {
  const payload = getTokenPayload();
  return (payload?.sub as string) ?? "local";
}

export async function login(provider: string): Promise<void> {
  if (!AUTH_API) return;
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const qs = origin ? `?redirect_to=${encodeURIComponent(origin)}` : "";
  const res = await fetch(`${AUTH_API}/auth/login/${encodeURIComponent(provider)}${qs}`);
  const json = await res.json();
  const url = json?.data?.redirect_url ?? json?.redirect_url;
  if (url) {
    window.location.href = url;
  }
}

export type OAuthCallbackResult =
  | { status: "ok" }
  | { status: "totp"; partialToken: string }
  | { status: "error" };

export async function handleCallback(
  provider: string,
  code: string,
  state?: string,
): Promise<OAuthCallbackResult> {
  if (!AUTH_API) return { status: "error" };
  try {
    const res = await fetch(
      `${AUTH_API}/auth/callback/${encodeURIComponent(provider)}?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state ?? "")}`,
      { credentials: "include" },
    );
    const json = await res.json();
    const data = json?.data ?? json;
    if (data.access_token) {
      setAccessToken(data.access_token);
      return { status: "ok" };
    }
    if (data.requires_totp && data.partial_token) {
      return { status: "totp", partialToken: data.partial_token };
    }
    return { status: "error" };
  } catch {
    return { status: "error" };
  }
}

export async function refreshToken(): Promise<boolean> {
  if (!AUTH_API) return false;
  try {
    const res = await fetch(`${AUTH_API}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) return false;
    const json = await res.json();
    const data = json?.data ?? json;
    if (data?.access_token) {
      setAccessToken(data.access_token);
      return true;
    }
    return false;
  } catch {
    return false;
  }
}

export function logout(): void {
  clearAccessToken();
  if (typeof window !== "undefined") {
    window.location.href = "/";
  }
}
