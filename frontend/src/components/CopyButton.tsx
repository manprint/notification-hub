import { useState } from "react";
import { copyText } from "../lib/clipboard";

interface CopyButtonProps {
  value: string;
  /** Etichetta del pulsante: serve dove "Copia" da solo non dice cosa si
   *  copia (il link di un invito accanto ad altri pulsanti). */
  label?: string;
}

export default function CopyButton({ value, label = "Copia" }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await copyText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <button type="button" onClick={() => void handleCopy()}>
      {copied ? "Copiato!" : label}
    </button>
  );
}