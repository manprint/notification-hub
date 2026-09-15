import { useEffect, useState } from "react";

/** Valore che si aggiorna solo quando chi scrive si ferma.
 *
 *  Serve ai campi di ricerca legati a una query: senza, ogni tasto premuto
 *  faceva partire una richiesta e la risposta della penultima poteva arrivare
 *  dopo l'ultima. */
export function useDebounced<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
