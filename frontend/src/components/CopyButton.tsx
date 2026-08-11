import { useState } from "react";
import { copyText } from "../lib/clipboard";

interface CopyButtonProps {
  value: string;
}

export default function CopyButton({ value }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await copyText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <button type="button" onClick={() => void handleCopy()}>
      {copied ? "Copiato!" : "Copia"}
    </button>
  );
}