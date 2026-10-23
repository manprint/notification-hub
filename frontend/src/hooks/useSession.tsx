import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  apiGet,
  apiGetWithToken,
  apiPost,
  asApiError,
  clearTokens,
  getRefreshToken,
  onLogout,
  refreshSession,
  storeTokens,
  watchOtherTabs,
} from "../api/client";
import type { MeOut, TokenPairOut, UserRole } from "../api/types";

interface SessionState {
  user: MeOut | null;
  role: UserRole | null;
  loading: boolean;
  /** Il server non ha risposto al caricamento della sessione: la sessione
   *  salvata resta, si può riprovare con `retryProfile`. */
  unreachable: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Rilegge il proprio profilo dopo una modifica fatta su se stessi (il
   *  ruolo, da Utenti): senza, la UI continuerebbe a mostrare il ruolo vecchio. */
  reloadProfile: () => Promise<void>;
  retryProfile: () => void;
}

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<MeOut | null>(null);
  // Senza refresh token non c'è sessione da caricare: partire da "caricamento"
  // farebbe solo lampeggiare la schermata d'attesa.
  const [loading, setLoading] = useState(() => getRefreshToken() !== null);
  const [unreachable, setUnreachable] = useState(false);
  // Ogni lettura del profilo ha un numero e vale solo l'ultima: un /me partito
  // prima di un logout (o di un cambio d'utente in un'altra scheda) non deve
  // riportare in vita l'utente di prima.
  const profileRequest = useRef(0);

  /** Dimentica l'utente e tutti i dati in cache: sono suoi, e il prossimo che
   *  entra dallo stesso browser non deve vederli nemmeno per un istante. */
  const forget = useCallback(() => {
    profileRequest.current += 1;
    queryClient.clear();
    setUser(null);
    setUnreachable(false);
    setLoading(false);
  }, [queryClient]);

  // Gli aggiornamenti di stato stanno nelle callback della promise, non nel
  // corpo sincrono: chi la chiama da un effetto non scatena render a cascata.
  const loadProfile = useCallback((suppressError = true): Promise<void> => {
    const request = ++profileRequest.current;
    return apiGet<MeOut>("/api/v1/auth/me")
      .then(
        (me) => {
          if (request !== profileRequest.current) return;
          setUser(me);
          setUnreachable(false);
        },
        (error: unknown) => {
          if (request === profileRequest.current) {
            // Un guasto del server (502 di nginx, api che riparte) non dice che la
            // sessione è finita: il refresh token resta, e si può riprovare. Senza
            // questo si finiva al login, senza un messaggio, con la sessione viva.
            const status = asApiError(error).status;
            setUser(null);
            setUnreachable(status === 0 || status >= 500);
          }
          if (!suppressError) throw error;
        },
      )
      .finally(() => {
        if (request === profileRequest.current) setLoading(false);
      });
  }, []);

  const retryProfile = useCallback(() => {
    setLoading(true);
    void loadProfile();
  }, [loadProfile]);

  useEffect(() => {
    if (getRefreshToken()) void loadProfile();

    // Logout forzato da client.ts (refresh rifiutato, logout in un'altra scheda).
    const stopLogout = onLogout(forget);
    const stopWatching = watchOtherTabs(() => {
      // Un altro utente è entrato da un'altra scheda: si ricarica la sessione con
      // i suoi token. Nel frattempo "Caricamento…" smonta le pagine, così nessuna
      // mostra i dati di prima accanto al nome nuovo.
      forget();
      setLoading(true);
      void loadProfile();
    });
    return () => {
      stopLogout();
      stopWatching();
    };
  }, [forget, loadProfile]);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await apiPost<TokenPairOut>("/api/v1/auth/login", { email, password });
      // Il profilo si legge con il token nuovo, senza salvarlo: se /me fallisce
      // non resta in localStorage una sessione mai mostrata, e le altre schede
      // non vedono un refresh token che sparisce (le farebbe uscire insieme).
      // Dopo un login esplicito l'errore torna al form, altrimenti la UI naviga
      // alla home e viene subito rimandata indietro senza alcun messaggio.
      // La cache è di chi c'era prima (o di nessuno): la sessione nuova riparte vuota.
      queryClient.clear();
      const me = await apiGetWithToken<MeOut>(tokens.access_token, "/api/v1/auth/me");
      storeTokens(tokens);
      // Una lettura del profilo ancora in volo (bootstrap) non deve più scrivere.
      profileRequest.current += 1;
      setUnreachable(false);
      setUser(me);
      setLoading(false);
    },
    [queryClient],
  );

  const logout = useCallback(async () => {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      try {
        // Il backend revoca l'intera famiglia di questo refresh token: senza, il
        // token resterebbe valido per tutta la sua durata. Se la richiesta deve
        // prima ruotare i token (access token scaduto), quello mandato qui è
        // appena stato revocato, ma è della stessa famiglia e basta a chiuderla.
        await apiPost("/api/v1/auth/logout", { refresh_token: refreshToken });
      } catch {
        // il logout locale procede comunque.
      }
    }
    clearTokens();
    forget();
  }, [forget]);

  const reloadProfile = useCallback(async () => {
    const request = profileRequest.current;
    try {
      // Prima i token, poi il profilo: il backend autorizza con il ruolo scritto
      // nell'access token, e rileggere solo /me cambierebbe la UI ma non i
      // permessi. Un refresh rifiutato passa già da onLogout.
      if (!(await refreshSession())) return;
      const me = await apiGet<MeOut>("/api/v1/auth/me");
      if (request !== profileRequest.current) return;
      setUser(me);
      // Col ruolo cambia anche cosa si vede (un operatore vede solo i suoi gruppi).
      void queryClient.invalidateQueries();
    } catch {
      // Un guasto passeggero lascia il profilo che c'è: i permessi veri li decide
      // comunque il backend a ogni richiesta.
    }
  }, [queryClient]);

  return (
    <SessionContext.Provider
      value={{
        user,
        role: user?.role ?? null,
        loading,
        unreachable,
        login,
        logout,
        reloadProfile,
        retryProfile,
      }}
    >
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionState {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession va usato dentro <SessionProvider>");
  return ctx;
}
