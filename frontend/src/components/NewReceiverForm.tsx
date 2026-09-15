import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiPost } from "../api/client";
import type { Severity } from "../api/types";
import ErrorBanner from "./ErrorBanner";
import Field, { RequiredLegend, fieldAria } from "./Field";
import { useAction } from "../hooks/useAction";

const SEVERITIES: Severity[] = ["critical", "error", "warning", "info", "debug"];

export default function NewReceiverForm({ groupId }: { groupId: string }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [defaultSeverity, setDefaultSeverity] = useState<Severity>("info");
  const [nameError, setNameError] = useState<string | null>(null);
  const { busy, error, run } = useAction();

  async function createReceiver(event: React.FormEvent) {
    event.preventDefault();
    if (name.trim() === "") {
      setNameError("Il nome del receiver è obbligatorio.");
      return;
    }
    setNameError(null);
    const ok = await run(
      async () => {
        await apiPost(`/api/v1/groups/${groupId}/receivers`, {
          name: name.trim(),
          default_severity: defaultSeverity,
        });
        await queryClient.invalidateQueries({ queryKey: ["receivers", groupId] });
      },
      { success: `Receiver "${name.trim()}" creato.` },
    );
    if (ok) {
      setName("");
      setDefaultSeverity("info");
    }
  }

  return (
    <details className="card collapsible">
      <summary>Nuovo receiver</summary>
      <p className="card-hint">
        Un receiver è un punto di invio: riceve i messaggi di un job e ha il suo slug, le sue regole
        di severity e la sua sorveglianza dell'attesa.
      </p>
      {error && <ErrorBanner error={error} />}
      <form className="form-stacked" onSubmit={(event) => void createReceiver(event)}>
        <RequiredLegend />
        <Field id="new-receiver-name" label="Nome receiver" required error={nameError}>
          <input
            {...fieldAria("new-receiver-name", { error: nameError })}
            required
            maxLength={120}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field
          id="new-receiver-severity"
          label="Severity di default"
          hint="Vale per i messaggi che nessuna regola classifica. Si cambia anche dopo."
        >
          <select
            {...fieldAria("new-receiver-severity", { hint: true })}
            value={defaultSeverity}
            onChange={(event) => setDefaultSeverity(event.target.value as Severity)}
          >
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </Field>
        <div className="form-actions">
          <button type="submit" className="primary" disabled={busy !== null}>
            {busy !== null ? "Creazione…" : "Aggiungi receiver"}
          </button>
        </div>
      </form>
    </details>
  );
}
