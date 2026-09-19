"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string>();

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(undefined);
    try {
      await login(email, password);
      router.replace("/dashboard");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to reach the API. Check the backend URL and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page">
      <section className="login-story">
        <div className="brand-lockup">
          <span className="brand-mark">FC</span>
          <span>
            <strong>FirstComment</strong>
            <small>Agent Console</small>
          </span>
        </div>
        <div>
          <p className="eyebrow">AUTHENTICITY BEFORE AUTOMATION</p>
          <h1>Be early. Stay specific. Speak truthfully.</h1>
          <p>
            A policy-aware workspace for discovering creator posts, preparing context-grounded comments, and keeping every publish decision reviewable.
          </p>
        </div>
        <div className="login-principles">
          <span>Official capability only</span>
          <span>Fail closed</span>
          <span>Full provenance</span>
        </div>
      </section>
      <section className="login-form-wrap">
        <form className="login-form" onSubmit={submit}>
          <p className="eyebrow">SECURE OPERATOR ACCESS</p>
          <h2>Welcome back</h2>
          <p>Sign in with an account provisioned by your workspace administrator.</p>
          <div className="login-form-fields">
            <div className="field">
              <label htmlFor="email">Email</label>
              <input
                className="input"
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="password">Password</label>
              <input
                className="input"
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>
            {error ? <div className="login-error" role="alert">{error}</div> : null}
            <Button variant="primary" type="submit" disabled={submitting}>
              {submitting ? "Signing in…" : "Sign in"}
            </Button>
          </div>
          <p className="login-footnote">
            Access is role-based and audited. Tokens are never rendered into server logs or committed configuration.
          </p>
        </form>
      </section>
    </div>
  );
}
