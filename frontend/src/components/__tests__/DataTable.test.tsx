import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import DataTable, { type DataTableColumn } from "../DataTable";

interface Riga {
  id: string;
  nome: string;
}

const colonne: DataTableColumn<Riga>[] = [
  { key: "nome", header: "Nome", render: (r) => r.nome },
  { key: "azioni", header: "", render: () => <button>Rimuovi</button> },
];

const righe: Riga[] = [{ id: "1", nome: "Alfa" }];

describe("DataTable", () => {
  it("durante il caricamento non dice che non c'è niente", () => {
    render(
      <DataTable
        columns={colonne}
        rows={[]}
        rowKey={(r) => r.id}
        loading
        emptyMessage="Nessun gruppo configurato."
      />,
    );
    expect(screen.getByText("Caricamento…")).toBeInTheDocument();
    expect(screen.queryByText("Nessun gruppo configurato.")).toBeNull();
  });

  it("con l'elenco vuoto mostra il messaggio di vuoto", () => {
    render(
      <DataTable
        columns={colonne}
        rows={[]}
        rowKey={(r) => r.id}
        emptyMessage="Nessun gruppo configurato."
      />,
    );
    expect(screen.getByText("Nessun gruppo configurato.")).toBeInTheDocument();
  });

  it("dopo un errore con l'elenco vuoto non dice «nessun risultato»", () => {
    render(
      <DataTable
        columns={colonne}
        rows={[]}
        rowKey={(r) => r.id}
        error={{ status: 500, title: "Errore", detail: "", type: "/problems/internal-error" }}
        emptyMessage="Nessuna consegna trovata."
      />,
    );
    expect(screen.queryByText("Nessuna consegna trovata.")).toBeNull();
    expect(screen.getByText(/Elenco non disponibile/)).toBeInTheDocument();
  });

  it("con righe mostra la tabella con nome e intestazioni accessibili", () => {
    render(
      <DataTable
        columns={colonne}
        rows={righe}
        rowKey={(r) => r.id}
        caption="Gruppi"
      />,
    );
    expect(screen.getByRole("table", { name: "Gruppi" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Nome" })).toBeInTheDocument();
    // La colonna senza intestazione (le azioni) ha un nome per chi legge lo schermo.
    expect(screen.getByRole("columnheader", { name: "Azioni" })).toBeInTheDocument();
    expect(screen.getByText("Alfa")).toBeInTheDocument();
  });

  it("«Carica altri» richiama onLoadMore una volta per click", async () => {
    const onLoadMore = vi.fn();
    render(
      <DataTable
        columns={colonne}
        rows={righe}
        rowKey={(r) => r.id}
        hasMore
        onLoadMore={onLoadMore}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Carica altri" }));
    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });
});
