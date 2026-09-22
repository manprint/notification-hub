/** Dove tornare dopo il login: la pagina chiesta prima di essere rimandati al
 *  form, ma solo se è un percorso di questa applicazione.
 *
 *  Il valore arriva dallo stato della navigazione, che la pagina di login non
 *  controlla: "//altro-sito" o "https://…" farebbero del login un redirect
 *  aperto verso l'esterno. "/login" riporterebbe al form appena lasciato. */
export function safeRedirectTarget(value: unknown): string {
  if (typeof value !== "string") return "/";
  if (!value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return "/";
  if (value === "/login" || value.startsWith("/login?") || value.startsWith("/login#")) return "/";
  return value;
}
