import { authedFetch, setAuthToken } from "./authToken";
import { API_BASE_URL, handleJsonResponse } from "./images";

// Backs the login/signup screen and AuthContext. Kept out of images.ts,
// which is session-scoped -- these three calls exist before any session
// does. Mirrors fastApi-app/schemas/auth.py's response shapes.

export interface AuthUser {
  id: string;
  email: string;
}

interface TokenResponse {
  access_token: string;
}

interface MeResponse {
  user_id: string;
  email: string;
}

async function requestToken(path: "signup" | "login", email: string, password: string): Promise<string> {
  const response = await authedFetch(`${API_BASE_URL}/auth/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const body = await handleJsonResponse<TokenResponse>(response);
  return body.access_token;
}

/** Creates an account and stores the returned token as the active session. */
export async function signup(email: string, password: string): Promise<void> {
  setAuthToken(await requestToken("signup", email, password));
}

/** Verifies credentials and stores the returned token as the active session. */
export async function login(email: string, password: string): Promise<void> {
  setAuthToken(await requestToken("login", email, password));
}

/** Resolves the caller's own identity from whatever token is currently held. */
export async function fetchCurrentUser(): Promise<AuthUser> {
  const response = await authedFetch(`${API_BASE_URL}/auth/me`);
  const body = await handleJsonResponse<MeResponse>(response);
  return { id: body.user_id, email: body.email };
}
