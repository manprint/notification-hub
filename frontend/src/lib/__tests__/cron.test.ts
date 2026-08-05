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

  it("formatta le occorrenze nel fuso richiesto", () => {
    const data = new Date("2026-08-06T01:00:00Z"); // le 03:00 di Roma in agosto
    const aUtc = formatExecutionPreview(data, "UTC");
    const aRoma = formatExecutionPreview(data, "Europe/Rome");
    expect(aRoma).not.toEqual(aUtc);
  });
});