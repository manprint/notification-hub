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

type Listener = () => void;
const logoutListeners = new Set<Listener>();

export function onLogout(listener: Listener): () => void {
  logoutListeners.add(listener);
  return () => logoutListeners.delete(listener);
}

function emitLogout(): void {
  setAccessToken(null);
  setRefreshToken(null);
  for (const listener of logoutListeners) listener();
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
    title: typeof title === "string" ? title : response.statusText,
    detail: typeof detail === "string" ? detail : "",
    extra,
  };
}

async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  const response = await fetch("/api/v1/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!response.ok) {
    emitLogout();
    return false;
  }

  const body = await response.json();
  setAccessToken(body.access_token);
  setRefreshToken(body.refresh_token);
  return true;
}

function refreshOnce(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = refreshAccessToken().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

interface RequestOptions {
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
}

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
  const url = buildUrl(path, options.query);
  const headers: Record<string, string> = {};
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(url, {
    method,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (response.status === 401 && !isRetry && path !== "/api/v1/auth/refresh") {
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
    return (await response.json()) as T;
  }
  return (await response.text()) as unknown as T;
}

export function apiGet<T>(path: string, query?: RequestOptions["query"]): Promise<T> {
  return request<T>("GET", path, { query });
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
  const content = await response.text();
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
