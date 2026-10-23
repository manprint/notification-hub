import { lazy, Suspense, type ReactNode } from "react";
import { Link, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import ErrorBoundary from "./components/ErrorBoundary";
import Layout from "./components/Layout";
import RequireRole from "./components/RequireRole";
import { SessionProvider, useSession } from "./hooks/useSession";

const AcceptInvitePage = lazy(() => import("./pages/AcceptInvitePage"));
const AuditNotificationStatusPage = lazy(() => import("./pages/AuditNotificationStatusPage"));
const AuditPage = lazy(() => import("./pages/AuditPage"));
const ChannelsPage = lazy(() => import("./pages/ChannelsPage"));
const DeliveriesPage = lazy(() => import("./pages/DeliveriesPage"));
const GroupDetailPage = lazy(() => import("./pages/GroupDetailPage"));
const GroupsPage = lazy(() => import("./pages/GroupsPage"));
const HomePage = lazy(() => import("./pages/HomePage"));
const LoginPage = lazy(() => import("./pages/LoginPage"));
const NotificationDetailPage = lazy(() => import("./pages/NotificationDetailPage"));
const NotificationsPage = lazy(() => import("./pages/NotificationsPage"));
const PresetsPage = lazy(() => import("./pages/PresetsPage"));
const ReceiverDetailPage = lazy(() => import("./pages/ReceiverDetailPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const UsersPage = lazy(() => import("./pages/UsersPage"));

/** Il testo di attesa sta nella stessa cornice del login (`auth-shell`): chi
 *  aspetta vede il messaggio al centro, e il riquadro che arriva dopo non lo
 *  sposta da un angolo. */
function CaricamentoPagina() {
  return (
    <main className="auth-shell">
      <div className="empty-state">Caricamento…</div>
    </main>
  );
}

/** Le pagine autenticate si caricano pigre dentro il layout: l'attesa sta nel
 *  riquadro della pagina, così il menu non sparisce mentre arriva il chunk.
 *  Lo stesso vale per un errore di una pagina: il suo confine sta qui dentro,
 *  e il menu resta a schermo per tornare altrove. */
function AttesaPagina() {
  const location = useLocation();
  return (
    <ErrorBoundary resetKey={location.pathname}>
      <Suspense fallback={<div className="empty-state">Caricamento…</div>}>
        <Outlet />
      </Suspense>
    </ErrorBoundary>
  );
}

/** Un admin che apre Impostazioni arriva all'audit, la sola scheda che gli
 *  spetta: una pagina senza scheda selezionata non diceva dove andare. */
function ImpostazioniIndice() {
  const { role } = useSession();
  if (role === "admin") return <Navigate to="/settings/audit" replace />;
  return <SettingsPage />;
}

/** Il server non ha risposto all'avvio: la sessione salvata resta, e chi la
 *  possiede può riprovare senza rifare il login. */
function ServerUnreachable({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="app-fallback" role="alert">
      <h1>Server non raggiungibile</h1>
      <p>
        NotifyHub non risponde in questo momento. La sessione non è scaduta: riprova tra un
        istante.
      </p>
      <button type="button" className="primary" onClick={onRetry}>
        Riprova
      </button>
    </div>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading, unreachable, retryProfile } = useSession();
  const location = useLocation();

  if (loading) return <CaricamentoPagina />;
  if (!user && unreachable) return <ServerUnreachable onRetry={retryProfile} />;
  if (!user) {
    // La pagina chiesta viaggia con il redirect: un link a una notifica aperto
    // da una mail deve portare lì dopo il login, non al riepilogo.
    const from = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to="/login" replace state={{ from }} />;
  }

  return <>{children}</>;
}

/** Un indirizzo che non esiste (link vecchio, errore di battitura): senza
 *  questa rotta la pagina restava bianca, senza modo di capire perché. */
function NotFound() {
  return (
    <div>
      <div className="page-header">
        <h1>Pagina non trovata</h1>
      </div>
      <p className="page-subtitle">L'indirizzo non corrisponde a nessuna pagina di NotifyHub.</p>
      <Link to="/">Torna al riepilogo</Link>
    </div>
  );
}

export default function App() {
  const location = useLocation();
  return (
    <SessionProvider>
      {/* Confine esterno: copre login, invito e il layout stesso. Gli errori
          delle pagine li prende quello in AttesaPagina, così il menu resta
          montato. Al cambio di indirizzo il confine riparte pulito. */}
      <ErrorBoundary resetKey={location.pathname}>
      <Suspense fallback={<CaricamentoPagina />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/invite" element={<AcceptInvitePage />} />
          <Route
            element={
              <RequireAuth>
                <Layout />
              </RequireAuth>
            }
          >
          <Route element={<AttesaPagina />}>
          <Route index element={<HomePage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/notifications/:id" element={<NotificationDetailPage />} />
          <Route
            path="/groups"
            element={
              <RequireRole allowed={["owner", "admin", "member"]}>
                <GroupsPage />
              </RequireRole>
            }
          />
          <Route
            path="/groups/:id"
            element={
              <RequireRole allowed={["owner", "admin", "member"]}>
                <GroupDetailPage />
              </RequireRole>
            }
          />
          <Route
            path="/receivers/:id"
            element={
              <RequireRole allowed={["owner", "admin", "member"]}>
                <ReceiverDetailPage />
              </RequireRole>
            }
          />
          <Route
            path="/presets"
            element={
              <RequireRole allowed={["owner", "admin", "member"]}>
                <PresetsPage />
              </RequireRole>
            }
          />
          <Route
            path="/channels"
            element={
              <RequireRole allowed={["owner", "admin", "member"]}>
                <ChannelsPage />
              </RequireRole>
            }
          />
          <Route path="/deliveries" element={<DeliveriesPage />} />
          <Route
            path="/settings"
            element={
              <RequireRole allowed={["owner", "admin"]}>
                <ImpostazioniIndice />
              </RequireRole>
            }
          />
          <Route
            path="/settings/audit"
            element={
              <RequireRole allowed={["owner", "admin"]}>
                <AuditPage />
              </RequireRole>
            }
          />
          <Route
            path="/settings/letture-e-verifiche"
            element={
              <RequireRole allowed={["owner", "admin"]}>
                <AuditNotificationStatusPage />
              </RequireRole>
            }
          />
          <Route
            path="/users"
            element={
              <RequireRole allowed={["owner", "admin"]}>
                <UsersPage />
              </RequireRole>
            }
          />
          {/* Dentro il layout autenticato: chi non è entrato passa prima dal
              login, e il menu resta a disposizione per tornare altrove. */}
          <Route path="*" element={<NotFound />} />
          </Route>
          </Route>
        </Routes>
      </Suspense>
      </ErrorBoundary>
    </SessionProvider>
  );
}
