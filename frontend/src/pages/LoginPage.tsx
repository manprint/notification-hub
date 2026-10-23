import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import type { ApiError } from "../api/types";
import ErrorBanner from "../components/ErrorBanner";
import Field, { RequiredLegend, fieldAria } from "../components/Field";
import { useSession } from "../hooks/useSession";
import { safeRedirectTarget } from "../lib/redirect";

export default function LoginPage() {
  const { user, loading, login } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Messo da RequireAuth: la pagina chiesta prima del redirect al login.
  const target = safeRedirectTarget((location.state as { from?: unknown } | null)?.from);

  async function handleSubmit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate(target, { replace: true });
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setSubmitting(false);
    }
  }

  // Mentre si ricarica una sessione salvata il form non si mostra: un login
  // fatto in quel momento si incrocerebbe col refresh della sessione di prima.
  if (loading) return <div className="empty-state">Caricamento…</div>;
  // Chi è già dentro non rientra come un altro utente sopra la sessione
  // aperta: token e cache di A resterebbero sotto il nome di B. Per cambiare
  // utente si passa da "Esci", che revoca la sessione e svuota la cache.
  if (user && !submitting) return <Navigate to={target} replace />;

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
