import type { ApiError } from "../api/types";

export default function ErrorBanner({ error }: { error: ApiError }) {
  return (
    <div className="error-banner" role="alert" aria-live="assertive">
      {error.detail || error.title}
    </div>
  );
}
