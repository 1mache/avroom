// Single seam for the caller's bearer token: where it's stored, and how it
// reaches every request this app makes. `AuthContext` is the only thing that
// calls `setAuthToken`; everything else (images.ts, debug.ts, preview.ts,
// and the three <img>-tag URL builders that can't set a header at all) reads
// through `authedFetch`/`withAuthParam`.
const STORAGE_KEY = "avroom_token";

function readStoredToken(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

let token: string | null = readStoredToken();

export function getAuthToken(): string | null {
  return token;
}

export function setAuthToken(next: string | null): void {
  token = next;
  try {
    if (next) {
      localStorage.setItem(STORAGE_KEY, next);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // Storage disabled (private browsing) — token still works for this tab.
  }
}

/**
 * Appends the token as a query param, for the handful of requests an <img>
 * tag makes directly and so can't attach an Authorization header to.
 */
export function withAuthParam(url: string): string {
  if (!token) {
    return url;
  }
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}token=${encodeURIComponent(token)}`;
}

/**
 * Drop-in replacement for `fetch` that attaches the bearer token. Every
 * request in the app goes through this (directly, or via images.ts's
 * fetchWithTimeout, which wraps it) instead of calling `fetch` itself —
 * that's what makes "attach the token" a one-line fact instead of something
 * every call site has to remember.
 */
export async function authedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const headers: Record<string, string> = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(init?.headers as Record<string, string> | undefined),
  };
  return fetch(input, { ...init, headers });
}
