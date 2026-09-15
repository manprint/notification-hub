import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiPost } from "../api/client";
import type { ApiError } from "../api/types";
import ErrorBanner from "../components/ErrorBanner";
import Field, { RequiredLegend, fieldAria } from "../components/Field";
import { useToast } from "../hooks/useToast";

function readTokenFromHash(): string | null {
  const hash = window.location.hash.replace(/^#/, "");
  const params = new URLSearchParams(hash);
  return params.get("token");
}

const MIN_PASSWORD_LENGTH = 12;

export default function AcceptInvitePage() {
  const navigate = useNavigate();
  const toast = useToast();
  const [password, setPassword] = useState("");
  const [repeated, setRepeated] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [repeatedError, setRepeatedError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const token = readTokenFromHash();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setValidationError(null);
    setPasswordError(null);
    setRepeatedError(null);

    if (password.length < MIN_PASSWORD_LENGTH) {
      setPasswordError(`La password deve avere almeno ${MIN_PASSWORD_LENGTH} caratteri.`);
      return;
    }
    // Una password scelta e sbagliata di battitura chiude fuori dall'account
    // appena creato: la si chiede due volte, come ovunque si imposti una
    // password e non la si digiti.
    if (repeated !== password) {
      setRepeatedError("Le due password non coincidono.");
      return;
    }
    if (!token) {
      setValidationError("Token di invito mancante nel collegamento.");
      return;
    }

    setSubmitting(true);
    try {
      await apiPost("/api/v1/invitations/accept", { token, password });
      toast.success("Account attivato: ora puoi accedere.");
      navigate("/login", { replace: true });
    } catch (err) {
      const apiError = err as ApiError;
      setError(apiError);
      toast.error(apiError.detail || apiError.title || "Attivazione non riuscita.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-shell">
      <div className="card auth-card">
        <h1 className="auth-title">Accetta invito</h1>
        <p className="auth-subtitle">
          Scegli la password del tuo account: da qui in poi si entra con quella.
        </p>
        {error && <ErrorBanner error={error} />}
        {validationError && (
          <div className="error-banner" role="alert">
            {validationError}
          </div>
        )}
        <form className="form-stacked" onSubmit={(event) => void handleSubmit(event)}>
          <RequiredLegend />
          <Field
            id="password"
            label="Scegli una password"
            required
            hint={`Almeno ${MIN_PASSWORD_LENGTH} caratteri.`}
            error={passwordError}
          >
            <input
              {...fieldAria("password", { hint: true, error: passwordError })}
              type="password"
              required
              minLength={MIN_PASSWORD_LENGTH}
              autoComplete="new-password"
              autoFocus
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>
          <Field id="password-repeat" label="Ripeti la password" required error={repeatedError}>
            <input
              {...fieldAria("password-repeat", { error: repeatedError })}
              type="password"
              required
              autoComplete="new-password"
              value={repeated}
              onChange={(event) => setRepeated(event.target.value)}
            />
          </Field>
          <div className="form-actions">
            <button type="submit" className="primary" disabled={submitting}>
              {submitting ? "Attivazione…" : "Attiva account"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
