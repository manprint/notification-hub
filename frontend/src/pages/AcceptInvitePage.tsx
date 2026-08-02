import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiPost } from "../api/client";
import type { ApiError } from "../api/types";
import ErrorBanner from "../components/ErrorBanner";

function readTokenFromHash(): string | null {
  const hash = window.location.hash.replace(/^#/, "");
  const params = new URLSearchParams(hash);
  return params.get("token");
}

const MIN_PASSWORD_LENGTH = 12;

export default function AcceptInvitePage() {
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const token = readTokenFromHash();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setValidationError(null);

    if (password.length < MIN_PASSWORD_LENGTH) {
      setValidationError(`La password deve avere almeno ${MIN_PASSWORD_LENGTH} caratteri.`);
      return;
    }
    if (!token) {
      setValidationError("Token di invito mancante nel collegamento.");
      return;
    }

    setSubmitting(true);
    try {
      await apiPost("/api/v1/invitations/accept", { token, password });
      navigate("/login", { replace: true });
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="app-main" style={{ maxWidth: 360, margin: "80px auto" }}>
      <h1>Accetta invito</h1>
      {error && <ErrorBanner error={error} />}
      {validationError && <div className="error-banner">{validationError}</div>}
      <form onSubmit={(event) => void handleSubmit(event)}>
        <div className="form-row">
          <label htmlFor="password">Scegli una password</label>
          <input
            id="password"
            type="password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        <button type="submit" className="primary" disabled={submitting}>
          Attiva account
        </button>
      </form>
    </div>
  );
}
