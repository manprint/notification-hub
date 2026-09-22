import { describe, expect, it } from "vitest";
import { safeRedirectTarget } from "../redirect";

describe("safeRedirectTarget", () => {
  it("tiene i percorsi interni con query e frammento", () => {
    expect(safeRedirectTarget("/notifications/n1")).toBe("/notifications/n1");
    expect(safeRedirectTarget("/deliveries?status=dead#riga")).toBe("/deliveries?status=dead#riga");
  });

  it("rifiuta tutto ciò che porterebbe fuori dall'applicazione", () => {
    // "//host" e "/\host" il browser li legge come indirizzi di un altro sito.
    for (const esterno of ["//evil.example", "/\\evil.example", "https://evil.example", "evil"]) {
      expect(safeRedirectTarget(esterno)).toBe("/");
    }
  });

  it("senza un valore utilizzabile, o verso il login stesso, va alla home", () => {
    expect(safeRedirectTarget(undefined)).toBe("/");
    expect(safeRedirectTarget(42)).toBe("/");
    expect(safeRedirectTarget("/login")).toBe("/");
    expect(safeRedirectTarget("/login?x=1")).toBe("/");
  });
});
