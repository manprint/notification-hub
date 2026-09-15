import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { ApiError } from "../api/types";
import ErrorBanner from "../components/ErrorBanner";
import Field, { RequiredLegend, fieldAria } from "../components/Field";
import { useSession } from "../hooks/useSession";

export default function LoginPage() {
  const { login } = useSession();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setSubmitting(false);
    }
  }

  const rateLimited = error?.status === 429;
  const retryAfterSeconds =
    typeof error?.extra?.retry_after === "number" ? error.extra.retry_after : null;
  const retryAfterMinutes = retryAfterSeconds !== null ? Math.ceil(retryAfterSeconds / 60) : null;

  return (
    <div className="auth-shell">
      <div className="card auth-card">
        <h1 className="auth-title">NotifyHub</h1>
        <p className="auth-subtitle">Accedi per vedere le notifiche del tuo tenant.</p>
        {rateLimited ? (
          <div className="error-banner" role="alert">
            {`Troppi tentativi, riprova fra ${retryAfterMinutes ?? "qualche"} minuti.`}
          </div>
        ) : (
          error && <ErrorBanner error={error} />
        )}
        <form className="form-stacked" onSubmit={(event) => void handleSubmit(event)}>
          <RequiredLegend />
          <Field id="email" label="Email" required>
            <input
              {...fieldAria("email")}
              type="email"
              required
              autoComplete="username"
              autoFocus
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </Field>
          <Field id="password" label="Password" required>
            <input
              {...fieldAria("password")}
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>
          <div className="form-actions">
            <button type="submit" className="primary" disabled={submitting}>
              {submitting ? "Accesso in corso…" : "Accedi"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
