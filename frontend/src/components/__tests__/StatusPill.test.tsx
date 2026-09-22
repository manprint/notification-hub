import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DeliveryStatus } from "../../api/types";
import StatusPill, { statusLabel } from "../StatusPill";

describe("StatusPill", () => {
  it("mostra l'etichetta italiana di uno stato noto", () => {
    render(<StatusPill status="dead" />);
    expect(screen.getByText("Morta")).toHaveClass("status-pill", "danger");
  });

  it("uno stato sconosciuto si legge come codice grezzo, non come pill vuota", () => {
    // Il backend ha aggiunto uno stato che questa versione della dashboard non
    // conosce ancora.
    const nuovo = "archived" as DeliveryStatus;
    const { container } = render(<StatusPill status={nuovo} />);

    const pill = container.querySelector(".status-pill");
    expect(pill).toHaveTextContent("archived");
    expect(pill?.className).toBe("status-pill");
    expect(statusLabel(nuovo)).toBe("archived");
  });
});
