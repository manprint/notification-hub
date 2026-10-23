import type { ReactNode } from "react";
import EmptyState from "./EmptyState";

export interface DataTableColumn<T> {
  key: string;
  /** Vuota per le colonne delle azioni: a schermo non si legge, ma chi usa
   *  uno screen reader sente "Azioni" invece di una colonna senza nome. */
  header: string;
  render: (row: T) => ReactNode;
}

interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  loading?: boolean;
  /** Errore della query. Con l'elenco vuoto non si dice "nessun risultato"
   *  (sarebbe falso): il banner dell'errore lo mostra la pagina. */
  error?: unknown;
  /** Nome della tabella per chi legge lo schermo (una didascalia nascosta). */
  caption?: string;
  emptyMessage?: string;
  hasMore?: boolean;
  onLoadMore?: () => void;
  loadingMore?: boolean;
}

// Paginazione a cursore soltanto: l'API non supporta la pagina per numero,
// quindi qui non compare mai un controllo "pagina N".
export default function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  error,
  caption,
  emptyMessage = "Nessun risultato.",
  hasMore,
  onLoadMore,
  loadingMore,
}: DataTableProps<T>) {
  if (loading) {
    return <EmptyState message="Caricamento…" />;
  }

  if (rows.length === 0) {
    if (error) {
      return <EmptyState message="Elenco non disponibile per un errore di caricamento." />;
    }
    return <EmptyState message={emptyMessage} />;
  }

  return (
    <div className="table-wrap">
      <table>
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col">
                {column.header || <span className="sr-only">Azioni</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => (
                <td key={column.key}>{column.render(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {hasMore && (
        <div className="table-more">
          <button onClick={onLoadMore} disabled={loadingMore}>
            {loadingMore ? "Caricamento…" : "Carica altri"}
          </button>
        </div>
      )}
    </div>
  );
}
