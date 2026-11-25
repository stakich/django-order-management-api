
export type RegisterData = {
  username: string;
  email: string;
  password: string;
  password_confirm: string;
};

export type AuthTokens = {
  access: string;
  refresh: string;
};

export type AuthUser = {
  id: number;
  username: string;
  email: string;
};

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const ACCESS_KEY = "access_token";
const REFRESH_KEY = "refresh_token";

export const SESSION_ENDED_EVENT = "auth:session-ended";

export function hasSession(): boolean {
  return Boolean(sessionStorage.getItem(ACCESS_KEY));
}

export function saveTokens(tokens: AuthTokens): void {
  sessionVersion += 1;
  sessionStorage.setItem(ACCESS_KEY, tokens.access);
  sessionStorage.setItem(REFRESH_KEY, tokens.refresh);
}

export function clearTokens(): void {
  sessionVersion += 1;
  sessionStorage.removeItem(ACCESS_KEY);
  sessionStorage.removeItem(REFRESH_KEY);

  window.dispatchEvent(new Event(SESSION_ENDED_EVENT));
}

let sessionVersion = 0;
let pendingRefresh: {
  version: number;
  promise: Promise<string | null>;
} | null = null;

function refreshAccessToken(version: number): Promise<string | null> {
  if (pendingRefresh?.version === version) {
    return pendingRefresh.promise;
  }

  const promise = (async () => {
    const refresh = sessionStorage.getItem(REFRESH_KEY);

    if (!refresh) {
      clearTokens();
      return null;
    }

    const response = await fetch("/api/v1/auth/token/refresh/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });

    if (sessionVersion !== version) return null;

    if (response.status === 400 || response.status === 401) {
      clearTokens();
      return null;
    }

    if (!response.ok) {
      throw new ApiError(response.status, "Token refresh failed");
    }

    const data: unknown = await response.json();

    if (
      !data ||
      typeof data !== "object" ||
      !("access" in data) ||
      typeof data.access !== "string"
    ) {
      throw new Error("Invalid token refresh response");
    }

    if (sessionVersion !== version) {
      return null;
    }

    sessionStorage.setItem(ACCESS_KEY, data.access);

    if ("refresh" in data && typeof data.refresh === "string") {
      sessionStorage.setItem(REFRESH_KEY, data.refresh);
    }

    return data.access;
  })().finally(() => {
    if (pendingRefresh?.promise === promise) {
      pendingRefresh = null;
    }
  });

  pendingRefresh = { version, promise };
  return promise;
}

export async function authenticatedFetch(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const originalToken = sessionStorage.getItem(ACCESS_KEY);
  const version = sessionVersion;

  function assertCurrentSession() {
    options.signal?.throwIfAborted();
    if (sessionVersion !== version) {
      throw new DOMException("The active session changed", "AbortError");
    }
  }

  function sendRequest(token: string | null): Promise<Response> {
    const headers = new Headers(options.headers);

    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    return fetch(url, { ...options, headers });
  }

  const response = await sendRequest(originalToken);
  assertCurrentSession();

  if (response.status !== 401 || !originalToken) {
    return response;
  }

  // Another request may have already refreshed the token.
  const currentToken = sessionStorage.getItem(ACCESS_KEY);

  const newToken =
    currentToken && currentToken !== originalToken
      ? currentToken
      : await refreshAccessToken(version);

  if (!newToken) {
    return response;
  }

  assertCurrentSession();
  const retryResponse = await sendRequest(newToken);
  assertCurrentSession();

  if (
    retryResponse.status === 401 &&
    sessionStorage.getItem(ACCESS_KEY) === newToken
  ) {
    clearTokens();
  }

  return retryResponse;
}

export async function request<T>(
  url: string,
  options: RequestInit = {},
  authenticated = false
): Promise<T> {
  const response = authenticated
    ? await authenticatedFetch(url, options)
    : await fetch(url, options);

  const data: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    let message = `Request failed (HTTP ${response.status})`;

    if (data && typeof data === "object" && !Array.isArray(data)) {
      for (const value of Object.values(data)) {
        if (typeof value === "string") {
          message = value;
          break;
        }

        if (Array.isArray(value) && typeof value[0] === "string") {
          message = value[0];
          break;
        }
      }
    }

    throw new ApiError(response.status, message);
  }

  return data as T;
}

export function register(data: RegisterData): Promise<AuthUser> {
  return request<AuthUser>("/api/v1/auth/register/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function login(
  username: string,
  password: string
): Promise<AuthTokens> {
  return request<AuthTokens>("/api/v1/auth/login/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export function getMe(signal?: AbortSignal): Promise<AuthUser> {
  return request<AuthUser>(
    "/api/v1/auth/me/",
    { signal },
    true
  );
}
