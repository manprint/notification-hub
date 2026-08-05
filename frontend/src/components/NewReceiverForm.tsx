import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiPost } from "../api/client";
import type { ApiError, Severity } from "../api/types";
import ErrorBanner from "./ErrorBanner";

const SEVERITIES: Severity[] = ["critical", "error", "warning", "info", "debug"];

export default function NewReceiverForm({ groupId }: { groupId: string }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [defaultSeverity, setDefaultSeverity] = useState<Severity>("info");
  const [error, setError] = useState<ApiError | null>(null);

  async function createReceiver(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await apiPost(`/api/v1/groups/${groupId}/receivers`, {
        name,
        default_severity: defaultSeverity,
      });
      setName("");
      setDefaultSeverity("info");
      await queryClient.invalidateQueries({ queryKey: ["receivers", groupId] });
    } catch (err) {
      setError(err as ApiError);
    }
  }

  return (
    <form onSubmit={(event) => void createReceiver(event)} className="toolbar">
      {error && <ErrorBanner error={error} />}
      <input
        placeholder="Nome receiver"
        required
        value={name}
        onChange={(event) => setName(event.target.value)}
      />
      <select
        value={defaultSeverity}
        onChange={(event) => setDefaultSeverity(event.target.value as Severity)}
      >
        {SEVERITIES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
      <button type="submit" className="primary">
        Aggiungi receiver
      </button>
    </form>
  );
}
