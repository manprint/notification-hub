import { Fragment, useEffect, useRef } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useSession } from "../hooks/useSession";
import type { UserRole } from "../api/types";

interface MenuItem {
  to: string;
  label: string;
  allowed: UserRole[];
}

/** Un indirizzo lungo senza spazi andrebbe a capo a metà parola: un <wbr> dopo
 *  @ e punto lascia spezzare solo fra le sue parti. Il testo resta lo stesso. */
function breakableAddress(address: string) {
  return address.split(/(?<=[@.])/).map((part, index) => (
    <Fragment key={index}>
      {index > 0 && <wbr />}
      {part}
    </Fragment>
  ));
}

const MENU_ITEMS: MenuItem[] = [
  { to: "/", label: "Riepilogo", allowed: ["owner", "admin", "member", "viewer"] },
  { to: "/notifications", label: "Notifiche", allowed: ["owner", "admin", "member", "viewer"] },
  { to: "/groups", label: "Gruppi", allowed: ["owner", "admin", "member"] },
  { to: "/presets", label: "Preset di regole", allowed: ["owner", "admin", "member"] },
  { to: "/channels", label: "Canali", allowed: ["owner", "admin", "member"] },
  { to: "/deliveries", label: "Consegne", allowed: ["owner", "admin", "member", "viewer"] },
  { to: "/users", label: "Utenti", allowed: ["owner", "admin"] },
  // owner + admin: l'audit vive sotto Impostazioni e serve a entrambi i
  // ruoli; la scheda "Generali" resta riservata all'owner (SettingsTabs).
  { to: "/settings", label: "Impostazioni", allowed: ["owner", "admin"] },
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
        <div className="app-brand">
          <strong>NotifyHub</strong>
          {user && (
            <span className="app-brand-user" title={`${user.email} · ${user.tenant_name}`}>
              {breakableAddress(user.email)} · {user.tenant_name}
            </span>
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
          <div className="app-sidebar-footer">
            <button onClick={() => void logout()}>Esci</button>
          </div>
        )}
      </aside>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
