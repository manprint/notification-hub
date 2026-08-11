import { useEffect, useRef } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useSession } from "../hooks/useSession";
import type { UserRole } from "../api/types";

interface MenuItem {
  to: string;
  label: string;
  allowed: UserRole[];
}

const MENU_ITEMS: MenuItem[] = [
  { to: "/", label: "Riepilogo", allowed: ["owner", "admin", "member", "viewer"] },
  { to: "/notifications", label: "Notifiche", allowed: ["owner", "admin", "member", "viewer"] },
  { to: "/groups", label: "Gruppi", allowed: ["owner", "admin", "member"] },
  { to: "/presets", label: "Preset di regole", allowed: ["owner", "admin", "member"] },
  { to: "/channels", label: "Canali", allowed: ["owner", "admin", "member"] },
  { to: "/deliveries", label: "Consegne", allowed: ["owner", "admin", "member", "viewer"] },
  { to: "/users", label: "Utenti", allowed: ["owner", "admin"] },
  { to: "/settings", label: "Impostazioni", allowed: ["owner"] },
];

export default function Layout() {
  const { user, role, logout } = useSession();
  const location = useLocation();
  const navigationRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    if (!window.matchMedia("(max-width: 760px)").matches) return;
    const navigation = navigationRef.current;
    const activeLink = navigation?.querySelector<HTMLElement>('a[aria-current="page"]');
    if (!navigation || !activeLink) return;

    // Allinea la voce attiva al margine del menu senza lasciare a sinistra
    // frammenti della voce precedente (un glitch evidente sui telefoni stretti).
    const offset = activeLink.getBoundingClientRect().left - navigation.getBoundingClientRect().left;
    navigation.scrollLeft += offset - 8;
  }, [location.pathname]);

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="card" style={{ marginBottom: "16px" }}>
          <strong>NotifyHub</strong>
          {user && (
            <div style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
              {user.email} · {user.tenant_name}
            </div>
          )}
        </div>
        <nav ref={navigationRef} aria-label="Navigazione principale">
          <ul>
            {MENU_ITEMS.filter((item) => role !== null && item.allowed.includes(role)).map(
              (item) => (
                <li key={item.to}>
                  <NavLink to={item.to} end={item.to === "/"}>
                    {item.label}
                  </NavLink>
                </li>
              ),
            )}
          </ul>
        </nav>
        {user && (
          <button style={{ marginTop: "16px" }} onClick={() => void logout()}>
            Esci
          </button>
        )}
      </aside>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
