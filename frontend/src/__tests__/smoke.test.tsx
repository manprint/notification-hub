import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

function Hello() {
  return <p>Ciao NotifyHub</p>;
}

describe("smoke", () => {
  it("renderizza un componente banale", () => {
    render(<Hello />);
    expect(screen.getByText("Ciao NotifyHub")).toBeInTheDocument();
  });
});
