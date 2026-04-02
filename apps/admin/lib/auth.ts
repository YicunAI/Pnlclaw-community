import {
  apiGet,
  apiFetch,
  setAccessToken,
  clearAccessToken,
  unwrapEnvelope,
} from "./api";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001/api/v1";

export async function login(provider: string) {
  const data = await apiGet<{ redirect_url: string }>(
    `/auth/login/${encodeURIComponent(provider)}`
  );
  if (data.redirect_url) {
    window.location.href = data.redirect_url;
  }
}

export type OAuthCallbackResult =
  | { status: "ok" }
  | { status: "totp"; partialToken: string }
  | { status: "error" };

export async function handleCallback(
  provider: string,
  code: string,
  state?: string
): Promise<OAuthCallbackResult> {
  try {
    const data = await apiGet<{
      access_token?: string;
      requires_totp?: boolean;
      partial_token?: string;
    }>(
      `/auth/callback/${encodeURIComponent(provider)}?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state ?? "")}`
    );

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
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) return false;
    const json = await res.json();
    const payload = unwrapEnvelope(json);
    const p = payload as { access_token?: string } | null;
    if (p && typeof p === "object" && p.access_token) {
      setAccessToken(p.access_token);
      return true;
    }
    return false;
  } catch {
    return false;
  }
}

export async function logout(): Promise<void> {
  try {
    await apiFetch("/auth/logout", { method: "POST" });
  } catch {
    /* best effort */
  } finally {
    clearAccessToken();
    window.location.href = "/login";
  }
}
