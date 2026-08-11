import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { apiGet, apiPost, getRefreshToken, onLogout, setAccessToken, setRefreshToken } from "../api/client";
import type { MeOut, UserRole } from "../api/types";

interface SessionState {
  user: MeOut | null;
  role: UserRole | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }): ReturnType<typeof createElement> {
  const [user, setUser] = useState<MeOut | null>(null);
  const [loading, setLoading] = useState(true);

  const loadProfile = useCallback(async (suppressError = true) => {
    try {
      const me = await apiGet<MeOut>("/api/v1/auth/me");
      setUser(me);
    } catch (error) {
      setUser(null);
      if (!suppressError) throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (getRefreshToken()) {
      void loadProfile();
    } else {
      setLoading(false);
    }

    return onLogout(() => setUser(null));
  }, [loadProfile]);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await apiPost<{
      access_token: string;
      refresh_token: string;
    }>("/api/v1/auth/login", { email, password });
    setAccessToken(tokens.access_token);
    setRefreshToken(tokens.refresh_token);
    // Durante il bootstrap un errore viene gestito come sessione assente; dopo
    // un login esplicito deve invece tornare al form, altrimenti la UI naviga
    // alla home e viene subito rimandata indietro senza alcun messaggio.
    await loadProfile(false);
  }, [loadProfile]);

  const logout = useCallback(async () => {
    try {
      await apiPost("/api/v1/auth/logout", {});
    } catch {
      // il logout locale procede comunque.
    }
    setAccessToken(null);
    setRefreshToken(null);
    setUser(null);
  }, []);

  return createElement(SessionContext.Provider, {
    value: { user, role: user?.role ?? null, loading, login, logout },
    children,
  });
}

export function useSession(): SessionState {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession va usato dentro <SessionProvider>");
  return ctx;
}
