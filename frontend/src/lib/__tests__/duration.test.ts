// Le durate si scrivono in tre posti (wrapper bash, backend Python, dashboard) e
// devono leggersi uguali: la stessa esecuzione vista in un log di cron, su Slack e
// in dashboard non puo' mostrare tre numeri scritti in tre modi.
//
// Le tabelle qui sotto sono le stesse dei test Python:
//   backend/tests/unit/test_outbound.py        -> format_duration_ms
//   backend/tests/unit/test_surveillance.py    -> format_seconds

import { describe, expect, it } from "vitest";
import {
  DURATION_UNIT_LABELS,
  type DurationUnit,
  formatDurationMs,
  formatDurationSeconds,
  INT4_MAX,
  formatIntervalSeconds,
  maxAmount,
  parseDurationInput,
  parseIntegerInput,
  splitDuration,
  toSeconds,
} from "../duration";
import { SEVERITY_SOURCE_LABELS, isSurveillanceSource, phaseLabel } from "../severitySource";
import type { SeveritySource } from "../../api/types";

describe("formatDurationMs", () => {
  it.each([
    [0, "0.000s"],
    [1, "0.001s"],
    [750, "0.750s"],
    [59_999, "59.999s"],
    [60_000, "1m00s"],
    [750_123, "12m30s"],
    [3_723_000, "1h02m03s"],
  ])("%i ms -> %s", (ms, atteso) => {
    expect(formatDurationMs(ms)).toBe(atteso);
  });

  it("una durata negativa non esiste: vale zero, non un numero col meno", () => {
    expect(formatDurationMs(-5)).toBe("0.000s");
  });
});

describe("formatIntervalSeconds", () => {
  // Stessa resa di format_seconds in app/services/surveillance.py, che e' quella
  // scritta dentro le notifiche di assenza.
  it.each([
    [0, "0s"],
    [45, "45s"],
    [90, "1m30s"],
    [3600, "1h00m"],
    [5430, "1h30m"],
    [86_400, "1g"],
    [97_200, "1g03h"],
    [604_800, "7g"],
  ])("%i s -> %s", (secondi, atteso) => {
    expect(formatIntervalSeconds(secondi)).toBe(atteso);
  });
});

describe("splitDuration e toSeconds", () => {
  it.each([
    [null, "", "m"],
    [30, "30", "s"],
    [600, "10", "m"],
    [7200, "2", "h"],
    [86_400, "1", "g"],
    [90, "90", "s"], // non divisibile per 60: resta in secondi
  ])("%s secondi -> %s %s", (secondi, amount, unit) => {
    expect(splitDuration(secondi as number | null)).toEqual({ amount, unit });
  });

  it("andata e ritorno: quello che il form mostra e' quello che salva", () => {
    for (const secondi of [1, 59, 60, 600, 3600, 86_400, 604_800]) {
      const { amount, unit } = splitDuration(secondi);
      expect(toSeconds(Number(amount), unit)).toBe(secondi);
    }
  });

  it("ogni unita' del menu ha un'etichetta", () => {
    const unita: DurationUnit[] = ["s", "m", "h", "g"];
    for (const unit of unita) {
      expect(DURATION_UNIT_LABELS[unit]).toBeTruthy();
    }
  });

  it("formatDurationSeconds resta al millisecondo, non al giorno", () => {
    // Serve alla soglia di durata, che si ragiona in minuti: 86400 la' e' "24h",
    // non "1g" come per gli intervalli dell'attesa.
    expect(formatDurationSeconds(600)).toBe("10m00s");
    expect(formatDurationSeconds(86_400)).toBe("24h00m00s");
  });
});

describe("etichette delle origini", () => {
  it("ogni valore di severity_source ha un'etichetta italiana", () => {
    // L'elenco rispecchia l'enum del backend (app/db/types.py): se ne nasce uno
    // nuovo, questo test costringe a dargli un nome leggibile invece di lasciare
    // in dashboard la stringa grezza.
    const fonti: SeveritySource[] = [
      "explicit",
      "exit_code",
      "duration",
      "missing",
      "recovered",
      "rule",
      "preset_rule",
      "receiver_default",
    ];
    for (const fonte of fonti) {
      expect(SEVERITY_SOURCE_LABELS[fonte], fonte).toBeTruthy();
    }
  });

  it("solo assenza e ripresa sono scritte dal server", () => {
    expect(isSurveillanceSource("missing")).toBe(true);
    expect(isSurveillanceSource("recovered")).toBe(true);
    expect(isSurveillanceSource("rule")).toBe(false);
    expect(isSurveillanceSource("explicit")).toBe(false);
  });

  it("la fase non dichiarata non ha etichetta", () => {
    expect(phaseLabel(null)).toBeNull();
    expect(phaseLabel("start")).toBe("avvio");
    expect(phaseLabel("end")).toBe("conclusione");
  });
});

// I campi interi del receiver finiscono in colonne integer di PostgreSQL: il
// backend li chiude a 2147483647 (contratto C8). Il modulo deve fermarsi prima,
// con un messaggio, invece di mandare un 422 o salvare 0 al posto del vuoto.
describe("parseIntegerInput", () => {
  it.each([
    ["60", 60],
    [" 0 ", 0],
    ["2147483647", INT4_MAX],
  ])("accetta %j", (raw, atteso) => {
    expect(parseIntegerInput(raw, { min: 0 })).toEqual({ ok: true, value: atteso });
  });

  it.each([
    ["", /Campo obbligatorio/],
    ["abc", /Non è un numero valido/],
    ["2147483648", /massimo è 2147483647/],
    ["1e308", /massimo è 2147483647/],
    ["Infinity", /massimo è 2147483647/],
    ["-Infinity", /Non è un numero valido/],
    ["1.5", /intero/],
    ["-1", /minimo è 0/],
  ])("rifiuta %j", (raw, messaggio) => {
    const esito = parseIntegerInput(raw, { min: 0 });
    expect(esito.ok).toBe(false);
    if (!esito.ok) expect(esito.error).toMatch(messaggio);
  });

  it("usa il messaggio del chiamante per il campo vuoto", () => {
    expect(parseIntegerInput("  ", { min: 0, empty: "Indica il rate limit." })).toEqual({
      ok: false,
      error: "Indica il rate limit.",
    });
  });
});

describe("parseDurationInput", () => {
  it.each([
    ["1.5", "h", 5400],
    ["0.7", "m", 42],
    ["24855", "g", 24855 * 86400],
    ["2147483647", "s", INT4_MAX],
    ["0", "s", 0],
  ] as [string, DurationUnit, number][])("%s %s = %d secondi", (raw, unita, atteso) => {
    expect(parseDurationInput(raw, unita, { minSeconds: 0 })).toEqual({ ok: true, value: atteso });
  });

  it.each([
    ["30000", "g", /massimo è 24855 giorni \(2147483647 secondi\)/],
    ["1e308", "s", /Troppo grande/],
    ["0.5", "s", /numero intero di secondi/],
    ["", "m", /Campo obbligatorio/],
    ["x", "m", /Non è un numero valido/],
  ] as [string, DurationUnit, RegExp][])("rifiuta %s %s", (raw, unita, messaggio) => {
    const esito = parseDurationInput(raw, unita, { minSeconds: 0 });
    expect(esito.ok).toBe(false);
    if (!esito.ok) expect(esito.error).toMatch(messaggio);
  });

  it("dice il minimo in forma leggibile", () => {
    expect(parseDurationInput("0", "m", { minSeconds: 1 })).toEqual({
      ok: false,
      error: "Il minimo è 1s.",
    });
    expect(parseDurationInput("-1", "m", { minSeconds: 0 })).toEqual({
      ok: false,
      error: "Non può essere negativa.",
    });
  });

  it("il massimo per unita' non supera mai INT4_MAX secondi", () => {
    for (const unita of ["s", "m", "h", "g"] as DurationUnit[]) {
      expect(toSeconds(maxAmount(unita), unita)).toBeLessThanOrEqual(INT4_MAX);
      expect(toSeconds(maxAmount(unita) + 1, unita)).toBeGreaterThan(INT4_MAX);
    }
  });
});
