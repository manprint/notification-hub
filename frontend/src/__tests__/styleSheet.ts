/* Lettura di styles.css come dato, per i test che non possono usare il browser:
   jsdom non applica il foglio e non fa layout, quindi qui si leggono le regole
   e i token e si verifica cio' che il CSS dichiara. */

/// <reference types="node" />
import { readFileSync } from "node:fs";
import { resolve as resolvePath } from "node:path";

// Vitest svuota i CSS importati (anche con ?raw): il file si legge dal disco.
// I comandi npm girano dalla cartella frontend/.
const css = readFileSync(resolvePath(process.cwd(), "src/styles.css"), "utf8");

export interface Rule {
  selectors: string[];
  decls: Record<string, string>;
}

const stripComments = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, "");

function parseRules(source: string): Rule[] {
  const out: Rule[] = [];
  // Una regola e' "prelude { dichiarazioni }" senza altre graffe dentro: le
  // @media si leggono come contenitori, le loro regole interne sono quelle vere.
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(source)) !== null) {
    const prelude = m[1].trim();
    if (prelude.startsWith("@")) continue;
    const decls: Record<string, string> = {};
    for (const raw of m[2].split(";")) {
      const i = raw.indexOf(":");
      if (i < 0) continue;
      decls[raw.slice(0, i).trim()] = raw.slice(i + 1).trim();
    }
    out.push({ selectors: prelude.split(",").map((s) => s.trim()), decls });
  }
  return out;
}

export const sheet = stripComments(css);
export const rules: Rule[] = parseRules(sheet);

/** Il testo dello sheet senza il blocco :root (dove i token possono avere valori). */
export const sheetOutsideRoot = sheet.replace(/:root\s*\{[^}]*\}/, "");

/** Ultima dichiarazione di `prop` per il selettore esatto `selector`, come fa il cascade. */
export function declared(selector: string, prop: string): string | undefined {
  let value: string | undefined;
  for (const r of rules) {
    if (r.selectors.includes(selector) && prop in r.decls) value = r.decls[prop];
  }
  return value;
}

export const tokens: Record<string, string> = (() => {
  const t: Record<string, string> = {};
  for (const r of rules) {
    if (!r.selectors.includes(":root")) continue;
    for (const [k, v] of Object.entries(r.decls)) if (k.startsWith("--")) t[k] = v;
  }
  return t;
})();

/** Sostituisce ricorsivamente var(--token) con il valore del token. */
export function resolve(value: string): string {
  let v = value;
  for (let i = 0; i < 10 && v.includes("var("); i++) {
    v = v.replace(/var\((--[\w-]+)\)/g, (_, name: string) => tokens[name] ?? `var(${name})`);
  }
  return v;
}

/** Classi che compaiono in almeno un selettore dello sheet. */
export function cssClasses(): Set<string> {
  const out = new Set<string>();
  for (const r of rules) {
    for (const sel of r.selectors) {
      for (const m of sel.matchAll(/\.([A-Za-z_][\w-]*)/g)) out.add(m[1]);
    }
  }
  return out;
}

export interface ClassUsage {
  /** Classi scritte per esteso nei className. */
  fixed: Set<string>;
  /** Prefissi di classi costruite a runtime (`severity-${x}`). */
  prefixes: Set<string>;
}

/** Legge le classi usate in un sorgente TSX: className="..", className={..} con
 *  stringhe, ternari e template literal. Le parti dinamiche diventano prefissi. */
export function classUsage(source: string): ClassUsage {
  const usage: ClassUsage = { fixed: new Set(), prefixes: new Set() };
  let at = source.indexOf("className=");
  while (at >= 0) {
    const start = at + "className=".length;
    const open = source[start];
    let end = start + 1;
    if (open === "{") {
      let depth = 0;
      for (end = start; end < source.length; end++) {
        if (source[end] === "{") depth++;
        else if (source[end] === "}" && --depth === 0) break;
      }
      collect(source.slice(start + 1, end), usage);
    } else if (open === '"' || open === "'") {
      end = source.indexOf(open, start + 1);
      collect(source.slice(start, end + 1), usage);
    }
    at = source.indexOf("className=", end);
  }
  return usage;
}

function collect(expr: string, usage: ClassUsage): void {
  let i = 0;
  while (i < expr.length) {
    const ch = expr[i];
    if (ch === '"' || ch === "'") {
      const end = expr.indexOf(ch, i + 1);
      for (const t of expr.slice(i + 1, end).split(/\s+/)) if (t) usage.fixed.add(t);
      i = end + 1;
    } else if (ch === "`") {
      const end = expr.indexOf("`", i + 1);
      const body = expr.slice(i + 1, end);
      const pieces = body.split(/\$\{[^}]*\}/);
      pieces.forEach((piece, n) => {
        const tokens = piece.split(/\s+/).filter(Boolean);
        const glued = n < pieces.length - 1 && !/\s$/.test(piece) && tokens.length > 0;
        tokens.forEach((t, k) => {
          if (glued && k === tokens.length - 1) usage.prefixes.add(t);
          else usage.fixed.add(t);
        });
      });
      for (const dyn of body.matchAll(/\$\{([^}]*)\}/g)) collect(dyn[1], usage);
      i = end + 1;
    } else {
      i++;
    }
  }
}

/** WCAG 2.x: rapporto di contrasto fra due colori esadecimali o rgba opachi. */
export function parseColor(v: string): [number, number, number, number] {
  const hex = v.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hex) {
    const h = hex[1].length === 3 ? [...hex[1]].map((c) => c + c).join("") : hex[1];
    const n = parseInt(h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255, 1];
  }
  const rgba = v.match(/^rgba?\(([^)]+)\)$/);
  if (rgba) {
    const [r, g, b, a = 1] = rgba[1].split(",").map((s) => parseFloat(s));
    return [r, g, b, a];
  }
  throw new Error(`colore non riconosciuto: ${v}`);
}

/** Compone un colore semitrasparente sopra uno sfondo opaco. */
export function over(fg: string, bg: string): [number, number, number, number] {
  const [r, g, b, a] = parseColor(fg);
  const [br, bgG, bb] = parseColor(bg);
  return [r * a + br * (1 - a), g * a + bgG * (1 - a), b * a + bb * (1 - a), 1];
}

function luminance([r, g, b]: [number, number, number, number]): number {
  const lin = (c: number) => {
    const x = c / 255;
    return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

export function contrast(a: [number, number, number, number], b: [number, number, number, number]): number {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}
