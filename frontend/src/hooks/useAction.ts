import { useCallback, useEffect, useRef, useState } from "react";
import { asApiError } from "../api/client";
import type { ApiError } from "../api/types";
import type { SaveState } from "../components/SaveIndicator";
import { problemMessage } from "../lib/problemMessages";
import { useToast } from "./useToast";

interface RunOptions {
  /** Messaggio del toast a operazione riuscita. Senza, non si mostra niente:
   *  è il caso delle azioni che hanno già un esito visibile a schermo. */
  success?: string;
  /** Nome dell'operazione in corso, per distinguere quale pulsante è occupato
   *  quando la stessa pagina ne ha più d'uno. */
  name?: string;
}

/** Quanto resta visibile "Salvato" prima che l'indicatore torni neutro. */
const SAVED_VISIBLE_MS = 2500;

/** Il giro che ogni scrittura fa: segna l'operazione in corso, cattura
 *  l'errore dell'API come ApiError, avvisa dell'esito.
 *
 *  L'errore resta anche nello stato (per il banner in linea, che dà il
 *  dettaglio e non sparisce dopo cinque secondi): il toast dice che è successo
 *  qualcosa, il banner dice cosa.
 *
 *  Più operazioni possono essere in corso insieme (due righe salvate a breve
 *  distanza): `busy` resta occupato finché non finisce l'ultima, e l'esito
 *  complessivo arriva quando sono finite tutte. */
export function useAction() {
  const toast = useToast();
  // Nomi delle operazioni in corso, in ordine di partenza: `busy` è l'ultima.
  const [active, setActive] = useState<string[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const pending = useRef(0);
  const batchFailed = useRef(false);
  const resetTimer = useRef<number | null>(null);

  const cancelReset = useCallback(() => {
    if (resetTimer.current !== null) {
      window.clearTimeout(resetTimer.current);
      resetTimer.current = null;
    }
  }, []);

  // Un timer sopravvissuto allo smontaggio scriverebbe stato su un componente
  // che non c'è più (cambio pagina subito dopo un salvataggio).
  useEffect(() => cancelReset, [cancelReset]);

  const run = useCallback(
    async (action: () => Promise<unknown>, options: RunOptions = {}): Promise<boolean> => {
      const name = options.name ?? "action";
      // Il ritorno a "idle" programmato da un salvataggio precedente non deve
      // scattare durante (o subito dopo) questo: cancellerebbe il suo esito.
      cancelReset();
      if (pending.current === 0) batchFailed.current = false;
      pending.current += 1;
      setError(null);
      setActive((names) => [...names, name]);
      setSaveState("saving");
      try {
        await action();
        if (options.success) toast.success(options.success);
        return true;
      } catch (err) {
        const apiError = asApiError(err);
        batchFailed.current = true;
        setError(apiError);
        toast.error(problemMessage(apiError));
        return false;
      } finally {
        pending.current -= 1;
        setActive((names) => {
          const index = names.indexOf(name);
          return index === -1 ? names : [...names.slice(0, index), ...names.slice(index + 1)];
        });
        // Finché un'altra operazione è in corso l'indicatore resta su
        // "Salvataggio…": dire "Salvato" a metà sarebbe falso.
        if (pending.current === 0) {
          if (batchFailed.current) {
            setSaveState("failed");
          } else {
            setSaveState("saved");
            // L'indicatore in linea torna neutro da solo: resta il tempo di essere
            // notato, non diventa una decorazione permanente della riga.
            resetTimer.current = window.setTimeout(() => {
              resetTimer.current = null;
              setSaveState("idle");
            }, SAVED_VISIBLE_MS);
          }
        }
      }
    },
    [toast, cancelReset],
  );

  const clearError = useCallback(() => setError(null), []);

  const busy = active.length > 0 ? active[active.length - 1] : null;
  return { busy, error, saveState, run, clearError };
}
