import React, { useState } from "react";

import { ApiError } from "../../api/images";
import avroomLogo from "../../assets/avroom.png";
import { useAuth } from "../../context/AuthContext";

type Mode = "login" | "signup";

/**
 * Entry gate shown only under the backend's jwt auth mode (see
 * AuthContext's boot probe). Sign in and create-account are the same form
 * with the same fields -- switching mode never loses what was typed.
 */
export const AuthScreen: React.FC = () => {
  const { login, signup } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleSubmit: React.FormEventHandler = (event) => {
    event.preventDefault();
    setError(null);
    setBusy(true);

    const run = mode === "login" ? login(email, password) : signup(email, password);
    void run
      .catch((submitError) => {
        if (submitError instanceof ApiError) {
          setError(submitError.detail || "That didn't work.");
        } else {
          setError(submitError instanceof Error ? submitError.message : "Couldn't reach the server.");
        }
      })
      .finally(() => setBusy(false));
  };

  const switchMode = () => {
    setMode((current) => (current === "login" ? "signup" : "login"));
    setError(null);
  };

  return (
    <div className="dashboard">
      <header className="dash-header">
        <img src={avroomLogo} alt="" className="dash-logo" />
        <span className="dash-wordmark">AVRoom</span>
      </header>

      <main className="dash-main is-narrow">
        <form className="auth-card" onSubmit={handleSubmit}>
          <h1 className="auth-title">{mode === "login" ? "Welcome back" : "Create an account"}</h1>
          <p className="auth-sub">
            {mode === "login"
              ? "Sign in to reach your sessions."
              : "A room and everything cut out of it belongs to you alone."}
          </p>

          <label className="auth-field">
            <span>Email</span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              required
              disabled={busy}
            />
          </label>

          <label className="auth-field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={mode === "signup" ? 8 : undefined}
              required
              disabled={busy}
            />
          </label>

          {error ? <p className="upload-rejection">{error}</p> : null}

          <button type="submit" className="btn is-primary auth-submit" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Sign up"}
          </button>

          <button type="button" className="auth-switch" onClick={switchMode} disabled={busy}>
            {mode === "login" ? "New here? Create an account" : "Already have an account? Sign in"}
          </button>
        </form>
      </main>
    </div>
  );
};
