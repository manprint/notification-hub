// Etichette di `severity_source`: chi ha deciso la severity di una notifica.
// Stanno qui e non in un solo componente perche' compaiono in tre posti che
// devono dire la stessa cosa: il riassunto della catena sul receiver, l'elenco
// delle notifiche e il dettaglio.
//
// `missing` e `recovered` non sono passi della catena: sono notifiche scritte dal
// server (sorveglianza dell'attesa, job check_expected_schedules), e l'etichetta
// deve renderlo evidente a chi le legge in elenco.

import type { SeveritySource } from "../api/types";

export const SEVERITY_SOURCE_LABELS: Record<string, string> = {
  explicit: "severity esplicita",
  exit_code: "exit code",
  duration: "durata oltre la soglia",
  missing: "notifica mancante",
  recovered: "ripresa degli invii",
  rule: "regola del receiver",
  preset_rule: "regola di un preset",
  receiver_default: "default del receiver",
};

/** Origini generate dal server: nessuno le ha inviate. */
export const SURVEILLANCE_SOURCES: SeveritySource[] = ["missing", "recovered"];

export function severitySourceLabel(source: string): string {
  return SEVERITY_SOURCE_LABELS[source] ?? source;
}

export function isSurveillanceSource(source: string): boolean {
  return (SURVEILLANCE_SOURCES as string[]).includes(source);
}

// Fase dell'esecuzione dichiarata dal mittente (header X-Phase). Un ping di
// avvio non e' un esito: in elenco va detto, altrimenti sembra un job che ha
// concluso senza dire niente.
export const PHASE_LABELS: Record<string, string> = {
  start: "avvio",
  end: "conclusione",
};

export function phaseLabel(phase: string | null): string | null {
  return phase === null ? null : (PHASE_LABELS[phase] ?? phase);
}
