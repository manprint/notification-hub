import { useEffect, useRef, useState } from "react";
import { useToast } from "../hooks/useToast";
import { copyText } from "../lib/clipboard";

interface CopyButtonProps {
  value: string;
  /** Etichetta del pulsante: serve dove "Copia" da solo non dice cosa si
   *  copia (il link di un invito accanto ad altri pulsanti). */
  label?: string;
}

const COPIED_VISIBLE_MS = 2000;

export default function CopyButton({ value, label = "Copia" }: CopyButtonProps) {
  const toast = useToast();
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    },
    [],
  );

  async function handleCopy() {
    try {
      await copyText(value);
    } catch {
      // Senza questo avviso un fallimento era indistinguibile da un pulsante
      // rotto: chi ha bisogno del valore deve sapere che va copiato a mano.
      toast.error("Copia non riuscita: seleziona il testo e copialo a mano.");
      return;
    }
    setCopied(true);
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      timer.current = null;
      setCopied(false);
    }, COPIED_VISIBLE_MS);
  }

  return (
    <button type="button" onClick={() => void handleCopy()}>
      {copied ? "Copiato!" : label}
    </button>
  );
}
