/* Controlli sul foglio di stile: classi usate contro classi definite, scala dei
   testi, token al posto dei valori a mano, contrasto WCAG delle coppie colore
   usate nell'interfaccia, regole di hover e di overflow che il cascade deve
   far valere. Non sostituiscono la verifica nel browser, ma impediscono che un
   rinomino o un valore fuori scala passi senza che nessuno se ne accorga. */

import { describe, expect, it } from "vitest";
import {
  classUsage,
  contrast,
  cssClasses,
  declared,
  over,
  parseColor,
  resolve,
  rules,
  sheetOutsideRoot,
  tokens,
  type ClassUsage,
} from "./styleSheet";

const sources = import.meta.glob("../**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const usage: ClassUsage = { fixed: new Set(), prefixes: new Set() };
for (const [path, source] of Object.entries(sources)) {
  if (path.includes("__tests__")) continue;
  const u = classUsage(source);
  u.fixed.forEach((c) => usage.fixed.add(c));
  u.prefixes.forEach((p) => usage.prefixes.add(p));
}

/** Valori che il codice costruisce senza scriverli come stringa nel className:
 *  gli stati di SaveIndicator (`save-state ${state}`), i toni di StatusPill
 *  (tabella TONES) e le etichette di Field (labelClass). Vanno qui a mano, con
 *  il file che li produce, perche' il controllo statico non li vede. */
const DYNAMIC_ONLY = new Set([
  "saving", // SaveIndicator: save-state ${state}
  "saved",
  "failed",
  "ok", // StatusPill TONES
  "warn",
  "danger",
  "info",
  "is-required", // Field.tsx labelClass
  "is-optional",
]);

describe("classi di styles.css", () => {
  it("ogni classe usata nei TSX è definita in styles.css", () => {
    const defined = cssClasses();
    const missing = [...usage.fixed].filter((c) => !defined.has(c));
    const missingPrefix = [...usage.prefixes].filter((p) => ![...defined].some((c) => c.startsWith(p)));
    expect({ missing, missingPrefix }).toEqual({ missing: [], missingPrefix: [] });
  });

  it("ogni classe definita in styles.css è usata da qualche TSX (regole morte)", () => {
    const unused = [...cssClasses()].filter(
      (c) =>
        !usage.fixed.has(c) &&
        ![...usage.prefixes].some((p) => c.startsWith(p)) &&
        !DYNAMIC_ONLY.has(c),
    );
    expect(unused).toEqual([]);
  });
});

describe("scala e token", () => {
  it("nessuna dimensione del testo in px fuori dai token", () => {
    const px = rules
      .filter((r) => !r.selectors.includes(":root"))
      .flatMap((r) =>
        /\d(\.\d+)?px\b/.test(r.decls["font-size"] ?? "")
          ? r.selectors.map((s) => `${s}: ${r.decls["font-size"]}`)
          : [],
      );
    expect(px).toEqual([]);
  });

  it("nessun colore esadecimale fuori dal blocco :root", () => {
    expect(sheetOutsideRoot.match(/#[0-9a-fA-F]{3,8}\b/g) ?? []).toEqual([]);
  });

  it("nessun rgba() fuori dai token, salvo ombre e velo (nero)", () => {
    const literal = [...sheetOutsideRoot.matchAll(/rgba?\([^)]*\)/g)]
      .map((m) => m[0])
      .filter((v) => !/^rgba?\(\s*0,\s*0,\s*0\s*,/.test(v));
    expect(literal).toEqual([]);
  });

  it("i valori di :root sono definiti per ogni token usato", () => {
    const used = new Set<string>();
    for (const r of rules) for (const v of Object.values(r.decls)) for (const m of v.matchAll(/var\((--[\w-]+)\)/g)) used.add(m[1]);
    expect([...used].filter((t) => !(t in tokens))).toEqual([]);
  });
});

describe("contrasto WCAG AA (4.5:1) delle coppie usate", () => {
  const SURFACE = "--color-surface";
  const bgOf = (v: string) => resolve(v);
  const colorOf = (sel: string) => resolve(declared(sel, "color") ?? "");

  // Testo bianco su sfondo pieno, o colore di testo su superficie. I casi
  // seguono i selettori reali: se cambia il CSS, cambia la verifica.
  const cases: Array<[string, () => number]> = [
    ["pulsante principale", () => contrast(parseColor(colorOf("button.primary")), parseColor(bgOf(declared("button.primary", "background") ?? "")))],
    ["pulsante principale in hover", () => contrast(parseColor(colorOf("button.primary")), parseColor(bgOf(declared("button.primary:hover:not(:disabled)", "background") ?? "")))],
    ["conferma distruttiva", () => contrast(parseColor(colorOf("button.primary.danger")), parseColor(bgOf(declared("button.primary.danger", "background") ?? "")))],
    ["conferma distruttiva in hover", () => contrast(parseColor(colorOf("button.primary.danger")), parseColor(bgOf(declared("button.primary.danger:hover:not(:disabled)", "background") ?? "")))],
    ["badge critico", () => contrast(parseColor(colorOf(".severity-badge")), parseColor(bgOf(declared(".severity-critical", "background") ?? "")))],
    ["badge errore", () => contrast(parseColor(colorOf(".severity-badge")), parseColor(bgOf(declared(".severity-error", "background") ?? "")))],
    ["pillola Verificata", () => contrast(parseColor(colorOf(".status-pill.verified")), parseColor(bgOf(declared(".status-pill.verified", "background") ?? "")))],
    ["pulsante distruttivo (testo su superficie alta)", () => contrast(parseColor(colorOf("button.danger")), parseColor(bgOf(declared("button", "background") ?? "")))],
    [
      "pillola Morta (rosso tenue su superficie)",
      () => contrast(parseColor(colorOf(".status-pill.danger")), over(bgOf(declared(".status-pill.danger", "background") ?? ""), bgOf(`var(${SURFACE})`))),
    ],
    ["messaggio di campo", () => contrast(parseColor(colorOf(".field-error")), parseColor(bgOf(`var(${SURFACE})`)))],
    ["salvataggio fallito", () => contrast(parseColor(colorOf(".save-state.failed")), parseColor(bgOf(`var(${SURFACE})`)))],
    ["badge avviso", () => contrast(parseColor(colorOf(".severity-warning")), parseColor(bgOf(declared(".severity-warning", "background") ?? "")))],
    ["badge info", () => contrast(parseColor(colorOf(".severity-info")), parseColor(bgOf(declared(".severity-info", "background") ?? "")))],
  ];

  it.each(cases)("%s: rapporto >= 4.5", (_name, ratio) => {
    expect(ratio()).toBeGreaterThanOrEqual(4.5);
  });
});

describe("cascata: regole che devono vincere sui pulsanti", () => {
  // button:hover:not(:disabled) ha specificita' 0,2,1: le regole di hover delle
  // classi usate su <button> devono avere la stessa forma per vincere.
  it("la card del gruppo in hover mostra il bordo d'accento", () => {
    expect(declared("button.group-card:hover:not(:disabled)", "border-color")).toBe("var(--color-accent)");
  });

  it("la X della notifica e il pulsante di riepilogo non cambiano sfondo in hover", () => {
    expect(declared("button.toast-close:hover:not(:disabled)", "background")).toBe("none");
    expect(declared("button.stats-toggle:hover:not(:disabled)", "background")).toBe("none");
  });

  it("il titolo di pagina va a capo sulle parole lunghe senza spazi", () => {
    expect(declared(".page-header h1", "overflow-wrap")).toBe("anywhere");
    expect(declared(".page-header h1", "min-width")).toBe("0");
  });

  it("le celle non si spezzano a metà parola: la tabella scorre invece di farsi stringere", () => {
    expect(declared("td", "overflow-wrap")).toBe("break-word");
    expect(declared("th", "overflow-wrap")).toBe("break-word");
  });

  it("gli elementi assoluti dentro una tabella scorrono con lei e non allargano la pagina", () => {
    expect(declared(".table-wrap", "overflow-x")).toBe("auto");
    expect(declared(".table-wrap", "position")).toBe("relative");
  });

  it("il pulsante principale in hover usa il fill di hover, piu' scuro", () => {
    expect(declared("button.primary:hover:not(:disabled)", "background")).toBe("var(--color-accent-fill-hover)");
  });

  it("il nome lungo nella home va a capo, il segnale accanto resta su una riga", () => {
    expect(declared(".status-cell-wrap", "white-space")).toBe("normal");
    expect(declared(".status-cell-wrap > a", "overflow-wrap")).toBe("anywhere");
    expect(declared(".status-pill", "white-space")).toBe("nowrap");
  });

  it("i filtri sono allineati in cima e il pulsante sta alla altezza delle caselle", () => {
    expect(declared(".filters", "align-items")).toBe("flex-start");
    // La regola da 760px in giu' riporta il pulsante in riga: qui si legge la prima, quella di desktop.
    const desktop = rules.find((r) => r.selectors.includes(".filters-actions") && "margin-top" in r.decls);
    expect(desktop?.decls["margin-top"]).toBe("var(--space-4)");
  });

  it("il menu mobile e' una testata su due righe, non una colonna alta un quinto dello schermo", () => {
    const mobile = rules.filter((r) => r.selectors.includes(".app-sidebar"));
    expect(mobile.some((r) => r.decls["grid-template-columns"] === "minmax(0, 1fr) auto")).toBe(true);
  });

  it("il pattern RE2 in tabella ha una larghezza minima: la colonna non si schiaccia a un carattere per riga", () => {
    expect(declared("code.rule-pattern", "display")).toBe("inline-block");
    expect(declared("code.rule-pattern", "min-width")).toBe("20ch");
  });

  it("l'etichetta del pattern prende lo spazio che resta nella toolbar, e il campo dentro la riempie", () => {
    expect(declared(".pattern-field", "flex")).toBe("1 1 18rem");
    expect(declared(".grow-input", "width")).toBe("100%");
    expect(declared(".grow-input", "min-width")).toBe("0");
  });
});

describe("distanze e breakpoint", () => {
  it("nessuna distanza (padding, margin, gap) scritta in px fuori dai token", () => {
    // .sr-only usa il margine di -1px dell'idioma standard per i testi solo per lettori di
    // schermo: non e' una distanza di layout.
    const hand = rules
      .filter((r) => !r.selectors.includes(":root") && !r.selectors.includes(".sr-only"))
      .flatMap((r) =>
        Object.entries(r.decls)
          .filter(([p, v]) => /^(padding|margin|gap|row-gap|column-gap)/.test(p) && /\b\d+(\.\d+)?px\b/.test(v))
          .map(([p, v]) => `${r.selectors.join(", ")} { ${p}: ${v} }`),
      );
    expect(hand).toEqual([]);
  });

  it("i breakpoint sono 1000px per la testata e 760px per le colonne", () => {
    expect(sheetOutsideRoot).toContain("@media (max-width: 1000px)");
    expect(sheetOutsideRoot).toContain("@media (max-width: 760px)");
  });
});
