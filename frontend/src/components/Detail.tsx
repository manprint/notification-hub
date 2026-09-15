import type { ReactNode } from "react";

/** Una coppia etichetta/valore dentro una `.detail-grid`.
 *
 *  Le viste di sola lettura erano elenchi di `<p>Etichetta: valore</p>`: su un
 *  monitor largo occupavano una colonna sottile e dieci righe di scroll, e
 *  l'etichetta non si distingueva dal valore. */
export default function Detail({
  label,
  children,
  wide = false,
}: {
  label: string;
  children: ReactNode;
  /** Valore lungo (una URL, un comando): prende tutta la riga della griglia. */
  wide?: boolean;
}) {
  return (
    <div className={wide ? "detail-wide" : undefined}>
      <span className="detail-label">{label}</span>
      <div className="detail-value">{children}</div>
    </div>
  );
}
