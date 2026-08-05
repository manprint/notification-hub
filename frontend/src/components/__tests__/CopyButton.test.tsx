import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import CopyButton from "../CopyButton";
import { copyText } from "../../lib/clipboard";

vi.mock("../../lib/clipboard", () => ({
  copyText: vi.fn().mockResolvedValue(undefined),
}));

describe("CopyButton", () => {
  it("T-GRP3 test_copia_clipboard: scrive il valore completo e mostra Copiato!", async () => {
    const user = userEvent.setup();
    const value = "maritime-backup-notturno-Kj8mQ2xN7vB4pR9wLs3tYc";
    render(<CopyButton value={value} />);

    await user.click(screen.getByRole("button", { name: "Copia" }));

    expect(copyText).toHaveBeenCalledWith(value);
    expect(await screen.findByText("Copiato!")).toBeInTheDocument();
  });
});