import type { ReactNode } from "react";
import EmptyState from "./EmptyState";

export interface DataTableColumn<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
}

interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  loading?: boolean;
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
  emptyMessage = "Nessun risultato.",
  hasMore,
  onLoadMore,
  loadingMore,
}: DataTableProps<T>) {
  if (loading) {
    return <EmptyState message="Caricamento…" />;
  }

  if (rows.length === 0) {
    return <EmptyState message={emptyMessage} />;
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key}>{column.header}</th>
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
