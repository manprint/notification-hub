import { lazy, Suspense, type ReactNode } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
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

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useSession();
  const location = useLocation();

  if (loading) return <div className="empty-state">Caricamento…</div>;
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
  return (
    <SessionProvider>
      <Suspense fallback={<div className="empty-state">Caricamento…</div>}>
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
                <SettingsPage />
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
        </Routes>
      </Suspense>
    </SessionProvider>
  );
}
