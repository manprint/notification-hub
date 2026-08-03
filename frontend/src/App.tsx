import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import RequireRole from "./components/RequireRole";
import { SessionProvider, useSession } from "./hooks/useSession";
import AcceptInvitePage from "./pages/AcceptInvitePage";
import ChannelsPage from "./pages/ChannelsPage";
import DeliveriesPage from "./pages/DeliveriesPage";
import GroupsPage from "./pages/GroupsPage";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import NotificationDetailPage from "./pages/NotificationDetailPage";
import NotificationsPage from "./pages/NotificationsPage";
import PresetsPage from "./pages/PresetsPage";
import ReceiverDetailPage from "./pages/ReceiverDetailPage";
import SettingsPage from "./pages/SettingsPage";
import UsersPage from "./pages/UsersPage";

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useSession();

  if (loading) return <div className="empty-state">Caricamento…</div>;
  if (!user) return <Navigate to="/login" replace />;

  return <>{children}</>;
}

export default function App() {
  return (
    <SessionProvider>
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
              <RequireRole allowed={["owner"]}>
                <SettingsPage />
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
    </SessionProvider>
  );
}
