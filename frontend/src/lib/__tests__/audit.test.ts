import { describe, expect, it } from "vitest";
import { RESOURCE_TYPES, actionLabel, endOfDay, shortLabel, startOfDay } from "../audit";

const ISO_CON_OFFSET = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}$/;

describe("startOfDay / endOfDay", () => {
  it("il giorno scelto diventa un intervallo chiuso nel fuso del browser", () => {
    const da = startOfDay("2026-09-22");
    const a = endOfDay("2026-09-22");

    // Un istante con l'offset esplicito, non il giorno nudo che il backend
    // leggerebbe come mezzanotte nel fuso del server.
    expect(da).toMatch(ISO_CON_OFFSET);
    expect(a).toMatch(ISO_CON_OFFSET);
    expect(new Date(da as string).getTime()).toBe(new Date(2026, 8, 22, 0, 0, 0, 0).getTime());
    expect(new Date(a as string).getTime()).toBe(new Date(2026, 8, 22, 23, 59, 59, 999).getTime());
  });

  it("un evento di oggi sta fra Da=oggi e A=oggi", () => {
    const adesso = new Date();
    const oggi = `${adesso.getFullYear()}-${String(adesso.getMonth() + 1).padStart(2, "0")}-${String(
      adesso.getDate(),
    ).padStart(2, "0")}`;

    const da = new Date(startOfDay(oggi) as string).getTime();
    const a = new Date(endOfDay(oggi) as string).getTime();
    expect(da).toBeLessThanOrEqual(adesso.getTime());
    expect(a).toBeGreaterThanOrEqual(adesso.getTime());
  });

  it("un valore vuoto o malformato non diventa un filtro", () => {
    expect(startOfDay("")).toBeUndefined();
    expect(endOfDay(null)).toBeUndefined();
    expect(startOfDay("22/09/2026")).toBeUndefined();
  });
});

describe("shortLabel", () => {
  it("accorcia solo cio' che non sta nella cella", () => {
    expect(shortLabel("breve")).toBe("breve");
    const lungo = "x".repeat(200);
    expect(shortLabel(lungo)).toHaveLength(81);
    expect(shortLabel(lungo).endsWith("…")).toBe(true);
  });
});

describe("RESOURCE_TYPES", () => {
  it("comprende le risorse che il backend scrive nell'audit", () => {
    for (const tipo of [
      "group_channel_binding",
      "receiver_channel_override",
      "severity_preset_rule",
      "receiver_severity_preset",
      "session",
    ]) {
      expect(RESOURCE_TYPES).toContain(tipo);
    }
  });
});

describe("actionLabel", () => {
  it("le azioni esplicite (notifiche, accessi) hanno la loro etichetta", () => {
    expect(actionLabel("auth.login")).toBe("Accesso");
    expect(actionLabel("notification.marked_read")).toBe("Segnata come letta");
  });

  it("le azioni generiche `<risorsa>.<tipo>` si leggono in italiano", () => {
    expect(actionLabel("group.created")).toBe("Creazione: Gruppo");
    expect(actionLabel("receiver.updated")).toBe("Modifica: Receiver");
    expect(actionLabel("severity_preset_rule.deleted")).toBe("Eliminazione: Regola di preset");
  });

  it("ogni risorsa scritta dal backend ha un'etichetta per creazione, modifica ed eliminazione", () => {
    for (const tipo of RESOURCE_TYPES) {
      for (const tipoAzione of ["created", "updated", "deleted"]) {
        const azione = `${tipo}.${tipoAzione}`;
        expect(actionLabel(azione), azione).not.toBe(azione);
      }
    }
  });

  it("un'azione sconosciuta resta leggibile come codice", () => {
    expect(actionLabel("cosa.nuova")).toBe("cosa.nuova");
  });
});
