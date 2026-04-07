/**
 * Desktop authentication helpers — Community edition.
 *
 * Auth is disabled in Community edition. All functions return safe defaults.
 */

export function isAuthEnabled(): boolean {
  return false;
}

export function getAccessToken(): string | null {
  return null;
}

export function setAccessToken(_token: string): void {}

export function clearAccessToken(): void {}

export function getTokenPayload(): Record<string, unknown> | null {
  return null;
}

export function getUserRole(): string {
  return "admin";
}

export function getUserId(): string {
  return "local";
}

export async function login(_provider: string): Promise<void> {}

export type OAuthCallbackResult =
  | { status: "ok" }
  | { status: "totp"; partialToken: string }
  | { status: "error" };

export async function handleCallback(
  _provider: string,
  _code: string,
  _state?: string,
): Promise<OAuthCallbackResult> {
  return { status: "error" };
}

export async function refreshToken(): Promise<boolean> {
  return false;
}

export function logout(): void {
  if (typeof window !== "undefined") {
    window.location.href = "/";
  }
}

export async function authFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  return fetch(input, init);
}
