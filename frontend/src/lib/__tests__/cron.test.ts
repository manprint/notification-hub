// Validazione e preview delle espressioni cron dell'attesa dei receiver. Le
// regole ricalcano il backend (backend/tests/unit/test_surveillance.py ->
// test_validate_cron_*): accettare e rifiutare lo stesso set di espressioni.

import { describe, expect, it } from "vitest";
import {
  formatExecutionPreview,
  nextCronExecutions,
  validateCronExpression,
  validateTimezone,
} from "../cron";

describe("validateCronExpression", () => {
  it("T-CRON1 accetta espressioni valide a 5 campi", () => {
    const valide = ["0 3 * * 1-5", "*/5 * * * *", "0 0 * * 1"];
    for (const expr of valide) {
      expect(validateCronExpression(expr)).toBeNull();
    }
  });

  it("T-CRON2 rifiuta espressioni vuote o col numero di campi sbagliato", () => {
    const vuote = ["", "   "];
    for (const expr of vuote) {
      expect(validateCronExpression(expr)).toContain("vuota");
    }
    const troppiPochi = ["0 3 * *", "@daily"];
    for (const expr of troppiPochi) {
      expect(validateCronExpression(expr)).toContain("5 campi");
    }
    // Sempre 5 campi di parola, ma 6 campi fisici: non e' crontab standard.
    expect(validateCronExpression("0 3 * * * *")).toContain("5 campi");
  });

  it("T-CRON3 rifiuta espressioni illeggibili o con campi fuori range", () => {
    expect(validateCronExpression("99 3 * * *")).toContain("non valida");
    // Contano di piu' i 5 campi della sintassi: testo libero e gia' sbagliato
    // qui, con lo stesso messaggio del backend.
    expect(validateCronExpression("non un cron")).not.toBeNull();
    expect(validateCronExpression("0 3 * * * ; rm -rf /")).not.toBeNull();
  });

  it("T-CRON3b rifiuta le espressioni che non scattano mai, come il backend", () => {
    // Sintassi corretta ma nessuna data che le soddisfi: il 30 febbraio e il 31
    // aprile non esistono. Il backend le respinge con 422 ("non scatta mai"), e
    // il form non deve lasciarle salvare per poi mostrare l'errore del server.
    expect(validateCronExpression("0 0 30 2 *")).not.toBeNull();
    expect(validateCronExpression("0 0 31 4 *")).not.toBeNull();
    // Il 29 febbraio invece esiste (negli anni bisestili) ed e' accettato da
    // entrambi i lati: la regola e' "non scatta mai", non "scatta di rado".
    expect(validateCronExpression("0 0 29 2 *")).toBeNull();
  });

  // Tabella verificata contro il backend: ogni riga e' stata passata a
  // validate_cron (backend/app/services/surveillance.py, croniter 6.2) e a
  // questa funzione, con lo stesso esito. Serve a tenere il form allineato a
  // quello che il backend salva: prima cron-parser divergeva su meta' di questi.
  it.each([
    "0 3 * * *",
    "0 0 * * 7",
    "0 0 * * sun",
    "0 0 * * MON-FRI",
    "0 0 1 jan *",
    "0 0 L * *",
    "0 0 * * 1#2",
    "0 0 * * mon#2",
    "0 0 * * l3",
    "0 0 15W * *",
    "0 0 1W * *",
    "0 0 31W 2 *",
    "0 0 ? * *",
    "0 0 * * ?",
    "1/2 * * * *",
    "0 0 * * 1/2",
    "5-1 * * * *",
    "0 22-2 * * *",
    "0 0 * * 7-1",
    "0 0 * * fri-mon",
    "*/61 * * * *",
    "5-5 * * * *",
    "0 0 1,15 * 1",
    "0 0 15W * 1",
  ])("T-CRON8 accetta come il backend: %s", (expr) => {
    expect(validateCronExpression(expr)).toBeNull();
  });

  it.each([
    "0 0 * * 5L",
    "0 0 * * L",
    "0 0 * * 1L",
    "0 0 LW * *",
    "0 0 L-2 * *",
    "0 0 * * 2#6",
    "0 0 * * 1#2,3",
    "? * * * *",
    "*/0 * * * *",
    "0,,1 * * * *",
    "-1 * * * *",
    "60 * * * *",
    "* 24 * * *",
    "0 0 0 * *",
    "0 0 * 0 *",
    "0 0 * * 8",
  ])("T-CRON9 rifiuta come il backend: %s", (expr) => {
    expect(validateCronExpression(expr)).toContain("non valida");
  });

  it.each(["0 0 30 2 *", "0 0 31 4 *", "0 0 31 2,4 *", "0 0 30 2 1", "0 0 15 * 1#2"])(
    "T-CRON10 rifiuta come il backend le espressioni che non scattano mai: %s",
    (expr) => {
      expect(validateCronExpression(expr)).toContain("non scatta mai");
    },
  );

  it.each(["H * * * *", "H(0-5) * * * *", "R * * * *", "r/5 * * * *", "1,R * * * *"])(
    "T-CRON11 rifiuta H e R (orario casuale), come il backend: %s",
    (expr) => {
      expect(validateCronExpression(expr)).toMatch(/H e R/);
    },
  );

  it("T-CRON4 rifiuta le espressioni piu' lunghe della soglia", () => {
    const overlong = `0 ${"3".repeat(200)} * * *`;
    expect(validateCronExpression(overlong)).toContain("100 caratteri");
  });

  it("T-CRON5 convalida i fusi orari", () => {
    const noti = ["UTC", "Europe/Rome", "America/New_York"];
    for (const nome of noti) {
      expect(validateTimezone(nome)).toBeNull();
    }
    const estranei = ["", "  ", "Europa/Roma"];
    for (const nome of estranei) {
      expect(validateTimezone(nome)).not.toBeNull();
    }
  });
});

describe("nextCronExecutions", () => {
  const now = new Date("2026-08-05T12:00:00Z");

  it("T-CRON6 una cron che non scatta mai non solleva errori", () => {
    const occorrenze = nextCronExecutions("0 0 30 2 *", "UTC", now);
    expect(Array.isArray(occorrenze)).toBe(true);
  });

  it("T-CRON7 ritorna le prossime tre occorrenze in ordine crescente", () => {
    const occorrenze = nextCronExecutions("0 10 * * 1-5", "UTC", now);
    expect(occorrenze).toHaveLength(3);
    for (const data of occorrenze) {
      expect(data.getUTCHours()).toBe(10);
      const diff = data.getTime() - now.getTime();
      expect(diff).toBeGreaterThan(0);
      expect(diff).toBeLessThan(8 * 86_400_000);
    }
    expect(occorrenze[0].getTime())
      .toBeLessThan(occorrenze[1].getTime());
    expect(occorrenze[1].getTime())
      .toBeLessThan(occorrenze[2].getTime());
  });

  // Occorrenze calcolate dal backend (next_fire_after, applicato a catena come
  // fa questa anteprima) per gli stessi input. Coprono i punti in cui
  // cron-parser dava altre date: il cambio d'ora (orario saltato e orario
  // doppio), `1/2` nel giorno della settimana, gli intervalli che scavalcano la
  // fine del campo, W, L, # e l'OR fra giorno del mese e giorno della settimana.
  it.each([
    ["0 3 * * *", "Europe/Rome", "2026-03-28T12:00:00Z", ["2026-03-29T01:00:00Z", "2026-03-30T01:00:00Z", "2026-03-31T01:00:00Z"]],
    ["30 2 * * *", "Europe/Rome", "2026-03-28T20:00:00Z", ["2026-03-29T01:00:00Z", "2026-03-30T00:30:00Z", "2026-03-31T00:30:00Z"]],
    ["30 2 * * *", "Europe/Rome", "2026-10-24T20:00:00Z", ["2026-10-25T00:30:00Z", "2026-10-25T01:30:00Z", "2026-10-26T01:30:00Z"]],
    ["0 1 * * *", "America/New_York", "2026-10-31T20:00:00Z", ["2026-11-01T05:00:00Z", "2026-11-01T06:00:00Z", "2026-11-02T06:00:00Z"]],
    ["0 0 * * 1/2", "UTC", "2026-03-28T12:00:00Z", ["2026-03-30T00:00:00Z", "2026-04-01T00:00:00Z", "2026-04-03T00:00:00Z"]],
    ["0 0 * * fri-mon", "UTC", "2026-08-05T12:00:00Z", ["2026-08-07T00:00:00Z", "2026-08-08T00:00:00Z", "2026-08-09T00:00:00Z"]],
    ["0 22-2 * * *", "UTC", "2026-08-05T12:00:00Z", ["2026-08-05T22:00:00Z", "2026-08-05T23:00:00Z", "2026-08-06T00:00:00Z"]],
    ["0 0 15W * *", "UTC", "2026-08-01T12:00:00Z", ["2026-08-14T00:00:00Z", "2026-09-15T00:00:00Z", "2026-10-15T00:00:00Z"]],
    ["0 0 L * *", "UTC", "2026-01-30T12:00:00Z", ["2026-01-31T00:00:00Z", "2026-02-28T00:00:00Z", "2026-03-31T00:00:00Z"]],
    ["0 0 * * 1#2", "UTC", "2026-08-05T12:00:00Z", ["2026-08-10T00:00:00Z", "2026-09-14T00:00:00Z", "2026-10-12T00:00:00Z"]],
    ["0 0 1,15 * 1", "UTC", "2026-08-05T12:00:00Z", ["2026-08-10T00:00:00Z", "2026-08-15T00:00:00Z", "2026-08-17T00:00:00Z"]],
    ["0 0 29 2 *", "UTC", "2026-08-05T12:00:00Z", ["2028-02-29T00:00:00Z", "2032-02-29T00:00:00Z", "2036-02-29T00:00:00Z"]],
  ])("T-CRON12 %s in %s da %s: stesse date del backend", (expr, tz, start, attese) => {
    const occorrenze = nextCronExecutions(expr, tz, new Date(start));
    expect(occorrenze.map((d) => d.toISOString().replace(".000Z", "Z"))).toEqual(attese);
  });

  it("T-CRON13 un'espressione non valida o un fuso sconosciuto danno un'anteprima vuota", () => {
    expect(nextCronExecutions("0 0 * * 5L", "UTC", now)).toEqual([]);
    expect(nextCronExecutions("0 3 * * *", "Europa/Roma", now)).toEqual([]);
  });

  it("formatta le occorrenze nel fuso richiesto", () => {
    const data = new Date("2026-08-06T01:00:00Z"); // le 03:00 di Roma in agosto
    const aUtc = formatExecutionPreview(data, "UTC");
    const aRoma = formatExecutionPreview(data, "Europe/Rome");
    expect(aRoma).not.toEqual(aUtc);
  });
});