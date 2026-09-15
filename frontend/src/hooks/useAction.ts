import { useCallback, useRef, useState } from "react";
import type { ApiError } from "../api/types";
import type { SaveState } from "../components/SaveIndicator";
import { useToast } from "./useToast";

interface RunOptions {
  /** Messaggio del toast a operazione riuscita. Senza, non si mostra niente:
   *  è il caso delle azioni che hanno già un esito visibile a schermo. */
  success?: string;
  /** Nome dell'operazione in corso, per distinguere quale pulsante è occupato
   *  quando la stessa pagina ne ha più d'uno. */
  name?: string;
}

/** Il giro che ogni scrittura fa: segna l'operazione in corso, cattura
 *  l'errore dell'API come ApiError, avvisa dell'esito.
 *
 *  L'errore resta anche nello stato (per il banner in linea, che dà il
 *  dettaglio e non sparisce dopo cinque secondi): il toast dice che è successo
 *  qualcosa, il banner dice cosa. */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const timers = useRef<number[]>([]);

  const run = useCallback(
    async (action: () => Promise<unknown>, options: RunOptions = {}): Promise<boolean> => {
      setError(null);
      setBusy(options.name ?? "action");
      setSaveState("saving");
      try {
        await action();
        setSaveState("saved");
        // L'indicatore in linea torna neutro da solo: resta il tempo di essere
        // notato, non diventa una decorazione permanente della riga.
        timers.current.push(window.setTimeout(() => setSaveState("idle"), 2500));
        if (options.success) toast.success(options.success);
        return true;
      } catch (err) {
        const apiError = err as ApiError;
        setError(apiError);
        setSaveState("failed");
        toast.error(apiError.detail || apiError.title || "Operazione non riuscita.");
        return false;
      } finally {
        setBusy(null);
      }
    },
    [toast],
  );

  const clearError = useCallback(() => setError(null), []);

  return { busy, error, saveState, run, clearError };
}
