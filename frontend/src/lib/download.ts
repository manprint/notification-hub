/** Consegna al browser, come file da salvare, un contenuto che la pagina ha gia'
 *  in mano (scaricato col Bearer dal client API, quindi non raggiungibile con
 *  un semplice `<a href download>`). */

/** Byte order mark UTF-8. Excel apre un CSV senza BOM con la codifica di
 *  sistema (Windows-1252 su un'installazione italiana) e trasforma "è" in
 *  "Ã¨": il BOM è l'unico segnale che legge. */
export const UTF8_BOM = "\uFEFF";

/** Quanto resta valido l'URL del blob dopo il click. Firefox e Safari avviano lo
 *  scaricamento in modo asincrono: revocare l'URL subito dopo `click()` puo'
 *  farlo fallire ("file non trovato"). Mezzo minuto basta anche a un disco lento,
 *  e un blob tenuto in memoria per trenta secondi non costa niente. */
export const REVOKE_DELAY_MS = 30_000;

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = "none";
  // Un'ancora fuori dal documento: Firefox ignora il click e non scarica.
  document.body.appendChild(anchor);
  try {
    anchor.click();
  } finally {
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), REVOKE_DELAY_MS);
  }
}
