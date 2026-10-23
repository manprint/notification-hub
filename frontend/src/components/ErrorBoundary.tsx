import { Component, type ErrorInfo, type ReactNode } from "react";

/** Chiave di sessione: il ricaricamento automatico per un chunk mancante si fa
 *  una sola volta, altrimenti una pagina rotta ricaricherebbe all'infinito. */
const CHUNK_RELOAD_KEY = "notifyhub.chunk_reload";

/** Il browser non trova più il file di una pagina lazy: succede quando
 *  NotifyHub viene aggiornato mentre la scheda è aperta (il bundle vecchio
 *  chiede file che non esistono più). */
function isChunkLoadError(error: unknown): boolean {
  const text = error instanceof Error ? `${error.name} ${error.message}` : String(error);
  return /ChunkLoadError|Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(
    text,
  );
}

/** Ricarica al massimo una volta per sessione. Senza storage disponibile non
 *  ricarica da sola: resta il pulsante. */
function reloadOnceForChunk(): boolean {
  try {
    if (sessionStorage.getItem(CHUNK_RELOAD_KEY) !== null) return false;
    sessionStorage.setItem(CHUNK_RELOAD_KEY, "1");
    return true;
  } catch {
    return false;
  }
}

interface ErrorBoundaryProps {
  children: ReactNode;
  /** Cambia con la pagina: al cambio il confine torna a mostrare i figli. */
  resetKey?: string;
}

interface ErrorBoundaryState {
  failed: boolean;
}

/** Un errore di rendering o un caricamento di pagina fallito non deve lasciare
 *  la schermata bianca: mostra cosa è successo e come ripartire. */
export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { failed: true };
  }

  componentDidCatch(error: unknown, _info: ErrorInfo): void {
    if (isChunkLoadError(error) && reloadOnceForChunk()) {
      window.location.reload();
    }
  }

  componentDidUpdate(previous: ErrorBoundaryProps): void {
    if (this.state.failed && previous.resetKey !== this.props.resetKey) {
      this.setState({ failed: false });
    }
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="app-fallback" role="alert">
        <h1>Questa pagina non si è caricata</h1>
        <p>
          Può succedere dopo un aggiornamento di NotifyHub con la scheda ancora aperta. Ricarica la
          pagina per continuare: quello che non era salvato va rifatto.
        </p>
        <button type="button" className="primary" onClick={() => window.location.reload()}>
          Ricarica la pagina
        </button>
      </div>
    );
  }
}
