import type { ApiError } from "./types";

let accessToken: string | null = null;
let refreshPromise: Promise<boolean> | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

const REFRESH_TOKEN_KEY = "notifyhub.refresh_token";
/** Di chi è la sessione salvata: l'id utente (claim `sub` dell'access token).
 *  Il refresh token è opaco, e senza questa chiave una scheda non potrebbe
 *  distinguere la rotazione fatta da un'altra scheda dello stesso utente dal
 *  login di un utente diverso. */
const SESSION_USER_KEY = "notifyhub.session_user";
/** Nome del lock che serializza il refresh fra le schede dello stesso browser. */
const REFRESH_LOCK = "notifyhub.refresh";

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setRefreshToken(token: string | null): void {
  if (token === null) {
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  } else {
    localStorage.setItem(REFRESH_TOKEN_KEY, token);
  }
}

/** Utente a cui appartiene un access token, letto dal claim `sub` del JWT.
 *  Serve solo a riconoscere un cambio d'utente fra le schede: la firma non si
 *  verifica qui, la verifica il backend a ogni richiesta. */
function tokenSubject(token: string): string | null {
  const payload = token.split(".")[1];
  if (!payload) return null;
  try {
    const claims = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/"))) as {
      sub?: unknown;
    };
    return typeof claims.sub === "string" ? claims.sub : null;
  } catch {
    return null;
  }
}

/** Salva la coppia di token appena ottenuta (login o refresh). */
export function storeTokens(tokens: { access_token: string; refresh_token: string }): void {
  setAccessToken(tokens.access_token);
  // Prima il proprietario, poi il token: una scheda che vede cambiare il
  // refresh token (evento storage) deve trovare già scritto di chi è.
  const owner = tokenSubject(tokens.access_token);
  if (owner) localStorage.setItem(SESSION_USER_KEY, owner);
  else localStorage.removeItem(SESSION_USER_KEY);
  setRefreshToken(tokens.refresh_token);
}

/** Dimentica la sessione in questa scheda e, via localStorage, nelle altre. */
export function clearTokens(): void {
  setAccessToken(null);
  localStorage.removeItem(SESSION_USER_KEY);
  setRefreshToken(null);
}

type Listener = () => void;
const logoutListeners = new Set<Listener>();

export function onLogout(listener: Listener): () => void {
  logoutListeners.add(listener);
  return () => logoutListeners.delete(listener);
}

function emitLogout(): void {
  clearTokens();
  for (const listener of logoutListeners) listener();
}

/** Tiene questa scheda allineata alla sessione che le altre schede scrivono in
 *  localStorage (unico posto condiviso: l'access token vive nella memoria di
 *  ciascuna).
 *
 *  - refresh token rimosso: logout in un'altra scheda. La famiglia è già
 *    revocata lato server; qui resta da dimenticare access token e dati, con lo
 *    stesso giro del logout forzato (`onLogout`).
 *  - refresh token di un altro utente: login di qualcun altro in un'altra
 *    scheda. Restare "A" con in tasca il refresh token di "B" vorrebbe dire,
 *    al primo refresh, mostrare dati di B sotto il nome di A: si butta l'access
 *    token di A e si avvisa `onUserSwitch`, che ricarica la sessione.
 *
 *  Una rotazione fatta da un'altra scheda dello stesso utente non richiede
 *  niente: il prossimo refresh rileggerà il token nuovo. */
export function watchOtherTabs(onUserSwitch: () => void): () => void {
  function handleStorage(event: StorageEvent): void {
    // key null: localStorage.clear() in un'altra scheda.
    if (event.key !== null && event.key !== REFRESH_TOKEN_KEY) return;
    if (getRefreshToken() === null) {
      emitLogout();
      return;
    }
    const owner = localStorage.getItem(SESSION_USER_KEY);
    const mine = accessToken ? tokenSubject(accessToken) : null;
    if (owner !== null && mine !== null && owner !== mine) {
      setAccessToken(null);
      onUserSwitch();
    }
  }
  window.addEventListener("storage", handleStorage);
  return () => window.removeEventListener("storage", handleStorage);
}

function networkError(): ApiError {
  return {
    status: 0,
    type: "/problems/network-unreachable",
    title: "Server non raggiungibile",
    detail:
      "Impossibile contattare NotifyHub. Controlla la connessione e che l'istanza sia attiva.",
    extra: {},
  };
}

async function safeFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch {
    throw networkError();
  }
}

/** Legge il corpo di una risposta. Se la lettura cade (connessione interrotta a
 *  metà, JSON guasto) l'errore diventa quello di rete: un TypeError grezzo non
 *  ha titolo, e il banner dell'errore resterebbe vuoto. */
async function readBody<T>(read: () => Promise<T>): Promise<T> {
  try {
    return await read();
  } catch {
    throw networkError();
  }
}

function isApiError(error: unknown): error is ApiError {
  if (typeof error !== "object" || error === null) return false;
  const { status, title } = error as Partial<ApiError>;
  return typeof status === "number" && typeof title === "string" && title !== "";
}

/** Un errore qualunque come ApiError: quello che il client non ha già
 *  normalizzato (un'eccezione fuori dal client) diventa comunque leggibile. */
export function asApiError(error: unknown): ApiError {
  if (isApiError(error)) return error;
  return {
    status: 0,
    type: "/problems/generic",
    title: "Errore imprevisto",
    detail: "",
    extra: {},
  };
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: Record<string, unknown> = {};
  try {
    body = await response.json();
  } catch {
    // corpo non-JSON: si ricade sui default sotto.
  }
  const { type, title, detail, ...extra } = body as Record<string, unknown>;
  delete extra.status;
  return {
    status: response.status,
    type: typeof type === "string" ? type : "/problems/generic",
    // Su HTTP/2 lo statusText è sempre vuoto: un errore non-JSON (pagina del
    // proxy, 502 di nginx) lascerebbe il banner senza una parola.
    title:
      typeof title === "string" && title !== ""
        ? title
        : response.statusText || `Errore HTTP ${response.status}`,
    detail: typeof detail === "string" ? detail : "",
    extra,
  };
}

/** Esegue `task` tenendo un lock condiviso da tutte le schede dell'origine.
 *  Due schede che ruotano in parallelo lo stesso refresh token fanno scattare
 *  nel backend il rilevamento del riuso, che revoca l'intera famiglia e butta
 *  fuori tutte e due. Dove la Web Locks API manca si ricade sul comportamento
 *  di una sola scheda (il dedup di `refreshOnce`). */
async function withRefreshLock<T>(task: () => Promise<T>): Promise<T> {
  const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
  if (!locks || typeof locks.request !== "function") return task();
  return await locks.request(REFRESH_LOCK, task);
}

async function refreshAccessToken(): Promise<boolean> {
  if (!getRefreshToken()) {
    // Si arriva qui con una richiesta rifiutata e nessun modo di rinnovarla
    // (logout in un'altra scheda): la sessione di questa scheda non esiste più.
    emitLogout();
    return false;
  }

  return withRefreshLock(async () => {
    // Si rilegge il token solo dopo aver preso il lock: se nel frattempo
    // un'altra scheda ha ruotato, quello con cui si era partiti è già revocato
    // e presentarlo sarebbe proprio il riuso che revoca la famiglia. L'access
    // token nuovo di quella scheda sta nella sua memoria, non qui: si ruota di
    // nuovo, ma con il token corrente.
    let refreshToken = getRefreshToken();
    while (refreshToken) {
      const response = await safeFetch("/api/v1/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      // Il login non passa dal lock: se un'altra scheda ha aperto una sessione
      // mentre questo refresh era in volo, il suo esito riguarda la sessione di
      // prima. Scriverlo, o cancellare tutto su un 401, distruggerebbe quella
      // nuova: si riprova con il token corrente (un cambio d'utente lo gestisce
      // watchOtherTabs).
      const current = getRefreshToken();
      if (current !== refreshToken) {
        refreshToken = current;
        continue;
      }

      // Solo un rifiuto del token chiude la sessione. Un 5xx o un proxy giù
      // dicono che il server non risponde, non che il token non valga: buttarlo
      // costringerebbe a un nuovo login per un guasto passeggero.
      if (response.status === 401 || response.status === 403) break;
      if (!response.ok) throw await toApiError(response);

      storeTokens(
        await readBody(() => response.json() as Promise<{ access_token: string; refresh_token: string }>),
      );
      return true;
    }
    emitLogout();
    return false;
  });
}

function refreshOnce(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = refreshAccessToken().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

/** Ruota subito i token. Serve dopo una modifica al proprio ruolo: il backend
 *  autorizza con il ruolo scritto nell'access token, che resterebbe quello
 *  vecchio fino alla scadenza. Restituisce false se la sessione è finita. */
export function refreshSession(): Promise<boolean> {
  return refreshOnce();
}

interface RequestOptions {
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
}

/** Endpoint che si chiamano senza sessione. Non ricevono il Bearer (un token di
 *  un'altra sessione non c'entra) e un loro 401 non avvia un refresh: per il
 *  login vuol dire "credenziali sbagliate", non "sessione scaduta", e un
 *  refresh senza token farebbe scattare il logout. */
const AUTH_WITHOUT_SESSION = new Set([
  "/api/v1/auth/login",
  "/api/v1/auth/register",
  "/api/v1/auth/refresh",
  "/api/v1/invitations/accept",
]);

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null) params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

async function rawRequest(
  method: string,
  path: string,
  options: RequestOptions = {},
  isRetry = false,
): Promise<Response> {
  const withoutSession = AUTH_WITHOUT_SESSION.has(path);

  // L'access token vive solo in memoria. Dopo un reload, se esiste una
  // sessione persistente, ruotala prima della prima API protetta: evita una
  // richiesta /me 401 usata soltanto come segnale per avviare il refresh.
  // Il secondo giro parte comunque come retry: se il refresh ha chiuso la
  // sessione, un 401 non deve avviarne un altro.
  if (!accessToken && getRefreshToken() && !isRetry && !withoutSession) {
    await refreshOnce();
    return rawRequest(method, path, options, true);
  }

  const url = buildUrl(path, options.query);
  const headers: Record<string, string> = {};
  // Il token con cui parte questa richiesta: se al suo 401 la sessione è già
  // stata rinnovata da un'altra richiesta, non serve un altro giro di rotazione.
  const sentToken = accessToken;
  if (sentToken && !withoutSession) headers.Authorization = `Bearer ${sentToken}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  const response = await safeFetch(url, {
    method,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (response.status === 401 && !isRetry && !withoutSession) {
    if (accessToken !== null && accessToken !== sentToken) {
      return rawRequest(method, path, options, true);
    }
    const refreshed = await refreshOnce();
    if (refreshed) {
      return rawRequest(method, path, options, true);
    }
    throw await toApiError(response);
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  return response;
}

async function request<T>(
  method: string,
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const response = await rawRequest(method, path, options);

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return await readBody(() => response.json() as Promise<T>);
  }
  const text = await readBody(() => response.text());
  return text as unknown as T;
}

export function apiGet<T>(path: string, query?: RequestOptions["query"]): Promise<T> {
  return request<T>("GET", path, { query });
}

/** Una lettura con un token dato, senza passare dalla sessione di questa scheda:
 *  serve al login, prima che il token venga salvato. Un 401 qui vuol dire che il
 *  token non vale, non che la sessione è scaduta: niente refresh. */
export async function apiGetWithToken<T>(token: string, path: string): Promise<T> {
  const response = await safeFetch(path, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) throw await toApiError(response);
  return await readBody(() => response.json() as Promise<T>);
}

const FILENAME_MARKER = 'filename="';

/** Nome del file dalla Content-Disposition, senza dover ricostruire lato client
 * una regola che il backend ha gia' applicato. */
function filenameFromDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const start = header.indexOf(FILENAME_MARKER);
  if (start === -1) return fallback;
  const rest = header.slice(start + FILENAME_MARKER.length);
  const end = rest.indexOf('"');
  const name = end === -1 ? rest : rest.slice(0, end);
  return name.trim() === "" ? fallback : name;
}

/** Scarica un allegato di testo (lo script wrapper) tenendo il nome scelto dal
 * server: il contenuto va in un Blob, non nella cache di react-query. */
export async function apiGetFile(
  path: string,
  fallbackFilename: string,
): Promise<{ content: string; filename: string }> {
  const response = await rawRequest("GET", path);
  const content = await readBody(() => response.text());
  return {
    content,
    filename: filenameFromDisposition(
      response.headers.get("content-disposition"),
      fallbackFilename,
    ),
  };
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>("POST", path, { body });
}

export function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  return request<T>("PATCH", path, { body });
}

export function apiPut<T>(path: string, body?: unknown): Promise<T> {
  return request<T>("PUT", path, { body });
}

export function apiDelete<T>(path: string): Promise<T> {
  return request<T>("DELETE", path);
}
