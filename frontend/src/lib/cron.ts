// Espressioni cron dell'attesa di un receiver.
//
// Il backend le valuta con croniter (app/services/surveillance.py:
// validate_cron e next_fire_after). Questo modulo trascrive la stessa semantica
// per le espressioni a 5 campi, invece di affidarsi a una libreria JS con regole
// sue: cron-parser, usato prima, divergeva su troppi casi reali. Accettava
// `5L`, `H`, `?` nel minuto e `0 0 31 2,4 *` (che il backend rifiuta),
// rifiutava `15W`, `22-2`, `fri-mon` (che il backend accetta), leggeva `1/2` nel
// giorno della settimana come 1,3,5,7 invece di 1,3,5 e saltava le 03:00 di Roma
// il giorno del passaggio all'ora legale. Il form prometteva una cosa e il
// backend ne sorvegliava un'altra.
//
// Scelte, verificate su una tabella di casi confrontata con il backend (vedi
// lib/__tests__/cron.test.ts):
// - validita': stesse regole di croniter.is_valid piu' "scatta almeno una
//   volta" (get_next in UTC con 50 anni di ricerca, come validate_cron);
// - anteprima: stesso algoritmo di next_fire_after, compresi i giorni di cambio
//   d'ora (un orario che non esiste slitta alla fine del salto, un orario che
//   capita due volte scatta due volte) e l'OR fra giorno del mese e giorno della
//   settimana quando sono ristretti entrambi;
// - `H` e `R` si rifiutano, come nel backend: `H` richiede un hash_id che la
//   sorveglianza non passa, `R` pescherebbe un orario diverso a ogni controllo;
// - cifre non ASCII: rifiutate qui. Unico caso in cui il form e' piu' severo
//   del parser del backend, e solo su input che nessun crontab contiene.
//
// Il backend resta l'unica autorita': questa libreria non salva nulla, mostra e
// blocca.

/** Minuto ora giorno mese giorno-settimana, come in crontab. */
export const CRON_FIELDS = 5;
/** Oltre non si va: stessa soglia di app/services/surveillance.py. */
export const CRON_MAX_CHARS = 100;

const MESSAGGIO_5_CAMPI =
  "L'espressione cron deve avere 5 campi come in crontab: minuto ora giorno mese giorno-settimana.";

const MINUTE = 0;
const HOUR = 1;
const DAY = 2;
const MONTH = 3;
const DOW = 4;

// Da croniter.RANGES e croniter.LEN_MEANS_ALL, limitati ai 5 campi di crontab.
const RANGES: readonly (readonly [number, number])[] = [
  [0, 59],
  [0, 23],
  [1, 31],
  [1, 12],
  [0, 6],
];
const LEN_MEANS_ALL = [60, 24, 31, 12, 7];
// croniter: max_years_between_matches di default.
const MAX_YEARS_BETWEEN_MATCHES = 50;

const MINUTE_MS = 60_000;
const HOUR_MS = 3_600_000;
const DAY_MS = 86_400_000;

const MONTH_NAMES = new Map<string, number>([
  ["jan", 1],
  ["feb", 2],
  ["mar", 3],
  ["apr", 4],
  ["may", 5],
  ["jun", 6],
  ["jul", 7],
  ["aug", 8],
  ["sep", 9],
  ["oct", 10],
  ["nov", 11],
  ["dec", 12],
]);
const WEEKDAY_NAMES = new Map<string, number>([
  ["sun", 0],
  ["mon", 1],
  ["tue", 2],
  ["wed", 3],
  ["thu", 4],
  ["fri", 5],
  ["sat", 6],
]);
const ALPHACONV: readonly Map<string, number | "l">[] = [
  new Map(),
  new Map(),
  new Map([["l", "l"]]),
  MONTH_NAMES,
  WEEKDAY_NAMES,
];

const WEEKDAYS = [...WEEKDAY_NAMES.keys()].join("|");
const MONTHS = [...MONTH_NAMES.keys()].join("|");
// Le stesse espressioni regolari di croniter.
const STEP_SEARCH_RE = /^([^-]+)-([^-/]+)(\/(\d+))?$/;
const ONLY_INT_RE = /^\d+$/;
const STAR_OR_INT_RE = /^(\d+|\*)$/;
const SPECIAL_DOW_RE = new RegExp(
  `^(?<pre>((?<he>((${WEEKDAYS})(-(${WEEKDAYS}))?)|((${MONTHS})(-(${MONTHS}))?)|\\w+)#)|l)(?<last>\\d+)$`,
);
const NEAREST_WEEKDAY_RE = /^(?:(\d+)w|w(\d+))$/;
const HASH_RE = /^(h|r)(\((\d+)-(\d+)\))?(\/(\d+))?$/;

type Value = number | "l" | "*";
type NthSpec = number | "l";

/** Un'espressione espansa come la espande croniter: per ogni campo i valori
 *  ammessi (con "*" = tutti), piu' le due forme speciali dei giorni. */
interface CronSchedule {
  fields: Value[][];
  /** `2#3` (terzo martedi') e `l5` (ultimo venerdi'): giorno -> posizioni. */
  nth: Map<number, Set<NthSpec>>;
  /** `15W`: giorno feriale piu' vicino al 15. */
  nearest: Set<number>;
}

class CronSyntaxError extends Error {}
class CronRandomError extends CronSyntaxError {}
class CronNoMatchError extends Error {}

function alphaconv(field: number, key: string): number | "l" {
  const value = ALPHACONV[field].get(key);
  if (value === undefined) throw new CronSyntaxError(`valore sconosciuto: ${key}`);
  return value;
}

/** Solo il 7 del giorno della settimana ha un alias (domenica = 0): nel cron a
 *  5 campi croniter non converte lo 0 di giorno e mese. */
function valueAlias(value: number, field: number): number {
  return field === DOW && value === 7 ? 0 : value;
}

/** `range(start, stop, step)` di Python, con step positivo. */
function pyRange(start: number, stop: number, step: number): number[] {
  const out: number[] = [];
  for (let value = start; value < stop; value += step) out.push(value);
  return out;
}

function sortKey(value: Value): string {
  return typeof value === "number" ? String(value).padStart(2, "0") : value;
}

/** Trascrizione di croniter._expand per i 5 campi di crontab. */
function expandSchedule(expression: string): CronSchedule {
  const expressions = expression.toLowerCase().trim().split(/\s+/);
  if (expressions.length !== CRON_FIELDS) throw new CronSyntaxError(MESSAGGIO_5_CAMPI);

  // Prima di tutto H e R, in qualunque elemento di qualunque campo: stesso
  // controllo del backend.
  for (const expr of expressions) {
    if (expr.split(",").some((element) => HASH_RE.test(element))) {
      throw new CronRandomError("H/R non ammessi");
    }
  }

  const fields: Value[][] = [];
  const nth = new Map<number, Set<NthSpec>>();
  const nearest = new Set<number>();

  expressions.forEach((raw, field) => {
    let expr = raw;
    if (expr.includes("?")) {
      if (expr !== "?") throw new CronSyntaxError("? va usato da solo");
      if (field !== DAY && field !== DOW) throw new CronSyntaxError("? solo nei giorni");
      expr = "*";
    }

    const [fieldMin, fieldMax] = RANGES[field];
    const pending = expr.split(",");
    const res: Value[] = [];
    const seen = new Set<string>();

    while (pending.length > 0) {
      let element = pending.pop() as string;
      let nthSpec: NthSpec | null = null;

      if (field === DOW) {
        const special = SPECIAL_DOW_RE.exec(element);
        if (special?.groups) {
          const { he, last } = special.groups;
          if (he) {
            element = he;
            const position = Number(last);
            if (position < 1 || position > 5) throw new CronSyntaxError("posizione fuori range");
            nthSpec = position;
          } else if (last) {
            element = last;
            nthSpec = "l";
          }
        }
      }

      if (field === DAY) {
        const weekday = NEAREST_WEEKDAY_RE.exec(element);
        if (weekday) {
          const day = Number(weekday[1] ?? weekday[2]);
          if (day < 1 || day > 31) throw new CronSyntaxError("W fuori range");
          if (pending.length > 0 || res.length > 0) {
            throw new CronSyntaxError("W solo con un giorno singolo");
          }
          nearest.add(day);
          res.push(day);
          continue;
        }
      }

      let text = element.replace(/^\*(\/.+)$/, `${fieldMin}-${fieldMax}$1`);
      let match = STEP_SEARCH_RE.exec(text);
      if (!match) {
        text = element.replace(/^(.+)\/(.+)$/, `$1-${fieldMax}/$2`);
        match = STEP_SEARCH_RE.exec(text);
      }

      if (match) {
        let lowText = match[1];
        let highText = match[2];
        const step = Number(match[4] ?? "1");
        if (field === DAY && highText === "l") highText = "31";
        if (!ONLY_INT_RE.test(lowText)) lowText = String(alphaconv(field, lowText));
        if (!ONLY_INT_RE.test(highText)) highText = String(alphaconv(field, highText));
        if (step === 0) throw new CronSyntaxError("passo zero");
        if (!ONLY_INT_RE.test(lowText) || !ONLY_INT_RE.test(highText)) {
          throw new CronSyntaxError("estremi non numerici");
        }
        const low = valueAlias(Number(lowText), field);
        const high = valueAlias(Number(highText), field);
        if (Math.max(low, high) > fieldMax) throw new CronSyntaxError("fuori range");

        let values: number[];
        if (low > high) {
          // Intervallo che scavalca la fine del campo (22-2, fri-mon): come
          // croniter, fino in fondo e poi dall'inizio rispettando il passo.
          const whole = pyRange(fieldMin, fieldMax + 1, 1);
          values = pyRange(low, fieldMax + 1, step);
          let toSkip = 0;
          if (values.length > 0) {
            const lastValue = values[values.length - 1];
            const alreadySkipped = [...whole].reverse().indexOf(lastValue);
            const position = whole.indexOf(lastValue);
            if (position + step > whole.length && alreadySkipped < step) {
              toSkip = step - alreadySkipped;
            }
          }
          values = values.concat(pyRange(fieldMin + toSkip, high + 1, step));
        } else if (low === high) {
          // croniter: `5-5` o `sun-sun` significano il giro intero del campo.
          values = pyRange(fieldMin, fieldMax + 1, step);
        } else {
          values = pyRange(low, high + 1, step);
        }

        const items =
          field === DOW && nthSpec !== null && nthSpec !== "l"
            ? values.map((value) => `${value}#${nthSpec}`)
            : values.map(String);
        for (const item of items) if (!seen.has(item)) pending.push(item);
        for (const item of items) seen.add(item);
      } else {
        if (text.startsWith("-")) throw new CronSyntaxError("numeri negativi");
        let value: Value;
        if (STAR_OR_INT_RE.test(text)) value = text === "*" ? "*" : Number(text);
        else value = alphaconv(field, text);
        if (typeof value === "number") value = valueAlias(value, field);
        if (typeof value === "number" && (value < fieldMin || value > fieldMax)) {
          throw new CronSyntaxError("fuori range");
        }
        res.push(value);
        if (field === DOW && nthSpec !== null && typeof value === "number") {
          const specs = nth.get(value) ?? new Set<NthSpec>();
          specs.add(nthSpec);
          nth.set(value, specs);
        }
      }
    }

    let values = [...new Map(res.map((value) => [sortKey(value), value])).values()].sort(
      (a, b) => (sortKey(a) < sortKey(b) ? -1 : sortKey(a) > sortKey(b) ? 1 : 0),
    );
    if (values.length === LEN_MEANS_ALL[field]) {
      const keepList =
        (field === DAY && !expressions[DOW].includes("*")) ||
        (field === DOW && !expressions[DAY].includes("*"));
      if (!keepList) values = ["*"];
    }
    fields.push(values.length === 1 && values[0] === "*" ? ["*"] : values);
  });

  if (nth.size > 0) {
    const plain = new Set<Value>(fields[DOW]);
    for (const key of nth.keys()) plain.delete(key);
    plain.delete("*");
    if (plain.size > 0 && new Set(fields[DOW]).size !== LEN_MEANS_ALL[DOW]) {
      throw new CronSyntaxError("# mescolato a giorni semplici");
    }
  }

  return { fields, nth, nearest };
}

// ---------------------------------------------------------------------------
// Calcolo delle occorrenze: trascrizione di croniter._calc_next e _calc.
// Un "wall" e' l'ora dell'orologio nel fuso, codificata come millisecondi di un
// Date letto in UTC (il datetime senza fuso di Python).

interface Civil {
  y: number;
  mo: number;
  d: number;
  h: number;
  mi: number;
  /** 0 = domenica, come `isoweekday() % 7`. */
  dow: number;
}

function civil(wall: number): Civil {
  const date = new Date(wall);
  return {
    y: date.getUTCFullYear(),
    mo: date.getUTCMonth() + 1,
    d: date.getUTCDate(),
    h: date.getUTCHours(),
    mi: date.getUTCMinutes(),
    dow: date.getUTCDay(),
  };
}

function wallOf(y: number, mo: number, d: number, h = 0, mi = 0): number {
  return Date.UTC(y, mo - 1, d, h, mi);
}

function lastDayOfMonth(y: number, mo: number): number {
  return new Date(Date.UTC(y, mo, 0)).getUTCDate();
}

/** I giorni del mese che cadono nel giorno della settimana dato. */
function weekdaysOfMonth(y: number, mo: number, dow: number): number[] {
  const first = new Date(Date.UTC(y, mo - 1, 1)).getUTCDay();
  const days: number[] = [];
  for (let day = 1 + ((dow - first + 7) % 7); day <= lastDayOfMonth(y, mo); day += 7) {
    days.push(day);
  }
  return days;
}

/** croniter._get_nearest_weekday. */
function nearestWeekday(y: number, mo: number, target: number): number {
  const last = lastDayOfMonth(y, mo);
  const day = Math.min(target, last);
  const weekday = (new Date(Date.UTC(y, mo - 1, day)).getUTCDay() + 6) % 7; // 0 = lunedi'
  if (weekday < 5) return day;
  if (weekday === 5) return day > 1 ? day - 1 : day + 2;
  return day < last ? day + 1 : day - 2;
}

/** croniter._get_next_nearest_diff. */
function nextNearestDiff(x: number, allowed: Value[], rangeVal: number): number {
  for (const item of allowed) {
    let value: number;
    if (item === "l") value = rangeVal;
    else if (item === "*" || item > rangeVal) continue;
    else value = item;
    if (value >= x) return value - x;
  }
  const first = allowed[0];
  return (typeof first === "number" ? first : rangeVal) - x + rangeVal;
}

/** Prima ora dell'orologio che soddisfa l'espressione, strettamente dopo
 *  `start` al minuto: il ciclo dei `proc_*` di croniter._calc. */
function searchWall(start: number, fields: Value[][], schedule: CronSchedule): number {
  let wall = Math.floor((start + MINUTE_MS) / MINUTE_MS) * MINUTE_MS;
  const currentYear = civil(wall).y;
  let year = currentYear;

  const month = (c: Civil): number | null => {
    if (fields[MONTH].includes("*")) return null;
    const diff = nextNearestDiff(c.mo, fields[MONTH], 12);
    if (diff === 0) return null;
    const total = c.mo - 1 + diff;
    return wallOf(c.y + Math.floor(total / 12), (total % 12) + 1, 1);
  };
  const dayOfMonth = (c: Civil): number | null => {
    if (fields[DAY].includes("*")) return null;
    const days = lastDayOfMonth(c.y, c.mo);
    if (fields[DAY].includes("l") && days === c.d) return null;
    const diff = nextNearestDiff(c.d, fields[DAY], days);
    return diff === 0 ? null : wallOf(c.y, c.mo, c.d) + diff * DAY_MS;
  };
  const toCandidate = (c: Civil, candidates: number[]): number | null => {
    if (candidates.length === 0) {
      return wallOf(c.y, c.mo, c.d) + (lastDayOfMonth(c.y, c.mo) - c.d + 1) * DAY_MS;
    }
    const diff = Math.min(...candidates) - c.d;
    return diff === 0 ? null : wallOf(c.y, c.mo, c.d) + diff * DAY_MS;
  };
  const nearestDay = (c: Civil): number | null => {
    const candidates = [...schedule.nearest]
      .map((target) => nearestWeekday(c.y, c.mo, target))
      .filter((candidate) => c.d <= candidate);
    return toCandidate(c, candidates);
  };
  const dayOfWeek = (c: Civil): number | null => {
    if (fields[DOW].includes("*")) return null;
    const diff = nextNearestDiff(c.dow, fields[DOW], 7);
    return diff === 0 ? null : wallOf(c.y, c.mo, c.d) + diff * DAY_MS;
  };
  const nthDayOfWeek = (c: Civil): number | null => {
    const candidates: number[] = [];
    for (const [weekday, specs] of schedule.nth) {
      const days = weekdaysOfMonth(c.y, c.mo, weekday);
      for (const spec of specs) {
        let candidate: number;
        if (spec === "l") candidate = days[days.length - 1];
        else if (days.length < spec) continue;
        else candidate = days[spec - 1];
        if (c.d <= candidate) candidates.push(candidate);
      }
    }
    return toCandidate(c, candidates);
  };
  const hour = (c: Civil): number | null => {
    if (fields[HOUR].includes("*")) return null;
    const diff = nextNearestDiff(c.h, fields[HOUR], 24);
    return diff === 0 ? null : wallOf(c.y, c.mo, c.d, c.h) + diff * HOUR_MS;
  };
  const minute = (c: Civil): number | null => {
    if (fields[MINUTE].includes("*")) return null;
    const diff = nextNearestDiff(c.mi, fields[MINUTE], 60);
    return diff === 0 ? null : wallOf(c.y, c.mo, c.d, c.h, c.mi) + diff * MINUTE_MS;
  };

  const procs = [
    month,
    schedule.nearest.size > 0 ? nearestDay : dayOfMonth,
    schedule.nth.size > 0 ? nthDayOfWeek : dayOfWeek,
    hour,
    minute,
  ];

  while (Math.abs(year - currentYear) <= MAX_YEARS_BETWEEN_MATCHES) {
    let changed = false;
    for (const proc of procs) {
      const next = proc(civil(wall));
      if (next !== null) {
        wall = next;
        year = civil(wall).y;
        changed = true;
        break;
      }
    }
    if (!changed) return wall;
  }
  throw new CronNoMatchError("nessuna occorrenza");
}

// --- Fusi orari -------------------------------------------------------------

/** Un istante letto in un fuso: ora dell'orologio, istante UTC, scarto. */
interface Moment {
  wall: number;
  instant: number;
  offset: number;
}

const formatters = new Map<string, Intl.DateTimeFormat>();

function offsetAt(timezone: string, instant: number): number {
  if (timezone === "UTC") return 0;
  let formatter = formatters.get(timezone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat("en-US", {
      timeZone: timezone,
      hourCycle: "h23",
      year: "numeric",
      month: "numeric",
      day: "numeric",
      hour: "numeric",
      minute: "numeric",
      second: "numeric",
    });
    formatters.set(timezone, formatter);
  }
  const parts = formatter.formatToParts(new Date(instant));
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((p) => p.type === type)?.value);
  const wall = Date.UTC(
    part("year"),
    part("month") - 1,
    part("day"),
    part("hour"),
    part("minute"),
    part("second"),
  );
  return wall - (instant - (((instant % 1000) + 1000) % 1000));
}

function momentAt(timezone: string, instant: number): Moment {
  const offset = offsetAt(timezone, instant);
  return { wall: instant + offset, instant, offset };
}

/** Gli istanti che hanno quell'ora dell'orologio nel fuso: nessuno se l'ora e'
 *  saltata dal cambio d'ora, due se capita due volte. In ordine crescente. */
function instantsOf(timezone: string, wall: number): number[] {
  const offsets = new Set([
    offsetAt(timezone, wall - DAY_MS),
    offsetAt(timezone, wall),
    offsetAt(timezone, wall + DAY_MS),
  ]);
  const instants = new Set<number>();
  for (const offset of offsets) {
    const instant = wall - offset;
    if (offsetAt(timezone, instant) === offset) instants.add(instant);
  }
  return [...instants].sort((a, b) => a - b);
}

/** croniter._add_tzinfo (ramo zoneinfo): un'ora inesistente avanza di minuto in
 *  minuto fino alla prima che esiste; un'ora doppia prende il primo passaggio,
 *  o il secondo se il primo non viene dopo `now`. */
function addTimezone(
  timezone: string,
  wall: number,
  now: Moment,
): { moment: Moment; exists: boolean } {
  let instants = instantsOf(timezone, wall);
  if (instants.length === 0) {
    let moved = wall;
    do {
      moved += MINUTE_MS;
      instants = instantsOf(timezone, moved);
    } while (instants.length === 0);
    return { moment: { wall: moved, instant: instants[0], offset: moved - instants[0] }, exists: false };
  }
  let instant = instants[0];
  if (instants.length > 1 && !(instant > now.instant)) instant = instants[instants.length - 1];
  return { moment: { wall, instant, offset: wall - instant }, exists: true };
}

/** croniter._calc con un `now` provvisto di fuso. */
function calcAware(
  timezone: string,
  now: Moment,
  fields: Value[][],
  schedule: CronSchedule,
): Moment {
  let wall = searchWall(now.wall, fields, schedule);
  let { moment, exists } = addTimezone(timezone, wall, now);
  if (!exists && (!(moment.instant > now.instant) || fields[HOUR].includes("*"))) {
    while (!exists) {
      wall = searchWall(wall, fields, schedule);
      ({ moment, exists } = addTimezone(timezone, wall, now));
    }
  }

  const offsetDelta = moment.offset - now.offset;
  if (offsetDelta === 0) return moment;

  // C'e' stato un cambio d'ora: croniter cerca anche l'occorrenza con l'altro
  // scarto e tiene la prima delle due che viene dopo `now`.
  const alternativeWall = searchWall(now.wall + offsetDelta, fields, schedule);
  const alternative = addTimezone(timezone, alternativeWall, now).moment;
  if (!(alternative.instant > now.instant)) return moment;
  if (moment.instant > alternative.instant) return alternative;
  return moment;
}

/** Prima occorrenza strettamente successiva a `instant`, come
 *  next_fire_after del backend. Solleva CronNoMatchError se non ce n'e' una
 *  entro 50 anni. */
function nextFireAfter(schedule: CronSchedule, timezone: string, instant: number): number {
  const now = momentAt(timezone, instant);
  const { fields } = schedule;
  if (!fields[DAY].includes("*") && !fields[DOW].includes("*")) {
    // Giorno del mese e giorno della settimana ristretti entrambi: vale l'uno
    // o l'altro (OR, come cron). croniter calcola i due rami e confronta le
    // due date come ore dell'orologio.
    const byDay = calcAware(timezone, now, fields.map((f, i) => (i === DOW ? ["*"] : f)), schedule);
    const byWeekday = calcAware(
      timezone,
      now,
      fields.map((f, i) => (i === DAY ? ["*"] : f)),
      schedule,
    );
    return (byDay.wall < byWeekday.wall ? byDay : byWeekday).instant;
  }
  return calcAware(timezone, now, fields, schedule).instant;
}

/** Verifica un'espressione cron a 5 campi. Ritorna il messaggio d'errore, o
 *  null se accettabile. Stesse regole di validate_cron del backend. */
export function validateCronExpression(expression: string): string | null {
  const candidate = expression.trim();
  if (candidate === "") return "L'espressione cron è vuota.";
  // In caratteri e non in unita' UTF-16, come len() di Python.
  if (Array.from(candidate).length > CRON_MAX_CHARS)
    return `L'espressione cron supera ${CRON_MAX_CHARS} caratteri.`;
  if (candidate.split(/\s+/).length !== CRON_FIELDS) return MESSAGGIO_5_CAMPI;
  let schedule: CronSchedule;
  try {
    schedule = expandSchedule(candidate);
  } catch (err) {
    if (err instanceof CronRandomError) {
      return "H e R (valore casuale) non sono ammessi: la sorveglianza ha bisogno di un orario fisso, scrivi il minuto e l'ora esatti.";
    }
    return `Espressione cron non valida: ${candidate}`;
  }
  try {
    nextFireAfter(schedule, "UTC", Date.now());
  } catch {
    // `0 0 30 2 *` o `0 0 31 2,4 *`: sintassi giusta, nessuna data possibile.
    // Salvarla vorrebbe dire una sorveglianza che non sorveglia.
    return `L'espressione cron non scatta mai: ${candidate}`;
  }
  return null;
}

/** Verifica un nome di fuso orario IANA: vuoto o sconosciuto al runtime non
 *  passa. */
export function validateTimezone(name: string): string | null {
  const candidate = name.trim();
  if (candidate === "") return "Scegli un fuso orario correttamente.";
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: candidate });
    return null;
  } catch {
    return `Fuso orario non valido: ${candidate}`;
  }
}

/** Prossime occorrenze di un'espressione cron nel fuso dichiarato, calcolate
 *  come le calcola il backend. Ritorna fino a `count` date (default 3).
 *  Un'espressione non valida o che non scatta mai ritorna una lista piu' corta
 *  o vuota, mai un errore. */
export function nextCronExecutions(
  expression: string,
  timezone: string,
  now: Date = new Date(),
  count = 3,
): Date[] {
  const dates: Date[] = [];
  try {
    const schedule = expandSchedule(expression.trim());
    let cursor = now.getTime();
    for (let i = 0; i < count; i += 1) {
      cursor = nextFireAfter(schedule, timezone, cursor);
      dates.push(new Date(cursor));
    }
  } catch {
    // Espressione o fuso non utilizzabili, o nessuna occorrenza successiva:
    // ci si ferma con quel che c'e'.
  }
  return dates;
}

/** Rappresentazione compatta e localizzata di una data d'esecuzione, nel fuso
 *  indicato. */
export function formatExecutionPreview(date: Date, timezone: string): string {
  return new Intl.DateTimeFormat("it-IT", {
    timeZone: timezone,
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
