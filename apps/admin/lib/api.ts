const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001/api/v1";

let accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function clearAccessToken() {
  accessToken = null;
}

export class ApiError extends Error {
  status: number;
  info?: unknown;

  constructor(message: string, status: number, info?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.info = info;
  }
}

/** Unwrap APIResponse envelope from admin-api `{ data, meta, error }`. */
export function unwrapEnvelope(json: unknown): unknown {
  if (
    json &&
    typeof json === "object" &&
    "data" in json &&
    "meta" in json
  ) {
    return (json as { data: unknown }).data;
  }
  return json;
}

async function tryRefreshToken(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) return false;
    const json = await res.json();
    const payload = unwrapEnvelope(json) as { access_token?: string } | null;
    if (payload && typeof payload === "object" && payload.access_token) {
      setAccessToken(payload.access_token);
      return true;
    }
    return false;
  } catch {
    return false;
  }
}

async function parseJsonResponse(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers);

  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  if (
    options.body &&
    typeof options.body === "string" &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });

  if (res.status === 401) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      headers.set("Authorization", `Bearer ${accessToken}`);
      const retryRes = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers,
        credentials: "include",
      });
      if (!retryRes.ok) {
        throw new ApiError(retryRes.statusText, retryRes.status);
      }
      if (retryRes.status === 204) {
        return undefined as T;
      }
      const retryJson = await parseJsonResponse(retryRes);
      return unwrapEnvelope(retryJson) as T;
    }
    clearAccessToken();
    if (
      typeof window !== "undefined" &&
      !window.location.pathname.startsWith("/login")
    ) {
      window.location.href = "/login";
    }
    throw new ApiError("Unauthorized", 401);
  }

  if (!res.ok) {
    let info: unknown;
    try {
      info = await res.json();
    } catch {
      /* ignore parse error */
    }
    throw new ApiError(res.statusText, res.status, info);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const json = await parseJsonResponse(res);
  return unwrapEnvelope(json) as T;
}

/** Authenticated GET/POST-style request that returns a Blob (e.g. CSV/JSON export). */
export async function apiFetchBlob(
  path: string,
  options: RequestInit = {}
): Promise<Blob> {
  const headers = new Headers(options.headers);
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });

  if (res.status === 401) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      headers.set("Authorization", `Bearer ${accessToken}`);
      const retryRes = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers,
        credentials: "include",
      });
      if (!retryRes.ok) {
        throw new ApiError(retryRes.statusText, retryRes.status);
      }
      return retryRes.blob();
    }
    clearAccessToken();
    if (
      typeof window !== "undefined" &&
      !window.location.pathname.startsWith("/login")
    ) {
      window.location.href = "/login";
    }
    throw new ApiError("Unauthorized", 401);
  }

  if (!res.ok) {
    let info: unknown;
    try {
      info = await res.json();
    } catch {
      /* ignore */
    }
    throw new ApiError(res.statusText, res.status, info);
  }

  return res.blob();
}

export async function apiGet<T = unknown>(path: string): Promise<T> {
  return apiFetch<T>(path, { method: "GET" });
}

export async function apiPost<T = unknown>(
  path: string,
  body?: unknown
): Promise<T> {
  return apiFetch<T>(path, {
    method: "POST",
    body: body != null ? JSON.stringify(body) : undefined,
  });
}

export async function apiPatch<T = unknown>(
  path: string,
  body?: unknown
): Promise<T> {
  return apiFetch<T>(path, {
    method: "PATCH",
    body: body != null ? JSON.stringify(body) : undefined,
  });
}

export async function apiDelete<T = unknown>(path: string): Promise<T> {
  return apiFetch<T>(path, { method: "DELETE" });
}
