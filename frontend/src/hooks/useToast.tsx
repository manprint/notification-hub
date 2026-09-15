import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type ToastKind = "success" | "error" | "info";

interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

export interface ToastApi {
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

/** Quanto resta a schermo un avviso prima di sparire da solo. Abbastanza per
 *  leggerlo senza costringere a chiuderlo, e comunque richiudibile a mano. */
const AUTO_DISMISS_MS = 5000;

const ICONS: Record<ToastKind, string> = { success: "✓", error: "!", info: "i" };

/** Avvisi di esito per le operazioni che scrivono.
 *
 *  Senza, l'unica differenza fra "salvato" e "non è successo niente" è che i
 *  campi tornano al valore del server — cioè nessuna differenza visibile se il
 *  valore era già quello. Gli errori continuano a comparire anche in linea
 *  (ErrorBanner) dove il contesto conta: il toast è il riscontro immediato, il
 *  banner è il dettaglio che resta. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);
  const timers = useRef<number[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback(
    (kind: ToastKind, message: string) => {
      const id = nextId.current++;
      setToasts((prev) => [...prev, { id, kind, message }]);
      const timer = window.setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
      timers.current.push(timer);
    },
    [dismiss],
  );

  // I timer sopravviverebbero allo smontaggio (cambio pagina, fine di un test)
  // e scriverebbero stato su un componente che non c'è più.
  useEffect(() => {
    const pending = timers.current;
    return () => {
      for (const timer of pending) window.clearTimeout(timer);
    };
  }, []);

  const api = useMemo<ToastApi>(
    () => ({
      success: (message: string) => push("success", message),
      error: (message: string) => push("error", message),
      info: (message: string) => push("info", message),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-stack" aria-live="polite" aria-atomic="false">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast-${toast.kind}`} role="status">
            <span className="toast-icon" aria-hidden="true">
              {ICONS[toast.kind]}
            </span>
            <span className="toast-message">{toast.message}</span>
            <button
              type="button"
              className="toast-close"
              aria-label="Chiudi l'avviso"
              onClick={() => dismiss(toast.id)}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

const NO_TOASTS: ToastApi = {
  success: () => undefined,
  error: () => undefined,
  info: () => undefined,
};

/** Fuori dal provider non solleva: un componente montato da solo (in un test,
 *  o in una pagina di errore) deve poter funzionare senza avvisi. */
export function useToast(): ToastApi {
  return useContext(ToastContext) ?? NO_TOASTS;
}
