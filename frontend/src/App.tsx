import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
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

  if (loading) return <div className="empty-state">Caricamento…</div>;
  if (!user) return <Navigate to="/login" replace />;

  return <>{children}</>;
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
          </Route>
        </Routes>
      </Suspense>
    </SessionProvider>
  );
}
