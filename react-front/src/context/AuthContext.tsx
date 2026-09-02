import React, { createContext, useCallback, useContext, useEffect, useState } from "react";

import { fetchCurrentUser, login as apiLogin, signup as apiSignup, type AuthUser } from "../api/auth";
import { setAuthToken } from "../api/authToken";

type AuthStatus = "checking" | "authed" | "anon";

interface AuthContextValue {
  user: AuthUser | null;
  status: AuthStatus;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * Owns the session end to end: token persistence (via api/authToken.ts),
 * and resolving who's currently logged in. Every other screen only ever
 * reads `user`/`status` from `useAuth()` -- none of them need to know a
 * token exists.
 *
 * Boot behavior doubles as the AUTH_MODE probe: GET /auth/me always
 * succeeds under the backend's single_user mode (token or not), so local
 * dev goes straight to the dashboard with no login screen, exactly as
 * before. Under jwt mode it 401s with no/invalid token, which is what
 * shows the login/signup screen.
 */
export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>("checking");

  const resolveSession = useCallback(async () => {
    try {
      setUser(await fetchCurrentUser());
      setStatus("authed");
    } catch {
      setAuthToken(null);
      setUser(null);
      setStatus("anon");
    }
  }, []);

  useEffect(() => {
    void resolveSession();
  }, [resolveSession]);

  const login = useCallback(
    async (email: string, password: string) => {
      await apiLogin(email, password);
      await resolveSession();
    },
    [resolveSession],
  );

  const signup = useCallback(
    async (email: string, password: string) => {
      await apiSignup(email, password);
      await resolveSession();
    },
    [resolveSession],
  );

  const logout = useCallback(() => {
    setAuthToken(null);
    setUser(null);
    setStatus("anon");
  }, []);

  return (
    <AuthContext.Provider value={{ user, status, login, signup, logout }}>{children}</AuthContext.Provider>
  );
};

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
