import type { ApiError } from "../api/types";

export default function ErrorBanner({ error }: { error: ApiError }) {
  return <div className="error-banner">{error.detail || error.title}</div>;
}
