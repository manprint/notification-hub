import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import GroupList from "../GroupList";
import type { GroupOut } from "../../api/types";

const groups: GroupOut[] = [
  {
    id: "g1",
    name: "Server Produzione",
    description: "Ambiente di produzione",
    receiver_count: 1,
  },
  { id: "g2", name: "Backup", description: null, receiver_count: 0 },
];

describe("GroupList", () => {
  it("group_list_renders_name_and_description: mostra nome e descrizione", () => {
    render(<GroupList groups={groups} onSelect={() => {}} />);
    expect(screen.getByText("Server Produzione")).not.toBeNull();
    expect(screen.getByText("Ambiente di produzione")).not.toBeNull();
  });

  it("group_list_fires_onSelect_with_id: il click chiama onSelect con l'id del gruppo", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<GroupList groups={groups} onSelect={onSelect} />);

    await user.click(screen.getByRole("button", { name: /server produzione/i }));

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith("g1");
  });

  it("group_list_hides_empty_description: non rende la descrizione se vuota", () => {
    const noDesc: GroupOut[] = [{ id: "g2", name: "Backup", description: null, receiver_count: 0 }];
    const { container } = render(<GroupList groups={noDesc} onSelect={() => {}} />);
    expect(container.querySelector(".group-card-desc")).toBeNull();
  });

  it("group_list_empty_message: mostra il messaggio quando non ci sono gruppi", () => {
    render(<GroupList groups={[]} onSelect={() => {}} />);
    expect(screen.getByText("Nessun gruppo configurato.")).not.toBeNull();
  });

  it("group_list_loading: mostra Caricamento… quando in caricamento", () => {
    render(<GroupList groups={[]} onSelect={() => {}} loading />);
    expect(screen.getByText("Caricamento…")).not.toBeNull();
  });

  it("group_list_search_filters_by_name: la ricerca filtra per nome", async () => {
    const user = userEvent.setup();
    render(<GroupList groups={groups} onSelect={() => {}} />);

    await user.type(screen.getByLabelText("Cerca gruppi"), "backup");

    expect(screen.queryByRole("button", { name: /server produzione/i })).toBeNull();
    expect(screen.getByRole("button", { name: /backup/i })).not.toBeNull();
  });

  it("group_list_search_filters_by_description: la ricerca filtra anche per descrizione", async () => {
    const user = userEvent.setup();
    render(<GroupList groups={groups} onSelect={() => {}} />);

    await user.type(screen.getByLabelText("Cerca gruppi"), "produzione");

    expect(screen.getByRole("button", { name: /server produzione/i })).not.toBeNull();
    expect(screen.queryByRole("button", { name: /backup/i })).toBeNull();
  });

  it("group_list_search_no_match: nessun risultato mostra il messaggio dedicato", async () => {
    const user = userEvent.setup();
    render(<GroupList groups={groups} onSelect={() => {}} />);

    await user.type(screen.getByLabelText("Cerca gruppi"), "inesistente");

    expect(screen.getByText("Nessun gruppo corrisponde alla ricerca.")).not.toBeNull();
    expect(screen.queryByRole("button", { name: /server produzione/i })).toBeNull();
  });
});