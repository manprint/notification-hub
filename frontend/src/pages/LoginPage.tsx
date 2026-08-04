import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSession } from "../hooks/useSession";
import type { ApiError } from "../api/types";
import ErrorBanner from "../components/ErrorBanner";

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
    <div className="app-main" style={{ maxWidth: 360, margin: "80px auto" }}>
      <h1>NotifyHub</h1>
      {rateLimited ? (
        <div className="error-banner">
          {`Troppi tentativi, riprova fra ${retryAfterMinutes ?? "qualche"} minuti.`}
        </div>
      ) : (
        error && <ErrorBanner error={error} />
      )}
      <form onSubmit={(event) => void handleSubmit(event)}>
        <div className="form-row">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        <div className="form-row">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        <button type="submit" className="primary" disabled={submitting}>
          Accedi
        </button>
      </form>
    </div>
  );
}
