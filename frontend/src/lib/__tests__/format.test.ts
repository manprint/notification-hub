// Le formattazioni condivise: prima stavano copiate in ogni pagina, e la stessa
// data si leggeva in tre modi diversi in tre schermate.

import { describe, expect, it } from "vitest";
import {
  channelTypeLabel,
  formatBytes,
  formatDate,
  formatDateTime,
  formatInstantOr,
  formatTime,
  roleLabel,
  userStatusLabel,
} from "../format";

describe("format", () => {
  it("un valore assente diventa un trattino, non «Invalid Date»", () => {
    for (const vuoto of [null, undefined, ""]) {
      expect(formatDateTime(vuoto)).toBe("—");
      expect(formatDate(vuoto)).toBe("—");
      expect(formatTime(vuoto)).toBe("—");
    }
  });

  it("una data illeggibile diventa un trattino", () => {
    // Un campo che arriva sporco non deve stampare "Invalid Date" in tabella.
    expect(formatDateTime("non-una-data")).toBe("—");
    expect(formatDate("non-una-data")).toBe("—");
    expect(formatTime("non-una-data")).toBe("—");
  });

  it("formatta data e ora in italiano", () => {
    const testo = formatDateTime("2026-08-05T03:30:00Z");
    // Giorno/mese/anno, non il formato ISO né quello americano.
    expect(testo).toMatch(/^05\/08\/2026/);
    expect(formatDate("2026-08-05T03:30:00Z")).toBe("05/08/2026");
  });

  it("formatInstantOr distingue «vuoto» da «non disponibile»", () => {
    // Su un receiver che non ha mai inviato, il vuoto ha un significato: va
    // detto con la parola giusta, non con un trattino generico.
    expect(formatInstantOr(null, "mai")).toBe("mai");
    expect(formatInstantOr(undefined, "mai")).toBe("mai");
    expect(formatInstantOr("2026-08-05T03:30:00Z", "mai")).toMatch(/^05\/08\/2026/);
  });

  it("le dimensioni salgono di unità e restano leggibili", () => {
    expect(formatBytes(0)).toBe("0 byte");
    expect(formatBytes(512)).toBe("512 byte");
    expect(formatBytes(1024)).toBe("1 kB");
    expect(formatBytes(1048576)).toBe("1 MB");
    expect(formatBytes(1073741824)).toBe("1 GB");
    // Oltre l'ultima unità non si inventa un nome: resta in GB.
    expect(formatBytes(1024 * 1024 * 1024 * 1024)).toBe("1024 GB");
  });

  it("arrotonda a un decimale sopra il byte", () => {
    expect(formatBytes(1536)).toBe("1,5 kB");
    expect(formatBytes(1500)).toBe("1,5 kB");
  });

  it("ruoli e stati si leggono in italiano, i valori sconosciuti passano così come sono", () => {
    expect(roleLabel("owner")).toBe("Proprietario");
    expect(roleLabel("viewer")).toBe("Sola lettura");
    expect(userStatusLabel("invited")).toBe("Invitata");
    // Un valore nuovo lato server non deve diventare "undefined" a video.
    expect(userStatusLabel("qualcosa_di_nuovo")).toBe("qualcosa_di_nuovo");
    expect(channelTypeLabel("google_chat")).toBe("Google Chat");
    expect(channelTypeLabel("slack")).toBe("Slack");
    expect(channelTypeLabel("teams")).toBe("teams");
  });
});
