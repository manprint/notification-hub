import { Fragment, useEffect, useRef } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useSession } from "../hooks/useSession";
import type { UserRole } from "../api/types";

interface MenuItem {
  to: string;
  label: string;
  allowed: UserRole[];
  /** Stesso modulo del lazy() in App.tsx: Vite lo serve dallo stesso chunk. */
  load: () => Promise<unknown>;
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
  {
    to: "/",
    label: "Riepilogo",
    allowed: ["owner", "admin", "member", "viewer"],
    load: () => import("../pages/HomePage"),
  },
  {
    to: "/notifications",
    label: "Notifiche",
    allowed: ["owner", "admin", "member", "viewer"],
    load: () => import("../pages/NotificationsPage"),
  },
  {
    to: "/groups",
    label: "Gruppi",
    allowed: ["owner", "admin", "member"],
    load: () => import("../pages/GroupsPage"),
  },
  {
    to: "/presets",
    label: "Preset di regole",
    allowed: ["owner", "admin", "member"],
    load: () => import("../pages/PresetsPage"),
  },
  {
    to: "/channels",
    label: "Canali",
    allowed: ["owner", "admin", "member"],
    load: () => import("../pages/ChannelsPage"),
  },
  {
    to: "/deliveries",
    label: "Consegne",
    allowed: ["owner", "admin", "member", "viewer"],
    load: () => import("../pages/DeliveriesPage"),
  },
  {
    to: "/users",
    label: "Utenti",
    allowed: ["owner", "admin"],
    load: () => import("../pages/UsersPage"),
  },
  // owner + admin: l'audit vive sotto Impostazioni e serve a entrambi i
  // ruoli; la scheda "Generali" resta riservata all'owner (SettingsTabs).
  {
    to: "/settings",
    label: "Impostazioni",
    allowed: ["owner", "admin"],
    load: () => import("../pages/SettingsPage"),
  },
];

/** Precarica il codice di una pagina; un errore di rete qui non conta: il
 *  lazy() di App.tsx riprova al click e mostra l'errore nel suo confine. */
function preload(item: MenuItem) {
  item.load().catch(() => undefined);
}

/** Il menu diventa una riga a scorrimento sotto questa larghezza: stesso punto
 *  di rottura della barra laterale in styles.css (`@media (max-width: 1000px)`). */
const MENU_A_RIGA = "(max-width: 1000px)";

export default function Layout() {
  const { user, role, logout } = useSession();
  const location = useLocation();
  const navigationRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    if (!window.matchMedia(MENU_A_RIGA).matches) return;
    const navigation = navigationRef.current;
    const activeLink = navigation?.querySelector<HTMLElement>('a[aria-current="page"]');
    if (!navigation || !activeLink) return;

    // Centra la voce attiva nel menu: così si vedono anche le voci vicine, a
    // destra e a sinistra, e la voce non finisce nella sfumatura del bordo.
    // Allinearla al bordo sinistro nascondeva tutto ciò che la precede.
    const menu = navigation.getBoundingClientRect();
    const voce = activeLink.getBoundingClientRect();
    navigation.scrollLeft += voce.left - menu.left + voce.width / 2 - menu.width / 2;
  }, [location.pathname, role]);

  const visibleItems = MENU_ITEMS.filter((item) => role !== null && item.allowed.includes(role));

  // A pagina ferma si scaricano in sottofondo le pagine del menu: il primo
  // click su una voce non aspetta piu' il suo chunk.
  useEffect(() => {
    if (role === null || import.meta.env.MODE === "test") return;
    const items = MENU_ITEMS.filter((item) => item.allowed.includes(role));
    const handle = window.setTimeout(() => items.forEach(preload), 1500);
    return () => window.clearTimeout(handle);
  }, [role]);

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
            {visibleItems.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.to === "/"}
                  onMouseEnter={() => preload(item)}
                  onFocus={() => preload(item)}
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
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
