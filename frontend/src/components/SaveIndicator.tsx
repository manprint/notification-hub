export type SaveState = "idle" | "saving" | "saved" | "failed";

const LABELS: Record<Exclude<SaveState, "idle">, string> = {
  saving: "Salvataggio…",
  saved: "Salvato",
  failed: "Non salvato",
};

/** Esito di una modifica fatta in linea (una tendina dentro una riga di
 *  tabella), dove il toast in basso a destra è lontano dal punto in cui si è
 *  agito: qui il riscontro sta accanto al campo che è cambiato. */
export default function SaveIndicator({ state }: { state: SaveState }) {
  if (state === "idle") return null;
  return (
    <span className={`save-state ${state}`} role="status">
      {state === "saved" ? "✓ " : ""}
      {LABELS[state]}
    </span>
  );
}
