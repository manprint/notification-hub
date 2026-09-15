import { NavLink } from "react-router-dom";
import { useSession } from "../hooks/useSession";

/** Le tre schede di Impostazioni. "Generali" compare solo all'owner: le quote
 * del tenant restano una sua decisione, l'audit invece serve anche agli admin
 * (backend: require_owner su PATCH /tenant, require_admin su /audit/*). */
export default function SettingsTabs() {
  const { role } = useSession();

  return (
    <nav className="tabs" aria-label="Sezioni delle impostazioni">
      <ul>
        {role === "owner" && (
          <li>
            <NavLink to="/settings" end>
              Generali
            </NavLink>
          </li>
        )}
        <li>
          <NavLink to="/settings/audit">Audit</NavLink>
        </li>
        <li>
          <NavLink to="/settings/letture-e-verifiche">Letture e verifiche</NavLink>
        </li>
      </ul>
    </nav>
  );
}
